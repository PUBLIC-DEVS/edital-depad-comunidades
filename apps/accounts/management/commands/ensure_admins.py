"""Garante a existência dos administradores institucionais do sistema.

Cria (ou promove) as contas indicadas com o papel ADMINISTRADOR e acesso de
superusuário técnico. É idempotente: pode ser executado quantas vezes for preciso.

As contas usam senha inutilizável — o acesso ocorre via login Microsoft (Entra ID),
e o adaptador de autenticação vincula o OID a estas contas no primeiro acesso,
preservando o papel atribuído aqui.

Uso:
    python manage.py ensure_admins
    python manage.py ensure_admins --email outra.pessoa@mds.gov.br
"""

from django.core.management.base import BaseCommand
from django.db import transaction

from apps.accounts.models import User

# Administradores institucionais padrão do sistema.
DEFAULT_ADMIN_EMAILS = (
    "daniel.brasileiro@mds.gov.br",
    "joao.hall@mds.gov.br",
)


class Command(BaseCommand):
    help = "Garante que os administradores institucionais existam como ADMINISTRADOR + superusuário."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            action="append",
            dest="emails",
            help="E-mail adicional a garantir como administrador (pode repetir).",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        emails = list(DEFAULT_ADMIN_EMAILS) + list(options.get("emails") or [])
        # Normaliza e remove duplicados preservando a ordem.
        seen = set()
        emails = [
            e.strip().lower()
            for e in emails
            if e.strip() and e.strip().lower() not in seen and not seen.add(e.strip().lower())
        ]

        for email in emails:
            username = email.split("@")[0]
            user = User.objects.filter(email__iexact=email).first()
            if user is None:
                user = User(
                    username=username,
                    email=email,
                    role=User.Role.ADMINISTRADOR,
                    is_staff=True,
                    is_superuser=True,
                    is_active=True,
                )
                user.set_unusable_password()
                user.save()
                self.stdout.write(self.style.SUCCESS(f"Criado administrador: {email}"))
                continue

            changed = []
            if user.role != User.Role.ADMINISTRADOR:
                user.role = User.Role.ADMINISTRADOR
                changed.append("role")
            if not user.is_staff:
                user.is_staff = True
                changed.append("is_staff")
            if not user.is_superuser:
                user.is_superuser = True
                changed.append("is_superuser")
            if not user.is_active:
                user.is_active = True
                changed.append("is_active")
            if changed:
                user.save(update_fields=changed)
                self.stdout.write(
                    self.style.SUCCESS(f"Promovido {email}: {', '.join(changed)}")
                )
            else:
                self.stdout.write(f"Já administrador, sem alterações: {email}")
