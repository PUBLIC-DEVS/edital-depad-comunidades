import os
from pathlib import Path

import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.editais.models import Edital, Requirement, RequirementCheck
from apps.institutions.models import Institution, Municipality
from apps.submissions.models import Assignment, Submission
from tests.group_configuration import configure_example_groups


def pytest_ignore_collect(collection_path: Path, config):
    """Keep migration-only tests out when the optional legacy app is disabled."""
    if os.getenv("ENABLE_LEGACY_IMPORT", "true").lower() != "false":
        return None
    legacy_only_modules = {
        "test_legacy_import_safety.py",
        "test_legacy_management_commands.py",
        "test_real_legacy_workbook.py",
        "test_parity_status.py",
        "test_synthetic_legacy_importer.py",
    }
    return collection_path.name in legacy_only_modules


@pytest.fixture
def domain(db):
    users = {
        name: User.objects.create_user(username=name, email=f"{name}@example.test", role=role)
        for name, role in {
            "analyst": "ANALISTA",
            "other_analyst": "ANALISTA",
            "reviewer": "REVISOR",
            "other_reviewer": "REVISOR",
            "coord": "COORDENADOR",
            "consulta": "CONSULTA",
            "distributor": "DISTRIBUIDOR",
            "admin": "ADMINISTRADOR",
        }.items()
    }
    now = timezone.now()
    edital = Edital.objects.create(
        name="Test", number="test", year=2025, opens_at=now, closes_at=now
    )
    configure_example_groups(edital)
    municipality = Municipality.objects.create(name="São Paulo", state="SP", ibge_code="3550308")
    institution = Institution.objects.create(name="Test institution", cnpj="00000000000191")
    sub = Submission.objects.create(
        edital=edital,
        institution=institution,
        processo_sei="TEST-A",
        received_at=now,
        municipality=municipality,
        vagas_masculinas=10,
        workflow_status="ASSIGNED",
    )
    Assignment.objects.create(
        submission=sub, analyst=users["analyst"], assigned_by=users["coord"], assigned_at=now
    )
    req = Requirement.objects.create(edital=edital, code="4.2-III", name="Participation")
    check = RequirementCheck.objects.create(requirement=req, code="4.2-III-E", name="Signature")
    return {**users, "edital": edital, "sub": sub, "check": check}
