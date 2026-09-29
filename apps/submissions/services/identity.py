"""Explicit, audited correction of the CNPJ declared for one submission."""

from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.evaluations.models import Evaluation
from apps.institutions.cnpj import cnpj_validator, normalize_cnpj
from apps.institutions.models import Institution
from apps.submissions.models import Submission


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
        if Evaluation.objects.filter(submission=locked).exists():
            raise ValidationError("CNPJ não pode ser corrigido após o início da análise.")
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
            },
        )
        from apps.submissions.services.eligibility import ParticipationEligibilityService

        ParticipationEligibilityService.apply_preanalysis_block(locked, actor)
        return locked
