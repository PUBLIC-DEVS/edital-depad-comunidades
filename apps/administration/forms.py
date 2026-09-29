from django import forms
from django.contrib.auth.password_validation import validate_password

from apps.accounts.models import User
from apps.editais.forms import StyledModelForm
from apps.editais.models import Program
from apps.institutions.cnpj import normalize_cnpj
from apps.institutions.models import Institution, Municipality


class InstitutionForm(StyledModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.pk and self.instance.submissions.exists():
            self.fields["cnpj"].disabled = True

    class Meta:
        model = Institution
        fields = [
            "cnpj",
            "name",
            "trade_name",
            "legal_nature",
            "contact_email",
            "contact_phone",
            "address",
            "municipality",
        ]

    def clean_cnpj(self):
        cnpj = normalize_cnpj(self.cleaned_data["cnpj"])
        if Institution.objects.filter(cnpj=cnpj).exclude(pk=self.instance.pk).exists():
            raise forms.ValidationError("Já existe uma instituição com este CNPJ.")
        return cnpj


class MunicipalityForm(StyledModelForm):
    class Meta:
        model = Municipality
        fields = ["ibge_code", "name", "state"]

    def clean_ibge_code(self):
        value = self.cleaned_data["ibge_code"]
        if value and (len(value) != 7 or not value.isdigit()):
            raise forms.ValidationError(
                "Informe um código IBGE de sete dígitos ou deixe em branco."
            )
        return value or None

    def clean_state(self):
        value = self.cleaned_data["state"].upper()
        if value not in {
            "AC",
            "AL",
            "AP",
            "AM",
            "BA",
            "CE",
            "DF",
            "ES",
            "GO",
            "MA",
            "MT",
            "MS",
            "MG",
            "PA",
            "PB",
            "PR",
            "PE",
            "PI",
            "RJ",
            "RN",
            "RS",
            "RO",
            "RR",
            "SC",
            "SP",
            "SE",
            "TO",
        }:
            raise forms.ValidationError("UF inválida.")
        return value


class ProgramForm(StyledModelForm):
    class Meta:
        model = Program
        fields = ["code", "name", "description", "active"]


class UserForm(StyledModelForm):
    new_password = forms.CharField(
        required=False,
        label="Nova senha",
        widget=forms.PasswordInput,
        help_text="Obrigatória ao criar uma conta local. Em edição, deixe vazia para preservar a senha.",
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email", "role", "is_active"]

    def clean_new_password(self):
        value = self.cleaned_data["new_password"]
        if not value and not self.instance.pk:
            raise forms.ValidationError("Informe uma senha para a nova conta local.")
        if value:
            validate_password(value, self.instance)
        return value

    def save(self, commit=True):
        user = super().save(commit=False)
        if self.cleaned_data["new_password"]:
            user.set_password(self.cleaned_data["new_password"])
        if commit:
            user.save()
        return user
