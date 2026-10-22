"""Middleware de registro de acesso a páginas.

Grava um AuditEvent com action=ACCESS a cada visualização de página por um usuário
autenticado, para compor o log unificado ([acesso] + [modificação]) do sistema.

Projetado para ser inofensivo: qualquer falha ao gravar o log é engolida e nunca
derruba a requisição do usuário.
"""

import logging

logger = logging.getLogger(__name__)

# Prefixos de caminho que não geram log de acesso (ruído ou recursão).
_IGNORED_PREFIXES = (
    "/static/",
    "/media/",
    "/health",
    "/favicon",
    "/logs/stream",  # auto-refresh do próprio visualizador de logs
)


def _should_log(request, response) -> bool:
    user = getattr(request, "user", None)
    if user is None or not user.is_authenticated:
        return False
    if request.method != "GET":
        return False
    if response.status_code != 200:
        return False
    if "text/html" not in response.get("Content-Type", ""):
        return False
    path = request.path
    return not path.startswith(_IGNORED_PREFIXES)


class AccessLogMiddleware:
    """Registra o acesso de usuários autenticados às páginas HTML."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.get_response(request)
        try:
            if _should_log(request, response):
                self._record(request, response)
        except Exception:  # noqa: BLE001 - log de acesso nunca pode quebrar a página
            logger.debug("Falha ao registrar log de acesso.", exc_info=True)
        return response

    @staticmethod
    def _record(request, response):
        from apps.audit.models import AuditEvent

        match = getattr(request, "resolver_match", None)
        view_name = match.view_name if match else ""
        AuditEvent.objects.create(
            actor=request.user,
            entity_type="Página",
            entity_id=request.path[:100],
            action=AuditEvent.ACCESS_ACTION,
            metadata={
                "method": request.method,
                "status": response.status_code,
                "view": view_name,
                "query": request.META.get("QUERY_STRING", "")[:200],
            },
        )
