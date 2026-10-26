"""Garante o provisionamento nominal dos analistas e revisores da equipe DEPAD/MDS.

Cria (ou atualiza de forma idempotente) os 12 analistas e 6 revisores nominais para que
já apareçam imediatamente nas listas de distribuição de processos e fila de revisão.

Preparado para vinculação posterior de e-mails institucionais (@mds.gov.br) para login
via Microsoft Entra ID: basta preencher o campo ``email`` na tabela abaixo ou passar
``--email username=nome.sobrenome@mds.gov.br`` na linha de comando.

Uso:
    python manage.py ensure_team
    python manage.py ensure_team --email cleiton=cleiton.silva@mds.gov.br
"""

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.db.models import Q

from apps.accounts.models import User

TEAM_ANALYSTS: tuple[dict[str, str], ...] = (
    {"username": "cleiton", "first_name": "Cleiton", "last_name": "", "email": ""},
    {"username": "wlairton", "first_name": "Wlairton", "last_name": "", "email": ""},
    {"username": "mathews", "first_name": "Mathews", "last_name": "", "email": ""},
    {"username": "sandra", "first_name": "Sandra", "last_name": "", "email": ""},
    {"username": "elieny", "first_name": "Elieny", "last_name": "", "email": ""},
    {
        "username": "juliana.bezerra",
        "first_name": "Juliana",
        "last_name": "Bezerra",
        "email": "",
    },
    {"username": "juliana.viana", "first_name": "Juliana", "last_name": "Viana", "email": ""},
    {"username": "andre.frazol", "first_name": "Andre", "last_name": "Frazol", "email": ""},
    {"username": "leide", "first_name": "Leide", "last_name": "", "email": ""},
    {"username": "nilson", "first_name": "Nilson", "last_name": "", "email": ""},
    {"username": "katia", "first_name": "Katia", "last_name": "", "email": ""},
    {"username": "gigi", "first_name": "Gigi", "last_name": "", "email": ""},
)

TEAM_REVIEWERS: tuple[dict[str, str], ...] = (
    {"username": "heloise", "first_name": "Heloise", "last_name": "", "email": ""},
    {"username": "viviane", "first_name": "Viviane", "last_name": "", "email": ""},
    {"username": "karol", "first_name": "Karol", "last_name": "", "email": ""},
    {"username": "zenilda", "first_name": "Zenilda", "last_name": "", "email": ""},
    {"username": "flaviane", "first_name": "Flaviane", "last_name": "", "email": ""},
    {"username": "gedalias", "first_name": "Gedalias", "last_name": "", "email": ""},
)


class Command(BaseCommand):
    help = "Garante que os 12 analistas e 6 revisores da equipe existam e estejam ativos."

    def add_arguments(self, parser):
        parser.add_argument(
            "--email",
            action="append",
            dest="email_mappings",
            help=(
                "Associa e-mail institucional a um membro da equipe no formato "
                "username=email@mds.gov.br (pode repetir)."
            ),
        )
        parser.add_argument(
            "--password",
            dest="password",
            default="",
            help="Define senha opcional para acesso local antes da vinculação Microsoft.",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        email_overrides: dict[str, str] = {}
        for item in options.get("email_mappings") or []:
            if "=" not in item:
                raise CommandError(
                    f"Formato inválido '{item}'. Use --email username=email@mds.gov.br"
                )
            uname, addr = item.split("=", 1)
            uname = uname.strip().lower()
            addr = addr.strip().lower()
            if not uname or "@" not in addr:
                raise CommandError(
                    f"Mapeamento inválido '{item}'. Use --email username=email@mds.gov.br"
                )
            email_overrides[uname] = addr

        password = (options.get("password") or "").strip()

        roster = [
            *[(member, User.Role.ANALISTA) for member in TEAM_ANALYSTS],
            *[(member, User.Role.REVISOR) for member in TEAM_REVIEWERS],
        ]

        known_usernames = {member["username"].lower() for member, _ in roster}
        unknown = sorted(set(email_overrides) - known_usernames)
        if unknown:
            raise CommandError(f"Usuário(s) desconhecido(s) na equipe: {', '.join(unknown)}")

        for member, role in roster:
            username = member["username"].strip().lower()
            first_name = member["first_name"].strip()
            last_name = member["last_name"].strip()
            email = email_overrides.get(username, member.get("email", "").strip().lower()) or None

            lookup = Q(username__iexact=username)
            if email:
                lookup |= Q(email__iexact=email) | Q(upn__iexact=email)
            user = User.objects.filter(lookup).first()

            if user is None:
                user = User(
                    username=username,
                    first_name=first_name,
                    last_name=last_name,
                    email=email,
                    upn=email,
                    role=role,
                    is_active=True,
                )
                if password:
                    user.set_password(password)
                else:
                    user.set_unusable_password()
                user.save()
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Criado {user.get_role_display()}: {user.get_full_name()} ({username})"
                    )
                )
                continue

            changed: list[str] = []
            if user.role != role:
                user.role = role
                changed.append("role")
            if user.first_name != first_name:
                user.first_name = first_name
                changed.append("first_name")
            if user.last_name != last_name:
                user.last_name = last_name
                changed.append("last_name")
            if email and user.email != email:
                user.email = email
                changed.append("email")
            if email and user.upn != email:
                user.upn = email
                changed.append("upn")
            if not user.is_active:
                user.is_active = True
                changed.append("is_active")
            if password:
                user.set_password(password)
                changed.append("password")

            if changed:
                user.save(update_fields=changed)
                self.stdout.write(
                    self.style.SUCCESS(f"Atualizado {username} ({role}): {', '.join(changed)}")
                )
            else:
                self.stdout.write(f"Sem alterações: {username} ({role})")
