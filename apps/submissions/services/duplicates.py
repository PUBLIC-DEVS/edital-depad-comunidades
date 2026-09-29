"""Serviço e políticas explícitas de resolução de duplicidades de inscrições."""

from collections import defaultdict
from collections.abc import Iterable
from dataclasses import dataclass

from django.core.exceptions import ValidationError

from apps.editais.models import Edital
from apps.institutions.cnpj import normalize_cnpj
from apps.submissions.models import Submission


@dataclass(frozen=True)
class DuplicateResolution:
    """Resultado da resolução de duplicidades para um conjunto de inscrições."""

    retained: list[Submission]
    suppressed: list[Submission]
    suppression_reasons: dict[int, str]  # submission_id -> justificativa


class DuplicateService:
    """Serviço responsável por identificar e aplicar políticas de duplicidade por edital."""

    @staticmethod
    def group_by_institution_cnpj(submissions: Iterable[Submission]) -> dict[str, list[Submission]]:
        """Agrupa submissões pelo CNPJ normalizado da instituição."""
        groups: dict[str, list[Submission]] = defaultdict(list)
        for sub in submissions:
            cnpj = normalize_cnpj(sub.institution.cnpj)
            groups[cnpj].append(sub)
        return groups

    @classmethod
    def resolve_duplicates(
        cls,
        submissions: Iterable[Submission],
        policy: str = Edital.DuplicatePolicy.KEEP_EARLIEST_SUBMISSION,
        include_closed: bool = False,
    ) -> DuplicateResolution:
        """Resolve duplicidades para a lista de submissões segundo a política informada.

        Políticas suportadas:
        - KEEP_EARLIEST_SUBMISSION: Mantém a inscrição com menor received_at (mais antiga).
          Critério de desempate caso timestamps sejam idênticos: menor processo_sei, depois menor id.
        - KEEP_LATEST_SUBMISSION: Mantém a inscrição mais recente (retificadora).

        Submissões canceladas ou fechadas (CLOSED) não bloqueiam outras inscrições da mesma entidade.
        """
        if policy not in Edital.DuplicatePolicy.values:
            raise ValidationError("Política de duplicidade desconhecida.")
        groups = cls.group_by_institution_cnpj(submissions)

        retained: list[Submission] = []
        suppressed: list[Submission] = []
        reasons: dict[int, str] = {}

        for _cnpj, group in groups.items():
            # Filtra submissões ativas (ignora canceladas/fechadas na disputa de duplicidade)
            active_subs = [
                s
                for s in group
                if include_closed or s.workflow_status != Submission.WorkflowStatus.CLOSED
            ]

            if len(active_subs) <= 1:
                retained.extend(group)
                continue

            if policy == Edital.DuplicatePolicy.KEEP_LATEST_SUBMISSION:
                # Mais recente primeiro
                sorted_subs = sorted(
                    active_subs,
                    key=lambda s: (s.received_at, s.processo_sei, s.id),
                    reverse=True,
                )
            else:
                # Padrão histórico: mais antiga primeiro (KEEP_EARLIEST_SUBMISSION)
                sorted_subs = sorted(
                    active_subs,
                    key=lambda s: (s.received_at, s.processo_sei, s.id),
                )

            winner = sorted_subs[0]
            retained.append(winner)

            for loser in sorted_subs[1:]:
                suppressed.append(loser)
                if policy == Edital.DuplicatePolicy.KEEP_LATEST_SUBMISSION:
                    msg = (
                        f"Inscrição suprimida pela retificadora mais recente "
                        f"({winner.processo_sei} em {winner.received_at:%d/%m/%Y %H:%M})."
                    )
                else:
                    msg = (
                        f"Inscrição duplicada suprimida em favor da primeira submissão válida "
                        f"({winner.processo_sei} em {winner.received_at:%d/%m/%Y %H:%M})."
                    )
                reasons[loser.id] = msg

            # Submissões fechadas mantêm seu estado original
            for closed_sub in group:
                if (
                    not include_closed
                    and closed_sub.workflow_status == Submission.WorkflowStatus.CLOSED
                ):
                    retained.append(closed_sub)

        return DuplicateResolution(
            retained=retained,
            suppressed=suppressed,
            suppression_reasons=reasons,
        )
