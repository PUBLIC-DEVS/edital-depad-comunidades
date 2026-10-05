"""Explicit, audited correction of the CNPJ declared for one submission."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.evaluations.models import Evaluation
from apps.evaluations.validation_rules import ValidationRuleEvaluator
from apps.institutions.cnpj import cnpj_validator, normalize_cnpj
from apps.institutions.models import Institution
from apps.submissions.models import Submission
from apps.submissions.services.eligibility import ParticipationEligibilityService


class SubmissionIdentityService:
    @staticmethod
    @transaction.atomic
    def correct_cnpj(submission, raw_cnpj, reason, actor):
        if not actor.is_superuser and actor.role not in {
            User.Role.ADMINISTRADOR,
            User.Role.COORDENADOR,
        }:
            raise PermissionDenied("Somente Administração ou Coordenação pode corrigir o CNPJ.")
        if not reason or not reason.strip():
            raise ValidationError("Informe a justificativa da correção.")
        normalized = normalize_cnpj(raw_cnpj)
        cnpj_validator(normalized)
        locked = (
            Submission.objects.select_for_update()
            .select_related("institution", "edital")
            .get(pk=submission.pk)
        )
        evaluation = Evaluation.objects.select_for_update().filter(submission=locked).first()
        if evaluation and (
            evaluation.status != Evaluation.Status.DRAFT
            or locked.workflow_status != Submission.WorkflowStatus.UNDER_ANALYSIS
        ):
            raise ValidationError(
                "Correção durante análise exige avaliação em rascunho no estágio de análise. "
                "Decisões concluídas não são alteradas por esta operação."
            )
        if locked.workflow_status in {
            Submission.WorkflowStatus.RANKED,
            Submission.WorkflowStatus.CLOSED,
        }:
            raise ValidationError("Processo classificado ou encerrado não permite esta correção.")
        if (
            evaluation
            and ParticipationEligibilityService.active_restrictions(
                locked.edital, normalized
            ).exists()
        ):
            raise ValidationError(
                "Novo CNPJ possui restrição ativa. Correção não aplicada: "
                "a fonte de restrição deve ser tratada formalmente antes da recuperação."
            )
        old_institution = locked.institution
        if old_institution.cnpj == normalized:
            raise ValidationError("O CNPJ informado já é o CNPJ canônico desta candidatura.")
        institution = Institution.objects.filter(cnpj=normalized).first()
        if institution is None:
            institution = Institution(
                cnpj=normalized,
                name=old_institution.name,
                trade_name=old_institution.trade_name,
                legal_nature=old_institution.legal_nature,
                contact_email=old_institution.contact_email,
                contact_phone=old_institution.contact_phone,
                address=old_institution.address,
                postal_code=old_institution.postal_code,
                municipality=old_institution.municipality,
            )
            institution.full_clean()
            institution.save()
        locked.institution = institution
        locked.save(update_fields=["institution", "updated_at"])
        duplicates = list(
            Submission.objects.filter(edital=locked.edital, institution=institution)
            .exclude(pk=locked.pk)
            .values_list("pk", flat=True)
        )
        AuditEvent.objects.create(
            actor=actor,
            entity_type="Submission",
            entity_id=str(locked.pk),
            action="CANONICAL_CNPJ_CORRECTION",
            field="institution.cnpj",
            old_value=old_institution.cnpj,
            new_value=institution.cnpj,
            metadata={
                "reason": reason.strip(),
                "old_institution_id": old_institution.pk,
                "new_institution_id": institution.pk,
                "duplicate_submission_ids": duplicates,
            },
        )
        if evaluation:
            # Confirmation referred to the old canonical identity. Keep every document value.
            for result in evaluation.check_results.filter(canonical_cnpj_confirmed=True):
                result.canonical_cnpj_confirmed = False
                result.save(update_fields=["canonical_cnpj_confirmed", "updated_at"])
                AuditEvent.objects.create(
                    actor=actor,
                    entity_type="CheckResult",
                    entity_id=str(result.pk),
                    action="FIELD_CHANGE",
                    field="canonical_cnpj_confirmed",
                    old_value="True",
                    new_value="False",
                    metadata={
                        "evaluation_id": evaluation.pk,
                        "reason": "Canonical identity correction",
                    },
                )
            evaluation.submission = locked
            outcomes = ValidationRuleEvaluator.evaluate_evaluation(evaluation)
            AuditEvent.objects.create(
                actor=actor,
                entity_type="Evaluation",
                entity_id=str(evaluation.pk),
                action="IDENTITY_VALIDATIONS_REEVALUATED",
                metadata={
                    "submission_id": locked.pk,
                    "outcomes": [
                        {"rule_id": item.rule.pk, "status": item.status}
                        for item in outcomes
                        if item.rule.rule_type == "CNPJ_MATCH_CANONICAL"
                    ],
                },
            )
        else:
            ParticipationEligibilityService.apply_preanalysis_block(locked, actor)
        return locked
