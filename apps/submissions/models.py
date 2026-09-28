from django.conf import settings
from django.db import models


class Submission(models.Model):
    """Representa a inscrição / processo formal submetido ao edital."""

    class WorkflowStatus(models.TextChoices):
        RECEIVED = "RECEIVED", "Recebida"
        ASSIGNED = "ASSIGNED", "Distribuída"
        UNDER_ANALYSIS = "UNDER_ANALYSIS", "Em Análise"
        PENDING_REVIEW = "PENDING_REVIEW", "Pendente de Revisão"
        PENDING_DILIGENCE = "PENDING_DILIGENCE", "Em Diligência"
        ELIGIBLE_FOR_RANKING = "ELIGIBLE_FOR_RANKING", "Elegível para Ranking"
        INELIGIBLE = "INELIGIBLE", "Inabilitada / Inelegível"
        RANKED = "RANKED", "Classificada no Ranking"
        CLOSED = "CLOSED", "Encerrada"

    class TargetGroup(models.TextChoices):
        G1 = "G1", "Grupo 1 (Mulheres e Mães Nutrizes)"
        G2 = "G2", "Grupo 2 (Masculino PRONASCI)"
        G3 = "G3", "Grupo 3 (Masculino Demais Municípios)"
        SEM_GRUPO = "SEM_GRUPO", "Sem Grupo Definido"

    edital = models.ForeignKey(
        "editais.Edital",
        on_delete=models.PROTECT,
        related_name="submissions",
        verbose_name="Edital",
    )
    institution = models.ForeignKey(
        "institutions.Institution",
        on_delete=models.PROTECT,
        related_name="submissions",
        verbose_name="Instituição Proponente",
    )
    processo_sei = models.CharField(
        max_length=50,
        db_index=True,
        verbose_name="Processo SEI",
        help_text="Número do processo administrativo no SEI.",
    )
    received_at = models.DateTimeField(
        db_index=True,
        verbose_name="Data e Hora de Recebimento",
        help_text="Timestamp oficial de protocolo da inscrição.",
    )
    municipality = models.ForeignKey(
        "institutions.Municipality",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="submissions",
        verbose_name="Município da Execução",
    )
    vagas_femininas = models.PositiveIntegerField(
        default=0,
        verbose_name="Vagas Femininas",
    )
    vagas_masculinas = models.PositiveIntegerField(
        default=0,
        verbose_name="Vagas Masculinas",
    )
    vagas_maes_nutrizes = models.PositiveIntegerField(
        default=0,
        verbose_name="Vagas Mães Nutrizes",
    )
    vagas_solicitadas = models.PositiveIntegerField(
        default=0,
        verbose_name="Total de Vagas Solicitadas",
    )
    capacidade_total = models.PositiveIntegerField(
        default=0,
        verbose_name="Capacidade Total Instalada",
    )
    valor_global = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Valor Global Proposto (R$)",
    )
    patrimonio_minimo = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Patrimônio Líquido Mínimo Exigido (R$)",
    )
    workflow_status = models.CharField(
        max_length=30,
        choices=WorkflowStatus.choices,
        default=WorkflowStatus.RECEIVED,
        db_index=True,
        verbose_name="Status do Workflow",
    )
    target_group = models.CharField(
        max_length=20,
        choices=TargetGroup.choices,
        default=TargetGroup.SEM_GRUPO,
        db_index=True,
        verbose_name="Grupo de Enquadramento",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Inscrição / Processo"
        verbose_name_plural = "Inscrições / Processos"
        ordering = ["received_at", "processo_sei"]

    def __str__(self):
        status_disp = self.get_workflow_status_display()
        return f"{self.processo_sei} — {self.institution.name} ({status_disp})"

    @property
    def current_assignment(self):
        """Retorna a atribuição ativa mais recente para esta submissão."""
        return self.assignments.filter(status=Assignment.Status.ACTIVE).first()

    @property
    def assigned_analyst(self):
        assignment = self.current_assignment
        return assignment.analyst if assignment else None

    @property
    def computed_total_vagas(self) -> int:
        return self.vagas_femininas + self.vagas_masculinas + self.vagas_maes_nutrizes


class Assignment(models.Model):
    """Representa a atribuição formal de uma inscrição a um analista."""

    class Status(models.TextChoices):
        ACTIVE = "ACTIVE", "Ativa"
        REASSIGNED = "REASSIGNED", "Redistribuída"
        CANCELLED = "CANCELLED", "Cancelada"

    submission = models.ForeignKey(
        Submission,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="Inscrição",
    )
    analyst = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="assigned_submissions",
        verbose_name="Analista Responsável",
    )
    assigned_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="made_assignments",
        verbose_name="Distribuído por",
    )
    assigned_at = models.DateTimeField(auto_now_add=True, verbose_name="Data de Atribuição")
    ended_at = models.DateTimeField(null=True, blank=True, verbose_name="Data de Encerramento")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.ACTIVE,
        verbose_name="Status da Atribuição",
    )
    reason = models.CharField(
        max_length=255,
        blank=True,
        verbose_name="Motivo da Redistribuição / Encerramento",
    )

    class Meta:
        verbose_name = "Atribuição de Processo"
        verbose_name_plural = "Atribuições de Processos"
        ordering = ["-assigned_at"]

    def __str__(self):
        st = self.get_status_display()
        return f"{self.submission.processo_sei} -> {self.analyst.username} ({st})"
