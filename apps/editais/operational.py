"""Single edital boundary for the operational UI; generic configuration stays intact."""

from functools import wraps

from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render

from apps.editais.models import Edital


class OperationalEditalError(Exception):
    pass


def get_operational_edital():
    # Read at most two rows: cardinality is checked, never silently pick the first.
    active = list(Edital.objects.filter(status=Edital.Status.ACTIVE)[:2])
    if not active:
        raise OperationalEditalError(
            "Nenhum edital ativo. A coordenação precisa ativar o edital operacional."
        )
    if len(active) > 1:
        raise OperationalEditalError(
            "Mais de um edital ativo. A coordenação precisa manter apenas um edital operacional ativo."
        )
    return active[0]


def operational_edital_required(view):
    @wraps(view)
    def wrapped(request, *args, **kwargs):
        try:
            request.operational_edital = get_operational_edital()
        except OperationalEditalError as exc:
            can_manage = request.user.is_superuser or request.user.role in {
                "ADMINISTRADOR",
                "COORDENADOR",
            }
            return render(
                request,
                "editais/operational_error.html",
                {
                    "operational_error": str(exc)
                    if can_manage
                    else "Operação indisponível. Entre em contato com a coordenação.",
                },
                status=503,
            )
        return view(request, *args, **kwargs)

    return wrapped


def retired_configuration(request, **kwargs):
    if not request.user.is_authenticated:
        return redirect("login")
    if request.user.is_superuser or request.user.role in {"ADMINISTRADOR", "COORDENADOR"}:
        return redirect("administration-index")
    raise PermissionDenied("Configuração indisponível na operação.")


def disabled_diligence(request, **kwargs):
    raise Http404
