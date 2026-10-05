from django import forms

from .models import (
    ClassificationPolicy,
    Edital,
    FundingRule,
    Program,
    ProgramMunicipality,
    Requirement,
    RequirementCheck,
    RequirementValidationRule,
    TargetGroup,
    allowed_check_statuses,
)


class StyledModelForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            field.widget.attrs.setdefault("class", "form-input")
            if isinstance(field.widget, forms.Textarea):
                field.widget.attrs["rows"] = 3


class EditalForm(StyledModelForm):
    status = forms.ChoiceField(
        choices=[(Edital.Status.DRAFT, "Rascunho"), (Edital.Status.CONFIGURING, "Em configuração")],
        required=False,
        label="Estado da configuração",
    )

    def clean_status(self):
        return self.cleaned_data["status"] or self.instance.status or Edital.Status.DRAFT

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.instance.pk:
            self.initial.setdefault("duplicate_policy", Edital.DuplicatePolicy.WARN_ONLY)
        self.fields["duplicate_policy"].help_text = (
            "Duplicidade gera alerta. A opção inicial mantém todas as candidaturas para análise; "
            "se a coordenação definir prevalência, selecione uma política explícita."
        )
        self.fields["validation_reference_date"].help_text = (
            "Data oficial usada para validar vigência documental e idade mínima do CNPJ. "
            "A publicação será bloqueada se uma regra ativa exigir esta data e ela estiver vazia."
        )

    class Meta:
        model = Edital
        fields = [
            "name",
            "status",
            "number",
            "year",
            "description",
            "opens_at",
            "closes_at",
            "rules_version",
            "minimum_equity_percentage",
            "validation_reference_date",
            "requires_financial_rules",
            "duplicate_policy",
            "duplicate_scope",
            "tie_breaker_policy",
        ]
        widgets = {
            f: forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"})
            for f in ("opens_at", "closes_at")
        }
        widgets["validation_reference_date"] = forms.DateInput(attrs={"type": "date"})

    def clean(self):
        data = super().clean()
        if data.get("opens_at") and data.get("closes_at") and data["opens_at"] >= data["closes_at"]:
            self.add_error("closes_at", "Encerramento deve ser posterior à abertura.")
        return data


class CloneEditalForm(StyledModelForm):
    class Meta(EditalForm.Meta):
        fields = ["name", "number", "year", "opens_at", "closes_at", "rules_version"]


class TargetGroupForm(StyledModelForm):
    vacancy_types = forms.MultipleChoiceField(
        choices=FundingRule.VacancyType.choices,
        required=False,
        widget=forms.CheckboxSelectMultiple,
        label="Tipos de vaga que enquadram neste grupo",
    )

    class Meta:
        model = TargetGroup
        fields = ["code", "name", "description", "order", "active", "vacancy_types", "program"]
        labels = {"program": "Exigir município associado ao programa"}


CONFIG_FIELDS = [
    "allowed_statuses",
    "accepted_statuses",
    "failure_statuses",
    "collect_sei_number",
    "collect_pages",
    "collect_document_cnpj",
    "collect_valid_until",
    "collect_opened_on",
    "collect_cnae",
    "collect_canonical_cnpj_confirmed",
    "collect_numeric_value",
    "collect_notes",
]
STATUS_LABELS = {
    "ATENDE": "Atende",
    "NAO_ATENDE": "Não atende",
    "NAO_ENVIADO": "Não enviado",
    "NAO_APLICAVEL": "Não aplicável",
}


class EvidenceForm(StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, label in (
            ("allowed_statuses", "Valores disponíveis ao analista"),
            ("accepted_statuses", "Valores satisfatórios"),
            ("failure_statuses", "Valores impeditivos"),
        ):
            self.fields[name] = forms.MultipleChoiceField(
                choices=[(v, STATUS_LABELS[v]) for v in allowed_check_statuses()],
                widget=forms.CheckboxSelectMultiple,
                label=label,
                required=(name == "allowed_statuses"),
                initial=getattr(self.instance, name)
                or (
                    {
                        "accepted_statuses": ["ATENDE", "NAO_APLICAVEL"],
                        "failure_statuses": ["NAO_ATENDE", "NAO_ENVIADO"],
                    }.get(name, allowed_check_statuses())
                ),
            )
        for name in CONFIG_FIELDS:
            if name.startswith("collect_"):
                self.fields[name].label = (
                    "Coletar "
                    + {
                        "sei_number": "documento SEI",
                        "pages": "páginas",
                        "document_cnpj": "CNPJ do documento",
                        "valid_until": "validade",
                        "opened_on": "data de abertura",
                        "cnae": "CNAE",
                        "canonical_cnpj_confirmed": "confirmação do CNPJ da candidatura",
                        "numeric_value": "valor numérico",
                        "notes": "observações",
                    }[name.removeprefix("collect_")]
                )


class RequirementForm(EvidenceForm):
    class Meta:
        model = Requirement
        fields = [
            "code",
            "name",
            "description",
            "presentation_section",
            "order",
            "mandatory",
            "requires_checks",
            "failure_behavior",
            "active",
            *CONFIG_FIELDS,
        ]


class RequirementCheckForm(EvidenceForm):
    class Meta:
        model = RequirementCheck
        fields = [
            "requirement",
            "code",
            "name",
            "description",
            "order",
            "required",
            "active",
            "contributes_to_result",
            *CONFIG_FIELDS,
        ]

    def __init__(self, *args, edital, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["requirement"].queryset = edital.requirements.all()


class FundingRuleForm(StyledModelForm):
    class Meta:
        model = FundingRule
        fields = ["vacancy_type", "monthly_value", "duration_months", "valid_from", "valid_until"]
        labels = {
            "vacancy_type": "Tipo de vaga",
            "monthly_value": "Valor mensal por vaga",
            "duration_months": "Duração em meses",
        }
        widgets = {
            name: forms.DateInput(attrs={"type": "date"}) for name in ("valid_from", "valid_until")
        }

    def clean(self):
        data = super().clean()
        if (
            data.get("valid_from")
            and data.get("valid_until")
            and data["valid_from"] > data["valid_until"]
        ):
            self.add_error("valid_until", "Fim da vigência anterior ao início.")
        return data


class ProgramMunicipalityForm(StyledModelForm):
    class Meta:
        model = ProgramMunicipality
        fields = ["program", "municipality", "active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["program"].required = True
        self.fields["program"].queryset = Program.objects.filter(active=True)

    def save(self, commit=True):
        self.instance.program_name = self.cleaned_data["program"].code
        return super().save(commit=commit)


class ProgramForm(StyledModelForm):
    class Meta:
        model = Program
        fields = ["code", "name", "description", "active"]


class ClassificationPolicyForm(StyledModelForm):
    class Meta:
        model = ClassificationPolicy
        fields = ["policy_type", "mixed_group_code"]
        labels = {
            "policy_type": "Política de classificação",
            "mixed_group_code": "Grupo das entidades com vagas femininas e masculinas",
        }

    def __init__(self, *args, edital, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["mixed_group_code"] = forms.ChoiceField(
            choices=[("", "Selecione")]
            + list(
                edital.target_groups.filter(active=True)
                .order_by("order", "code")
                .values_list("code", "name")
            ),
            required=False,
            label=self.fields["mixed_group_code"].label,
        )


class RequirementValidationRuleForm(StyledModelForm):
    years = forms.IntegerField(required=False, min_value=1, label="Idade mínima em anos")
    expected_cnae = forms.CharField(required=False, max_length=30, label="CNAE esperado")
    match_mode = forms.ChoiceField(
        required=False,
        choices=[
            ("UNRESOLVED", "Aguardando decisão da coordenação"),
            ("EXACT", "Correspondência exata"),
            ("CONTAINS", "Presente entre os CNAEs informados"),
        ],
        label="Como comparar o CNAE",
    )

    class Meta:
        model = RequirementValidationRule
        fields = ["requirement_check", "rule_type", "severity", "blocks_completion", "active"]

    def __init__(self, *args, edital, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["requirement_check"].queryset = RequirementCheck.objects.filter(
            requirement__edital=edital, active=True
        ).select_related("requirement")
        self.fields["requirement_check"].label_from_instance = lambda check: (
            f"{check.requirement.code} — {check.name}"
        )
        config = (
            self.instance.config
            if self.instance.pk and isinstance(self.instance.config, dict)
            else {}
        )
        for key in ("years", "expected_cnae", "match_mode"):
            self.initial[key] = config.get(key)
        self.fields["years"].widget.attrs["data-rule-config"] = "CNPJ_MINIMUM_AGE"
        for key in ("expected_cnae", "match_mode"):
            self.fields[key].widget.attrs["data-rule-config"] = "CNAE_REQUIRED"

    def clean(self):
        data = super().clean()
        if not data.get("active"):
            return data
        if data.get("rule_type") == RequirementValidationRule.RuleType.CNPJ_MINIMUM_AGE:
            if not data.get("years"):
                self.add_error("years", "Informe a idade mínima.")
        if data.get("rule_type") == RequirementValidationRule.RuleType.CNAE_REQUIRED:
            if not data.get("expected_cnae"):
                self.add_error("expected_cnae", "Informe o CNAE esperado.")
            if not data.get("match_mode"):
                self.add_error("match_mode", "Escolha como comparar o CNAE.")
        return data

    def _post_clean(self):
        # Model.clean validates the typed JSON configuration; prepare a safe,
        # temporary shape so ordinary field errors remain attached to this form.
        rule_type = self.cleaned_data.get("rule_type")
        if rule_type == RequirementValidationRule.RuleType.CNPJ_MINIMUM_AGE:
            self.instance.config = {
                "years": self.cleaned_data.get("years") or 1,
                "reference_date": "EDITAL_REFERENCE_DATE",
            }
        elif rule_type == RequirementValidationRule.RuleType.CNAE_REQUIRED:
            self.instance.config = {
                "expected_cnae": self.cleaned_data.get("expected_cnae") or "PENDING",
                "match_mode": self.cleaned_data.get("match_mode") or "UNRESOLVED",
            }
        elif rule_type == RequirementValidationRule.RuleType.DATE_NOT_EXPIRED:
            self.instance.config = {"reference_date": "EDITAL_REFERENCE_DATE"}
        else:
            self.instance.config = {}
        super()._post_clean()

    def save(self, commit=True):
        instance = super().save(commit=False)
        rule_type = self.cleaned_data["rule_type"]
        if rule_type == RequirementValidationRule.RuleType.CNPJ_MINIMUM_AGE:
            instance.config = {
                "years": self.cleaned_data["years"],
                "reference_date": "EDITAL_REFERENCE_DATE",
            }
        elif rule_type == RequirementValidationRule.RuleType.CNAE_REQUIRED:
            instance.config = {
                "expected_cnae": self.cleaned_data["expected_cnae"],
                "match_mode": self.cleaned_data["match_mode"],
            }
        elif rule_type == RequirementValidationRule.RuleType.DATE_NOT_EXPIRED:
            instance.config = {"reference_date": "EDITAL_REFERENCE_DATE"}
        else:
            instance.config = {}
        if commit:
            instance.save()
        return instance
