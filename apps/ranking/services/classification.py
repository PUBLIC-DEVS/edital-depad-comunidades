"""Small, explicit classification policies configured by the edital."""

from collections.abc import Iterable

from django.db import transaction

from apps.audit.models import AuditEvent
from apps.editais.models import ClassificationPolicy, ProgramMunicipality

VACANCY_FIELDS = {
    "FEMALE": "vagas_femininas",
    "MALE": "vagas_masculinas",
    "NURSING_MOTHER": "vagas_maes_nutrizes",
}


class ClassificationService:
    @staticmethod
    def classify_submission(submission):
        policy = ClassificationPolicy.objects.filter(edital=submission.edital).first()
        groups = submission.edital.target_groups.filter(active=True)
        if policy is None:
            return "SEM_GRUPO"
        if policy.policy_type == "MANUAL_TARGET_POLICY_V1":
            group = groups.filter(pk=submission.target_group_definition_id).first()
            return group.code if group else "SEM_GRUPO"
        for group in groups.select_related("program").order_by("order", "code"):
            if not any(
                getattr(submission, VACANCY_FIELDS[t], 0) > 0
                for t in group.vacancy_types
                if t in VACANCY_FIELDS
            ):
                continue
            if (
                group.program_id
                and not ProgramMunicipality.objects.filter(
                    edital=submission.edital,
                    program=group.program,
                    municipality_id=submission.municipality_id,
                    active=True,
                ).exists()
            ):
                continue
            return group.code
        return "SEM_GRUPO"

    @classmethod
    @transaction.atomic
    def classify_and_update(cls, submission, actor=None):
        group_code = cls.classify_submission(submission)
        group = submission.edital.target_groups.filter(code=group_code, active=True).first()
        new_id = group.pk if group else None
        if submission.target_group != group_code or submission.target_group_definition_id != new_id:
            old = submission.target_group
            submission.target_group = group_code
            submission.target_group_definition = group
            submission.save(update_fields=["target_group", "target_group_definition", "updated_at"])
            AuditEvent.objects.create(
                actor=actor,
                entity_type="Submission",
                entity_id=str(submission.pk),
                action="CLASSIFICATION_CHANGE",
                field="target_group",
                old_value=old,
                new_value=group_code,
                metadata={"group_id": new_id, "rules_version": submission.edital.rules_version},
            )
        return group_code

    @classmethod
    def bulk_classify(cls, submissions: Iterable):
        return {s.pk: cls.classify_submission(s) for s in submissions}
