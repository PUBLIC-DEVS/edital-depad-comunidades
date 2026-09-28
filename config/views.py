from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import JsonResponse
from django.shortcuts import render


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
def dashboard_view(request):
    """View inicial do painel operacional."""
    return render(request, "dashboard.html", {"title": "Painel Operacional"})
