import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.editais.models import Edital, Requirement, RequirementCheck
from apps.evaluations.models import CheckResult, Evaluation
from apps.evaluations.services import (
    EvaluationService,
    InconsistentEvaluationError,
)
from apps.institutions.models import Institution, Municipality
from apps.submissions.models import Submission


@pytest.mark.django_db
class TestEvaluationService:
    @pytest.fixture
    def setup_data(self):
        analyst = User.objects.create_user(
            username="analista_eval",
            email="analista_eval@mds.gov.br",
            role=User.Role.ANALISTA,
        )
        mun = Municipality.objects.create(ibge_code="3550308", name="São Paulo", state="SP")
        inst = Institution.objects.create(
            cnpj="00000000000191", name="OSC Solidária", municipality=mun
        )
        now = timezone.now()
        edital = Edital.objects.create(
            name="Edital 2024",
            number="01",
            year=2024,
            opens_at=now,
            closes_at=now + timezone.timedelta(days=30),
        )
        req1 = Requirement.objects.create(
            edital=edital, code="4.2-I", name="Requerimento", mandatory=True, order=1
        )
        req2 = Requirement.objects.create(
            edital=edital, code="4.2-V", name="Estatuto", mandatory=True, order=2
        )
        req3 = Requirement.objects.create(
            edital=edital, code="4.2-X", name="Opcional", mandatory=False, order=3
        )

        c1 = RequirementCheck.objects.create(requirement=req1, code="4.2-I-01", name="Assinatura")
        c2 = RequirementCheck.objects.create(requirement=req2, code="4.2-V-01", name="Finalidade")
        c3 = RequirementCheck.objects.create(
            requirement=req3, code="4.2-X-01", name="Item facultativo"
        )

        sub = Submission.objects.create(
            edital=edital,
            institution=inst,
            processo_sei="71000.001/2024",
            received_at=now,
            municipality=mun,
            workflow_status=Submission.WorkflowStatus.UNDER_ANALYSIS,
        )
        eval_obj = EvaluationService.initialize_evaluation(sub, analyst)
        return {
            "analyst": analyst,
            "sub": sub,
            "eval_obj": eval_obj,
            "c1": c1,
            "c2": c2,
            "c3": c3,
        }

    def test_assessment_in_progress_when_unfilled(self, setup_data):
        eval_obj = setup_data["eval_obj"]
        assessment = EvaluationService.calculate_assessment(eval_obj)
        assert assessment.result == Evaluation.Result.EM_ANALISE
        assert assessment.is_complete is False
        assert assessment.pending_checks == 3
        assert assessment.failed_requirement_codes == []

    def test_assessment_inapta_when_mandatory_fails(self, setup_data):
        eval_obj = setup_data["eval_obj"]
        c1 = setup_data["c1"]
        c2 = setup_data["c2"]

        CheckResult.objects.filter(evaluation=eval_obj, requirement_check=c1).update(
            status=CheckResult.Status.ATENDE
        )
        CheckResult.objects.filter(evaluation=eval_obj, requirement_check=c2).update(
            status=CheckResult.Status.NAO_ATENDE
        )

        assessment = EvaluationService.calculate_assessment(eval_obj)
        assert assessment.result == Evaluation.Result.INAPTA
        assert "4.2-V" in assessment.failed_requirement_codes

    def test_assessment_apta_when_all_mandatory_satisfactory(self, setup_data):
        eval_obj = setup_data["eval_obj"]
        c1 = setup_data["c1"]
        c2 = setup_data["c2"]
        c3 = setup_data["c3"]

        CheckResult.objects.filter(evaluation=eval_obj, requirement_check=c1).update(
            status=CheckResult.Status.ATENDE
        )
        CheckResult.objects.filter(evaluation=eval_obj, requirement_check=c2).update(
            status=CheckResult.Status.ATENDE
        )
        CheckResult.objects.filter(evaluation=eval_obj, requirement_check=c3).update(
            status=CheckResult.Status.NAO_APLICAVEL
        )

        assessment = EvaluationService.calculate_assessment(eval_obj)
        assert assessment.result == Evaluation.Result.APTA
        assert assessment.is_complete is True
        assert assessment.failed_requirement_codes == []

    def test_conclude_evaluation_raises_when_checks_pending(self, setup_data):
        eval_obj = setup_data["eval_obj"]
        analyst = setup_data["analyst"]

        with pytest.raises(InconsistentEvaluationError):
            EvaluationService.conclude_evaluation(eval_obj, actor=analyst)

    def test_conclude_evaluation_advances_workflow(self, setup_data):
        eval_obj = setup_data["eval_obj"]
        analyst = setup_data["analyst"]
        sub = setup_data["sub"]
        c1 = setup_data["c1"]
        c2 = setup_data["c2"]
        c3 = setup_data["c3"]

        # Preenche todas
        for c in (c1, c2, c3):
            CheckResult.objects.filter(evaluation=eval_obj, requirement_check=c).update(
                status=CheckResult.Status.ATENDE
            )

        concluded = EvaluationService.conclude_evaluation(eval_obj, actor=analyst)
        assert concluded.status == Evaluation.Status.COMPLETED
        assert concluded.result == Evaluation.Result.APTA

        sub.refresh_from_db()
        assert sub.workflow_status == Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING
        assert not hasattr(concluded, "review")
