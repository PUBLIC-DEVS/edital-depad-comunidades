"""Serviço determinístico de ordenação, desempate e geração de snapshots de ranking."""

from collections import defaultdict

from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.editais.models import Edital
from apps.ranking.models import RankingEntry, RankingSnapshot
from apps.ranking.services.classification import ClassificationService
from apps.submissions.models import Submission
from apps.submissions.services.duplicates import DuplicateService


class RankingError(Exception):
    """Exceção base para erros na geração de ranking."""


class RankingService:
    """Orquestrador determinístico da classificação e geração de snapshots de ranking."""

    @classmethod
    @transaction.atomic
    def generate_snapshot(
        cls,
        edital: Edital,
        actor: User,
        snapshot_type: str = RankingSnapshot.SnapshotType.PRELIMINAR,
        description: str = "",
        eligible_statuses: list[str] | None = None,
    ) -> RankingSnapshot:
        """Gera um snapshot de ranking imutável para o edital informado.

        Critérios de elegibilidade:
        - Por padrão, inclui submissões com status ELIGIBLE_FOR_RANKING ou RANKED.
        - Também inclui submissões com avaliação concluída como APTA caso ainda não estejam formalmente fechadas/inabilitadas.
        - Suprime duplicidades conforme a política configurada no Edital.
        - Enquadra deterministamente em G1, G2 (PRONASCI por IBGE) e G3.
        - Ordena por data e hora de protocolo (received_at), desempatando por processo_sei e ID.
        - Atribui posições ordinais consecutivas a partir de 1 por grupo.
        """
        if eligible_statuses is None:
            eligible_statuses = [
                Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
                Submission.WorkflowStatus.RANKED,
            ]

        # Busca todas as submissões ativas do edital
        submissions_qs = (
            Submission.objects.filter(edital=edital)
            .exclude(workflow_status=Submission.WorkflowStatus.CLOSED)
            .select_related("institution", "municipality", "edital")
        )

        all_submissions = list(submissions_qs)

        # 1. Atualiza e garante grupos corretos
        ClassificationService.bulk_classify(all_submissions)
        for s in all_submissions:
            s.target_group = ClassificationService.classify_submission(s)

        # 2. Resolução de duplicidades
        dup_resolution = DuplicateService.resolve_duplicates(
            submissions=all_submissions,
            policy=edital.duplicate_policy,
        )
        suppressed_ids = {s.id for s in dup_resolution.suppressed}

        # 3. Criação do snapshot imutável
        snapshot = RankingSnapshot.objects.create(
            edital=edital,
            generated_by=actor,
            snapshot_type=snapshot_type,
            rules_version=edital.rules_version,
            duplicate_policy=edital.duplicate_policy,
            is_immutable=True,
            description=description or f"Snapshot gerado em {timezone.now():%d/%m/%Y %H:%M}",
        )

        # 4. Agrupa por target_group
        by_group: dict[str, list[Submission]] = defaultdict(list)
        for s in all_submissions:
            # Apenas grupos G1, G2 e G3 concorrem ao ranking
            if s.target_group in (
                Submission.TargetGroup.G1,
                Submission.TargetGroup.G2,
                Submission.TargetGroup.G3,
            ):
                by_group[s.target_group].append(s)

        entries_to_create: list[RankingEntry] = []

        for group_name, group_submissions in by_group.items():
            # Ordenação determinística:
            # 1º: Não suprimida por duplicidade (ativas primeiro)
            # 2º: Elegíveis para ranking primeiro
            # 3º: Timestamp de recebimento (received_at)
            # 4º: Processo SEI (desempate lexicográfico)
            # 5º: ID interno
            def sort_key(s: Submission):
                is_suppressed = s.id in suppressed_ids
                is_eligible = s.workflow_status in eligible_statuses
                return (
                    is_suppressed,  # False (0) antes de True (1)
                    not is_eligible,  # True elegível (False=0) antes de não elegível (True=1)
                    s.received_at,
                    s.processo_sei,
                    s.id,
                )

            sorted_group = sorted(group_submissions, key=sort_key)

            position = 1
            for sub in sorted_group:
                is_sup = sub.id in suppressed_ids
                reason = dup_resolution.suppression_reasons.get(sub.id, "")

                tie_note = (
                    f"Protocolo: {sub.received_at:%d/%m/%Y %H:%M:%S}. SEI: {sub.processo_sei}."
                )
                if is_sup:
                    tie_note += f" [Duplicidade suprimida: {reason}]"

                entry = RankingEntry(
                    snapshot=snapshot,
                    submission=sub,
                    target_group=group_name,
                    position=position,
                    received_at=sub.received_at,
                    total_vacancies=sub.vagas_solicitadas or sub.computed_total_vagas,
                    is_duplicate_suppressed=is_sup,
                    qualification_status=sub.get_workflow_status_display(),
                    tie_breaker_notes=tie_note,
                )
                entries_to_create.append(entry)
                position += 1

        RankingEntry.objects.bulk_create(entries_to_create)

        # Transiciona submissões elegíveis para RANKED se estiverem em ELIGIBLE_FOR_RANKING
        eligible_ranked_ids = [
            e.submission_id
            for e in entries_to_create
            if not e.is_duplicate_suppressed
            and e.submission.workflow_status == Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING
        ]
        if eligible_ranked_ids:
            Submission.objects.filter(id__in=eligible_ranked_ids).update(
                workflow_status=Submission.WorkflowStatus.RANKED,
            )

        AuditEvent.objects.create(
            actor=actor,
            entity_type="RankingSnapshot",
            entity_id=str(snapshot.id),
            action="GENERATE_SNAPSHOT",
            new_value=snapshot.snapshot_type,
            metadata={
                "total_entries": len(entries_to_create),
                "edital": edital.number,
                "rules_version": edital.rules_version,
            },
        )

        return snapshot
