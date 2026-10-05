"""Read/import an external workbook and report actual parity, including unresolved differences."""

import json
import os
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError

from apps.accounts.models import User
from apps.editais.models import Edital
from apps.legacy_import.importer import LegacyImporter
from apps.legacy_import.models import LegacyImportRun
from apps.legacy_import.parity import compare_workbook, entity_counts
from apps.legacy_import.reporting import write_reports
from apps.ranking.models import RankingSnapshot
from apps.ranking.services.ranking import RankingService


class Command(BaseCommand):
    help = "Real external XLSX golden master. Run only against an isolated development database."

    def add_arguments(self, parser):
        parser.add_argument("path", nargs="?", default=os.environ.get("LEGACY_XLSX_PATH"))
        parser.add_argument("--number", default="legacy-real")
        parser.add_argument("--year", type=int, default=2025)
        parser.add_argument("--output", default="artifacts/private")
        parser.add_argument("--generate-snapshot", action="store_true")
        parser.add_argument("--fail-on-mismatch", action="store_true")

    def handle(self, *args, **options):
        path = options["path"]
        if not path or not Path(path).is_file():
            self.stdout.write(json.dumps({"status": "NOT_RUN", "real_workbook_executed": False}))
            raise CommandError("Real workbook unavailable; parity NOT_RUN")
        output = Path(options["output"]).resolve()
        # Process-level evidence is private by default; prevent accidental Git publication.
        if "private" not in output.parts[2:]:
            raise CommandError("Record-level reports require a directory named private")
        edital = Edital.objects.filter(number=options["number"], year=options["year"]).first()
        before = entity_counts(edital)
        importer = LegacyImporter(path, options["number"], options["year"], strict=False)
        importer.run()
        run = LegacyImportRun.objects.get(pk=importer.report.run_id)
        snapshot = RankingSnapshot.objects.filter(edital=run.edital).order_by("-pk").first()
        snapshot_error = None
        if options["generate_snapshot"]:
            actor, created = User.objects.get_or_create(
                username="legacy.audit.coordinator",
                defaults={"role": "COORDENADOR", "is_active": False, "email": None},
            )
            if created:
                actor.set_unusable_password()
                actor.save(update_fields=["password"])
            try:
                snapshot = RankingService.generate_snapshot(
                    run.edital, actor, description="Isolated real legacy parity comparison"
                )
            except ValidationError as exc:
                snapshot_error = str(exc)
        report = compare_workbook(importer.data, run, snapshot)
        report["summary"]["counts_before_import"] = before
        report["summary"]["counts_after_import"] = entity_counts(run.edital)
        report["summary"]["snapshot_error"] = snapshot_error
        write_reports(report, output)
        self.stdout.write(json.dumps(report["summary"], ensure_ascii=False))
        if options["fail_on_mismatch"] and report["summary"]["status"] != "PASS":
            raise CommandError(
                f"Real parity {report['summary']['status']}; private differences written"
            )
