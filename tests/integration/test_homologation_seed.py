from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.editais.edital_2026 import DOCUMENTS_2026
from apps.editais.models import Edital, Requirement, RequirementCheck
from apps.evaluations.models import CheckResult, Evaluation
from apps.evaluations.services import EvaluationService
from apps.institutions.cnpj import validate_cnpj
from apps.institutions.models import Institution, Municipality
from apps.ranking.models import RankingSnapshot
from apps.reporting.services.metrics import DashboardMetricsService
from apps.reviews.models import Diligence, Review, ReviewItemDecision
from apps.reviews.services import ReviewService
from apps.submissions.management.commands.seed_homologation import LOCAL_PASSWORD, ROLES
from apps.submissions.models import Assignment, Submission

pytestmark = pytest.mark.django_db


@pytest.fixture
def seeded(settings):
    settings.DEBUG = True
    settings.AUTH_ADAPTER = "local"
    call_command("seed_homologation", stdout=StringIO())
    return Edital.objects.get(status="ACTIVE")


def test_seed_provides_documentary_structure_and_representative_scenarios(seeded):
    assert Edital.objects.filter(status="ACTIVE").count() == 1
    assert seeded.requirements.count() == 14
    assert RequirementCheck.objects.filter(requirement__edital=seeded).count() == 23
    assert list(seeded.requirements.values_list("code", flat=True)) == [
        d["code"] for d in DOCUMENTS_2026
    ]
    assert Submission.objects.count() == 8
    assert set(Submission.objects.values_list("target_group", flat=True)) == {"G1", "G2", "G3"}
    assert all(
        validate_cnpj(cnpj) and cnpj.startswith("HOMOLOG")
        for cnpj in Institution.objects.values_list("cnpj", flat=True)
    )
    partial = Evaluation.objects.get(submission__processo_sei="HOMOLOG-2026-002")
    assert partial.status == "DRAFT"
    assert partial.check_results.exclude(status="EM_BRANCO").count() == 17
    new = Evaluation.objects.get(submission__processo_sei="HOMOLOG-2026-003")
    assert new.check_results.filter(status="EM_BRANCO").count() == 23
    review = Review.objects.get(submission__processo_sei="HOMOLOG-2026-004")
    assert review.status == "PENDING"
    assert review.submission.workflow_status == "PENDING_REVIEW"
    assert review.evaluation.check_results.filter(status="NAO_ATENDE").count() == 3
    final = Review.objects.get(submission__processo_sei="HOMOLOG-2026-006")
    assert final.status == "COMPLETED"
    assert final.submission.workflow_status == "INELIGIBLE"
    assert final.evaluation.check_results.filter(status="NAO_ATENDE").count() == 3
    assert final.item_decisions.count() == 3
    assert Diligence.objects.count() == 0
    assert set(RankingSnapshot.objects.get().entries.values_list("target_group", flat=True)) == {
        "G1",
        "G2",
        "G3",
    }
    metrics = DashboardMetricsService.get_summary_metrics()
    assert [
        metrics[key]
        for key in (
            "total_received",
            "unassigned_count",
            "under_analysis",
            "pending_review",
            "apt_count",
            "inapt_count",
        )
    ] == [8, 1, 2, 1, 3, 1]
    assert metrics["by_group"] == {"G1": 3, "G2": 3, "G3": 2, "SEM_GRUPO": 0}
    assert metrics["show_timeline"] is True
    assert sum(row["count"] for row in metrics["timeline"]) == 8
    assert len(DashboardMetricsService.get_top_failed_checks()) == 3


def test_seed_second_run_preserves_human_work_and_counts(seeded):
    analyst = User.objects.get(username="homolog.analista")
    evaluation = Evaluation.objects.get(submission__processo_sei="HOMOLOG-2026-003")
    result = evaluation.check_results.first()
    EvaluationService.save_draft(
        evaluation,
        [
            {
                "check_result_id": result.pk,
                "status": "NAO_ATENDE",
                "notes": "Decisão humana a preservar",
            }
        ],
        analyst,
    )
    reviewer = User.objects.get(username="homolog.revisor")
    review = ReviewService.claim_review(Review.objects.get(status="PENDING"), reviewer)
    failed = review.evaluation.check_results.filter(status="NAO_ATENDE").first()
    decision = ReviewService.record_effective_status(
        review, failed.pk, "ATENDE", "Justificativa humana", reviewer
    )
    analyst.set_password("Senha.alterada#Local")
    analyst.save()
    models = (
        User,
        Edital,
        Municipality,
        Institution,
        Submission,
        Requirement,
        RequirementCheck,
        Assignment,
        Evaluation,
        CheckResult,
        Review,
        ReviewItemDecision,
        RankingSnapshot,
        AuditEvent,
    )
    counts = [model.objects.count() for model in models]
    original = list(review.evaluation.check_results.values())
    output = StringIO()
    call_command("seed_homologation", stdout=output)
    assert [model.objects.count() for model in models] == counts
    assert "já existente" in output.getvalue()
    result.refresh_from_db()
    assert result.status == "NAO_ATENDE" and result.notes == "Decisão humana a preservar"
    decision.refresh_from_db()
    assert decision.reviewer_status == "ATENDE" and decision.justification == "Justificativa humana"
    assert list(review.evaluation.check_results.values()) == original
    analyst.refresh_from_db()
    assert analyst.check_password("Senha.alterada#Local")


def test_documented_homologation_credentials_authenticate(client, seeded):
    for key, role in ROLES.items():
        client.logout()
        assert client.login(username=f"homolog.{key}", password=LOCAL_PASSWORD), key
        assert User.objects.get(username=f"homolog.{key}").role == role
        assert client.get("/", follow=True).status_code == 200


def test_seed_refuses_another_active_edital_without_changes(settings):
    settings.DEBUG = True
    call_command("seed_demo", stdout=StringIO())
    counts = (User.objects.count(), Submission.objects.count(), AuditEvent.objects.count())
    with pytest.raises(CommandError, match="Outro edital ACTIVE"):
        call_command("seed_homologation", stdout=StringIO())
    assert Edital.objects.count() == 1
    assert (User.objects.count(), Submission.objects.count(), AuditEvent.objects.count()) == counts
    assert not User.objects.filter(username__startswith="homolog.").exists()


@pytest.mark.parametrize("debug,adapter", [(False, "local"), (True, "microsoft")])
def test_seed_refuses_production_settings(settings, debug, adapter):
    settings.DEBUG = debug
    settings.AUTH_ADAPTER = adapter
    with pytest.raises(CommandError, match="Somente desenvolvimento local"):
        call_command("seed_homologation", stdout=StringIO())
    assert User.objects.count() == Edital.objects.count() == 0


def test_seed_does_not_overwrite_colliding_account(settings):
    settings.DEBUG = True
    user = User.objects.create_user(
        username="homolog.admin", role="CONSULTA", password="Preservar#2026"
    )
    with pytest.raises(CommandError, match="Contas homolog"):
        call_command("seed_homologation", stdout=StringIO())
    user.refresh_from_db()
    assert user.role == "CONSULTA" and user.check_password("Preservar#2026")
    assert Edital.objects.count() == 0


def test_seed_rolls_back_if_configuration_fails(settings, monkeypatch):
    from apps.editais.services import EditalConfigurationService

    settings.DEBUG = True

    def fail(*args):
        raise CommandError("Test configuration failure")

    monkeypatch.setattr(EditalConfigurationService, "publish", fail)
    with pytest.raises(CommandError, match="Test configuration failure"):
        call_command("seed_homologation", stdout=StringIO())
    assert User.objects.count() == Edital.objects.count() == AuditEvent.objects.count() == 0


def test_homologation_keeps_diligence_disabled(client, seeded):
    client.login(username="homolog.revisor", password=LOCAL_PASSWORD)
    assert client.get("/diligencias/").status_code == 404
    assert client.post("/diligencias/processo/4/abrir/", {"reason": "Blocked"}).status_code == 404
    assert Diligence.objects.count() == 0
