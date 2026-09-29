from decimal import Decimal

from django.conf import settings
from django.core.exceptions import PermissionDenied, ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models, transaction

from apps.audit.immutability import AppendOnlyQuerySet

from .configuration import MUTABLE_STATUSES, ConfigurationModel, EditalQuerySet


def allowed_check_statuses():
    return ["ATENDE", "NAO_ATENDE", "NAO_ENVIADO", "NAO_APLICAVEL"]


class EvidenceConfiguration(models.Model):
    allowed_statuses = models.JSONField(default=allowed_check_statuses)
    accepted_statuses = models.JSONField(default=list, blank=True)
    failure_statuses = models.JSONField(default=list, blank=True)
    collect_sei_number = models.BooleanField(default=True)
    collect_pages = models.BooleanField(default=True)
    collect_document_cnpj = models.BooleanField(default=False)
    collect_valid_until = models.BooleanField(default=False)
    collect_opened_on = models.BooleanField(default=False)
    collect_cnae = models.BooleanField(default=False)
    collect_canonical_cnpj_confirmed = models.BooleanField(default=False)
    collect_numeric_value = models.BooleanField(default=False)
    collect_notes = models.BooleanField(default=True)

    class Meta:
        abstract = True

    def clean(self):
        super().clean()
        allowed = set(allowed_check_statuses())
        for field in ("allowed_statuses", "accepted_statuses", "failure_statuses"):
            values = getattr(self, field)
            if not isinstance(values, list) or any(v not in allowed for v in values):
                raise ValidationError({field: "Valores de resultado inválidos."})
        if not self.allowed_statuses:
            raise ValidationError({"allowed_statuses": "Selecione ao menos um resultado."})
        if not set(self.accepted_statuses + self.failure_statuses) <= set(self.allowed_statuses):
            raise ValidationError(
                "Resultados satisfatórios/impeditivos devem estar entre os permitidos."
            )
        if set(self.accepted_statuses) & set(self.failure_statuses):
            raise ValidationError(
                "Um status não pode ser satisfatório e impeditivo simultaneamente."
            )

    @property
    def evidence_fields(self):
        return [
            f
            for f in (
                "sei_number",
                "pages",
                "document_cnpj",
                "valid_until",
                "opened_on",
                "cnae",
                "canonical_cnpj_confirmed",
                "numeric_value",
                "notes",
            )
            if getattr(self, f"collect_{f}")
        ]


class Edital(models.Model):
    objects = EditalQuerySet.as_manager()
    """Representa um edital público lançado pela DEPED/MDS."""

    class Status(models.TextChoices):
        DRAFT = "DRAFT", "Rascunho"
        CONFIGURING = "CONFIGURING", "Em configuração"
        ACTIVE = "ACTIVE", "Ativo"
        CLOSED = "CLOSED", "Encerrado"
        ARCHIVED = "ARCHIVED", "Arquivado"

    class DuplicatePolicy(models.TextChoices):
        WARN_ONLY = ("WARN_ONLY", "Alertar e manter candidaturas para análise")
        KEEP_EARLIEST_SUBMISSION = (
            "KEEP_EARLIEST_SUBMISSION",
            "Manter a inscrição mais antiga (Histórico)",
        )
        KEEP_LATEST_SUBMISSION = (
            "KEEP_LATEST_SUBMISSION",
            "Manter a inscrição mais recente (Retificadora)",
        )

    name = models.CharField(max_length=255, verbose_name="Nome do Edital")
    description = models.TextField(blank=True, verbose_name="Descrição")
    published_at = models.DateTimeField(null=True, blank=True)
    published_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="published_editais",
    )
    cloned_from = models.ForeignKey(
        "self", null=True, blank=True, on_delete=models.PROTECT, related_name="clones"
    )
    number = models.CharField(max_length=50, verbose_name="Número do Edital")
    year = models.PositiveIntegerField(verbose_name="Ano")
    status = models.CharField(
        max_length=20,
        choices=Status.choices,
        default=Status.DRAFT,
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
    duplicate_scope = models.CharField(
        max_length=20,
        choices=[
            ("ABSOLUTE", "Primeira inscrição absoluta"),
            ("ELIGIBLE", "Primeira inscrição elegível"),
        ],
        default="ABSOLUTE",
    )
    minimum_equity_percentage = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        default=Decimal("10.00"),
        validators=[MinValueValidator(0), MaxValueValidator(100)],
    )
    validation_reference_date = models.DateField(
        null=True,
        blank=True,
        verbose_name="Data de referência das validações",
        help_text="Data oficial usada para validade documental e idade mínima do CNPJ.",
    )
    requires_financial_rules = models.BooleanField(
        default=True,
        verbose_name="Este edital exige cálculo financeiro por vaga",
    )
    tie_breaker_policy = models.CharField(
        max_length=30,
        choices=[
            ("UNRESOLVED", "Política de empate não definida"),
            ("SEI_LEXICOGRAPHIC", "Processo SEI em ordem lexicográfica"),
        ],
        default="UNRESOLVED",
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

    @property
    def configuration_editable(self):
        return self.status in MUTABLE_STATUSES

    @transaction.atomic
    def save(self, *args, **kwargs):
        if self.pk:
            old = type(self).objects.select_for_update().get(pk=self.pk)
            protected = (
                "name",
                "number",
                "year",
                "description",
                "opens_at",
                "closes_at",
                "rules_version",
                "duplicate_scope",
                "duplicate_policy",
                "tie_breaker_policy",
                "minimum_equity_percentage",
                "validation_reference_date",
                "requires_financial_rules",
            )
            if not old.configuration_editable and any(
                getattr(old, f) != getattr(self, f) for f in protected
            ):
                raise ValidationError(
                    "Edite uma cópia versionada; as regras publicadas são protegidas."
                )
            if not old.configuration_editable and self.status in MUTABLE_STATUSES:
                raise ValidationError("Edital publicado não pode voltar a rascunho.")
        if self.status == self.Status.ACTIVE and (not self.pk or old.status != self.Status.ACTIVE):
            if (
                not self.pk
                or not self.configuration_snapshots.filter(
                    rules_version=self.rules_version
                ).exists()
            ):
                raise ValidationError("Use a operação Publicar para ativar o edital.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        if not type(self).objects.get(pk=self.pk).configuration_editable:
            raise ValidationError("Edital publicado deve ser arquivado.")
        return super().delete(*args, **kwargs)


class ProgramMunicipality(ConfigurationModel):
    """Vincula município canônico a um programa configurável no edital."""

    edital = models.ForeignKey(
        Edital,
        on_delete=models.CASCADE,
        related_name="program_municipalities",
        verbose_name="Edital",
    )
    municipality = models.ForeignKey(
        "institutions.Municipality",
        on_delete=models.PROTECT,
        related_name="edital_programs",
        verbose_name="Município",
    )
    program = models.ForeignKey(
        "Program",
        null=True,
        blank=True,
        on_delete=models.PROTECT,
        related_name="municipality_links",
    )
    program_name = models.CharField(
        max_length=100,
        default="",
        verbose_name="Programa Governamental",
        db_index=True,
    )
    active = models.BooleanField(default=True, verbose_name="Ativo")
    legacy_original_name = models.CharField(max_length=150, blank=True)
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


class LegacyGroupFundingRule(models.Model):
    """Regras financeiras parametrizadas por edital e grupo de atendimento."""

    edital = models.ForeignKey(
        Edital,
        on_delete=models.CASCADE,
        related_name="legacy_group_funding_rules",
        verbose_name="Edital",
    )
    target_group = models.CharField(
        max_length=50,
        verbose_name="Grupo de Atendimento",
        help_text="Código do público atendido na configuração histórica arquivada.",
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


class FundingRule(ConfigurationModel):
    """Financial rule by vacancy type. Old group rules remain in an archive table."""

    class VacancyType(models.TextChoices):
        FEMALE = "FEMALE", "Feminina"
        MALE = "MALE", "Masculina"
        NURSING_MOTHER = "NURSING_MOTHER", "Mãe nutriz"

    edital = models.ForeignKey(Edital, on_delete=models.CASCADE, related_name="funding_rules")
    vacancy_type = models.CharField(max_length=20, choices=VacancyType.choices)
    monthly_value = models.DecimalField(
        max_digits=12, decimal_places=2, validators=[MinValueValidator(0)]
    )
    duration_months = models.PositiveIntegerField(default=12, validators=[MinValueValidator(1)])
    valid_from = models.DateField(null=True, blank=True, verbose_name="Início da vigência")
    valid_until = models.DateField(null=True, blank=True, verbose_name="Fim da vigência")

    def clean(self):
        super().clean()
        if self.valid_from and self.valid_until and self.valid_from > self.valid_until:
            raise ValidationError("Vigência financeira inválida.")

    class Meta:
        db_table = "editais_vacancy_funding_rule"
        constraints = [
            models.UniqueConstraint(
                fields=["edital", "vacancy_type"], name="unique_funding_vacancy_type"
            )
        ]


class Requirement(ConfigurationModel, EvidenceConfiguration):
    """Representa um requisito ou item documental formal do edital."""

    edital = models.ForeignKey(
        Edital,
        on_delete=models.CASCADE,
        related_name="requirements",
        verbose_name="Edital",
    )
    code = models.CharField(
        max_length=50,
        verbose_name="Código do Requisito",
        help_text="Código do item (ex: CADASTRO, REGULARIDADE).",
    )
    name = models.CharField(max_length=255, verbose_name="Título do Requisito")
    description = models.TextField(blank=True, verbose_name="Descrição Detalhada")
    presentation_section = models.CharField(
        max_length=100, blank=True, verbose_name="Seção visual no espaço do analista"
    )
    requires_checks = models.BooleanField(
        default=False,
        verbose_name="Exige subcritérios configurados",
        help_text="Use quando este requisito precisa de um ou mais checks para publicação.",
    )
    order = models.PositiveIntegerField(default=0, verbose_name="Ordem de Exibição")
    mandatory = models.BooleanField(
        default=True,
        verbose_name="Obrigatório",
        help_text="Se não atendido, enseja a inaptidão da instituição.",
    )
    failure_behavior = models.CharField(
        max_length=20,
        default="SEND_TO_REVIEW",
        choices=[
            ("NONE", "Somente informativo"),
            ("MARK_INELIGIBLE", "Marcar inabilitado"),
            ("SEND_TO_REVIEW", "Encaminhar à revisão"),
        ],
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


class RequirementCheck(ConfigurationModel, EvidenceConfiguration):
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
        help_text="Código do subcritério (ex: IDENTIDADE, LICENCA).",
    )
    name = models.CharField(max_length=255, verbose_name="Descrição da Checagem")
    description = models.TextField(blank=True, verbose_name="Orientações ao Analista")
    order = models.PositiveIntegerField(default=0, verbose_name="Ordem")
    active = models.BooleanField(default=True, verbose_name="Ativo")
    required = models.BooleanField(default=True, verbose_name="Obrigatório")
    contributes_to_result = models.BooleanField(default=True)
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

    configuration_edital_path = "requirement__edital__"

    @property
    def configuration_edital(self):
        return self.requirement.edital


class RequirementValidationRule(ConfigurationModel):
    """Small, typed automatic validation attached to a configured check."""

    class RuleType(models.TextChoices):
        CNPJ_MATCH_CANONICAL = "CNPJ_MATCH_CANONICAL", "CNPJ igual ao da candidatura"
        DATE_NOT_EXPIRED = "DATE_NOT_EXPIRED", "Documento vigente na data de referência"
        CNPJ_MINIMUM_AGE = "CNPJ_MINIMUM_AGE", "Idade mínima de atividade do CNPJ"
        CNAE_REQUIRED = "CNAE_REQUIRED", "CNAE exigido"

    class Severity(models.TextChoices):
        CRITICAL = "CRITICAL", "Crítica"
        WARNING = "WARNING", "Aviso"

    requirement_check = models.ForeignKey(
        RequirementCheck, on_delete=models.CASCADE, related_name="validation_rules"
    )
    rule_type = models.CharField(max_length=40, choices=RuleType.choices)
    severity = models.CharField(max_length=12, choices=Severity.choices, default=Severity.CRITICAL)
    blocks_completion = models.BooleanField(default=True)
    config = models.JSONField(default=dict, blank=True)
    active = models.BooleanField(default=True)

    configuration_edital_path = "requirement_check__requirement__edital__"

    @property
    def configuration_edital(self):
        return self.requirement_check.requirement.edital

    def clean(self):
        super().clean()
        if not self.active:
            return
        from .validation_dependencies import missing_evidence_messages

        missing = missing_evidence_messages(self)
        if missing:
            raise ValidationError({"requirement_check": missing})
        config = self.config if isinstance(self.config, dict) else {}
        if self.rule_type == self.RuleType.CNPJ_MINIMUM_AGE:
            years = config.get("years")
            if not isinstance(years, int) or isinstance(years, bool) or years < 1:
                raise ValidationError({"config": "Informe years como inteiro maior que zero."})
        if self.rule_type == self.RuleType.CNAE_REQUIRED:
            if not config.get("expected_cnae"):
                raise ValidationError({"config": "Informe o CNAE esperado."})
            if config.get("match_mode") not in {"EXACT", "CONTAINS", "UNRESOLVED"}:
                raise ValidationError({"config": "Informe EXACT, CONTAINS ou UNRESOLVED."})
        if self.rule_type in {self.RuleType.DATE_NOT_EXPIRED, self.RuleType.CNPJ_MINIMUM_AGE}:
            if config.get("reference_date") != "EDITAL_REFERENCE_DATE":
                raise ValidationError({"config": "A referência deve ser EDITAL_REFERENCE_DATE."})

    class Meta:
        ordering = ["requirement_check__order", "rule_type"]
        constraints = [
            models.UniqueConstraint(
                fields=["requirement_check", "rule_type"], name="unique_check_validation_rule"
            )
        ]


class Program(models.Model):
    code = models.CharField(max_length=50, unique=True, verbose_name="Código")
    name = models.CharField(max_length=150, verbose_name="Nome")
    description = models.TextField(blank=True)
    active = models.BooleanField(default=True)

    def __str__(self):
        return self.name


class TargetGroup(ConfigurationModel):
    edital = models.ForeignKey(Edital, on_delete=models.CASCADE, related_name="target_groups")
    code = models.CharField(max_length=50, verbose_name="Código")
    name = models.CharField(max_length=150, verbose_name="Nome")
    description = models.TextField(blank=True, verbose_name="Descrição")
    order = models.PositiveIntegerField(default=0, verbose_name="Ordem / prioridade")
    active = models.BooleanField(default=True)
    vacancy_types = models.JSONField(default=list, blank=True)
    program = models.ForeignKey(Program, null=True, blank=True, on_delete=models.PROTECT)

    class Meta:
        ordering = ["order", "code"]
        constraints = [
            models.UniqueConstraint(fields=["edital", "code"], name="unique_edital_group")
        ]

    def clean(self):
        super().clean()
        if self.code == "SEM_GRUPO":
            raise ValidationError({"code": "Código reservado para ausência de enquadramento."})
        if not isinstance(self.vacancy_types, list) or any(
            v not in FundingRule.VacancyType.values for v in self.vacancy_types
        ):
            raise ValidationError({"vacancy_types": "Tipo de vaga inválido."})

    def __str__(self):
        return f"{self.code} — {self.name}"


class ClassificationPolicy(ConfigurationModel):
    edital = models.OneToOneField(
        Edital, on_delete=models.CASCADE, related_name="classification_policy"
    )
    policy_type = models.CharField(
        max_length=40,
        default="VACANCY_TARGET_POLICY_V1",
        choices=[
            ("VACANCY_TARGET_POLICY_V1", "Vagas e programa municipal (v1)"),
            (
                "VACANCY_TARGET_POLICY_V2_MIXED_FIRST",
                "Vagas com prioridade para entidades mistas (v2)",
            ),
            ("MANUAL_TARGET_POLICY_V1", "Grupo informado no cadastro (v1)"),
        ],
    )
    mixed_group_code = models.CharField(
        max_length=50,
        blank=True,
        verbose_name="Grupo para entidades com vagas femininas e masculinas",
    )

    def clean(self):
        super().clean()
        if self.policy_type == "VACANCY_TARGET_POLICY_V2_MIXED_FIRST":
            if (
                not self.mixed_group_code
                or not self.edital.target_groups.filter(
                    code=self.mixed_group_code, active=True
                ).exists()
            ):
                raise ValidationError(
                    {"mixed_group_code": "Selecione um grupo ativo deste edital."}
                )


class EditalConfigurationSnapshot(models.Model):
    objects = AppendOnlyQuerySet.as_manager()
    edital = models.ForeignKey(
        Edital, on_delete=models.PROTECT, related_name="configuration_snapshots"
    )
    rules_version = models.CharField(max_length=20)
    configuration = models.JSONField()
    published_at = models.DateTimeField(auto_now_add=True)
    published_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["edital", "rules_version"], name="unique_published_edital_version"
            )
        ]

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionDenied("Snapshot de configuração é imutável.")
        super().save(*args, **kwargs)

    def delete(self, *args, **kwargs):
        raise PermissionDenied("Snapshot de configuração é imutável.")
