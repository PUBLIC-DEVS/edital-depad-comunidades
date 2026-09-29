"""One transactional intake pipeline for validated operational forms."""

from dataclasses import dataclass

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.permissions import RolePermissionPolicy
from apps.audit.models import AuditEvent
from apps.institutions.models import Institution
from apps.ranking.services import ClassificationService
from apps.submissions.services.eligibility import ParticipationEligibilityService
from apps.submissions.services.validation import SubmissionAnomalyDetector


@dataclass(frozen=True)
class IntakeResult:
    submission: object
    restrictions: tuple
    alerts: tuple


class SubmissionIntakeService:
    @staticmethod
    @transaction.atomic
    def create_submission(form, actor, source="MANUAL", source_row=None):
        if not RolePermissionPolicy.can_distribute_submissions(actor):
            raise PermissionDenied("Cadastro restrito à equipe de distribuição.")
        if not form.is_valid():
            raise ValidationError("Dados de cadastro inválidos.")
        if form.instance.pk:
            raise ValidationError("Intake cria processos novos; edição usa operação própria.")
        existed = Institution.objects.filter(cnpj=form.cleaned_data["institution_cnpj"]).exists()
        submission = form.save()
        metadata = {"edital_id": submission.edital_id, "source": source}
        if source_row is not None:
            metadata["source_row"] = source_row
        action = "CREATE_CSV" if source == "CSV" else "CREATE"
        if not existed:
            AuditEvent.objects.create(
                actor=actor,
                entity_type="Institution",
                entity_id=str(submission.institution_id),
                action=action,
                metadata={"source": source},
            )
        AuditEvent.objects.create(
            actor=actor,
            entity_type="Submission",
            entity_id=str(submission.pk),
            action=action,
            metadata=metadata,
        )
        ClassificationService.classify_and_update(submission, actor)
        restrictions = ParticipationEligibilityService.apply_preanalysis_block(submission, actor)
        submission.refresh_from_db()
        alerts = SubmissionAnomalyDetector.check_submission(submission)
        return IntakeResult(submission, tuple(restrictions), tuple(alerts))
