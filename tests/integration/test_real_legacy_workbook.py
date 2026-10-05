"""External evidence only. Green tests validate the harness; summary.status states parity."""

import json
import os
import subprocess
import sys
from hashlib import sha256
from pathlib import Path

import pytest
from django.conf import settings
from django.core.exceptions import ValidationError

from apps.accounts.models import User
from apps.legacy_import.importer import LegacyImporter
from apps.legacy_import.models import LegacyImportRun
from apps.legacy_import.parity import compare_workbook
from apps.legacy_import.reporting import write_reports
from apps.ranking.services.ranking import RankingService

pytestmark = pytest.mark.legacy_real
AUDITED_HASH = "030b28f5ca61a3fa79e1b07834cee952fa262d3aef7b6641242d44865bf55ac2"


@pytest.fixture
def real_path():
    path = os.environ.get("LEGACY_XLSX_PATH")
    if not path:
        pytest.skip(
            "LEGACY_XLSX_PATH absent: real workbook NOT_RUN; synthetic tests cannot confer PASS"
        )
    if not Path(path).is_file():
        pytest.fail("LEGACY_XLSX_PATH specified but real workbook does not exist")
    return Path(path)


@pytest.mark.django_db
def test_external_workbook_golden_master(real_path, tmp_path, monkeypatch):
    from openpyxl.workbook.workbook import Workbook

    def reject_save(*args, **kwargs):
        raise AssertionError("The external historical workbook is read-only")

    monkeypatch.setattr(Workbook, "save", reject_save)
    before_hash = sha256(real_path.read_bytes()).hexdigest()
    importer = LegacyImporter(real_path, "real-golden", 2025, strict=False)
    importer.run()
    run = LegacyImportRun.objects.get(pk=importer.report.run_id)
    snapshot = None
    actor = User.objects.create_user(username="golden-coord", role="COORDENADOR", email=None)
    try:
        snapshot = RankingService.generate_snapshot(run.edital, actor)
    except ValidationError as exc:
        assert "OPEN BUSINESS QUESTION" in str(exc)
    report = compare_workbook(importer.data, run, snapshot)
    write_reports(report, tmp_path / "private")
    summary = report["summary"]
    assert summary["real_workbook_executed"]
    assert summary["processes_compared"] == len(importer.data.distribution)
    assert len(report["rows"]["submissions"]) == len(importer.data.distribution)
    assert len({r["processo_sei"] for r in report["rows"]["submissions"]}) == len(
        importer.data.distribution
    )
    if summary["mismatch_count"]:
        assert summary["status"] == "FAIL"  # Never turn harness success into a parity claim.
    if before_hash == AUDITED_HASH:
        # Independent audit fingerprint, never used to force domain/import results.
        assert summary["sheet_count"] == 23
        assert summary["processes_compared"] == 282
        assert summary["analyst_sheet_count"] == 11
        assert set(summary["analyst_workloads"]) == {25, 26}
        assert summary["raw_groups_system"] == {"G1": 9, "G2": 34, "G3": 212, "SEM_GRUPO": 27}
        assert summary["initial_results_excel"] == {"APTA": 180, "INAPTA": 102}
        assert summary["review_rows"] == 216
        assert (summary["diligence_rows"], summary["diligence_unique_seis"]) == (165, 158)
        assert summary["displayed_legacy_metrics"] == {"APTA": 177, "INAPTA": 105, "EM_ANALISE": 0}
        assert summary["materialized_ranking_groups"] == {"G1": 5, "G2": 24, "G3": 143}
        assert summary["historical_formula_groups"] == summary["materialized_ranking_groups"]
        assert (summary["duplicate_cnpjs"], summary["duplicate_excess"]) == (20, 21)
        assert all(
            "HISTORICAL_INITIAL_POSITION" not in row["mismatch_codes"]
            for row in report["rows"]["ranking"]
        )
        assert summary["status"] == "FAIL"
    assert sha256(real_path.read_bytes()).hexdigest() == before_hash


def test_external_import_idempotency_in_separate_processes(real_path, tmp_path):
    database = tmp_path / "independent-import.sqlite3"
    env = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{database}",
        "PYTHONPYCACHEPREFIX": str(tmp_path / "pycache"),
    }

    def command(*args):
        return subprocess.run(
            [sys.executable, str(settings.BASE_DIR / "manage.py"), *args],
            cwd=settings.BASE_DIR,
            env=env,
            check=True,
            capture_output=True,
            text=True,
            timeout=180,
        )

    command("migrate", "--noinput")
    first = tmp_path / "private" / "first"
    second = tmp_path / "private" / "second"
    command("audit_legacy_real", str(real_path), "--output", str(first))
    command("audit_legacy_real", str(real_path), "--output", str(second))
    a = json.loads((first / "legacy-real-summary.json").read_text())
    b = json.loads((second / "legacy-real-summary.json").read_text())
    assert all(value == 0 for value in a["counts_before_import"].values())
    assert a["counts_after_import"] == b["counts_before_import"] == b["counts_after_import"]
    for field in ("initial_results_calculated", "mismatches_by_code", "source_issue_codes"):
        assert a[field] == b[field]
    # Verify each process/result/evidence comparison, not only stable aggregate counts.
    for area in ("submissions", "evaluations", "reviews", "diligences", "ranking"):
        filename = f"legacy-real-{area}-diff.csv"
        assert (first / filename).read_text() == (second / filename).read_text()
