from django import forms

from .models import (
    ClassificationPolicy,
    Edital,
    FundingRule,
    Program,
    ProgramMunicipality,
    Requirement,
    RequirementCheck,
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
            "duplicate_policy",
            "duplicate_scope",
            "tie_breaker_policy",
        ]
        widgets = {
            f: forms.DateTimeInput(format="%Y-%m-%dT%H:%M", attrs={"type": "datetime-local"})
            for f in ("opens_at", "closes_at")
        }

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
            "order",
            "mandatory",
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


class ClassificationPolicyForm(StyledModelForm):
    class Meta:
        model = ClassificationPolicy
        fields = ["policy_type"]
        labels = {"policy_type": "Política de classificação"}
