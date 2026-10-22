"""Visualizador de logs (auditoria + acessos) dentro da plataforma.

Restrito a administradores. Oferece:
  - listagem filtrável e paginada do log unificado ([acesso] + [modificação]);
  - atualização em tempo quase real (polling HTMX no endpoint de stream);
  - exportação CSV do conjunto filtrado.
"""

import csv

from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, HttpResponse, StreamingHttpResponse
from django.shortcuts import render
from django.utils import timezone
from django.utils.dateparse import parse_date

from apps.accounts.models import User
from apps.accounts.permissions import require_role
from apps.audit.models import AuditEvent

PAGE_SIZE = 50
EXPORT_LIMIT = 100_000


def _filtered_events(request: HttpRequest):
    """Aplica os filtros da query string ao log e devolve o queryset ordenado."""
    events = AuditEvent.objects.select_related("actor")

    category = request.GET.get("cat", "").strip()
    if category == "acesso":
        events = events.filter(action=AuditEvent.ACCESS_ACTION)
    elif category == "modificacao":
        events = events.exclude(action=AuditEvent.ACCESS_ACTION)

    actor = request.GET.get("actor", "").strip()
    if actor:
        events = events.filter(
            Q(actor__username__icontains=actor) | Q(actor__email__icontains=actor)
        )

    action = request.GET.get("action", "").strip()
    if action:
        events = events.filter(action=action)

    search = request.GET.get("q", "").strip()
    if search:
        events = events.filter(
            Q(entity_type__icontains=search)
            | Q(entity_id__icontains=search)
            | Q(field__icontains=search)
            | Q(new_value__icontains=search)
            | Q(action__icontains=search)
        )

    date_from = parse_date(request.GET.get("from", "") or "")
    if date_from:
        events = events.filter(timestamp__date__gte=date_from)
    date_to = parse_date(request.GET.get("to", "") or "")
    if date_to:
        events = events.filter(timestamp__date__lte=date_to)

    return events.order_by("-timestamp")


def _common_context(request: HttpRequest):
    events = _filtered_events(request)
    page = Paginator(events, PAGE_SIZE).get_page(request.GET.get("page"))
    # Querystring preservando filtros, mas sem 'page' (para links de paginação).
    params = request.GET.copy()
    params.pop("page", None)
    base_querystring = params.urlencode()
    return {
        "page": page,
        "filters": {
            "cat": request.GET.get("cat", ""),
            "actor": request.GET.get("actor", ""),
            "action": request.GET.get("action", ""),
            "q": request.GET.get("q", ""),
            "from": request.GET.get("from", ""),
            "to": request.GET.get("to", ""),
        },
        "base_querystring": base_querystring,
    }


@login_required
@require_role(User.Role.ADMINISTRADOR)
def audit_log_view(request: HttpRequest) -> HttpResponse:
    """Página principal do log, com filtros e auto-refresh."""
    return render(request, "audit/log.html", _common_context(request))


@login_required
@require_role(User.Role.ADMINISTRADOR)
def audit_log_stream_view(request: HttpRequest) -> HttpResponse:
    """Apenas as linhas da tabela — usado pelo polling HTMX para tempo real."""
    return render(request, "audit/partials/log_rows.html", _common_context(request))


class _Echo:
    def write(self, value):
        return value


@login_required
@require_role(User.Role.ADMINISTRADOR)
def audit_export_csv_view(request: HttpRequest) -> StreamingHttpResponse:
    """Exporta o log filtrado em CSV (streaming, delimitado por ponto e vírgula)."""
    events = _filtered_events(request)[:EXPORT_LIMIT].iterator()
    writer = csv.writer(_Echo(), delimiter=";")

    header = [
        "timestamp",
        "categoria",
        "usuario",
        "email",
        "acao",
        "entidade",
        "entidade_id",
        "campo",
        "valor_anterior",
        "valor_novo",
        "metadata",
    ]

    def rows():
        yield writer.writerow(header)
        for e in events:
            yield writer.writerow(
                [
                    timezone.localtime(e.timestamp).strftime("%Y-%m-%d %H:%M:%S"),
                    e.category,
                    e.actor.username if e.actor else "SISTEMA",
                    (e.actor.email or "") if e.actor else "",
                    e.action,
                    e.entity_type,
                    e.entity_id,
                    e.field,
                    e.old_value,
                    e.new_value,
                    e.metadata,
                ]
            )

    stamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
    response = StreamingHttpResponse(rows(), content_type="text/csv; charset=utf-8")
    response["Content-Disposition"] = f'attachment; filename="logs-{stamp}.csv"'
    return response
