from django.db import models


class Edital(models.Model):
    """Representa um edital público lançado pela DEPED/MDS."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Rascunho"
        PUBLISHED = "PUBLISHED", "Publicado"
        IN_PROGRESS = "IN_PROGRESS", "Em Andamento"
        SUSPENDED = "SUSPENDED", "Suspenso"
        CLOSED = "CLOSED", "Encerrado"
        ARCHIVED = "ARCHIVED", "Arquivado"

    class DuplicatePolicy(models.TextChoices):
        KEEP_EARLIEST_SUBMISSION = (
            "KEEP_EARLIEST_SUBMISSION",
            "Manter a inscrição mais antiga (Histórico)",
        )
        KEEP_LATEST_SUBMISSION = (
            "KEEP_LATEST_SUBMISSION",
            "Manter a inscrição mais recente (Retificadora)",
        )

    name = models.CharField(max_length=255, verbose_name="Nome do Edital")
    number = models.CharField(max_length=50, verbose_name="Número do Edital")
    year = models.PositiveIntegerField(verbose_name="Ano")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.IN_PROGRESS,
        verbose_name="Status Operacional",
    )
    opens_at = models.DateTimeField(verbose_name="Início das Inscrições")
    closes_at = models.DateTimeField(verbose_name="Término das Inscrições")
    rules_version = models.CharField(
        max_length=20,
        default="1.0",
        verbose_name="Versão das Regras",
        help_text="Identificador versionado para preservar integridade de editais anteriores.",
    )
    duplicate_policy = models.CharField(
        max_length=40,
        choices=DuplicatePolicy.choices,
        default=DuplicatePolicy.KEEP_EARLIEST_SUBMISSION,
        verbose_name="Política de Duplicidade",
        help_text="Define qual inscrição prevalece quando há duplicidade da mesma instituição.",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Edital"
        verbose_name_plural = "Editais"
        ordering = ["-year", "number"]
        constraints = [
            models.UniqueConstraint(fields=["number", "year"], name="unique_edital_number_year"),
        ]

    def __str__(self):
        return f"Edital {self.number}/{self.year} - {self.name} (v{self.rules_version})"


class ProgramMunicipality(models.Model):
    """Vincula um município a um programa governamental (ex: PRONASCI) no edital."""

    edital = models.ForeignKey(
        Edital,
        on_delete=models.CASCADE,
        related_name="program_municipalities",
        verbose_name="Edital",
    )
    municipality = models.ForeignKey(
        "institutions.Municipality",
        on_delete=models.CASCADE,
        related_name="edital_programs",
        verbose_name="Município",
    )
    program_name = models.CharField(
        max_length=100,
        default="PRONASCI",
        verbose_name="Programa Governamental",
        db_index=True,
    )
    active = models.BooleanField(default=True, verbose_name="Ativo")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Município de Programa Prioritário"
        verbose_name_plural = "Municípios de Programas Prioritários"
        constraints = [
            models.UniqueConstraint(
                fields=["edital", "municipality", "program_name"],
                name="unique_edital_municipality_program",
            ),
        ]

    def __str__(self):
        mun = f"{self.municipality.name}/{self.municipality.state}"
        return f"{mun} - {self.program_name} ({self.edital.number}/{self.edital.year})"


class FundingRule(models.Model):
    """Regras financeiras parametrizadas por edital e grupo de atendimento."""

    edital = models.ForeignKey(
        Edital,
        on_delete=models.CASCADE,
        related_name="funding_rules",
        verbose_name="Edital",
    )
    target_group = models.CharField(
        max_length=50,
        verbose_name="Grupo de Atendimento",
        help_text="Identificador do grupo (ex: G1, G2, G3 ou GERAL).",
    )
    monthly_value_per_vacancy = models.DecimalField(
        max_digits=12,
        decimal_places=2,
        verbose_name="Valor Mensal por Vaga (R$)",
    )
    duration_months = models.PositiveIntegerField(
        default=12,
        verbose_name="Duração em Meses",
    )
    minimum_equity_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=0.00,
        verbose_name="Percentual Mínimo de Patrimônio Líquido (%)",
        help_text="Percentual exigido sobre o valor global (ex: 10.00 para 10%).",
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Regra de Financiamento"
        verbose_name_plural = "Regras de Financiamento"
        constraints = [
            models.UniqueConstraint(
                fields=["edital", "target_group"],
                name="unique_edital_target_group_funding",
            ),
        ]

    def __str__(self):
        ed = f"{self.edital.number}/{self.edital.year}"
        return f"{ed} - {self.target_group}: R$ {self.monthly_value_per_vacancy}/mês"


class Requirement(models.Model):
    """Representa um requisito ou item documental formal do edital (ex: 4.2-V Estatuto)."""

    edital = models.ForeignKey(
        Edital,
        on_delete=models.CASCADE,
        related_name="requirements",
        verbose_name="Edital",
    )
    code = models.CharField(
        max_length=50,
        verbose_name="Código do Requisito",
        help_text="Código identificador do item (ex: 4.2-I, 4.2-V, 4.2-XVI).",
    )
    name = models.CharField(max_length=255, verbose_name="Título do Requisito")
    description = models.TextField(blank=True, verbose_name="Descrição Detalhada")
    order = models.PositiveIntegerField(default=0, verbose_name="Ordem de Exibição")
    mandatory = models.BooleanField(
        default=True,
        verbose_name="Obrigatório",
        help_text="Se não atendido, enseja a inaptidão da instituição.",
    )
    active = models.BooleanField(default=True, verbose_name="Ativo")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Requisito do Edital"
        verbose_name_plural = "Requisitos do Edital"
        ordering = ["order", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["edital", "code"],
                name="unique_edital_requirement_code",
            ),
        ]

    def __str__(self):
        return f"{self.code} — {self.name}"


class RequirementCheck(models.Model):
    """Subcritério ou checagem atômica de verificação de um requisito."""

    requirement = models.ForeignKey(
        Requirement,
        on_delete=models.CASCADE,
        related_name="checks",
        verbose_name="Requisito Pai",
    )
    code = models.CharField(
        max_length=50,
        verbose_name="Código da Checagem",
        help_text="Código do subitem (ex: 4.2-V-01, 4.2-V-a).",
    )
    name = models.CharField(max_length=255, verbose_name="Descrição da Checagem")
    description = models.TextField(blank=True, verbose_name="Orientações ao Analista")
    order = models.PositiveIntegerField(default=0, verbose_name="Ordem")
    active = models.BooleanField(default=True, verbose_name="Ativo")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Subcritério / Checagem"
        verbose_name_plural = "Subcritérios / Checagens"
        ordering = ["order", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["requirement", "code"],
                name="unique_requirement_check_code",
            ),
        ]

    def __str__(self):
        return f"{self.requirement.code} / {self.code}: {self.name}"
