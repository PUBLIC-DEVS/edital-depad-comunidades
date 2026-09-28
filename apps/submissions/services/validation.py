"""Detector de anomalias e validações automáticas de integridade de processos."""

from dataclasses import dataclass

from apps.institutions.cnpj import normalize_cnpj, validate_cnpj
from apps.submissions.models import Submission


@dataclass(frozen=True)
class AnomalyAlert:
    code: str
    severity: str  # 'danger', 'warning', 'info'
    message: str


class SubmissionAnomalyDetector:
    """Detecta inconsistências, duplicidades e falhas cadastrais em processos."""

    @classmethod
    def check_submission(cls, submission: Submission) -> list[AnomalyAlert]:
        alerts: list[AnomalyAlert] = []

        # 1. Validação de CNPJ
        raw_cnpj = submission.institution.cnpj
        if not validate_cnpj(raw_cnpj):
            alerts.append(
                AnomalyAlert(
                    code="INVALID_CNPJ",
                    severity="danger",
                    message=f"CNPJ '{raw_cnpj}' possui formato ou dígitos verificadores inválidos.",
                )
            )

        # 2. CNPJ Duplicado no mesmo edital
        norm_cnpj = normalize_cnpj(raw_cnpj)
        dup_cnpj_count = (
            Submission.objects.filter(
                edital=submission.edital,
                institution__cnpj=norm_cnpj,
            )
            .exclude(id=submission.id)
            .exclude(workflow_status=Submission.WorkflowStatus.CLOSED)
            .count()
        )
        if dup_cnpj_count > 0:
            alerts.append(
                AnomalyAlert(
                    code="DUPLICATE_CNPJ",
                    severity="danger",
                    message=f"Existem outras {dup_cnpj_count} inscrição(ões) com o mesmo CNPJ neste edital.",
                )
            )

        # 3. Processo SEI Duplicado
        dup_sei_count = (
            Submission.objects.filter(
                edital=submission.edital,
                processo_sei=submission.processo_sei,
            )
            .exclude(id=submission.id)
            .count()
        )
        if dup_sei_count > 0:
            alerts.append(
                AnomalyAlert(
                    code="DUPLICATE_SEI",
                    severity="danger",
                    message=f"O Processo SEI '{submission.processo_sei}' está cadastrado em duplicidade.",
                )
            )

        # 4. Inconsistência na soma de vagas
        soma_vagas = (
            submission.vagas_femininas
            + submission.vagas_masculinas
            + submission.vagas_maes_nutrizes
        )
        if submission.vagas_solicitadas > 0 and soma_vagas != submission.vagas_solicitadas:
            alerts.append(
                AnomalyAlert(
                    code="INCONSISTENT_VACANCIES",
                    severity="warning",
                    message=(
                        f"Soma de vagas ({soma_vagas}) diverge do total informado "
                        f"({submission.vagas_solicitadas})."
                    ),
                )
            )

        # 5. Vagas solicitadas acima da capacidade instalada
        if submission.capacidade_total > 0 and submission.vagas_solicitadas > submission.capacidade_total:
            alerts.append(
                AnomalyAlert(
                    code="EXCESS_CAPACITY",
                    severity="warning",
                    message=(
                        f"Vagas solicitadas ({submission.vagas_solicitadas}) excedem a "
                        f"capacidade total instalada ({submission.capacidade_total})."
                    ),
                )
            )

        # 6. Ausência de valor global
        if not submission.valor_global or submission.valor_global <= 0:
            alerts.append(
                AnomalyAlert(
                    code="MISSING_GLOBAL_VALUE",
                    severity="warning",
                    message="Valor global da proposta não preenchido ou zerado.",
                )
            )

        return alerts
