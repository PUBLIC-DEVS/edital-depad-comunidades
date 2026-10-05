from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Review(models.Model):
    """Representa a revisão de conformidade efetuada por um revisor sobre uma análise concluída."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pendente de Decisão"
        COMPLETED = "COMPLETED", "Revisão Concluída"

    class PreliminaryResult(models.TextChoices):
        PRE_HABILITADO = "PRE_HABILITADO", "Pré-Habilitado"
        PRE_INABILITADO = "PRE_INABILITADO", "Pré-Inabilitado"
        PENDING_DECISION = "PENDING_DECISION", "Pendente de Conclusão"

    evaluation = models.OneToOneField(
        "evaluations.Evaluation",
        on_delete=models.CASCADE,
        related_name="review",
        verbose_name="Análise Original",
    )
    submission = models.ForeignKey(
        "submissions.Submission",
        on_delete=models.CASCADE,
        related_name="reviews",
        verbose_name="Inscrição",
    )
    reviewer = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="reviews_conducted",
        verbose_name="Revisor Responsável",
        null=True,
        blank=True,
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.PENDING,
        verbose_name="Status da Revisão",
    )
    preliminary_result = models.CharField(
        max_length=30,
        choices=PreliminaryResult.choices,
        default=PreliminaryResult.PENDING_DECISION,
        verbose_name="Resultado Preliminar da Revisão",
    )
    decision_notes = models.TextField(
        blank=True,
        verbose_name="Fundamentação da Decisão do Revisor",
    )
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Data da Conclusão")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Revisão de Análise"
        verbose_name_plural = "Revisões de Análises"
        ordering = ["-created_at"]

    def __str__(self):
        sei = self.submission.processo_sei
        res = self.get_preliminary_result_display()
        return f"Revisão {sei} por {self.reviewer or 'não atribuído'} ({res})"


class ReviewItemDecision(models.Model):
    """Decisão do revisor sobre um item específico da análise documental original."""

    review = models.ForeignKey(
        Review,
        on_delete=models.CASCADE,
        related_name="item_decisions",
        verbose_name="Revisão Pai",
    )
    check_result = models.ForeignKey(
        "evaluations.CheckResult",
        on_delete=models.PROTECT,
        related_name="review_decisions",
        verbose_name="Item da Análise Avaliado",
    )
    agrees_with_analyst = models.BooleanField(
        default=True,
        verbose_name="Concorda com o Parecer do Analista?",
    )
    reviewer_status = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="Status Atribuído pelo Revisor (em divergência)",
        help_text="Preenchido somente caso divirja do analista original.",
    )
    justification = models.TextField(
        blank=True,
        verbose_name="Justificativa da Divergência",
        help_text="Obrigatório em caso de discordância do parecer original.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Decisão de Item de Revisão"
        verbose_name_plural = "Decisões de Itens de Revisão"
        constraints = [
            models.UniqueConstraint(
                fields=["review", "check_result"],
                name="unique_review_check_result_decision",
            ),
        ]

    def __str__(self):
        status_txt = "Concorda" if self.agrees_with_analyst else f"Diverge ({self.reviewer_status})"
        return f"{self.check_result.definition.code} - {status_txt}"

    def clean(self):
        if (
            self.review_id
            and self.check_result_id
            and self.check_result.evaluation_id != self.review.evaluation_id
        ):
            raise ValidationError("CheckResult não pertence à Evaluation do Review.")

    def save(self, *args, **kwargs):
        self.clean()
        return super().save(*args, **kwargs)


class Diligence(models.Model):
    """Representa uma diligência / pedido de esclarecimento no fluxo processual."""

    class Status(models.TextChoices):
        LEGACY_UNKNOWN = "LEGACY_UNKNOWN", "Histórico: estado operacional desconhecido"
        OPEN = "OPEN", "Aberta / Aguardando Resposta"
        ANSWERED = "ANSWERED", "Respondida"
        CONCLUDED = "CONCLUDED", "Concluída"
        CANCELLED = "CANCELLED", "Cancelada"

    class Result(models.TextChoices):
        LEGACY_UNKNOWN = "LEGACY_UNKNOWN", "Histórico: resultado operacional desconhecido"
        PENDENTE = "PENDENTE", "Pendente de Julgamento"
        SANEADA = "SANEADA", "Falha Saneada / Acolhida"
        NAO_SANEADA = "NAO_SANEADA", "Não Saneada / Mantida Inaptidão"

    submission = models.ForeignKey(
        "submissions.Submission",
        on_delete=models.CASCADE,
        related_name="diligences",
        verbose_name="Inscrição Objeto de Diligência",
    )
    related_check_results = models.ManyToManyField(
        "evaluations.CheckResult",
        blank=True,
        related_name="diligences",
        verbose_name="Itens da análise relacionados",
    )
    requested_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="requested_diligences",
        verbose_name="Solicitado por",
        null=True,
        blank=True,
    )
    requested_at = models.DateTimeField(null=True, blank=True, verbose_name="Data da Solicitação")
    origin_status = models.CharField(max_length=30, blank=True)
    unsatisfied_return_status = models.CharField(max_length=30, blank=True)
    reason = models.TextField(
        verbose_name="Motivo e Fundamentação da Diligência",
        help_text="Detalhes dos itens ou inconsistências a serem esclarecidos.",
    )
    deadline = models.DateField(null=True, blank=True, verbose_name="Prazo Limite para Resposta")
    answered_at = models.DateTimeField(null=True, blank=True, verbose_name="Data da Resposta")
    response = models.TextField(blank=True, verbose_name="Teor da Resposta Apresentada")
    result = models.CharField(
        max_length=20,
        choices=Result.choices,
        default=Result.PENDENTE,
        verbose_name="Resultado da Diligência",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.OPEN,
        verbose_name="Status da Diligência",
    )
    concluded_at = models.DateTimeField(null=True, blank=True, verbose_name="Data de Conclusão")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Diligência"
        verbose_name_plural = "Diligências"
        ordering = ["-requested_at"]

    def __str__(self):
        return f"Diligência {self.submission.processo_sei} ({self.get_status_display()})"
