import pytest
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.urls import reverse

from apps.evaluations.services import EvaluationService
from apps.ranking.services import RankingService
from apps.reviews.models import ReviewItemDecision
from apps.reviews.services import ReviewService
from apps.submissions.models import Assignment, Submission
from apps.submissions.services import WorkflowService

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "role,allowed",
    [
        ("analyst", False),
        ("reviewer", False),
        ("distributor", False),
        ("consulta", True),
        ("coord", True),
        ("admin", True),
    ],
)
@pytest.mark.parametrize(
    "endpoint",
    [
        "ranking-index",
        "ranking-history",
        "ranking-export-csv",
        "reporting:dashboard",
        "reporting:validations",
        "reporting:failed-requirement",
        "reporting:export-csv",
    ],
)
def test_global_views_server_side_permissions(client, domain, role, allowed, endpoint):
    from tests.operational_helpers import publish_fixture

    publish_fixture(domain["edital"])
    snapshot = RankingService.generate_snapshot(domain["edital"], domain["coord"])
    args = (
        [snapshot.pk]
        if endpoint == "ranking-export-csv"
        else ["4.2-III"]
        if endpoint == "reporting:failed-requirement"
        else []
    )
    client.force_login(domain[role])
    response = client.get(reverse(endpoint, args=args))
    assert response.status_code == (200 if allowed else 403)


def review(domain):
    ev = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    ev.check_results.update(status="NAO_ATENDE")
    EvaluationService.conclude_evaluation(ev, domain["analyst"])
    return ReviewService.claim_review(ev.review, domain["reviewer"])


@pytest.mark.parametrize("role", ["other_reviewer", "analyst", "consulta"])
def test_review_post_ownership_and_roles(client, domain, role):
    rev = review(domain)
    client.force_login(domain[role])
    response = client.post(
        reverse("review-item-decision", args=[rev.pk, rev.evaluation.check_results.get().pk]),
        {"agrees_with_analyst": "true"},
    )
    assert response.status_code == 403
    assert not ReviewItemDecision.objects.exists()
    assert (
        client.post(
            reverse("review-conclude", args=[rev.pk]), {"preliminary_result": "PRE_HABILITADO"}
        ).status_code
        == 403
    )


@pytest.mark.parametrize("role", ["other_reviewer", "analyst", "consulta"])
def test_diligence_idor(client, domain, role):
    rev = review(domain)
    client.force_login(domain[role])
    assert (
        client.post(
            reverse("diligence-create", args=[domain["sub"].pk]),
            {"reason": "test", "deadline": "2026-12-01"},
        ).status_code
        == 404
    )
    assert not domain["sub"].diligences.exists()
    assert client.post(reverse("diligence-detail", args=[999])).status_code == 404
    rev.refresh_from_db()
    assert rev.status == "PENDING"


def test_unique_sei_per_edital_database_constraint(domain):
    with pytest.raises(IntegrityError), transaction.atomic():
        Submission.objects.create(
            edital=domain["edital"],
            institution=domain["sub"].institution,
            processo_sei=domain["sub"].processo_sei,
            received_at=domain["sub"].received_at,
        )


def test_only_one_active_assignment_database_constraint(domain):
    with pytest.raises(IntegrityError), transaction.atomic():
        Assignment.objects.create(
            submission=domain["sub"], analyst=domain["other_analyst"], assigned_by=domain["coord"]
        )


def test_draft_blocks_reassignment_and_preserves_analyst(domain):
    ev = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    with pytest.raises(ValidationError):
        WorkflowService.reassign_analyst(domain["sub"], domain["other_analyst"], domain["coord"])
    ev.refresh_from_db()
    assert ev.analyst == domain["analyst"]
    assert (
        Assignment.objects.filter(submission=domain["sub"], status="ACTIVE").get().analyst
        == domain["analyst"]
    )
