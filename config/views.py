from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import redirect


def health_check(request):
    """Health check endpoint para monitoramento de infraestrutura / containers."""
    db_ok = False
    try:
        with connection.cursor() as cursor:
            cursor.execute("SELECT 1")
            db_ok = bool(cursor.fetchone())
    except Exception as exc:  # noqa: BLE001
        return JsonResponse({"status": "error", "database": str(exc)}, status=503)

    return JsonResponse({"status": "ok", "database": "connected" if db_ok else "unreachable"})


@login_required
def dashboard(request):
    if request.user.is_superuser or request.user.role in {
        "ADMINISTRADOR",
        "COORDENADOR",
        "CONSULTA",
        "REVISOR",
    }:
        from apps.reporting.views import operational_home_view

        return operational_home_view(request)
    if request.user.role == "ANALISTA":
        return redirect("my-evaluations")
    return redirect("submission-list")
