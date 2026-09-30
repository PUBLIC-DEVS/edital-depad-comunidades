"""Serviço de cálculo de métricas operacionais e painel de validações/inconsistências."""

from collections import defaultdict
from typing import Any

from django.db.models import Count, Q, QuerySet

from apps.accounts.models import User
from apps.editais.models import Edital
from apps.evaluations.assessment import blocking_results
from apps.evaluations.models import CheckResult, Evaluation
from apps.institutions.cnpj import normalize_cnpj, validate_cnpj
from apps.reviews.models import ReviewItemDecision
from apps.submissions.models import Submission


class DashboardMetricsService:
    """Motor de agregação de métricas em tempo real e detecção de exceções do edital."""

    @classmethod
    def get_summary_metrics(cls, edital: Edital | None = None) -> dict[str, Any]:
        """Current workflow outcomes, scoped to one active edital by default."""
        from django.db.models.functions import TruncDate

        from apps.editais.operational import get_operational_edital

        edital = edital if edital is not None else get_operational_edital()
        subs = Submission.objects.filter(edital=edital)
        status_counts = dict(
            subs.values("workflow_status")
            .annotate(count=Count("pk"))
            .values_list("workflow_status", "count")
        )
        total = sum(status_counts.values())
        unassigned = (
            subs.filter(workflow_status="RECEIVED").exclude(assignments__status="ACTIVE").count()
        )
        analyzing = sum(status_counts.get(s, 0) for s in ("ASSIGNED", "UNDER_ANALYSIS"))
        apt = sum(status_counts.get(s, 0) for s in ("ELIGIBLE_FOR_RANKING", "RANKED"))
        inapt = status_counts.get("INELIGIBLE", 0)
        categories = [
            ("Sem distribuição", unassigned, "neutral"),
            ("Em análise", analyzing, "info"),
            ("Em revisão", status_counts.get("PENDING_REVIEW", 0), "warning"),
            ("Aptas", apt, "success"),
            ("Inaptas / Inelegíveis", inapt, "danger"),
        ]
        stages = [
            {
                "label": label,
                "count": count,
                "tone": tone,
                "percent": round(count * 100 / total, 1) if total else 0,
            }
            for label, count, tone in categories
        ]
        groups = dict.fromkeys(
            edital.target_groups.filter(active=True).values_list("code", flat=True), 0
        )
        groups["SEM_GRUPO"] = 0
        for item in subs.values("target_group").annotate(count=Count("pk")):
            key = item["target_group"] or "SEM_GRUPO"
            groups[key] = item["count"]
        assignment_scope = Q(
            assigned_submissions__status="ACTIVE", assigned_submissions__submission__edital=edital
        )
        analysts = (
            User.objects.filter(role="ANALISTA")
            .annotate(
                total_assigned=Count("assigned_submissions", filter=assignment_scope),
                analyzing_count=Count(
                    "assigned_submissions",
                    filter=assignment_scope
                    & Q(assigned_submissions__submission__workflow_status="UNDER_ANALYSIS"),
                ),
                completed_count=Count(
                    "assigned_submissions",
                    filter=assignment_scope
                    & Q(assigned_submissions__submission__evaluation__status="COMPLETED"),
                ),
            )
            .filter(Q(is_active=True) | Q(total_assigned__gt=0))
            .order_by("-total_assigned", "first_name", "username")
        )
        by_analyst = [
            {
                "analyst": a,
                "total_assigned": a.total_assigned,
                "under_analysis": a.analyzing_count,
                "concluded": a.completed_count,
            }
            for a in analysts
        ]
        timeline = [
            {"date": item["day"], "count": item["count"]}
            for item in subs.annotate(day=TruncDate("received_at"))
            .values("day")
            .annotate(count=Count("pk"))
            .order_by("day")
        ]
        # DEMO is the explicit process prefix used by seed_demo (no inferred chronology).
        has_demo = subs.filter(processo_sei__istartswith="DEMO-").exists()
        return {
            "total_received": total,
            "distributed_count": subs.filter(assignments__status="ACTIVE").count(),
            "unassigned_count": unassigned,
            "under_analysis": analyzing,
            "pending_review": status_counts.get("PENDING_REVIEW", 0),
            "apt_count": apt,
            "inapt_count": inapt,
            "concluded": apt + inapt + status_counts.get("CLOSED", 0),
            "stages": stages,
            "unrepresented_count": total - sum(c[1] for c in categories),
            "by_group": groups,
            "by_analyst": by_analyst,
            "timeline": timeline,
            "show_timeline": len(timeline) >= 3 and total >= 5 and not has_demo,
            "by_uf": list(subs.values("municipality__state").annotate(count=Count("pk"))),
        }

    @classmethod
    def get_top_failed_checks(cls, edital=None, limit=8):
        from apps.editais.operational import get_operational_edital

        edital = edital if edital is not None else get_operational_edital()
        # Original completed human findings; revisions never erase this analytical dimension.
        rows = (
            CheckResult.objects.filter(
                evaluation__submission__edital=edital,
                evaluation__status="COMPLETED",
                status="NAO_ATENDE",
            )
            .values(
                "requirement_check__code",
                "requirement_check__name",
                "requirement__code",
                "requirement__name",
            )
            .annotate(failure_count=Count("evaluation__submission_id", distinct=True))
            .order_by("-failure_count", "requirement__code", "requirement_check__code")[:limit]
        )
        return [
            {
                "code": row["requirement_check__code"] or row["requirement__code"],
                "name": row["requirement_check__name"] or row["requirement__name"],
                "document": row["requirement__name"],
                "failure_count": row["failure_count"],
            }
            for row in rows
        ]

    @classmethod
    def get_top_failed_requirements(
        cls, edital: Edital | None = None, limit: int = 10
    ) -> list[dict[str, Any]]:
        """Calcula o ranking dos requisitos que mais reprovaram propostas."""
        evaluations = Evaluation.objects.select_related("submission__edital")
        if edital:
            evaluations = evaluations.filter(submission__edital=edital)
        counts = defaultdict(set)
        definitions = {}
        for evaluation in evaluations:
            for result in blocking_results(evaluation):
                req = result.requirement
                counts[req.pk].add(evaluation.submission_id)
                definitions[req.pk] = req
        return [
            {
                "code": definitions[pk].code,
                "name": definitions[pk].name,
                "description": definitions[pk].description,
                "edital_id": definitions[pk].edital_id,
                "failure_count": len(ids),
            }
            for pk, ids in sorted(counts.items(), key=lambda item: (-len(item[1]), item[0]))[:limit]
        ]

    @classmethod
    def get_submissions_failing_requirement(
        cls, requirement_code: str, edital: Edital | None = None
    ) -> QuerySet[Submission]:
        evaluations = Evaluation.objects.all()
        if edital:
            evaluations = evaluations.filter(submission__edital=edital)
        ids = [
            evaluation.submission_id
            for evaluation in evaluations
            if any(r.requirement.code == requirement_code for r in blocking_results(evaluation))
        ]
        return (
            Submission.objects.filter(pk__in=ids)
            .select_related("institution", "municipality", "edital", "evaluation")
            .prefetch_related("assignments__analyst")
            .order_by("processo_sei")
        )

    @classmethod
    def get_validation_insights(cls, edital: Edital | None = None) -> dict[str, Any]:
        """Detecta inconsistências graves para o painel de conferência e validação.

        Verifica:
        1. Inconsistência de capacidade vs. vagas (solicitadas > instalada ou soma dos tipos != solicitadas)
        2. Divergências de CNPJ (dígitos inválidos ou divergência entre documento e instituição)
        3. Divergências entre parecer do analista e revisor
        4. Contradição: parecer positivo (APTO) com item reprovado obrigatório
        5. Processos sem município ou UF
        6. Processos duplicados não resolvidos
        """
        subs = Submission.objects.select_related("institution", "municipality", "edital")
        if edital:
            subs = subs.filter(edital=edital)

        # 1. Inconsistências de capacidade vs vagas
        capacity_inconsistencies = []
        for sub in subs:
            soma = sub.vagas_femininas + sub.vagas_masculinas + sub.vagas_maes_nutrizes
            has_error = False
            reasons = []
            if sub.capacidade_total > 0 and sub.vagas_solicitadas > sub.capacidade_total:
                has_error = True
                reasons.append(
                    f"Vagas solicitadas ({sub.vagas_solicitadas}) excedem capacidade instalada ({sub.capacidade_total})."
                )
            if soma != sub.vagas_solicitadas:
                has_error = True
                reasons.append(
                    f"Soma das vagas por público ({soma}) difere do total solicitado ({sub.vagas_solicitadas})."
                )
            if has_error:
                capacity_inconsistencies.append(
                    {
                        "submission": sub,
                        "reasons": reasons,
                        "vagas_solicitadas": sub.vagas_solicitadas,
                        "capacidade_total": sub.capacidade_total,
                        "soma_vagas": soma,
                    }
                )

        # 2. Divergências de CNPJ
        cnpj_issues = []
        for sub in subs:
            raw_cnpj = sub.institution.cnpj
            reasons = []
            if not validate_cnpj(raw_cnpj):
                reasons.append(f"CNPJ '{raw_cnpj}' inválido.")

            # Checa se algum CheckResult contém document_cnpj discrepante do CNPJ da instituição
            check_cnpjs = (
                CheckResult.objects.filter(evaluation__submission=sub)
                .exclude(document_cnpj="")
                .values_list("document_cnpj", flat=True)
            )
            for c_cnpj in check_cnpjs:
                if normalize_cnpj(c_cnpj) != normalize_cnpj(raw_cnpj):
                    reasons.append(
                        f"Documento anexado tem CNPJ '{c_cnpj}' diferente do cadastrado ({raw_cnpj})."
                    )

            if reasons:
                cnpj_issues.append(
                    {
                        "submission": sub,
                        "reasons": reasons,
                        "institution_cnpj": raw_cnpj,
                    }
                )

        # 3. Divergências entre analista e revisor
        reviewer_divergences_qs = (
            ReviewItemDecision.objects.filter(agrees_with_analyst=False)
            .select_related(
                "review__submission__institution",
                "review__reviewer",
                "check_result__requirement_check__requirement",
            )
            .order_by("-id")
        )
        if edital:
            reviewer_divergences_qs = reviewer_divergences_qs.filter(
                review__submission__edital=edital
            )

        reviewer_divergences = [
            {
                "submission": item.review.submission,
                "reviewer": item.review.reviewer,
                "item_name": item.check_result.definition.name,
                "analyst_decision": item.check_result.status,
                "reviewer_decision": item.reviewer_status,
                "justification": item.justification,
            }
            for item in reviewer_divergences_qs
        ]

        # 4. Parecer positivo com item obrigatório reprovado (Grave contradição)
        positive_with_failed_items = []
        for sub in subs.filter(evaluation__result=Evaluation.Result.APTA).select_related(
            "evaluation"
        ):
            failed_mandatory = blocking_results(sub.evaluation)
            if failed_mandatory:
                positive_with_failed_items.append(
                    {
                        "submission": sub,
                        "failed_requirements": sorted(
                            {r.requirement.code for r in failed_mandatory}
                        ),
                    }
                )

        # 5. Processos sem município/UF
        missing_municipality = list(
            subs.filter(
                Q(municipality__isnull=True)
                | Q(municipality__state="")
                | Q(municipality__ibge_code="")
                | Q(municipality__ibge_code__isnull=True)
            )
        )

        # 6. Duplicados não resolvidos (mesmo CNPJ ativo mais de uma vez)
        cnpj_map = defaultdict(list)
        for s in subs.exclude(workflow_status=Submission.WorkflowStatus.CLOSED):
            c = normalize_cnpj(s.institution.cnpj)
            cnpj_map[c].append(s)

        unresolved_duplicates = [
            {"cnpj": cnpj, "submissions": group}
            for cnpj, group in cnpj_map.items()
            if len(group) > 1
        ]

        total_anomalies_count = (
            len(capacity_inconsistencies)
            + len(cnpj_issues)
            + len(reviewer_divergences)
            + len(positive_with_failed_items)
            + len(missing_municipality)
            + len(unresolved_duplicates)
        )

        return {
            "capacity_inconsistencies": capacity_inconsistencies,
            "cnpj_issues": cnpj_issues,
            "reviewer_divergences": reviewer_divergences,
            "positive_with_failed_items": positive_with_failed_items,
            "missing_municipality": missing_municipality,
            "unresolved_duplicates": unresolved_duplicates,
            "total_anomalies_count": total_anomalies_count,
        }
