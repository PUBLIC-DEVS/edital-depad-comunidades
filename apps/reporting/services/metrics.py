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
        """Calcula o resumo consolidado de processos por status, grupo, analista e UF."""
        subs = Submission.objects.all()
        if edital:
            subs = subs.filter(edital=edital)

        total_received = subs.count()

        # Status do workflow
        status_counts = dict(
            subs.values("workflow_status")
            .annotate(count=Count("id"))
            .values_list("workflow_status", "count")
        )

        under_analysis = status_counts.get(Submission.WorkflowStatus.UNDER_ANALYSIS, 0)
        pending_review = status_counts.get(Submission.WorkflowStatus.PENDING_REVIEW, 0)
        pending_diligence = status_counts.get(Submission.WorkflowStatus.PENDING_DILIGENCE, 0)

        concluded = (
            status_counts.get(Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING, 0)
            + status_counts.get(Submission.WorkflowStatus.INELIGIBLE, 0)
            + status_counts.get(Submission.WorkflowStatus.RANKED, 0)
            + status_counts.get(Submission.WorkflowStatus.CLOSED, 0)
        )

        # Distribuídos vs. não distribuídos
        # Um processo é distribuído se tem atribuição ativa
        distributed_count = subs.filter(assignments__status="ACTIVE").distinct().count()
        unassigned_count = total_received - distributed_count

        # Two mutually exclusive dimensions, never an OR across lifecycle phases.
        initial_results = {"APTA": 0, "INAPTA": 0, "EM_ANALISE": 0}
        for result in subs.values_list("evaluation__result", flat=True):
            initial_results[result or "EM_ANALISE"] += 1
        outcome_by_workflow = {
            "RECEIVED": ("RECEBIDO", "Recebido"),
            "ASSIGNED": ("DISTRIBUIDO", "Distribuído"),
            "UNDER_ANALYSIS": ("EM_ANALISE", "Em análise"),
            "PENDING_REVIEW": ("EM_REVISAO", "Em revisão"),
            "PENDING_DILIGENCE": ("EM_DILIGENCIA", "Em diligência"),
            "ELIGIBLE_FOR_RANKING": ("HABILITADO", "Habilitado"),
            "INELIGIBLE": ("INABILITADO", "Inabilitado"),
            "RANKED": ("CLASSIFICADO", "Classificado"),
            "CLOSED": ("ENCERRADO", "Encerrado"),
        }
        consolidated_results = {
            outcome: status_counts.get(status, 0)
            for status, (outcome, _) in outcome_by_workflow.items()
        }
        consolidated_labels = dict(outcome_by_workflow.values())
        group_counts = subs.values("edital__number", "edital__year", "target_group").annotate(
            count=Count("id")
        )
        by_group = {}
        if edital:
            by_group.update({g.code: 0 for g in edital.target_groups.all()})
            by_group["SEM_GRUPO"] = 0
        for item in group_counts:
            key = (
                item["target_group"]
                if edital
                else f"{item['edital__number']}/{item['edital__year']} · {item['target_group']}"
            )
            by_group[key] = by_group.get(key, 0) + item["count"]

        # Distribuição por analista
        analysts = User.objects.filter(role=User.Role.ANALISTA, is_active=True).order_by(
            "first_name", "username"
        )
        by_analyst = []
        for analyst in analysts:
            analyst_subs = subs.filter(assignments__analyst=analyst, assignments__status="ACTIVE")
            assigned_c = analyst_subs.count()
            analyzing_c = analyst_subs.filter(
                workflow_status=Submission.WorkflowStatus.UNDER_ANALYSIS
            ).count()
            concluded_c = analyst_subs.filter(
                workflow_status__in=[
                    Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
                    Submission.WorkflowStatus.INELIGIBLE,
                    Submission.WorkflowStatus.RANKED,
                    Submission.WorkflowStatus.CLOSED,
                    Submission.WorkflowStatus.PENDING_REVIEW,
                ]
            ).count()
            by_analyst.append(
                {
                    "analyst": analyst,
                    "total_assigned": assigned_c,
                    "under_analysis": analyzing_c,
                    "concluded": concluded_c,
                }
            )

        # Distribuição por UF
        by_uf_qs = (
            subs.filter(municipality__isnull=False)
            .values("municipality__state")
            .annotate(count=Count("id"))
            .order_by("-count")
        )
        by_uf = [
            {"state": item["municipality__state"], "count": item["count"]} for item in by_uf_qs
        ]

        return {
            "total_received": total_received,
            "distributed_count": distributed_count,
            "unassigned_count": unassigned_count,
            "under_analysis": under_analysis,
            "pending_review": pending_review,
            "pending_diligence": pending_diligence,
            "concluded": concluded,
            "apt_count": initial_results["APTA"],
            "inapt_count": initial_results["INAPTA"],
            "initial_results": initial_results,
            "consolidated_results": consolidated_results,
            "consolidated_labels": consolidated_labels,
            "consolidated_cards": [
                {"label": label, "count": consolidated_results[outcome]}
                for outcome, label in consolidated_labels.items()
            ],
            "by_group": by_group,
            "by_analyst": by_analyst,
            "by_uf": by_uf,
        }

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
