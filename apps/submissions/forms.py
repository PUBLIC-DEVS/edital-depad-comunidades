"""Formulários de captação e distribuição de processos."""

from django import forms

from apps.accounts.models import User
from apps.institutions.cnpj import cnpj_validator, normalize_cnpj
from apps.institutions.models import Institution
from apps.submissions.models import Submission


class SubmissionIntakeForm(forms.ModelForm):
    """Formulário para cadastro e edição de inscrições / processos."""

    institution_cnpj = forms.CharField(
        max_length=20,
        label="CNPJ da Instituição",
        validators=[cnpj_validator],
        widget=forms.TextInput(attrs={"placeholder": "00.000.000/0000-00", "class": "form-input"}),
    )
    institution_name = forms.CharField(
        max_length=255,
        label="Razão Social da Instituição",
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )

    class Meta:
        model = Submission
        fields = [
            "edital",
            "processo_sei",
            "received_at",
            "municipality",
            "vagas_femininas",
            "vagas_masculinas",
            "vagas_maes_nutrizes",
            "vagas_solicitadas",
            "capacidade_total",
            "valor_global",
            "patrimonio_minimo",
        ]
        widgets = {
            "received_at": forms.DateTimeInput(attrs={"type": "datetime-local", "class": "form-input"}),
            "edital": forms.Select(attrs={"class": "form-select"}),
            "municipality": forms.Select(attrs={"class": "form-select"}),
            "processo_sei": forms.TextInput(attrs={"class": "form-input"}),
        }

    def clean_institution_cnpj(self):
        return normalize_cnpj(self.cleaned_data["institution_cnpj"])

    def clean(self):
        cleaned_data = super().clean()
        fem = cleaned_data.get("vagas_femininas") or 0
        masc = cleaned_data.get("vagas_masculinas") or 0
        mae = cleaned_data.get("vagas_maes_nutrizes") or 0
        solic = cleaned_data.get("vagas_solicitadas") or 0

        if solic > 0 and (fem + masc + mae) != solic:
            self.add_error(
                "vagas_solicitadas",
                f"O total solicitado ({solic}) difere da soma das vagas individuais ({fem + masc + mae}).",
            )
        return cleaned_data

    def save(self, commit=True):
        cnpj = self.cleaned_data["institution_cnpj"]
        name = self.cleaned_data["institution_name"]
        municipality = self.cleaned_data["municipality"]

        institution, _ = Institution.objects.get_or_create(
            cnpj=cnpj,
            defaults={
                "name": name,
                "municipality": municipality,
            },
        )
        self.instance.institution = institution
        return super().save(commit=commit)


class SingleAssignmentForm(forms.Form):
    """Formulário para atribuição ou redistribuição individual de um processo."""

    analyst = forms.ModelChoiceField(
        queryset=User.objects.filter(role=User.Role.ANALISTA, is_active=True),
        label="Analista Designado",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason = forms.CharField(
        max_length=255,
        required=False,
        label="Motivo da Atribuição / Redistribuição",
        widget=forms.TextInput(attrs={"placeholder": "Opcional", "class": "form-input"}),
    )


class BulkAssignmentForm(forms.Form):
    """Formulário para atribuição em lote de múltiplos processos."""

    selected_ids = forms.CharField(widget=forms.HiddenInput())
    analyst = forms.ModelChoiceField(
        queryset=User.objects.filter(role=User.Role.ANALISTA, is_active=True),
        label="Analista para Atribuição em Lote",
        widget=forms.Select(attrs={"class": "form-select"}),
    )
    reason = forms.CharField(
        max_length=255,
        required=False,
        label="Motivo",
        widget=forms.TextInput(attrs={"placeholder": "Motivo da distribuição em lote", "class": "form-input"}),
    )
