"""Detector de anomalias e validações automáticas de integridade de processos."""

from dataclasses import dataclass

from apps.institutions.cnpj import extract_cnpj_root, normalize_cnpj, validate_cnpj
from apps.submissions.models import Submission
from apps.submissions.services.eligibility import ParticipationEligibilityService


@dataclass(frozen=True)
class AnomalyAlert:
    code: str
    severity: str  # 'danger', 'warning', 'info'
    message: str
    details: tuple[str, ...] = ()


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
        duplicates = (
            Submission.objects.filter(
                edital=submission.edital,
                institution__cnpj=norm_cnpj,
            )
            .exclude(id=submission.id)
            .select_related("institution")
            .order_by("received_at")
        )
        if duplicates.exists():
            previous = tuple(
                (
                    f"Processo {other.processo_sei}; recebimento "
                    f"{other.received_at:%d/%m/%Y %H:%M}; "
                    f"{other.get_workflow_status_display()}; analista "
                    f"{other.assigned_analyst.get_full_name() or other.assigned_analyst.username}"
                    if other.assigned_analyst
                    else f"Processo {other.processo_sei}; recebimento "
                    f"{other.received_at:%d/%m/%Y %H:%M}; {other.get_workflow_status_display()}; "
                    "sem analista atribuído"
                )
                for other in duplicates
            )
            alerts.append(
                AnomalyAlert(
                    code="DUPLICATE_CNPJ",
                    severity="warning",
                    message="Já existe outra inscrição deste CNPJ neste edital.",
                    details=previous,
                )
            )

        # 2b. Vínculo Matriz / Filial (mesma raiz de 8 dígitos em CNPJ diferente no mesmo edital)
        cnpj_root = extract_cnpj_root(norm_cnpj)
        if len(cnpj_root) == 8:
            same_root_others = (
                Submission.objects.filter(
                    edital=submission.edital,
                    institution__cnpj__startswith=cnpj_root,
                )
                .exclude(institution__cnpj=norm_cnpj)
                .select_related("institution")
                .order_by("received_at")
            )
            if same_root_others.exists():
                root_details = tuple(
                    f"Processo {other.processo_sei} — {other.institution.formatted_cnpj} "
                    f"({other.institution.cnpj_hierarchy_label}); recebimento "
                    f"{other.received_at:%d/%m/%Y %H:%M}; {other.get_workflow_status_display()}"
                    for other in same_root_others
                )
                alerts.append(
                    AnomalyAlert(
                        code="SAME_CNPJ_ROOT_MATRIZ_FILIAL",
                        severity="warning",
                        message=(
                            f"Existe outra inscrição neste edital com a mesma raiz de CNPJ "
                            f"({submission.institution.formatted_cnpj_root} — Matriz/Filial)."
                        ),
                        details=root_details,
                    )
                )

        restrictions = list(
            ParticipationEligibilityService.active_restrictions(submission.edital, raw_cnpj)
        )
        if restrictions:
            alerts.append(
                AnomalyAlert(
                    code="ACTIVE_CONTRACT_RESTRICTION",
                    severity="danger",
                    message="Participação vedada por restrição ativa; análise documental bloqueada.",
                    details=tuple(
                        f"{rule.reason} · {rule.source} · {rule.reference_period}".strip(" ·")
                        for rule in restrictions
                    ),
                )
            )

        if submission.target_group == "SEM_GRUPO":
            alerts.append(
                AnomalyAlert(
                    code="NO_TARGET_GROUP",
                    severity="warning",
                    message="Sem grupo: revise vagas, município e associação ao programa.",
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

        # 4b. Faixa de vagas: Mães + Feminino >= 5
        soma_fem_maes = submission.vagas_femininas + submission.vagas_maes_nutrizes
        if soma_fem_maes > 0 and soma_fem_maes < 5:
            alerts.append(
                AnomalyAlert(
                    code="MIN_VACANCIES_FEMALE_MOTHERS",
                    severity="warning",
                    message=(
                        f"Mães + Feminino ({soma_fem_maes}) abaixo do mínimo de referência "
                        f"(Mães + Feminino >= 5; informado: {submission.vagas_femininas} femininas + "
                        f"{submission.vagas_maes_nutrizes} mães nutrizes)."
                    ),
                )
            )

        # 4c. Faixa de vagas: 10 <= Masculino <= 60
        if submission.vagas_masculinas > 0 and not (10 <= submission.vagas_masculinas <= 60):
            alerts.append(
                AnomalyAlert(
                    code="MALE_VACANCIES_OUT_OF_RANGE",
                    severity="warning",
                    message=(
                        f"Vagas masculinas ({submission.vagas_masculinas}) fora da faixa de referência "
                        f"(10 <= Masculino <= 60)."
                    ),
                )
            )

        # 5. Vagas solicitadas acima da capacidade instalada
        if (
            submission.capacidade_total > 0
            and submission.vagas_solicitadas > submission.capacidade_total
        ):
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
        if submission.edital.requires_financial_rules and (
            not submission.valor_global or submission.valor_global <= 0
        ):
            alerts.append(
                AnomalyAlert(
                    code="MISSING_GLOBAL_VALUE",
                    severity="warning",
                    message="Valor global da proposta não preenchido ou zerado.",
                )
            )

        return alerts
