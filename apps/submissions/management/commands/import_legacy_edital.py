"""Comando de importação do arquivo Excel legado do edital."""

import os

from django.core.management.base import BaseCommand, CommandError

from apps.submissions.services.legacy_importer import LegacyImporter


class Command(BaseCommand):
    help = (
        "Importa o arquivo Excel legado (282 processos) de forma idempotente e com rastreabilidade."
    )

    def add_arguments(self, parser):
        parser.add_argument("filepath", type=str, help="Caminho para o arquivo .xlsx legado")
        parser.add_argument(
            "--edital-number", type=str, default="1", help="Número do edital (padrão: 1)"
        )
        parser.add_argument(
            "--edital-year", type=int, default=2026, help="Ano do edital (padrão: 2026)"
        )
        parser.add_argument(
            "--dry-run", action="store_true", help="Executa validação sem persistir no banco"
        )

    def handle(self, *args, **options):
        filepath = options["filepath"]
        edital_number = options["edital_number"]
        edital_year = options["edital_year"]
        dry_run = options["dry_run"]

        if not os.path.exists(filepath):
            raise CommandError(f"Arquivo não encontrado: {filepath}")

        self.stdout.write(self.style.NOTICE(f"Iniciando importação do arquivo: {filepath}"))
        if dry_run:
            self.stdout.write(
                self.style.WARNING("Modo DRY-RUN ativado: nenhuma alteração será gravada.")
            )

        importer = LegacyImporter(
            filepath=filepath,
            edital_number=edital_number,
            edital_year=edital_year,
            dry_run=dry_run,
        )
        report = importer.run()

        self.stdout.write(self.style.SUCCESS("\n=== RELATÓRIO DE IMPORTAÇÃO DO EDITAL LEGADO ==="))
        self.stdout.write(f"Total de linhas lidas:           {report.total_rows_read}")
        self.stdout.write(f"Inscrições criadas:              {report.submissions_created}")
        self.stdout.write(f"Inscrições atualizadas:          {report.submissions_updated}")
        self.stdout.write(f"Atribuições a analistas:         {report.assignments_created}")
        self.stdout.write(f"Avaliações recuperadas:          {report.evaluations_created}")
        self.stdout.write(f"Revisões importadas:             {report.reviews_created}")
        self.stdout.write(f"Diligências importadas:          {report.diligences_created}")
        self.stdout.write(
            self.style.MIGRATE_HEADING("\n--- Consolidação de Grupos (Paridade Legada) ---")
        )
        self.stdout.write(f"Grupo 1 (G1):                    {report.g1_count} (Esperado: 9)")
        self.stdout.write(f"Grupo 2 (G2 - PRONASCI):         {report.g2_count} (Esperado: 34)")
        self.stdout.write(f"Grupo 3 (G3 - Ampla):            {report.g3_count} (Esperado: 212)")
        self.stdout.write(
            f"Sem Grupo (Zeradas):             {report.sem_grupo_count} (Esperado: 27)"
        )
        total_groups = report.g1_count + report.g2_count + report.g3_count + report.sem_grupo_count
        self.stdout.write(f"Total de Processos Mapeados:     {total_groups} (Esperado: 282)")

        if report.warnings:
            self.stdout.write(self.style.WARNING(f"\nAvisos ({len(report.warnings)}):"))
            for w in report.warnings:
                self.stdout.write(f" - {w}")

        if report.skipped_rows:
            self.stdout.write(
                self.style.WARNING(f"\nLinhas ignoradas ({len(report.skipped_rows)}):")
            )
            for s in report.skipped_rows[:10]:
                self.stdout.write(f" - {s}")
            if len(report.skipped_rows) > 10:
                self.stdout.write(f" ... e mais {len(report.skipped_rows) - 10} linhas.")

        self.stdout.write(self.style.SUCCESS("\nImportação concluída com sucesso!"))
