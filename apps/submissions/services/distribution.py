"""Serviço de cálculo de carga de trabalho e balanceamento de distribuição."""

from dataclasses import dataclass

from django.db import transaction
from django.db.models import Count, Q

from apps.accounts.models import User
from apps.submissions.models import Assignment, Submission
from apps.submissions.services.workflow import WorkflowService


@dataclass(frozen=True)
class AnalystWorkload:
    analyst_id: int
    username: str
    full_name: str
    active_count: int


@dataclass(frozen=True)
class DistributionSuggestion:
    submission_id: int
    processo_sei: str
    suggested_analyst_id: int
    suggested_analyst_name: str


class DistributionService:
    """Gerencia a distribuição de processos e sugestão balanceada de carga de trabalho."""

    @staticmethod
    def get_analysts_workload() -> list[AnalystWorkload]:
        """Calcula o volume de processos ativos sob responsabilidade de cada analista."""
        analysts = (
            User.objects.filter(role=User.Role.ANALISTA, is_active=True)
            .annotate(
                active_count=Count(
                    "assigned_submissions",
                    filter=Q(
                        assigned_submissions__status=Assignment.Status.ACTIVE,
                        assigned_submissions__submission__workflow_status__in=[
                            Submission.WorkflowStatus.ASSIGNED,
                            Submission.WorkflowStatus.UNDER_ANALYSIS,
                        ],
                    ),
                )
            )
            .order_by("active_count", "first_name", "username")
        )

        return [
            AnalystWorkload(
                analyst_id=a.id,
                username=a.username,
                full_name=a.get_full_name() or a.username,
                active_count=a.active_count,
            )
            for a in analysts
        ]

    @classmethod
    def suggest_balanced_distribution(
        cls, submission_ids: list[int]
    ) -> list[DistributionSuggestion]:
        """Calcula sugestão de distribuição round-robin ponderada pela carga atual dos analistas.

        Importante: apenas sugere; não altera nenhuma atribuição sem a confirmação explícita do usuário.
        """
        workloads = cls.get_analysts_workload()
        if not workloads:
            return []

        # Mantém simulação de contadores de carga
        simulated_counts = {w.analyst_id: w.active_count for w in workloads}
        analysts_map = {w.analyst_id: w for w in workloads}

        submissions = Submission.objects.filter(id__in=submission_ids).order_by(
            "received_at", "processo_sei"
        )

        suggestions: list[DistributionSuggestion] = []
        for sub in submissions:
            # Seleciona o analista com menor carga acumulada
            least_loaded_id = min(simulated_counts.keys(), key=lambda aid: simulated_counts[aid])
            analyst = analysts_map[least_loaded_id]

            suggestions.append(
                DistributionSuggestion(
                    submission_id=sub.id,
                    processo_sei=sub.processo_sei,
                    suggested_analyst_id=analyst.analyst_id,
                    suggested_analyst_name=analyst.full_name,
                )
            )
            simulated_counts[least_loaded_id] += 1

        return suggestions

    @classmethod
    @transaction.atomic
    def bulk_assign(
        cls,
        submission_ids: list[int],
        analyst_id: int,
        assigned_by: User,
        reason: str = "",
    ) -> int:
        """Atribui em lote uma lista de processos a um analista selecionado."""
        analyst = User.objects.get(id=analyst_id)
        submissions = Submission.objects.filter(id__in=submission_ids)

        assigned_count = 0
        for sub in submissions:
            WorkflowService.assign_analyst(
                submission=sub,
                analyst=analyst,
                assigned_by=assigned_by,
                reason=reason or "Atribuição em lote",
            )
            assigned_count += 1

        return assigned_count
