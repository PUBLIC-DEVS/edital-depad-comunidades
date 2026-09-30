"""Product contract for the single edital operation (controlled fixtures, no demo seed)."""

from datetime import date

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.editais.edital_2026 import configure_edital_2026_base
from apps.editais.models import Edital, ProgramMunicipality, RequirementValidationRule
from apps.editais.services import EditalConfigurationService
from apps.evaluations.models import Evaluation
from apps.evaluations.services import EvaluationService, InconsistentEvaluationError
from apps.reviews.models import Diligence, Review
from apps.reviews.services import ReviewService
from apps.submissions.models import Assignment, Submission
from apps.submissions.services import WorkflowService

pytestmark = pytest.mark.django_db


@pytest.fixture
def operational(domain):
    # Configuration remains mutable during fixture setup. Publish only at the boundary.
    domain["edital"].closes_at += timezone.timedelta(days=30)
    domain["edital"].requires_financial_rules = False
    domain["edital"].save()
    ProgramMunicipality.objects.create(
        edital=domain["edital"],
        program=domain["edital"].target_groups.get(code="G2").program,
        municipality=domain["sub"].municipality,
    )
    EditalConfigurationService.publish(domain["edital"], domain["admin"])
    return domain


def test_resolver_requires_exactly_one_active(domain):
    from apps.editais.operational import OperationalEditalError, get_operational_edital

    with pytest.raises(OperationalEditalError, match="Nenhum edital ativo"):
        get_operational_edital()
    domain["edital"].closes_at += timezone.timedelta(days=30)
    domain["edital"].requires_financial_rules = False
    domain["edital"].save()
    ProgramMunicipality.objects.create(
        edital=domain["edital"],
        program=domain["edital"].target_groups.get(code="G2").program,
        municipality=domain["sub"].municipality,
    )
    EditalConfigurationService.publish(domain["edital"], domain["admin"])
    assert get_operational_edital() == domain["edital"]
    other = Edital.objects.create(
        name="Other",
        number="other",
        year=2031,
        opens_at=timezone.now(),
        closes_at=timezone.now() + timezone.timedelta(days=30),
    )
    configure_edital_2026_base(other, domain["admin"])
    other.requires_financial_rules = False
    other.validation_reference_date = date(2031, 1, 1)
    other.save()
    ProgramMunicipality.objects.create(
        edital=other,
        program=other.target_groups.get(code="G2").program,
        municipality=domain["sub"].municipality,
    )
    EditalConfigurationService.publish(other, domain["admin"])
    with pytest.raises(OperationalEditalError, match="Mais de um edital ativo"):
        get_operational_edital()


@pytest.mark.parametrize("role", ["admin", "coord", "consulta"])
def test_operational_home_is_not_metrics_redirect(client, operational, role):
    client.force_login(operational[role])
    response = client.get("/")
    assert response.status_code == 200
    assert response.context["edital"] == operational["edital"]
    assert "submissions/partials/table.html" in [t.name for t in response.templates]


@pytest.mark.parametrize(
    "role,items",
    [
        ("admin", ["Início", "Processos", "Revisão", "Classificação", "Administração"]),
        ("coord", ["Início", "Processos", "Revisão", "Classificação", "Administração"]),
        ("distributor", ["Processos"]),
        ("analyst", ["Minhas Análises"]),
        ("reviewer", ["Revisão"]),
        ("consulta", ["Início", "Processos", "Classificação"]),
    ],
)
def test_navbar_by_role(client, operational, role, items):
    from html.parser import HTMLParser

    class NavParser(HTMLParser):
        def __init__(self):
            super().__init__()
            self.in_nav = False
            self.in_link = False
            self.labels = []

        def handle_starttag(self, tag, attrs):
            if tag == "nav" and dict(attrs).get("aria-label") == "Navegação Principal":
                self.in_nav = True
            if self.in_nav and tag == "a":
                self.in_link = True

        def handle_endtag(self, tag):
            if tag == "nav":
                self.in_nav = False
            if tag == "a":
                self.in_link = False

        def handle_data(self, data):
            if self.in_nav and self.in_link and data.strip():
                self.labels.append(data.strip())

    client.force_login(operational[role])
    response = client.get("/", follow=True)
    parser = NavParser()
    parser.feed(response.content.decode())
    assert parser.labels == items


def test_analyst_home_and_global_rbac(client, operational):
    client.force_login(operational["analyst"])
    assert client.get("/").url == "/minhas-analises/"
    for path in ["/processos/", "/classificacao/", "/administracao/", "/revisoes/", "/metricas/"]:
        assert client.get(path).status_code == 403


@pytest.mark.parametrize(
    "role", ["admin", "coord", "reviewer", "analyst", "consulta", "distributor"]
)
def test_diligence_routes_off_for_every_role(client, operational, role):
    client.force_login(operational[role])
    for url in ["/diligencias/", reverse("diligence-create", args=[operational["sub"].pk])]:
        assert client.get(url).status_code == 404
        assert client.post(url, {"reason": "test", "deadline": "2031-01-01"}).status_code == 404
    assert not Diligence.objects.exists()


def test_diligence_service_and_transition_off(domain):
    domain["sub"].workflow_status = "UNDER_ANALYSIS"
    domain["sub"].save()
    before = AuditEvent.objects.count()
    with pytest.raises(ValidationError, match="desativad"):
        WorkflowService.open_diligence(domain["sub"], domain["coord"], "test", date.today())
    with pytest.raises(ValidationError, match="desativad"):
        WorkflowService.transition(domain["sub"], "PENDING_DILIGENCE", domain["coord"])
    assert not Diligence.objects.exists()
    assert AuditEvent.objects.count() == before


def test_retired_configuration_does_not_mutate(client, operational):
    client.force_login(operational["admin"])
    response = client.post(reverse("edital-clone", args=[operational["edital"].pk]))
    assert response.status_code == 302
    assert response.url == "/administracao/"
    assert Edital.objects.count() == 1
    client.force_login(operational["analyst"])
    assert client.get(reverse("edital-list")).status_code == 403


def test_only_simplified_statuses_can_be_saved(domain):
    evaluation = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    result = evaluation.check_results.get()
    with pytest.raises(ValidationError):
        EvaluationService.save_draft(
            evaluation, [{"check_result_id": result.pk, "status": "NAO_ENVIADO"}], domain["analyst"]
        )
    result.refresh_from_db()
    assert result.status == "EM_BRANCO"


def test_validators_are_support_alerts(domain):
    check = domain["check"]
    check.collect_valid_until = True
    check.save()
    RequirementValidationRule.objects.create(
        requirement_check=check,
        rule_type="DATE_NOT_EXPIRED",
        severity="CRITICAL",
        blocks_completion=True,
    )
    evaluation = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    EvaluationService.save_draft(
        evaluation,
        [
            {
                "check_result_id": evaluation.check_results.get().pk,
                "status": "ATENDE",
                "valid_until": date(2000, 1, 1),
            }
        ],
        domain["analyst"],
    )
    EvaluationService.conclude_evaluation(evaluation, domain["analyst"])
    evaluation.refresh_from_db()
    assert evaluation.result == "APTA"
    assert evaluation.status == "COMPLETED"
    assert not Review.objects.exists()


@pytest.mark.parametrize(
    "original,effective,expected,target",
    [
        ("NAO_ATENDE", "ATENDE", "PRE_HABILITADO", "ELIGIBLE_FOR_RANKING"),
        ("ATENDE", "NAO_ATENDE", "PRE_INABILITADO", "INELIGIBLE"),
    ],
)
def test_review_effective_result_preserves_original(domain, original, effective, expected, target):
    evaluation = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    EvaluationService.save_draft(
        evaluation,
        [{"check_result_id": evaluation.check_results.get().pk, "status": original}],
        domain["analyst"],
    )
    if original == "NAO_ATENDE":
        EvaluationService.conclude_evaluation(evaluation, domain["analyst"])
        review = evaluation.review
    else:
        # Controlled legitimate review test: completed original, pending review task.
        evaluation.status = "COMPLETED"
        evaluation.save()
        domain["sub"].workflow_status = "PENDING_REVIEW"
        domain["sub"].save()
        review = Review.objects.create(evaluation=evaluation, submission=domain["sub"])
    review = ReviewService.claim_review(review, domain["reviewer"])
    check = evaluation.check_results.get()
    original_time = check.updated_at
    decision = ReviewService.record_effective_status(
        review, check.pk, effective, "Documento conferido", domain["reviewer"]
    )
    assert decision.agrees_with_analyst is False
    ReviewService.conclude_review(review, decision_notes="Conferido", actor=domain["reviewer"])
    review.refresh_from_db()
    domain["sub"].refresh_from_db()
    check.refresh_from_db()
    assert review.preliminary_result == expected
    assert domain["sub"].workflow_status == target
    assert check.status == original
    assert check.updated_at == original_time
    evaluation.refresh_from_db()
    assert evaluation.status == "COMPLETED"


@pytest.mark.parametrize(
    "status,expected",
    [
        ("ATENDE", "APTA"),
        ("NAO_ATENDE", "INAPTA"),
        ("NAO_APLICAVEL", "APTA"),
        ("EM_BRANCO", "EM_ANALISE"),
    ],
)
def test_2026_anexo_iii_and_document_counts(domain, status, expected):
    edital = Edital.objects.create(
        name="Base", number="base", year=2030, opens_at=timezone.now(), closes_at=timezone.now()
    )
    configure_edital_2026_base(edital, domain["admin"])
    domain["sub"].edital = edital
    domain["sub"].save()
    evaluation = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    assert edital.requirements.filter(active=True).count() == 14
    assert evaluation.check_results.count() == 23
    payloads = [
        {
            "check_result_id": cr.pk,
            "status": status if cr.definition.code == "COMPROVACAO_AUTODECLARADA" else "ATENDE",
        }
        for cr in evaluation.check_results.select_related("requirement_check")
    ]
    assert EvaluationService.save_draft(evaluation, payloads, domain["analyst"]).result == expected
    if status == "EM_BRANCO":
        with pytest.raises(InconsistentEvaluationError):
            EvaluationService.conclude_evaluation(evaluation, domain["analyst"])


def test_metrics_math_and_active_scope(client, operational):
    from apps.reporting.services.metrics import DashboardMetricsService

    base = operational["sub"]
    base.workflow_status = "UNDER_ANALYSIS"
    base.save()
    for index, status in enumerate(
        [
            "RECEIVED",
            "ASSIGNED",
            "PENDING_REVIEW",
            "ELIGIBLE_FOR_RANKING",
            "RANKED",
            "INELIGIBLE",
            "PENDING_DILIGENCE",
            "CLOSED",
        ]
    ):
        sub = Submission.objects.create(
            edital=base.edital,
            institution=base.institution,
            received_at=base.received_at - timezone.timedelta(days=index),
            processo_sei=f"M-{index}",
            workflow_status=status,
            target_group="G1",
        )
        if status == "ASSIGNED":
            Assignment.objects.create(
                submission=sub, analyst=operational["analyst"], assigned_by=operational["coord"]
            )
    other = Edital.objects.create(
        name="Archive",
        number="archive",
        year=2001,
        status="CLOSED",
        opens_at=timezone.now(),
        closes_at=timezone.now(),
    )
    Submission.objects.create(
        edital=other,
        institution=base.institution,
        received_at=base.received_at,
        processo_sei="OUTSIDE",
    )
    summary = DashboardMetricsService.get_summary_metrics()
    assert summary["total_received"] == 9
    assert summary["unassigned_count"] == 1
    assert summary["under_analysis"] == 2
    assert summary["pending_review"] == 1
    assert summary["apt_count"] == 2
    assert summary["inapt_count"] == 1
    assert summary["by_group"]["G1"] == 8
    assert "pending_diligence" not in summary
    assert summary["by_analyst"][0]["total_assigned"] == 2
    assert summary["by_analyst"][0]["under_analysis"] == 1
    assert sum(point["count"] for point in summary["timeline"]) == 9
    client.force_login(operational["coord"])
    response = client.get(f"/metricas/?edital={other.pk}")
    assert response.context["summary"]["total_received"] == 9
    for url in ["/", "/processos/"]:
        response = client.get(url)
        assert response.status_code == 200
        assert "M-0" in response.content.decode()
        assert "OUTSIDE" not in response.content.decode()


def test_workspace_23_checks_uses_bounded_queries(client, domain):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    edital = Edital.objects.create(
        name="Base", number="base", year=2030, opens_at=timezone.now(), closes_at=timezone.now()
    )
    configure_edital_2026_base(edital, domain["admin"])
    domain["sub"].edital = edital
    domain["sub"].save()
    EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    client.force_login(domain["analyst"])
    with CaptureQueriesContext(connection) as queries:
        response = client.get(reverse("evaluation-workspace", args=[domain["sub"].pk]))
    assert response.status_code == 200
    assert len(response.context["document_sections"]) == 14
    assert response.context["assessment"].total_checks == 23
    assert len(queries) <= 20, [q["sql"] for q in queries]
    html = response.content.decode()
    assert 'value="NAO_ENVIADO"' not in html
    assert 'name="check_' in html
    assert "Detalhes do documento" in html
    assert "Diligência" not in html


def test_timeline_uses_weeks_for_long_period_and_hides_demo_data(operational):
    from apps.reporting.services.metrics import DashboardMetricsService

    base = operational["sub"]
    for index in range(1, 5):
        Submission.objects.create(
            edital=base.edital,
            institution=base.institution,
            received_at=base.received_at - timezone.timedelta(days=index * 30),
            processo_sei=f"TIMELINE-{index}",
        )
    summary = DashboardMetricsService.get_summary_metrics()
    assert summary["timeline_unit"] == "semana"
    assert summary["show_timeline"] is True
    assert sum(point["count"] for point in summary["timeline"]) == 5
    base.processo_sei = "DEMO-SYNTHETIC"
    base.save()
    assert DashboardMetricsService.get_summary_metrics()["show_timeline"] is False


def test_analyst_default_list_prioritizes_unfinished_work(client, operational):
    evaluation = EvaluationService.start_evaluation(operational["sub"], operational["analyst"])
    client.force_login(operational["analyst"])
    assert len(client.get("/minhas-analises/").context["eval_items"]) == 1
    EvaluationService.save_draft(
        evaluation,
        [{"check_result_id": evaluation.check_results.get().pk, "status": "ATENDE"}],
        operational["analyst"],
    )
    EvaluationService.conclude_evaluation(evaluation, operational["analyst"])
    response = client.get("/minhas-analises/")
    assert response.context["eval_items"] == []
    assert response.context["completed_count"] == 1
    assert "Nenhuma análise pendente." in response.content.decode()
    response = client.get("/minhas-analises/?status=completed")
    assert len(response.context["eval_items"]) == 1
    assert response.context["show_completed"] is True


def test_review_justification_and_previous_decision_audit(domain):
    evaluation = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    check = evaluation.check_results.get()
    EvaluationService.save_draft(
        evaluation, [{"check_result_id": check.pk, "status": "NAO_ATENDE"}], domain["analyst"]
    )
    EvaluationService.conclude_evaluation(evaluation, domain["analyst"])
    review = ReviewService.claim_review(evaluation.review, domain["reviewer"])
    with pytest.raises(ValidationError):
        ReviewService.record_effective_status(review, check.pk, "ATENDE", "", domain["reviewer"])
    decision = ReviewService.record_effective_status(
        review, check.pk, "ATENDE", "Primeira decisão", domain["reviewer"]
    )
    ReviewService.record_effective_status(
        review, check.pk, "NAO_ATENDE", "Conferência posterior", domain["reviewer"]
    )
    event = AuditEvent.objects.filter(
        entity_type="ReviewItemDecision", entity_id=str(decision.pk)
    ).latest("pk")
    assert "Primeira decisão" in event.old_value
    assert "Conferência posterior" in event.new_value


def test_top_failed_checks_counts_completed_original_decisions(domain):
    from apps.reporting.services.metrics import DashboardMetricsService

    evaluation = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    EvaluationService.save_draft(
        evaluation,
        [{"check_result_id": evaluation.check_results.get().pk, "status": "NAO_ATENDE"}],
        domain["analyst"],
    )
    assert DashboardMetricsService.get_top_failed_checks(domain["edital"]) == []
    EvaluationService.conclude_evaluation(evaluation, domain["analyst"])
    top = DashboardMetricsService.get_top_failed_checks(domain["edital"])
    assert top[0]["code"] == domain["check"].code
    assert top[0]["failure_count"] == 1


@pytest.mark.parametrize("failure_behavior", ["MARK_INELIGIBLE", "NONE"])
def test_every_failed_mandatory_check_reaches_review(domain, failure_behavior):
    requirement = domain["check"].requirement
    requirement.failure_behavior = failure_behavior
    requirement.save()
    evaluation = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    EvaluationService.save_draft(
        evaluation,
        [{"check_result_id": evaluation.check_results.get().pk, "status": "NAO_ATENDE"}],
        domain["analyst"],
    )
    EvaluationService.conclude_evaluation(evaluation, domain["analyst"])
    domain["sub"].refresh_from_db()
    assert domain["sub"].workflow_status == "PENDING_REVIEW"
    assert Review.objects.get(evaluation=evaluation).status == "PENDING"


def test_historical_not_sent_is_preserved_and_requires_current_decision(domain):
    evaluation = EvaluationService.start_evaluation(domain["sub"], domain["analyst"])
    # Historical importer compatibility; new drafts cannot introduce this status.
    evaluation.check_results.update(status="NAO_ENVIADO")
    result = evaluation.check_results.get()
    EvaluationService.save_draft(
        evaluation,
        [{"check_result_id": result.pk, "status": "NAO_ENVIADO", "notes": "Histórico preservado"}],
        domain["analyst"],
    )
    result.refresh_from_db()
    assert result.status == "NAO_ENVIADO"
    with pytest.raises(InconsistentEvaluationError):
        EvaluationService.conclude_evaluation(evaluation, domain["analyst"])
    EvaluationService.save_draft(
        evaluation, [{"check_result_id": result.pk, "status": "NAO_ATENDE"}], domain["analyst"]
    )
    EvaluationService.conclude_evaluation(evaluation, domain["analyst"])
    assert Review.objects.filter(evaluation=evaluation).exists()


@pytest.mark.parametrize("role", ["admin", "coord"])
def test_no_active_edital_displays_clear_operational_error(client, domain, role):
    client.force_login(domain[role])
    response = client.get("/")
    assert response.status_code == 503
    assert "Nenhum edital ativo" in response.content.decode()
    assert not Evaluation.objects.exists()
