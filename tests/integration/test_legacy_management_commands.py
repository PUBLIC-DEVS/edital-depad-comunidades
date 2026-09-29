from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.legacy_import.models import LegacyImportRun

pytestmark = [pytest.mark.legacy, pytest.mark.django_db]


def test_missing_real_workbook_is_not_run(tmp_path):
    output = StringIO()
    with pytest.raises(CommandError, match="NOT_RUN"):
        call_command("audit_legacy_real", str(tmp_path / "absent.xlsx"), stdout=output)
    assert '"status": "NOT_RUN"' in output.getvalue()
    assert not LegacyImportRun.objects.exists()


def test_record_level_reports_must_be_private(tmp_path):
    path = tmp_path / "sentinel.xlsx"
    path.write_text("not a real workbook")
    with pytest.raises(CommandError, match="private"):
        call_command("audit_legacy_real", str(path), "--output", str(tmp_path / "public"))
    assert not LegacyImportRun.objects.exists()
