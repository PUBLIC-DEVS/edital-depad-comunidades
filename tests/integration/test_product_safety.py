from datetime import timedelta
from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import ProtectedError
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.editais.models import (
    Edital,
    FundingRule,
    RequirementCheck,
    TargetGroup,
)
from apps.evaluations.services import EvaluationService
from apps.reporting.services.metrics import DashboardMetricsService
from apps.reviews.models import Review
from apps.reviews.services import ReviewService


@pytest.mark.django_db
def test_audit_event_queryset_is_append_only(domain):
    event = AuditEvent.objects.create(
        actor=domain["admin"], entity_type="Example", entity_id="1", action="START"
    )
    with pytest.raises(PermissionDenied):
        AuditEvent.objects.filter(pk=event.pk).update(action="TAMPER")
    with pytest.raises(PermissionDenied):
        AuditEvent.objects.filter(pk=event.pk).delete()
    with pytest.raises(PermissionDenied):
        AuditEvent.objects.bulk_update([event], ["action"])
    with pytest.raises(PermissionDenied):
        AuditEvent.objects.bulk_create(
            [event], update_conflicts=True, update_fields=["action"], unique_fields=["id"]
        )
    with pytest.raises(PermissionDenied):
        event.delete()
    with pytest.raises(ProtectedError):
        domain["admin"].delete()
    event.refresh_from_db()
    assert event.action == "START"


@pytest.mark.django_db
def test_per_check_change_history_has_exact_old_and_new_values(domain):
    evaluation = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    result = evaluation.check_results.get(requirement_check=domain["check"])
    EvaluationService.save_draft(
        evaluation,
        [{"check_result_id": result.pk, "status": "ATENDE", "sei_number": "DOC-1", "pages": "12"}],
        domain["analyst"],
    )
    EvaluationService.save_draft(
        evaluation,
        [
            {
                "check_result_id": result.pk,
                "status": "NAO_ATENDE",
                "sei_number": "DOC-1",
                "pages": "12",
            }
        ],
        domain["analyst"],
    )
    events = list(
        AuditEvent.objects.filter(entity_type="CheckResult", entity_id=str(result.pk))
        .order_by("timestamp", "pk")
        .values_list("field", "old_value", "new_value")
    )
    assert events == [
        ("status", "EM_BRANCO", "ATENDE"),
        ("sei_number", "", "DOC-1"),
        ("pages", "", "12"),
        ("status", "ATENDE", "NAO_ATENDE"),
    ]
    before = len(events)
    EvaluationService.save_draft(
        evaluation,
        [
            {
                "check_result_id": result.pk,
                "status": "NAO_ATENDE",
                "sei_number": "DOC-1",
                "pages": "12",
            }
        ],
        domain["analyst"],
    )
    assert (
        AuditEvent.objects.filter(entity_type="CheckResult", entity_id=str(result.pk)).count()
        == before
    )
    with pytest.raises(ValidationError):
        EvaluationService.save_draft(
            evaluation,
            [{"check_result_id": result.pk, "status": "ATENDE", "numeric_value": Decimal("1.00")}],
            domain["analyst"],
        )
    result.refresh_from_db()
    assert result.status == "NAO_ATENDE"


@pytest.mark.django_db
def test_review_requires_all_blockers_and_consistent_outcome(domain):
    other = RequirementCheck.objects.create(
        requirement=domain["check"].requirement, code="OTHER", name="Outro impedimento"
    )
    evaluation = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    payload = [
        {"check_result_id": r.pk, "status": "NAO_ATENDE"} for r in evaluation.check_results.all()
    ]
    EvaluationService.save_draft(evaluation, payload, domain["analyst"])
    EvaluationService.conclude_evaluation(evaluation, domain["analyst"])
    review = ReviewService.claim_review(
        Review.objects.get(evaluation=evaluation), domain["reviewer"]
    )
    first = evaluation.check_results.get(requirement_check=domain["check"])
    second = evaluation.check_results.get(requirement_check=other)
    with pytest.raises(ValidationError, match="Trate todos"):
        ReviewService.conclude_review(
            review, "PRE_INABILITADO", "Tentativa incompleta", domain["reviewer"]
        )
    ReviewService.record_item_decision(review, first.pk, True, actor=domain["reviewer"])
    with pytest.raises(ValidationError, match="Trate todos"):
        ReviewService.conclude_review(
            review, "PRE_HABILITADO", "Ainda incompleta", domain["reviewer"]
        )
    ReviewService.record_item_decision(
        review, second.pk, False, "ATENDE", "Regularidade comprovada.", domain["reviewer"]
    )
    with pytest.raises(ValidationError, match="coerente"):
        ReviewService.conclude_review(
            review, "PRE_HABILITADO", "Ainda existe falha", domain["reviewer"]
        )
    ReviewService.record_item_decision(
        review, first.pk, False, "ATENDE", "Novo documento válido.", domain["reviewer"]
    )
    with pytest.raises(ValidationError, match="coerente"):
        ReviewService.conclude_review(
            review, "PRE_INABILITADO", "Nenhuma falha pendente", domain["reviewer"]
        )
    ReviewService.conclude_review(
        review, "PRE_HABILITADO", "Todos os impedimentos resolvidos", domain["reviewer"]
    )
    review.refresh_from_db()
    assert review.status == "COMPLETED"
    assert review.item_decisions.count() == 2
    assert domain["sub"].reviews.get().pk == review.pk


@pytest.mark.django_db
def test_operational_metrics_use_effective_workflow_outcome(domain):
    evaluation = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    EvaluationService.save_draft(
        evaluation,
        [{"check_result_id": r.pk, "status": "NAO_ATENDE"} for r in evaluation.check_results.all()],
        domain["analyst"],
    )
    EvaluationService.conclude_evaluation(evaluation, domain["analyst"])
    review = ReviewService.claim_review(
        Review.objects.get(evaluation=evaluation), domain["reviewer"]
    )
    result = evaluation.check_results.get()
    ReviewService.record_item_decision(
        review, result.pk, False, "ATENDE", "Evidência validada.", domain["reviewer"]
    )
    ReviewService.conclude_review(
        review, "PRE_HABILITADO", "Revisão procedente", domain["reviewer"]
    )
    summary = DashboardMetricsService.get_summary_metrics(domain["edital"])
    assert summary["apt_count"] == 1
    assert summary["inapt_count"] == 0
    assert summary["pending_review"] == 0
    assert summary["total_received"] == 1
    evaluation.refresh_from_db()
    assert evaluation.result == "INAPTA"  # preserved original, never counted as final inapt


@pytest.mark.django_db
@pytest.mark.urls("tests.technical_urls")
def test_funding_rule_crud_and_published_protection(domain, client):
    edital = domain["edital"]
    client.force_login(domain["admin"])
    data = {
        "vacancy_type": "MALE",
        "monthly_value": "1234.50",
        "duration_months": 5,
        "valid_from": "2027-01-01",
        "valid_until": "2027-12-31",
    }
    assert (
        client.post(
            reverse("edital-section-create", args=[edital.pk, "financeiro"]), data
        ).status_code
        == 302
    )
    rule = FundingRule.objects.get(edital=edital, vacancy_type="MALE")
    assert rule.monthly_value == Decimal("1234.50")
    data["monthly_value"] = "1800.25"
    assert (
        client.post(
            reverse("edital-section-edit", args=[edital.pk, "financeiro", rule.pk]), data
        ).status_code
        == 302
    )
    rule.refresh_from_db()
    assert rule.monthly_value == Decimal("1800.25")
    assert (
        client.post(
            reverse("edital-section-action", args=[edital.pk, "financeiro", rule.pk, "remover"])
        ).status_code
        == 302
    )
    assert not FundingRule.objects.filter(pk=rule.pk).exists()


@pytest.mark.django_db
def test_institution_catalog_scope_and_create_permissions(domain, client):
    client.force_login(domain["distributor"])
    assert client.get(reverse("catalog-list", args=["instituicoes"])).status_code == 200
    assert (
        client.get(reverse("institution-detail", args=[domain["sub"].institution.pk])).status_code
        == 200
    )
    client.force_login(domain["analyst"])
    assert (
        client.get(reverse("institution-detail", args=[domain["sub"].institution.pk])).status_code
        == 200
    )
    assert (
        client.post(
            reverse("catalog-create", args=["instituicoes"]),
            {"cnpj": "00000000000191", "name": "Overwrite"},
        ).status_code
        == 403
    )
    client.force_login(domain["consulta"])
    assert client.get(reverse("catalog-create", args=["instituicoes"])).status_code == 403
    assert (
        client.get(reverse("institution-detail", args=[domain["sub"].institution.pk])).status_code
        == 200
    )
    assert client.get(reverse("catalog-create", args=["programas"])).status_code == 403


@pytest.mark.django_db
def test_manual_group_is_scoped_to_selected_edital(domain):
    edital = domain["edital"]
    edital.classification_policy.policy_type = "MANUAL_TARGET_POLICY_V1"
    edital.classification_policy.save()
    group = TargetGroup.objects.get(edital=edital, code="G1")
    sub = domain["sub"]
    sub.target_group_definition = group
    sub.save(update_fields=["target_group_definition"])
    from apps.ranking.services import ClassificationService

    assert ClassificationService.classify_submission(sub) == "G1"
    other = Edital.objects.create(
        name="Other",
        number="oth",
        year=2030,
        opens_at=timezone.now(),
        closes_at=timezone.now() + timedelta(days=1),
    )
    foreign = TargetGroup.objects.create(edital=other, code="FOREIGN", name="Foreign")
    sub.target_group_definition = foreign
    sub.save(update_fields=["target_group_definition"])
    assert ClassificationService.classify_submission(sub) == "SEM_GRUPO"
