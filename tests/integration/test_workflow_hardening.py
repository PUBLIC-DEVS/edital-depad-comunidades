import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.evaluations.models import CheckResult, Evaluation
from apps.evaluations.services import EvaluationService
from apps.reviews.models import Diligence, Review, ReviewItemDecision
from apps.reviews.services import ReviewService
from apps.submissions.models import Submission
from apps.submissions.services import WorkflowService

pytestmark = pytest.mark.django_db


def complete(domain, status):
    ev = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    ev.check_results.update(status=status)
    EvaluationService.conclude_evaluation(ev, domain["analyst"])
    domain["sub"].refresh_from_db()
    return ev


@pytest.mark.parametrize(
    "status,target,reviews",
    [("ATENDE", "ELIGIBLE_FOR_RANKING", 0), ("NAO_ATENDE", "PENDING_REVIEW", 1)],
)
def test_completion_routes(domain, status, target, reviews):
    ev = complete(domain, status)
    assert domain["sub"].workflow_status == target
    assert Review.objects.filter(evaluation=ev).count() == reviews
    if reviews:
        assert ev.review.reviewer_id is None


@pytest.mark.parametrize("role", ["analyst", "consulta", "distributor", "coord"])
def test_workspace_get_never_writes(client, domain, role):
    client.force_login(domain[role])
    before = AuditEvent.objects.count()
    res = client.get(reverse("evaluation-workspace", args=[domain["sub"].pk]))
    assert res.status_code == 200
    assert not Evaluation.objects.exists()
    assert not CheckResult.objects.exists()
    assert AuditEvent.objects.count() == before
    domain["sub"].refresh_from_db()
    assert domain["sub"].workflow_status == "ASSIGNED"


def test_start_requires_assigned_analyst_post(client, domain):
    url = reverse("evaluation-start", args=[domain["sub"].pk])
    client.force_login(domain["other_analyst"])
    assert client.post(url).status_code == 403
    client.force_login(domain["consulta"])
    assert client.post(url).status_code == 403
    client.force_login(domain["analyst"])
    assert client.get(url).status_code == 405
    assert client.post(url).status_code == 302
    assert Evaluation.objects.get().analyst == domain["analyst"]


def test_review_claim_stale_competitor_and_ownership(domain):
    ev = complete(domain, "NAO_ATENDE")
    first, stale = Review.objects.get(pk=ev.review.pk), Review.objects.get(pk=ev.review.pk)
    claimed = ReviewService.claim_review(first, domain["reviewer"])
    with pytest.raises(ValidationError):
        ReviewService.claim_review(stale, domain["other_reviewer"])
    with pytest.raises(PermissionDenied):
        ReviewService.record_item_decision(
            claimed, ev.check_results.get().pk, True, actor=domain["other_reviewer"]
        )
    assert not ReviewItemDecision.objects.exists()


def test_cross_process_review_item_rejected(domain):
    ev = complete(domain, "NAO_ATENDE")
    review = ReviewService.claim_review(ev.review, domain["reviewer"])
    sub = Submission.objects.create(
        edital=domain["edital"],
        institution=domain["sub"].institution,
        processo_sei="TEST-B",
        received_at=timezone.now(),
    )
    other = Evaluation.objects.create(submission=sub, analyst=domain["other_analyst"])
    check = CheckResult.objects.create(evaluation=other, requirement_check=domain["check"])
    with pytest.raises(ValidationError):
        ReviewService.record_item_decision(review, check.pk, True, actor=domain["reviewer"])
    assert not ReviewItemDecision.objects.exists()


@pytest.mark.parametrize("result", ["PENDING_DECISION", "bogus", ""])
def test_review_invalid_conclusion(domain, result):
    ev = complete(domain, "NAO_ATENDE")
    review = ReviewService.claim_review(ev.review, domain["reviewer"])
    with pytest.raises(ValidationError):
        ReviewService.conclude_review(review, result, "notes", domain["reviewer"])
    review.refresh_from_db()
    assert review.status == "PENDING"


@pytest.mark.parametrize(
    "origin", ["UNDER_ANALYSIS", "PENDING_REVIEW", "ELIGIBLE_FOR_RANKING", "INELIGIBLE"]
)
@pytest.mark.parametrize("result", ["SANEADA", "NAO_SANEADA"])
def test_diligence_origin_and_explicit_consequence(domain, origin, result):
    sub = domain["sub"]
    sub.workflow_status = origin
    sub.save()
    d = WorkflowService.open_diligence(
        sub, domain["coord"], "test", timezone.now().date(), unsatisfied_return_status="INELIGIBLE"
    )
    WorkflowService.conclude_diligence(d, domain["coord"], result, "response")
    sub.refresh_from_db()
    assert sub.workflow_status == (origin if result == "SANEADA" else "INELIGIBLE")
    assert AuditEvent.objects.filter(entity_type="Diligence", action="ANSWER_DILIGENCE").exists()


def test_unsatisfied_diligence_has_no_invented_legal_consequence(domain):
    sub = domain["sub"]
    sub.workflow_status = "UNDER_ANALYSIS"
    sub.save()
    diligence = WorkflowService.open_diligence(sub, domain["coord"], "test", timezone.now().date())
    with pytest.raises(ValidationError, match="OPEN BUSINESS QUESTION"):
        WorkflowService.conclude_diligence(diligence, domain["coord"], "NAO_SANEADA")
    diligence.refresh_from_db()
    assert diligence.status == Diligence.Status.OPEN
