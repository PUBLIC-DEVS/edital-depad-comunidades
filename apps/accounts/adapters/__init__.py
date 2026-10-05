from django.conf import settings

from .base import AuthenticationAdapter
from .local import LocalAuthAdapter
from .microsoft import MicrosoftAuthAdapter


def get_auth_adapter() -> AuthenticationAdapter:
    """Retorna a instância do adaptador de autenticação configurado."""
    adapter_name = getattr(settings, "AUTH_ADAPTER", "local").lower()
    if adapter_name == "microsoft":
        return MicrosoftAuthAdapter()
    return LocalAuthAdapter()


__all__ = ["AuthenticationAdapter", "LocalAuthAdapter", "MicrosoftAuthAdapter", "get_auth_adapter"]
