import datetime

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.editais.models import Edital, Requirement, RequirementCheck
from apps.evaluations.models import CheckResult, Evaluation
from apps.evaluations.services import EvaluationService
from apps.institutions.models import Institution, Municipality
from apps.reviews.models import Diligence, Review
from apps.reviews.services import ReviewService
from apps.submissions.models import Assignment, Submission
from apps.submissions.services.workflow import WorkflowService


@pytest.mark.django_db
class TestReviewsAndDiligenceIntegration:
    @pytest.fixture
    def setup_data(self):
        analyst = User.objects.create_user(
            username="analyst_rev", email="an_rev@mds.gov.br", role=User.Role.ANALISTA
        )
        reviewer = User.objects.create_user(
            username="reviewer_user", email="rev_u@mds.gov.br", role=User.Role.REVISOR
        )
        coord = User.objects.create_user(
            username="coord_rev", email="c_rev@mds.gov.br", role=User.Role.COORDENADOR
        )

        mun = Municipality.objects.create(ibge_code="3550308", name="São Paulo", state="SP")
        inst = Institution.objects.create(
            cnpj="00000000000191", name="OSC Revisada", municipality=mun
        )
        now = timezone.now()
        edital = Edital.objects.create(
            name="Edital 2024", number="01", year=2024, opens_at=now, closes_at=now
        )

        req = Requirement.objects.create(
            edital=edital, code="4.2-I", name="Requerimento", mandatory=True
        )
        check = RequirementCheck.objects.create(requirement=req, code="4.2-I-01", name="Assinatura")

        sub = Submission.objects.create(
            edital=edital,
            institution=inst,
            processo_sei="71000.333/2024",
            received_at=now,
            municipality=mun,
            workflow_status=Submission.WorkflowStatus.ASSIGNED,
        )
        Assignment.objects.create(
            submission=sub, analyst=analyst, assigned_by=coord, status=Assignment.Status.ACTIVE
        )

        eval_obj = EvaluationService.start_evaluation(sub, analyst=analyst)
        CheckResult.objects.filter(evaluation=eval_obj, requirement_check=check).update(
            status=CheckResult.Status.NAO_ATENDE,
            sei_number="DOC-1234",
        )
        EvaluationService.conclude_evaluation(eval_obj, actor=analyst)
        sub.refresh_from_db()
        review = ReviewService.claim_review(Review.objects.get(submission=sub), reviewer)

        from tests.operational_helpers import publish_fixture

        publish_fixture(edital)

        return {
            "analyst": analyst,
            "reviewer": reviewer,
            "coord": coord,
            "sub": sub,
            "eval_obj": eval_obj,
            "check": check,
            "review": review,
        }

    def test_review_queue_and_detail_views(self, client, setup_data):
        client.force_login(setup_data["reviewer"])
        # Lista de revisões
        res_list = client.get(reverse("review-list"))
        assert res_list.status_code == 200
        assert "71000.333/2024" in res_list.content.decode("utf-8")

        # Detalhe da revisão
        url_det = reverse("review-detail", kwargs={"review_id": setup_data["review"].id})
        res_det = client.get(url_det)
        assert res_det.status_code == 200
        assert "DOC-1234" in res_det.content.decode("utf-8")

    def test_review_item_decision_agreement_and_divergence(self, setup_data):
        review = setup_data["review"]
        check_result = CheckResult.objects.get(evaluation=review.evaluation)

        # 1. Concordância simples
        dec1 = ReviewService.record_item_decision(
            review=review,
            check_result_id=check_result.id,
            agrees_with_analyst=True,
            actor=setup_data["reviewer"],
        )
        assert dec1.agrees_with_analyst is True

        # 2. Divergência sem justificativa DEVE falhar
        with pytest.raises(ValidationError):
            ReviewService.record_item_decision(
                review=review,
                check_result_id=check_result.id,
                agrees_with_analyst=False,
                reviewer_status="NAO_ATENDE",
                justification="",
                actor=setup_data["reviewer"],
            )

        # 3. Divergência com justificativa tem sucesso
        dec2 = ReviewService.record_item_decision(
            review=review,
            check_result_id=check_result.id,
            agrees_with_analyst=False,
            reviewer_status="NAO_ATENDE",
            justification="Documento ilegível na folha 3",
            actor=setup_data["reviewer"],
        )
        assert dec2.agrees_with_analyst is False
        assert dec2.reviewer_status == "NAO_ATENDE"

    def test_conclude_review_transitions_submission(self, setup_data):
        review = setup_data["review"]
        reviewer = setup_data["reviewer"]
        sub = setup_data["sub"]

        ReviewService.record_item_decision(
            review,
            CheckResult.objects.get(evaluation=review.evaluation).pk,
            False,
            "ATENDE",
            "Documento comprovado na revisão.",
            reviewer,
        )

        ReviewService.conclude_review(
            review=review,
            preliminary_result=Review.PreliminaryResult.PRE_HABILITADO,
            decision_notes="Parecer integralmente acatado e validado.",
            actor=reviewer,
        )

        review.refresh_from_db()
        assert review.status == Review.Status.COMPLETED
        assert review.preliminary_result == Review.PreliminaryResult.PRE_HABILITADO

        sub.refresh_from_db()
        assert sub.workflow_status == Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING

    def test_diligence_workflow_and_views_disabled(self, client, setup_data):
        sub = setup_data["sub"]
        client.force_login(setup_data["reviewer"])
        assert client.get(reverse("diligence-list")).status_code == 404
        assert (
            client.post(
                reverse("diligence-create", args=[sub.pk]),
                {"reason": "Complemento", "deadline": "2026-12-01"},
            ).status_code
            == 404
        )
        sub.refresh_from_db()
        assert sub.workflow_status == "PENDING_REVIEW"
        assert not Diligence.objects.exists()

    def test_diligence_related_check_result_cannot_start_request(self, client, setup_data):
        client.force_login(setup_data["reviewer"])
        result = setup_data["eval_obj"].check_results.get()
        assert (
            client.post(
                reverse("diligence-create", args=[setup_data["sub"].pk]),
                {
                    "related_check_results": [result.pk],
                    "reason": "Conferir",
                    "deadline": "2026-12-01",
                },
            ).status_code
            == 404
        )
        assert not Diligence.objects.exists()

    def test_diligence_rejects_foreign_check_result_id(self, setup_data):
        current = setup_data["sub"]
        foreign_institution = Institution.objects.create(cnpj="11222333000181", name="Outra OSC")
        foreign_submission = Submission.objects.create(
            edital=current.edital,
            institution=foreign_institution,
            processo_sei="71000.FOREIGN/2024",
            received_at=timezone.now(),
            municipality=current.municipality,
        )
        foreign_evaluation = Evaluation.objects.create(
            submission=foreign_submission, analyst=setup_data["analyst"]
        )
        foreign_result = CheckResult.objects.create(
            evaluation=foreign_evaluation,
            requirement_check=setup_data["check"],
            status=CheckResult.Status.EM_BRANCO,
        )
        with pytest.raises(ValidationError, match="desativad"):
            WorkflowService.open_diligence(
                submission=current,
                requested_by=setup_data["reviewer"],
                reason="Diligência limitada ao processo atual.",
                deadline=timezone.now().date() + datetime.timedelta(days=10),
                related_check_result_ids=[foreign_result.pk],
            )
        assert not Diligence.objects.filter(submission=current).exists()
