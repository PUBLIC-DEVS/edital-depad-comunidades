"""Serviço determinístico de enquadramento em grupos (G1, G2, G3) conforme regras do edital."""

from collections.abc import Iterable

from django.db import transaction

from apps.audit.models import AuditEvent
from apps.editais.models import ProgramMunicipality
from apps.submissions.models import Submission


class ClassificationService:
    """Enquadra submissões nos grupos G1, G2, G3 ou SEM_GRUPO.

    Regras de Negócio do Edital:
    - G1: vagas_femininas + vagas_maes_nutrizes > 0
    - G2: Não é G1 E vagas_masculinas > 0 E município executor pertence ao programa PRONASCI
          configurado para o edital (comparação estrita por chave de Município / Código IBGE).
    - G3: Não é G1 E Não é G2 E vagas_masculinas > 0.
    - SEM_GRUPO: Casos em que nenhuma vaga válida foi solicitada ou não atende aos grupos anteriores.
    """

    @classmethod
    def classify_submission(
        cls,
        submission: Submission,
        pronasci_municipality_ids: set[int] | None = None,
    ) -> str:
        """Determina o grupo de enquadramento para uma única submissão."""
        fem_nutrizes = submission.vagas_femininas + submission.vagas_maes_nutrizes
        if fem_nutrizes > 0:
            return Submission.TargetGroup.G1

        if submission.vagas_masculinas > 0:
            if pronasci_municipality_ids is not None:
                is_pronasci = submission.municipality_id in pronasci_municipality_ids
            else:
                is_pronasci = ProgramMunicipality.objects.filter(
                    edital=submission.edital,
                    municipality=submission.municipality,
                    program_name="PRONASCI",
                    active=True,
                ).exists()

            if is_pronasci:
                return Submission.TargetGroup.G2
            return Submission.TargetGroup.G3

        return Submission.TargetGroup.SEM_GRUPO

    @classmethod
    @transaction.atomic
    def classify_and_update(cls, submission: Submission, actor=None) -> str:
        """Determina o grupo, atualiza o modelo e persiste se houver alteração."""
        group = cls.classify_submission(submission)
        if submission.target_group != group:
            old = submission.target_group
            submission.target_group = group
            submission.save(update_fields=["target_group", "updated_at"])
            AuditEvent.objects.create(
                actor=actor,
                entity_type="Submission",
                entity_id=str(submission.pk),
                action="CLASSIFICATION_CHANGE",
                field="target_group",
                old_value=old,
                new_value=group,
            )
        return group

    @classmethod
    def bulk_classify(cls, submissions: Iterable[Submission]) -> dict[int, str]:
        """Classifica em lote um conjunto de submissões otimizando queries ao banco."""
        submissions_list = list(submissions)
        if not submissions_list:
            return {}

        edital_ids = {s.edital_id for s in submissions_list}
        pronasci_pairs = set(
            ProgramMunicipality.objects.filter(
                edital_id__in=edital_ids,
                program_name="PRONASCI",
                active=True,
            ).values_list("edital_id", "municipality_id")
        )

        results = {}
        for s in submissions_list:
            fem_nutrizes = s.vagas_femininas + s.vagas_maes_nutrizes
            if fem_nutrizes > 0:
                results[s.id] = Submission.TargetGroup.G1
            elif s.vagas_masculinas > 0:
                if (s.edital_id, s.municipality_id) in pronasci_pairs:
                    results[s.id] = Submission.TargetGroup.G2
                else:
                    results[s.id] = Submission.TargetGroup.G3
            else:
                results[s.id] = Submission.TargetGroup.SEM_GRUPO

        return results
