import pytest
from django.contrib import admin
from django.test import RequestFactory
from django.urls import reverse
from django.utils import timezone

from apps.evaluations.models import CheckResult, Evaluation
from apps.ranking.models import RankingSnapshot
from apps.reviews.models import Diligence, Review
from apps.submissions.models import Assignment, Submission
from apps.submissions.services.workflow import WorkflowService

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "model", [Submission, Assignment, Evaluation, CheckResult, Review, Diligence]
)
def test_operational_admin_cannot_bypass_audited_services(domain, model):
    request = RequestFactory().get("/admin/")
    request.user = domain["admin"]
    model_admin = admin.site._registry[model]
    assert not model_admin.has_change_permission(request)
    assert not model_admin.has_delete_permission(request)
    assert not model_admin.has_add_permission(request)


def test_diligence_without_failure_policy_is_disabled(client, domain):
    import pytest
    from django.core.exceptions import ValidationError

    domain["sub"].workflow_status = "UNDER_ANALYSIS"
    domain["sub"].save()
    with pytest.raises(ValidationError, match="desativad"):
        WorkflowService.open_diligence(
            domain["sub"], domain["coord"], "test", timezone.now().date()
        )
    client.force_login(domain["coord"])
    assert client.post(reverse("diligence-create", args=[domain["sub"].pk])).status_code == 404
    assert not Diligence.objects.exists()


def test_unverified_old_snapshot_not_exported_as_official(client, domain):
    from tests.operational_helpers import publish_fixture

    publish_fixture(domain["edital"])
    snapshot = RankingSnapshot.objects.create(
        edital=domain["edital"],
        generated_by=domain["coord"],
        rules_version="old",
        duplicate_policy="KEEP_EARLIEST_SUBMISSION",
    )
    client.force_login(domain["consulta"])
    assert client.get(reverse("ranking-export-csv", args=[snapshot.pk])).status_code == 409
