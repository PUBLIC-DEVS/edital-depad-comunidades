"""Formulários de captação e distribuição de processos."""

from django import forms
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.editais.models import Edital, TargetGroup
from apps.institutions.cnpj import cnpj_validator, normalize_cnpj
from apps.institutions.models import Institution
from apps.submissions.models import ParticipationRestriction, Submission
from apps.submissions.services.funding import FundingRuleNotFoundError, FundingService


class SubmissionIntakeForm(forms.ModelForm):
    """Formulário para cadastro e edição de inscrições / processos."""

    institution_cnpj = forms.CharField(
        max_length=20,
        label="CNPJ da candidatura / declarado no Anexo I",
        validators=[cnpj_validator],
        widget=forms.TextInput(attrs={"placeholder": "00.000.000/0000-00", "class": "form-input"}),
    )
    institution_name = forms.CharField(
        max_length=255,
        label="Razão Social da Instituição",
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )

    institution_email = forms.EmailField(
        required=False,
        label="E-mail de contato",
        widget=forms.EmailInput(attrs={"class": "form-input"}),
    )
    institution_phone = forms.CharField(
        required=False,
        max_length=50,
        label="Telefone",
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )
    institution_address = forms.CharField(
        required=False,
        max_length=255,
        label="Endereço",
        widget=forms.TextInput(attrs={"class": "form-input"}),
    )
    institution_postal_code = forms.CharField(
        required=False,
        max_length=9,
        label="CEP",
        widget=forms.TextInput(attrs={"class": "form-input", "placeholder": "00000-000"}),
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
            "target_group_definition",
        ]
        widgets = {
            "received_at": forms.DateTimeInput(
                attrs={"type": "datetime-local", "class": "form-input"}
            ),
            "edital": forms.Select(attrs={"class": "form-select"}),
            "municipality": forms.Select(attrs={"class": "form-select"}),
            "processo_sei": forms.TextInput(attrs={"class": "form-input"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["edital"].queryset = Edital.objects.filter(status=Edital.Status.ACTIVE)
        self.fields["target_group_definition"].label = "Grupo (somente para política manual)"
        self.fields["target_group_definition"].required = False
        edital_id = (
            self.data.get("edital")
            if self.is_bound
            else self.instance.edital_id or self.initial.get("edital")
        )
        self.fields["target_group_definition"].queryset = (
            TargetGroup.objects.filter(edital_id=edital_id, active=True)
            if str(edital_id or "").isdigit()
            else TargetGroup.objects.none()
        )
        if str(edital_id or "").isdigit():
            selected_edital = Edital.objects.filter(pk=edital_id).first()
            if (
                selected_edital
                and getattr(
                    getattr(selected_edital, "classification_policy", None), "policy_type", None
                )
                != "MANUAL_TARGET_POLICY_V1"
            ):
                self.fields["target_group_definition"].disabled = True
                self.fields["target_group_definition"].widget = forms.HiddenInput()
        if self.instance.pk:
            self.fields["edital"].disabled = True
            self.fields["institution_cnpj"].disabled = True
            self.fields["institution_name"].disabled = True
            self.initial.update(
                institution_cnpj=self.instance.institution.cnpj,
                institution_name=self.instance.institution.name,
                institution_email=self.instance.institution.contact_email,
                institution_phone=self.instance.institution.contact_phone,
                institution_address=self.instance.institution.address,
                institution_postal_code=self.instance.institution.postal_code,
            )
            for field in (
                "institution_email",
                "institution_phone",
                "institution_address",
                "institution_postal_code",
            ):
                self.fields[field].disabled = True

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
        if solic > (cleaned_data.get("capacidade_total") or 0):
            self.add_error("capacidade_total", "Capacidade inferior às vagas solicitadas.")
        edital = cleaned_data.get("edital")
        group = cleaned_data.get("target_group_definition")
        if edital:
            policy = getattr(edital, "classification_policy", None)
            if not policy:
                self.add_error("edital", "Edital sem política de classificação.")
            elif policy.policy_type == "MANUAL_TARGET_POLICY_V1" and not group:
                self.add_error("target_group_definition", "Selecione o grupo deste edital.")
            elif (
                policy.policy_type != "MANUAL_TARGET_POLICY_V1"
                and group
                and (not self.instance.pk or group.pk != self.instance.target_group_definition_id)
            ):
                self.add_error(
                    "target_group_definition",
                    "Este edital enquadra automaticamente pelas vagas/programa.",
                )
            try:
                temporary = Submission(
                    edital=edital,
                    vagas_femininas=fem,
                    vagas_masculinas=masc,
                    vagas_maes_nutrizes=mae,
                    received_at=cleaned_data.get("received_at"),
                )
                cleaned_data["calculated_funding"] = FundingService.calculate_submission_values(
                    temporary
                )
            except (FundingRuleNotFoundError, ValidationError) as exc:
                self.add_error("edital", str(exc))
        cnpj = cleaned_data.get("institution_cnpj")
        existing = Institution.objects.filter(cnpj=cnpj).first() if cnpj else None
        if existing:
            mapped = {
                "institution_name": existing.name,
                "institution_email": existing.contact_email,
                "institution_phone": existing.contact_phone,
                "institution_address": existing.address,
                "institution_postal_code": existing.postal_code,
            }
            if any(
                cleaned_data.get(field) and cleaned_data[field] != value
                for field, value in mapped.items()
            ):
                self.add_error(
                    "institution_cnpj",
                    "CNPJ já cadastrado com dados diferentes. Atualize a instituição no cadastro antes de reutilizá-la.",
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
                "contact_email": self.cleaned_data.get("institution_email", ""),
                "contact_phone": self.cleaned_data.get("institution_phone", ""),
                "address": self.cleaned_data.get("institution_address", ""),
                "postal_code": self.cleaned_data.get("institution_postal_code", ""),
            },
        )
        self.instance.institution = institution
        self.instance.valor_global, self.instance.patrimonio_minimo = self.cleaned_data[
            "calculated_funding"
        ]
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
        widget=forms.TextInput(
            attrs={"placeholder": "Motivo da distribuição em lote", "class": "form-input"}
        ),
    )


class ParticipationRestrictionForm(forms.ModelForm):
    cnpj = forms.CharField(
        max_length=20,
        label="CNPJ impedido",
        validators=[cnpj_validator],
        widget=forms.TextInput(attrs={"placeholder": "00.000.000/0000-00"}),
    )

    class Meta:
        model = ParticipationRestriction
        fields = ["edital", "cnpj", "reason", "source", "reference_period", "active"]
        labels = {
            "edital": "Edital",
            "reason": "Motivo do impedimento",
            "source": "Fonte da informação",
            "reference_period": "Período de referência",
            "active": "Restrição ativa",
        }
        help_texts = {
            "reference_period": "Ex.: contrato vigente em 2024 e 2025.",
            "source": "Ex.: cadastro manual, CSV ou integração futura.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["edital"].queryset = Edital.objects.filter(status=Edital.Status.ACTIVE)
        if self.instance.pk:
            self.fields["edital"].disabled = True
            self.fields["cnpj"].disabled = True

    def clean_cnpj(self):
        return normalize_cnpj(self.cleaned_data["cnpj"])


class SubmissionCnpjCorrectionForm(forms.Form):
    confirm = forms.BooleanField(label="Confirmo a correção formal desta candidatura.")
    cnpj = forms.CharField(
        max_length=20,
        label="CNPJ correto declarado no Anexo I",
        validators=[cnpj_validator],
    )
    reason = forms.CharField(
        label="Justificativa da correção",
        min_length=10,
        widget=forms.Textarea(attrs={"rows": 4}),
    )

    def clean_cnpj(self):
        return normalize_cnpj(self.cleaned_data["cnpj"])
