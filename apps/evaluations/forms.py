from django import forms

from apps.evaluations.drafts import EVIDENCE_FIELDS
from apps.evaluations.models import CheckResult
from apps.institutions.cnpj import cnpj_validator


class CheckResultForm(forms.Form):
    def __init__(self, *args, result, can_edit=True, **kwargs):
        super().__init__(*args, prefix=result.input_prefix, **kwargs)
        self.result = result
        definition = result.definition
        self.fields["status"] = forms.ChoiceField(
            label="Resultado",
            choices=[
                (value, label)
                for value, label in CheckResult.Status.choices
                if value in {*definition.allowed_statuses, "EM_BRANCO"}
            ],
            initial=result.status,
        )
        constructors = {
            "sei_number": lambda: forms.CharField(
                label="Documento SEI", max_length=100, required=False
            ),
            "pages": lambda: forms.CharField(label="Páginas", max_length=100, required=False),
            "document_cnpj": lambda: forms.CharField(
                label="CNPJ do documento",
                max_length=20,
                required=False,
                validators=[cnpj_validator],
            ),
            "valid_until": lambda: forms.DateField(
                label="Validade",
                required=False,
                widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            ),
            "opened_on": lambda: forms.DateField(
                label="Data de abertura do CNPJ",
                required=False,
                widget=forms.DateInput(format="%Y-%m-%d", attrs={"type": "date"}),
            ),
            "cnae": lambda: forms.CharField(label="CNAE informado", max_length=30, required=False),
            "canonical_cnpj_confirmed": lambda: forms.BooleanField(
                label="Confirmo o CNPJ da candidatura declarado no Anexo I",
                required=False,
            ),
            "numeric_value": lambda: forms.DecimalField(
                label="Valor numérico", max_digits=14, decimal_places=2, required=False
            ),
            "notes": lambda: forms.CharField(
                label="Observações", required=False, widget=forms.Textarea(attrs={"rows": 2})
            ),
        }
        for name in definition.evidence_fields:
            self.fields[name] = constructors[name]()
            self.initial[name] = getattr(result, name)
        for field in self.fields.values():
            field.disabled = not can_edit
            field.widget.attrs["class"] = "form-input text-sm"

    def add_prefix(self, field_name):
        return f"{self.prefix}{field_name}"

    def clean(self):
        data = super().clean()
        for field in EVIDENCE_FIELDS:
            if field not in self.fields and self.data.get(self.add_prefix(field)):
                raise forms.ValidationError("Campo de evidência não configurado para este item.")
        return data

    def payload(self):
        return {"check_result_id": self.result.pk, **self.cleaned_data}
