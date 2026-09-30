from django import template

from apps.submissions.selectors import STATUS_LABELS

register = template.Library()


@register.filter
def workflow_label(status):
    return STATUS_LABELS.get(status, "Registro histórico")


@register.filter
def qualification_label(value):
    return {
        "Elegível para Ranking": "Apta",
        "Classificada no Ranking": "Classificada",
        "Inabilitada / Inelegível": "Inapta",
        "Pré-Habilitado": "Apta",
        "Pré-Inabilitado": "Inapta",
    }.get(value, value)
