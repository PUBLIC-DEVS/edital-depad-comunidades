from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.evaluations.models import Evaluation
from apps.institutions.cnpj import normalize_cnpj
from apps.submissions.models import Assignment, ParticipationRestriction, Submission
from apps.submissions.services.workflow import WorkflowService


class ParticipationEligibilityService:
    @staticmethod
    def active_restrictions(edital, cnpj):
        normalized = normalize_cnpj(cnpj or "")
        if not normalized:
            return ParticipationRestriction.objects.none()
        return ParticipationRestriction.objects.filter(edital=edital, cnpj=normalized, active=True)

    @classmethod
    def is_restricted(cls, submission):
        return cls.active_restrictions(submission.edital, submission.institution.cnpj).exists()

    @classmethod
    @transaction.atomic
    def apply_preanalysis_block(cls, submission, actor):
        submission = (
            Submission.objects.select_for_update()
            .select_related("edital", "institution")
            .get(pk=submission.pk)
        )
        restrictions = list(cls.active_restrictions(submission.edital, submission.institution.cnpj))
        if not restrictions:
            return []
        if Evaluation.objects.filter(submission=submission).exists():
            return restrictions
        if submission.workflow_status in {
            Submission.WorkflowStatus.RECEIVED,
            Submission.WorkflowStatus.ASSIGNED,
        }:
            WorkflowService.transition(
                submission,
                Submission.WorkflowStatus.INELIGIBLE,
                actor,
                reason="Impedimento cadastral antes da análise documental.",
                metadata={
                    "restriction_ids": [restriction.pk for restriction in restrictions],
                    "reason_codes": [restriction.reason for restriction in restrictions],
                },
            )
            for assignment in submission.assignments.filter(status=Assignment.Status.ACTIVE):
                assignment.status = Assignment.Status.CANCELLED
                assignment.ended_at = timezone.now()
                assignment.reason = "Participação vedada antes da análise."
                assignment.save(update_fields=["status", "ended_at", "reason"])
                AuditEvent.objects.create(
                    actor=actor,
                    entity_type="Assignment",
                    entity_id=str(assignment.pk),
                    action="CANCEL_RESTRICTED",
                    metadata={"submission_id": submission.pk},
                )
        return restrictions

    @classmethod
    def require_assignable(cls, submission):
        restrictions = cls.active_restrictions(submission.edital, submission.institution.cnpj)
        if restrictions.exists():
            reasons = "; ".join(dict.fromkeys(r.reason for r in restrictions))
            raise PermissionDenied(f"Participação vedada: {reasons}")

    @classmethod
    @transaction.atomic
    def create_restriction(cls, restriction, actor):
        if restriction.pk:
            raise ValidationError(
                "Restrições existentes devem ser editadas pela operação auditada."
            )
        restriction.cnpj = normalize_cnpj(restriction.cnpj)
        if (
            restriction.active
            and Evaluation.objects.filter(
                submission__edital=restriction.edital,
                submission__institution__cnpj=restriction.cnpj,
            ).exists()
        ):
            raise ValidationError(
                "Restrição retroativa encontrada após início de análise. "
                "A aplicação exige decisão formal da coordenação."
            )
        restriction.created_by = actor
        restriction.full_clean()
        restriction.save()
        AuditEvent.objects.create(
            actor=actor,
            entity_type="ParticipationRestriction",
            entity_id=str(restriction.pk),
            action="CREATE_RESTRICTION",
            metadata={
                "edital_id": restriction.edital_id,
                "cnpj": restriction.cnpj,
                "source": restriction.source,
                "reference_period": restriction.reference_period,
            },
        )
        affected = Submission.objects.filter(
            edital=restriction.edital, institution__cnpj=restriction.cnpj
        ).select_related("institution", "edital")
        for submission in affected:
            cls.apply_preanalysis_block(submission, actor)
        return restriction

    @classmethod
    @transaction.atomic
    def update_restriction(cls, restriction, actor):
        locked = ParticipationRestriction.objects.select_for_update().get(pk=restriction.pk)
        if (
            restriction.edital_id != locked.edital_id
            or normalize_cnpj(restriction.cnpj) != locked.cnpj
        ):
            raise ValidationError("Edital e CNPJ da restrição são imutáveis; crie outro registro.")
        if (
            restriction.active
            and not locked.active
            and Evaluation.objects.filter(
                submission__edital=locked.edital,
                submission__institution__cnpj=locked.cnpj,
            ).exists()
        ):
            raise ValidationError(
                "Restrição retroativa encontrada após início de análise. "
                "A aplicação exige decisão formal da coordenação."
            )
        changed_fields = []
        for name in ("reason", "source", "reference_period", "active"):
            old = getattr(locked, name)
            new = getattr(restriction, name)
            if old != new:
                changed_fields.append((name, old, new))
                setattr(locked, name, new)
        locked.full_clean()
        locked.save(update_fields=[name for name, _, _ in changed_fields])
        for name, old, new in changed_fields:
            AuditEvent.objects.create(
                actor=actor,
                entity_type="ParticipationRestriction",
                entity_id=str(locked.pk),
                action="UPDATE_RESTRICTION",
                field=name,
                old_value=str(old),
                new_value=str(new),
                metadata={"edital_id": locked.edital_id, "cnpj": locked.cnpj},
            )
        if locked.active:
            affected = Submission.objects.filter(
                edital=locked.edital, institution__cnpj=locked.cnpj
            ).select_related("institution", "edital")
            for submission in affected:
                cls.apply_preanalysis_block(submission, actor)
        return locked
