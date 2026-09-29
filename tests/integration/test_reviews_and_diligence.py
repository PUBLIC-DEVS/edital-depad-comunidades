import datetime

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.editais.models import Edital, Requirement, RequirementCheck
from apps.evaluations.models import CheckResult
from apps.evaluations.services import EvaluationService
from apps.institutions.models import Institution, Municipality
from apps.reviews.models import Diligence, Review
from apps.reviews.services import ReviewService
from apps.submissions.models import Assignment, Submission


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

    def test_diligence_workflow_and_views(self, client, setup_data):
        reviewer = setup_data["reviewer"]
        sub = setup_data["sub"]
        client.force_login(reviewer)

        # Abre diligência via view
        url_create = reverse("diligence-create", kwargs={"submission_id": sub.id})
        deadline_str = (timezone.now().date() + datetime.timedelta(days=10)).strftime("%Y-%m-%d")
        res_create = client.post(
            url_create,
            {"reason": "Apresentar certidão municipal atualizada.", "deadline": deadline_str},
        )
        assert res_create.status_code == 302

        sub.refresh_from_db()
        assert sub.workflow_status == Submission.WorkflowStatus.PENDING_DILIGENCE

        diligence = Diligence.objects.get(submission=sub)
        assert diligence.status == Diligence.Status.OPEN

        # Julga e conclui diligência
        url_detail = reverse("diligence-detail", kwargs={"diligence_id": diligence.id})
        res_conclude = client.post(
            url_detail,
            {
                "response": "Certidão apresentada no doc SEI 7788.",
                "result": Diligence.Result.SANEADA,
            },
        )
        assert res_conclude.status_code == 302

        diligence.refresh_from_db()
        assert diligence.status == Diligence.Status.CONCLUDED
        assert diligence.result == Diligence.Result.SANEADA

        sub.refresh_from_db()
        assert sub.workflow_status == Submission.WorkflowStatus.PENDING_REVIEW

        # Verifica evento de auditoria gerado
        audit_exists = AuditEvent.objects.filter(
            entity_type="Submission", entity_id=str(sub.id)
        ).exists()
        assert audit_exists is True
