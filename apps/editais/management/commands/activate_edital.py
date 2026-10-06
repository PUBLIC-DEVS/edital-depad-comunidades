"""Configura e publica (ativa) um edital sem depender da UI de configuração.

Faz, numa só operação e de forma idempotente:
  1. define a data oficial de referência;
  2. associa municípios ao programa dos grupos (ex.: PRONASCI no grupo G2);
  3. publica o edital (status ACTIVE), rodando a mesma validação do serviço.

Pré-requisitos para publicar (validados pelo serviço):
  - pelo menos um ANALISTA ativo e um REVISOR ativo cadastrados;
  - municípios cadastrados e associados ao programa;
  - data oficial de referência definida.

Uso típico:
  manage.py activate_edital --admin daniel.brasileiro \
      --reference-date 2026-01-01 --all-municipalities
"""

from datetime import datetime

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import User
from apps.editais.models import Edital, ProgramMunicipality, TargetGroup
from apps.editais.services import EditalConfigurationService
from apps.institutions.models import Municipality


class Command(BaseCommand):
    help = "Define data de referência, associa municípios ao programa e publica (ativa) o edital."

    def add_arguments(self, parser):
        parser.add_argument("--admin", required=True, help="Username de um ADMINISTRADOR")
        parser.add_argument("--number", default="2026-BASE")
        parser.add_argument("--year", type=int, default=2026)
        parser.add_argument(
            "--reference-date", help="Data oficial de referência ISO (ex.: 2026-01-01)"
        )
        parser.add_argument(
            "--all-municipalities",
            action="store_true",
            help="Associa todos os municípios cadastrados ao programa dos grupos",
        )
        parser.add_argument(
            "--ibge",
            action="append",
            default=[],
            help="Código IBGE de um município a associar (pode repetir)",
        )
        parser.add_argument(
            "--no-publish",
            action="store_true",
            help="Apenas configura (data + municípios), sem publicar",
        )

    @transaction.atomic
    def handle(self, *args, **options):
        actor = User.objects.filter(username=options["admin"], role=User.Role.ADMINISTRADOR).first()
        if actor is None:
            raise CommandError("Informe um usuário existente com papel ADMINISTRADOR.")

        try:
            edital = Edital.objects.get(number=options["number"], year=options["year"])
        except Edital.DoesNotExist as exc:
            raise CommandError(
                f"Edital {options['number']}/{options['year']} não encontrado."
            ) from exc

        if not edital.configuration_editable:
            raise CommandError("Edital já publicado ou encerrado; configuração bloqueada.")

        # 1) Data oficial de referência
        if options["reference_date"]:
            try:
                reference = datetime.fromisoformat(options["reference_date"]).date()
            except ValueError as exc:
                raise CommandError(f"Data de referência inválida: {exc}") from exc
            edital.validation_reference_date = reference
            EditalConfigurationService.save(edital, actor)
            self.stdout.write(self.style.SUCCESS(f"Data de referência definida: {reference}"))

        # 2) Municípios -> programa dos grupos
        if options["all_municipalities"] or options["ibge"]:
            if options["ibge"]:
                municipalities = list(Municipality.objects.filter(ibge_code__in=options["ibge"]))
                found = {m.ibge_code for m in municipalities}
                missing = sorted(set(options["ibge"]) - found)
                if missing:
                    raise CommandError(
                        f"Municípios não cadastrados (código IBGE): {', '.join(missing)}"
                    )
            else:
                municipalities = list(Municipality.objects.all())

            if not municipalities:
                raise CommandError(
                    "Nenhum município para associar. Cadastre os municípios antes "
                    "(em /administracao/municipios/)."
                )

            groups = TargetGroup.objects.filter(
                edital=edital, active=True, program__isnull=False
            ).select_related("program")
            if not groups:
                raise CommandError("Nenhum grupo com programa configurado neste edital.")

            associated = 0
            for group in groups:
                for municipality in municipalities:
                    existing = ProgramMunicipality.objects.filter(
                        edital=edital, municipality=municipality, program=group.program
                    ).first()
                    if existing:
                        if not existing.active:
                            existing.active = True
                            EditalConfigurationService.save(existing, actor)
                        continue
                    EditalConfigurationService.save(
                        ProgramMunicipality(
                            edital=edital,
                            municipality=municipality,
                            program=group.program,
                            program_name=group.program.name,
                            active=True,
                        ),
                        actor,
                    )
                    associated += 1
            self.stdout.write(
                self.style.SUCCESS(
                    f"{len(municipalities)} município(s) garantido(s) no(s) programa(s) "
                    f"({associated} novo(s) vínculo(s))."
                )
            )

        # 3) Publicar
        if options["no_publish"]:
            self.stdout.write("Configuração salva. Edital permanece como rascunho (--no-publish).")
            return

        try:
            EditalConfigurationService.publish(edital, actor)
        except ValidationError as exc:
            raise CommandError(
                "Não foi possível publicar. Pendências:\n  - " + "\n  - ".join(exc.messages)
            ) from exc

        edital.refresh_from_db()
        self.stdout.write(
            self.style.SUCCESS(
                f"Edital {edital.number}/{edital.year} PUBLICADO. Status: {edital.status}."
            )
        )
