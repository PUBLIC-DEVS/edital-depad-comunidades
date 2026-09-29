"""Official eligible ranking with separate immutable exclusions."""

from collections import defaultdict

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.permissions import RolePermissionPolicy
from apps.audit.models import AuditEvent
from apps.ranking.models import RankingEntry, RankingExclusion, RankingSnapshot, _build_snapshot
from apps.ranking.services.classification import ClassificationService
from apps.submissions.models import Submission
from apps.submissions.services.duplicates import DuplicateService
from apps.submissions.services.workflow import WorkflowService


class RankingError(Exception):
    pass


class RankingService:
    @classmethod
    @transaction.atomic
    def generate_snapshot(
        cls,
        edital,
        actor,
        snapshot_type=RankingSnapshot.SnapshotType.PRELIMINAR,
        description="",
        eligible_statuses=None,
    ):
        if not RolePermissionPolicy.can_generate_ranking(actor):
            raise PermissionDenied("Sem permissão para gerar ranking.")
        if snapshot_type not in RankingSnapshot.SnapshotType.values:
            raise ValidationError("Tipo de snapshot inválido.")
        allowed = {"ELIGIBLE_FOR_RANKING", "RANKED"}
        eligible = set(eligible_statuses) if eligible_statuses is not None else allowed
        if not eligible or not eligible.issubset(allowed):
            raise ValidationError("Ranking oficial exige estágios elegíveis.")
        universe = list(
            Submission.objects.select_for_update()
            .filter(edital=edital)
            .select_related("institution", "municipality", "edital")
        )
        for sub in universe:
            ClassificationService.classify_and_update(sub, actor)
        duplicate_universe = (
            universe
            if edital.duplicate_scope == "ABSOLUTE"
            else [s for s in universe if s.workflow_status in eligible]
        )
        if edital.tie_breaker_policy == "UNRESOLVED":
            for members in DuplicateService.group_by_institution_cnpj(duplicate_universe).values():
                if len({s.received_at for s in members}) != len(members):
                    raise ValidationError(
                        "OPEN BUSINESS QUESTION: empate absoluto entre duplicatas."
                    )
        resolution = DuplicateService.resolve_duplicates(
            duplicate_universe,
            edital.duplicate_policy,
            include_closed=edital.duplicate_scope == "ABSOLUTE",
        )
        suppressed = {s.pk for s in resolution.suppressed}
        winners = {s.institution.cnpj: s for s in resolution.retained}
        grouped = defaultdict(list)
        exclusions = []
        for sub in universe:
            reason, winner = None, None
            if sub.pk in suppressed:
                reason, winner = "DUPLICATE_SUPPRESSED", winners[sub.institution.cnpj]
            elif sub.workflow_status == "CLOSED":
                reason = "CLOSED"
            elif sub.workflow_status not in eligible:
                reason = "NOT_ELIGIBLE"
            elif sub.target_group == "SEM_GRUPO":
                reason = "NO_TARGET_GROUP"
            if reason:
                exclusions.append((sub, reason, winner))
            else:
                grouped[sub.target_group].append(sub)
        if edital.tie_breaker_policy == "UNRESOLVED":
            for group in grouped.values():
                if len({s.received_at for s in group}) != len(group):
                    raise ValidationError(
                        "OPEN BUSINESS QUESTION: configure a política de empate absoluto."
                    )
        snapshot = RankingSnapshot.objects.create(
            edital=edital,
            generated_by=actor,
            snapshot_type=snapshot_type,
            rules_version=edital.rules_version,
            duplicate_policy=edital.duplicate_policy,
            description=description,
            policy_metadata={
                "duplicate_scope": edital.duplicate_scope,
                "tie_breaker_policy": edital.tie_breaker_policy,
                "eligible_statuses": sorted(eligible),
            },
        )
        with _build_snapshot(snapshot):
            for sub, reason, winner in exclusions:
                RankingExclusion.objects.create(
                    snapshot=snapshot,
                    submission=sub,
                    reason_code=reason,
                    reason_text=resolution.suppression_reasons.get(sub.pk, reason),
                    duplicate_of=winner,
                    metadata={
                        "received_at": sub.received_at.isoformat(),
                        "target_group": sub.target_group,
                        "workflow_status": sub.workflow_status,
                    },
                )
            for group, submissions in grouped.items():
                for position, sub in enumerate(
                    sorted(submissions, key=lambda s: (s.received_at, s.processo_sei)), 1
                ):
                    RankingEntry.objects.create(
                        snapshot=snapshot,
                        submission=sub,
                        target_group=group,
                        position=position,
                        received_at=sub.received_at,
                        total_vacancies=sub.vagas_solicitadas,
                        qualification_status=sub.workflow_status,
                        snapshot_data={
                            "processo_sei": sub.processo_sei,
                            "institution": sub.institution.name,
                            "cnpj": sub.institution.cnpj,
                            "municipality": sub.municipality.name if sub.municipality else None,
                            "state": sub.municipality.state if sub.municipality else None,
                        },
                        tie_breaker_notes=f"Policy: {edital.tie_breaker_policy}",
                    )
                    if sub.workflow_status == "ELIGIBLE_FOR_RANKING":
                        WorkflowService.transition(
                            sub,
                            "RANKED",
                            actor,
                            reason="Entrada em snapshot oficial.",
                            metadata={"snapshot_id": snapshot.pk},
                        )
        AuditEvent.objects.create(
            actor=actor,
            entity_type="RankingSnapshot",
            entity_id=str(snapshot.pk),
            action="GENERATE_SNAPSHOT",
            metadata={
                "total_entries": snapshot.entries.count(),
                "total_exclusions": snapshot.exclusions.count(),
                **snapshot.policy_metadata,
            },
        )
        return snapshot
