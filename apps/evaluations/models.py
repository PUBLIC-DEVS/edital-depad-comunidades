from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models


class Evaluation(models.Model):
    """Representa a análise documental formal realizada pelo analista designado."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Rascunho em Andamento"
        COMPLETED = "COMPLETED", "Concluída"

    class Result(models.TextChoices):
        EM_ANALISE = "EM_ANALISE", "Em Análise"
        APTA = "APTA", "Apta"
        INAPTA = "INAPTA", "Inapta"

    submission = models.OneToOneField(
        "submissions.Submission",
        on_delete=models.CASCADE,
        related_name="evaluation",
        verbose_name="Inscrição Avaliada",
    )
    analyst = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="evaluations",
        verbose_name="Analista Avaliador",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
        verbose_name="Status da Análise",
    )
    result = models.CharField(
        max_length=20,
        choices=Result.choices,
        default=Result.EM_ANALISE,
        verbose_name="Resultado Calculado",
    )
    failed_requirement_codes = models.JSONField(
        default=list,
        blank=True,
        verbose_name="Códigos dos Requisitos com Falha",
        help_text="Lista explícita dos requisitos obrigatórios não atendidos ou não enviados.",
    )
    general_notes = models.TextField(
        blank=True,
        verbose_name="Observações Gerais da Análise",
    )
    configuration_snapshot = models.ForeignKey(
        "editais.EditalConfigurationSnapshot",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="evaluations",
    )
    started_at = models.DateTimeField(null=True, blank=True, verbose_name="Início da Análise")
    completed_at = models.DateTimeField(null=True, blank=True, verbose_name="Conclusão da Análise")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Análise Documental"
        verbose_name_plural = "Análises Documentais"
        ordering = ["-updated_at"]

    def __str__(self):
        sei = self.submission.processo_sei
        return f"Análise {sei} por {self.analyst.username} ({self.get_result_display()})"


class CheckResult(models.Model):
    """Resultado individual de verificação para uma checagem/subcritério."""

    class Status(models.TextChoices):
        ATENDE = "ATENDE", "Atende"
        NAO_ATENDE = "NAO_ATENDE", "Não Atende"
        NAO_ENVIADO = "NAO_ENVIADO", "Não Enviado"
        NAO_APLICAVEL = "NAO_APLICAVEL", "Não Aplicável"
        EM_BRANCO = "EM_BRANCO", "Não Avaliado"

    evaluation = models.ForeignKey(
        Evaluation,
        on_delete=models.CASCADE,
        related_name="check_results",
        verbose_name="Análise Pai",
    )
    requirement_check = models.ForeignKey(
        "editais.RequirementCheck",
        on_delete=models.PROTECT,
        related_name="results",
        verbose_name="Checagem / Subcritério",
        null=True,
        blank=True,
    )
    requirement = models.ForeignKey(
        "editais.Requirement",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="direct_and_check_results",
    )
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.EM_BRANCO,
        verbose_name="Status da Checagem",
    )
    legacy_raw_value = models.JSONField(null=True, blank=True)
    sei_number = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Número do Documento SEI",
    )
    pages = models.CharField(
        max_length=100,
        blank=True,
        verbose_name="Páginas / Folhas",
    )
    document_cnpj = models.CharField(
        max_length=20,
        blank=True,
        verbose_name="CNPJ Constante no Documento",
    )
    valid_until = models.DateField(
        null=True,
        blank=True,
        verbose_name="Data de Validade da Certidão / Documento",
    )
    numeric_value = models.DecimalField(
        max_digits=14,
        decimal_places=2,
        null=True,
        blank=True,
        verbose_name="Valor Numérico / Patrimônio",
    )
    notes = models.TextField(
        blank=True,
        verbose_name="Anotações e Justificativas",
    )
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Resultado de Checagem"
        verbose_name_plural = "Resultados de Checagem"
        constraints = [
            models.UniqueConstraint(
                fields=["evaluation", "requirement_check"],
                name="unique_evaluation_check_result",
            ),
            models.CheckConstraint(
                condition=models.Q(requirement__isnull=False), name="check_result_has_requirement"
            ),
            models.UniqueConstraint(
                fields=["evaluation", "requirement"],
                condition=models.Q(requirement_check__isnull=True),
                name="unique_evaluation_direct_requirement",
            ),
        ]

    def __str__(self):
        return f"{self.definition.code}: {self.get_status_display()}"

    @property
    def definition(self):
        return self.requirement_check if self.requirement_check_id else self.requirement

    @property
    def input_prefix(self):
        return (
            f"check_{self.requirement_check_id}_"
            if self.requirement_check_id
            else f"requirement_{self.requirement_id}_"
        )

    def clean(self):
        super().clean()
        if self.requirement_check_id:
            parent_id = self.requirement_check.requirement_id
            if self.requirement_id and self.requirement_id != parent_id:
                raise ValidationError("Requisito e subcritério incompatíveis.")
            self.requirement_id = parent_id
        if (
            not self.requirement_id
            or self.requirement.edital_id != self.evaluation.submission.edital_id
        ):
            raise ValidationError("Requisito não pertence ao edital desta avaliação.")

    def save(self, *args, **kwargs):
        if self.requirement_check_id and not self.requirement_id:
            self.requirement_id = self.requirement_check.requirement_id
        return super().save(*args, **kwargs)
