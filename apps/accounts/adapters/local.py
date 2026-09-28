from typing import Any

from django.contrib.auth import authenticate
from django.http import HttpRequest

from apps.accounts.models import User

from .base import AuthenticationAdapter


class LocalAuthAdapter(AuthenticationAdapter):
    """Adaptador de autenticação local usando credenciais internas do Django."""

    def authenticate_request(self, request: HttpRequest, **credentials: Any) -> User | None:
        username = credentials.get("username")
        password = credentials.get("password")
        if not username or not password:
            return None
        return authenticate(request, username=username, password=password)

    def sync_user_profile(self, user: User, external_claims: dict[str, Any]) -> User:
        # No adapter local, o modelo interno é a fonte autoritativa de dados
        return user
