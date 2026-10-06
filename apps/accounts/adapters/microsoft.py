import logging
from typing import Any

from django.db.models import Q
from django.http import HttpRequest

from apps.accounts.models import User

from .base import AuthenticationAdapter

logger = logging.getLogger(__name__)


class MicrosoftAuthAdapter(AuthenticationAdapter):
    """Adaptador de autenticação Microsoft / Entra ID.

    Estrutura preparada para receber os tokens e claims retornados pelo
    módulo de integração institucional (MSAL / OIDC / SharePoint).
    """

    def authenticate_request(self, request: HttpRequest, **credentials: Any) -> User | None:
        token = credentials.get("id_token") or credentials.get("access_token")
        if not token:
            logger.debug("Tentativa de autenticação Microsoft sem token fornecido.")
            return None

        # Ponto de extensão para validação do JWT/OIDC do Microsoft Entra ID
        # Quando o backend do colaborador estiver pronto, os claims decodificados
        # alimentarão a criação ou sincronização do usuário.
        claims = credentials.get("claims", {})
        azure_oid = claims.get("oid")
        upn = claims.get("preferred_username") or claims.get("upn")
        email = claims.get("email") or upn

        if not azure_oid or not email:
            logger.warning("Claims Microsoft incompletos; perfil não sincronizado.")
            return None

        # 1) Conta já vinculada a este OID.
        user = User.objects.filter(azure_oid=azure_oid).first()

        # 2) Conta pré-provisionada pela administração (e-mail/UPN já cadastrado, sem OID):
        #    vincula o OID a ela, preservando o papel atribuído (ex.: ADMINISTRADOR).
        if user is None:
            lookup = Q(email__iexact=email)
            if upn:
                lookup |= Q(upn__iexact=upn)
            user = User.objects.filter(lookup, azure_oid__isnull=True).first()
            if user is not None:
                user.azure_oid = azure_oid
                user.save(update_fields=["azure_oid"])

        # 3) Primeiro acesso de um usuário novo: cria com o menor privilégio.
        if user is None:
            user = User(
                username=upn or email,
                email=email,
                azure_oid=azure_oid,
                first_name=claims.get("given_name", ""),
                last_name=claims.get("family_name", ""),
                upn=upn,
                role=User.Role.CONSULTA,
            )
            user.set_unusable_password()
            user.save()
        else:
            self.sync_user_profile(user, claims)

        # Contas desativadas pela administração não autenticam.
        if not user.is_active:
            logger.warning("Usuário inativo tentou autenticar via Microsoft: %s", email)
            return None

        return user

    def sync_user_profile(self, user: User, external_claims: dict[str, Any]) -> User:
        updated = False
        upn = external_claims.get("preferred_username") or external_claims.get("upn")
        if upn and user.upn != upn:
            user.upn = upn
            updated = True
        given_name = external_claims.get("given_name")
        if given_name and user.first_name != given_name:
            user.first_name = given_name
            updated = True
        family_name = external_claims.get("family_name")
        if family_name and user.last_name != family_name:
            user.last_name = family_name
            updated = True

        if updated:
            user.save(update_fields=["upn", "first_name", "last_name"])
        return user
