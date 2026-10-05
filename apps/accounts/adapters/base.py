from abc import ABC, abstractmethod
from typing import Any

from django.http import HttpRequest

from apps.accounts.models import User


class AuthenticationAdapter(ABC):
    """Interface abstrata para adaptadores de autenticação institucional."""

    @abstractmethod
    def authenticate_request(self, request: HttpRequest, **credentials: Any) -> User | None:
        """Autentica a requisição e retorna o usuário correspondente ou None."""
        pass

    @abstractmethod
    def sync_user_profile(self, user: User, external_claims: dict[str, Any]) -> User:
        """Sincroniza claims externos (nome, email, UPN, OID) com o modelo de usuário interno."""
        pass
