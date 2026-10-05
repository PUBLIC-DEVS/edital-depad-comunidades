from decimal import Decimal

import pytest
from django.urls import reverse

from apps.editais.models import Requirement, RequirementCheck
from apps.evaluations.assessment import definition_rows
from apps.evaluations.models import CheckResult, Evaluation
from apps.evaluations.services import EvaluationService
from apps.submissions.services.validation import SubmissionAnomalyDetector

# Test-only routes exercise retained configuration; operational retirement has separate coverage.
pytestmark = pytest.mark.urls("tests.technical_urls")


@pytest.mark.django_db
@pytest.mark.parametrize(
    "required,value,missing",
    [
        (False, None, False),
        (False, Decimal("0"), False),
        (True, None, True),
        (True, Decimal("10"), False),
    ],
)
def test_financial_anomaly_respects_edital_configuration(domain, required, value, missing):
    domain["edital"].requires_financial_rules = required
    domain["edital"].save()
    sub = domain["sub"]
    sub.edital = domain["edital"]
    sub.valor_global = value
    codes = {item.code for item in SubmissionAnomalyDetector.check_submission(sub)}
    assert ("MISSING_GLOBAL_VALUE" in codes) == missing


@pytest.mark.django_db
@pytest.mark.parametrize("active_flags", [[], [True], [True, False], [False]])
def test_preview_uses_same_active_definitions_as_runtime(client, domain, active_flags):
    req = Requirement.objects.create(
        edital=domain["edital"], code="PREVIEW", name="Preview documento"
    )
    for index, active in enumerate(active_flags):
        RequirementCheck.objects.create(
            requirement=req, code=f"CHECK-{index}", name=f"Preview decisão {index}", active=active
        )
    client.force_login(domain["admin"])
    url = reverse("edital-analyst-preview", args=[domain["edital"].pk])
    before = (
        Evaluation.objects.count(),
        CheckResult.objects.count(),
        domain["sub"].workflow_status,
    )
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    for index, active in enumerate(active_flags):
        assert (f"Preview decisão {index}" in content) == active
    if not any(active_flags):
        assert "Check direto" in content
    domain["sub"].refresh_from_db()
    assert before == (
        Evaluation.objects.count(),
        CheckResult.objects.count(),
        domain["sub"].workflow_status,
    )
    evaluation = EvaluationService.initialize_evaluation(domain["sub"], domain["analyst"])
    rows = [row for row in definition_rows(evaluation) if row[0].pk == req.pk]
    assert len(rows) == (sum(active_flags) or 1)
    assert all(row[2] is not None for row in rows)
    if not any(active_flags):
        assert rows[0][1].pk == req.pk
        assert rows[0][2].requirement_check_id is None
