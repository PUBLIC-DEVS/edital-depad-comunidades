"""Views de autenticação Microsoft Entra ID (fluxo Authorization Code via MSAL).

Estas views apenas orquestram o fluxo OAuth2/OIDC: redirecionam o usuário ao
Entra ID, recebem o callback e trocam o `code` por tokens. Os claims decodificados
são entregues ao `MicrosoftAuthAdapter` (apps.accounts.adapters), que é a fronteira
responsável por criar/sincronizar o usuário interno. A autorização (RBAC) continua
sendo responsabilidade estrita da aplicação — ver docs/adr/0004.
"""

import logging

import msal
from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect

from apps.accounts.adapters import get_auth_adapter

logger = logging.getLogger(__name__)

# Backend usado para a sessão. O adapter já resolve/cria o usuário, então o
# login apenas persiste a sessão; usamos o backend padrão do Django.
_SESSION_BACKEND = "django.contrib.auth.backends.ModelBackend"
_FLOW_SESSION_KEY = "ms_auth_flow"


def _build_msal_app() -> msal.ConfidentialClientApplication:
    """Instancia o cliente confidencial MSAL a partir das settings."""
    return msal.ConfidentialClientApplication(
        client_id=settings.MS_CLIENT_ID,
        authority=settings.MS_AUTHORITY,
        client_credential=settings.MS_CLIENT_SECRET,
    )


def _microsoft_enabled() -> bool:
    return (
        getattr(settings, "AUTH_ADAPTER", "local").lower() == "microsoft"
        and bool(settings.MS_CLIENT_ID)
        and bool(settings.MS_AUTHORITY)
    )


def ms_login(request: HttpRequest) -> HttpResponse:
    """Inicia o fluxo de login: monta a URL de autorização e redireciona ao Entra ID."""
    if not _microsoft_enabled():
        messages.error(request, "Login institucional (Microsoft) não está configurado.")
        return redirect("login")

    app = _build_msal_app()
    flow = app.initiate_auth_code_flow(
        scopes=settings.MS_SCOPES,
        redirect_uri=settings.MS_REDIRECT_URI,
    )
    # O flow carrega o state e o code_verifier (PKCE); precisa sobreviver ao redirect.
    request.session[_FLOW_SESSION_KEY] = flow
    return redirect(flow["auth_uri"])


def ms_callback(request: HttpRequest) -> HttpResponse:
    """Recebe o retorno do Entra ID, troca o code por tokens e autentica a sessão."""
    if not _microsoft_enabled():
        messages.error(request, "Login institucional (Microsoft) não está configurado.")
        return redirect("login")

    flow = request.session.pop(_FLOW_SESSION_KEY, None)
    if not flow:
        messages.error(request, "Sessão de login expirada. Tente novamente.")
        return redirect("login")

    app = _build_msal_app()
    try:
        result = app.acquire_token_by_auth_code_flow(flow, request.GET.dict())
    except ValueError:
        # state inválido / resposta adulterada
        logger.warning("Falha na validação do fluxo MSAL (state/parametros).")
        messages.error(request, "Não foi possível validar o login. Tente novamente.")
        return redirect("login")

    if "error" in result:
        logger.warning(
            "Erro do Entra ID no callback: %s — %s",
            result.get("error"),
            result.get("error_description"),
        )
        messages.error(request, "O provedor de identidade recusou o login.")
        return redirect("login")

    claims = result.get("id_token_claims", {})
    adapter = get_auth_adapter()
    user = adapter.authenticate_request(
        request,
        id_token=result.get("id_token"),
        access_token=result.get("access_token"),
        claims=claims,
    )

    if user is None:
        messages.error(request, "Conta sem permissão de acesso ao sistema.")
        return redirect("login")

    login(request, user, backend=_SESSION_BACKEND)
    return redirect(settings.LOGIN_REDIRECT_URL)
