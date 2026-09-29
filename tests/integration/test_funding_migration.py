"""Verify upgrade with populated legacy rules in a separate database."""

import os
import subprocess
import sys
from textwrap import dedent

from django.conf import settings


def test_financial_migration_preserves_old_rules_without_guessing_types(tmp_path):
    env = {**os.environ, "DATABASE_URL": f"sqlite:///{tmp_path / 'migration.sqlite3'}"}
    code = dedent("""
        import os
        os.environ.setdefault("DJANGO_SETTINGS_MODULE", "config.settings")
        import django
        django.setup()
        from django.db import connection
        from django.db.migrations.executor import MigrationExecutor
        from django.utils import timezone
        executor = MigrationExecutor(connection)
        executor.migrate([("editais", "0001_initial")])
        old = executor.loader.project_state([("editais", "0001_initial")]).apps
        edital = old.get_model("editais", "Edital").objects.create(
            number="upgrade", year=2025, name="Upgrade", opens_at=timezone.now(), closes_at=timezone.now())
        rule = old.get_model("editais", "FundingRule").objects.create(
            edital=edital, target_group="G1", monthly_value_per_vacancy="999.99")
        executor = MigrationExecutor(connection)
        executor.migrate(executor.loader.graph.leaf_nodes())
        from apps.editais.models import LegacyGroupFundingRule, FundingRule
        archived = LegacyGroupFundingRule.objects.get(pk=rule.pk)
        assert str(archived.monthly_value_per_vacancy) == "999.99"
        assert archived.target_group == "G1"
        assert not FundingRule.objects.exists()
    """)
    subprocess.run(
        [sys.executable, "-c", code],
        cwd=settings.BASE_DIR,
        env=env,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
