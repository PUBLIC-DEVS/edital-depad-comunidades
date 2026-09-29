from datetime import datetime

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from apps.accounts.models import User
from apps.editais.edital_2026 import configure_edital_2026_base
from apps.editais.models import Edital
from apps.editais.services import EditalConfigurationService


class Command(BaseCommand):
    help = "Cria uma configuração inicial do Edital 2026 sem abrir qualquer planilha."

    def add_arguments(self, parser):
        parser.add_argument(
            "--admin", required=True, help="Username do administrador autor da configuração"
        )
        parser.add_argument("--number", default="2026-BASE")
        parser.add_argument(
            "--opens-at", required=True, help="Data/hora ISO, por exemplo 2026-01-01T09:00:00-03:00"
        )
        parser.add_argument(
            "--closes-at",
            required=True,
            help="Data/hora ISO, por exemplo 2026-12-31T18:00:00-03:00",
        )
        parser.add_argument(
            "--reference-date",
            help="Data oficial de referência ISO; omitida enquanto a decisão estiver aberta",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        actor = User.objects.filter(username=options["admin"], role=User.Role.ADMINISTRADOR).first()
        if actor is None:
            raise CommandError("Informe um usuário existente com papel ADMINISTRADOR.")
        if Edital.objects.filter(number=options["number"], year=2026).exists():
            raise CommandError(
                "Já existe edital com este número em 2026; nenhuma configuração foi alterada."
            )
        try:
            opens_at = datetime.fromisoformat(options["opens_at"])
            closes_at = datetime.fromisoformat(options["closes_at"])
            reference_date = (
                datetime.fromisoformat(options["reference_date"]).date()
                if options["reference_date"]
                else None
            )
        except ValueError as exc:
            raise CommandError(f"Data/hora inválida: {exc}") from exc
        if timezone.is_naive(opens_at) or timezone.is_naive(closes_at):
            raise CommandError("Use data/hora ISO com fuso horário explícito.")
        edital = Edital(
            name="Base funcional do Edital 2026",
            number=options["number"],
            year=2026,
            opens_at=opens_at,
            closes_at=closes_at,
            rules_version="2026.1",
            validation_reference_date=reference_date,
            requires_financial_rules=False,
            duplicate_policy=Edital.DuplicatePolicy.WARN_ONLY,
            duplicate_scope="ABSOLUTE",
            tie_breaker_policy="UNRESOLVED",
        )
        EditalConfigurationService.save(edital, actor)
        configure_edital_2026_base(edital, actor)
        self.stdout.write(
            self.style.SUCCESS(
                f"Base {edital.number}/2026 criada como rascunho. Configure municípios PRONASCI, "
                "data oficial de referência e demais dados pendentes na interface antes de publicar."
            )
        )
