"""Formulários de revisão de conformidade e gestão de diligências."""

from django import forms

from apps.reviews.models import Diligence, Review


class ReviewConcludeForm(forms.ModelForm):
    """Formulário para emissão do parecer conclusivo da revisão."""

    def clean_preliminary_result(self):
        value = self.cleaned_data["preliminary_result"]
        if value == Review.PreliminaryResult.PENDING_DECISION:
            raise forms.ValidationError("Escolha um resultado conclusivo.")
        return value

    class Meta:
        model = Review
        fields = ["preliminary_result", "decision_notes"]
        widgets = {
            "preliminary_result": forms.Select(attrs={"class": "form-select"}),
            "decision_notes": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Fundamentação técnica da conclusão da revisão...",
                    "class": "form-input",
                }
            ),
        }


class DiligenceCreateForm(forms.ModelForm):
    """Formulário para abertura de diligência no processo."""

    deadline = forms.DateField(required=True, widget=forms.DateInput(attrs={"type": "date"}))

    class Meta:
        model = Diligence
        fields = ["reason", "deadline"]
        widgets = {
            "deadline": forms.DateInput(attrs={"type": "date", "class": "form-input"}),
            "reason": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Descreva com clareza o motivo e os documentos a serem apresentados...",
                    "class": "form-input",
                }
            ),
        }


class DiligenceResponseForm(forms.ModelForm):
    """Formulário para registro da resposta e conclusão da diligência."""

    class Meta:
        model = Diligence
        fields = ["response", "result"]
        widgets = {
            "result": forms.Select(attrs={"class": "form-select"}),
            "response": forms.Textarea(
                attrs={
                    "rows": 4,
                    "placeholder": "Teor da resposta, número do documento SEI de juntada...",
                    "class": "form-input",
                }
            ),
        }
