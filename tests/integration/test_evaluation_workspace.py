import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.editais.models import Edital, Requirement, RequirementCheck
from apps.evaluations.models import CheckResult, Evaluation
from apps.institutions.models import Institution, Municipality
from apps.submissions.models import Assignment, Submission


@pytest.mark.django_db
class TestEvaluationWorkspaceIntegration:
    @pytest.fixture
    def setup_data(self):
        analyst_a = User.objects.create_user(
            username="analyst_ws_a", email="a@mds.gov.br", role=User.Role.ANALISTA
        )
        analyst_b = User.objects.create_user(
            username="analyst_ws_b", email="b@mds.gov.br", role=User.Role.ANALISTA
        )
        coord = User.objects.create_user(
            username="coord_ws", email="c@mds.gov.br", role=User.Role.COORDENADOR
        )

        mun = Municipality.objects.create(ibge_code="3550308", name="São Paulo", state="SP")
        inst = Institution.objects.create(
            cnpj="00000000000191", name="OSC Estudo", municipality=mun
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
            processo_sei="71000.111/2024",
            received_at=now,
            municipality=mun,
            workflow_status=Submission.WorkflowStatus.ASSIGNED,
        )
        Assignment.objects.create(
            submission=sub,
            analyst=analyst_a,
            assigned_by=coord,
            status=Assignment.Status.ACTIVE,
        )

        return {
            "a": analyst_a,
            "b": analyst_b,
            "coord": coord,
            "sub": sub,
            "req": req,
            "check": check,
        }

    def test_my_evaluations_view(self, client, setup_data):
        client.force_login(setup_data["a"])
        response = client.get(reverse("my-evaluations"))
        assert response.status_code == 200
        assert "71000.111/2024" in response.content.decode("utf-8")

        # Analista B não vê o processo de A
        client.force_login(setup_data["b"])
        response_b = client.get(reverse("my-evaluations"))
        assert response_b.status_code == 200
        assert "71000.111/2024" not in response_b.content.decode("utf-8")

    def test_workspace_view_rendering_and_draft_save(self, client, setup_data):
        analyst_a = setup_data["a"]
        sub = setup_data["sub"]
        check = setup_data["check"]

        client.force_login(analyst_a)
        # Abre o workspace
        url_ws = reverse("evaluation-workspace", kwargs={"submission_id": sub.id})
        client.post(reverse("evaluation-start", args=[sub.id]))
        response = client.get(url_ws)
        assert response.status_code == 200
        assert "4.2-I" in response.content.decode("utf-8")

        eval_obj = Evaluation.objects.get(submission=sub)

        # Salva rascunho com HTMX
        url_draft = reverse("evaluation-save-draft", kwargs={"evaluation_id": eval_obj.id})
        post_data = {
            f"check_{check.id}_status": CheckResult.Status.ATENDE,
            f"check_{check.id}_sei_number": "DOC-SEI-9988",
            "general_notes": "Rascunho inicial testado",
        }
        res_draft = client.post(url_draft, post_data, HTTP_HX_REQUEST="true")
        assert res_draft.status_code == 200

        cr = CheckResult.objects.get(evaluation=eval_obj, requirement_check=check)
        assert cr.status == CheckResult.Status.ATENDE
        assert cr.sei_number == "DOC-SEI-9988"

    def test_conclude_evaluation_flow(self, client, setup_data):
        analyst_a = setup_data["a"]
        sub = setup_data["sub"]
        check = setup_data["check"]

        client.force_login(analyst_a)
        from apps.evaluations.services import EvaluationService

        eval_obj = EvaluationService.start_evaluation(sub, analyst=analyst_a)

        # Marca check como ATENDE
        CheckResult.objects.filter(evaluation=eval_obj, requirement_check=check).update(
            status=CheckResult.Status.ATENDE
        )

        url_conclude = reverse("evaluation-conclude", kwargs={"evaluation_id": eval_obj.id})
        response = client.post(url_conclude, {"general_notes": "Conclusão com sucesso"})
        assert response.status_code == 302

        eval_obj.refresh_from_db()
        assert eval_obj.status == Evaluation.Status.COMPLETED
        assert eval_obj.result == Evaluation.Result.APTA

        sub.refresh_from_db()
        assert sub.workflow_status == Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING

    def test_analyst_b_forbidden_from_analyst_a_workspace(self, client, setup_data):
        analyst_b = setup_data["b"]
        sub = setup_data["sub"]

        client.force_login(analyst_b)
        url_ws = reverse("evaluation-workspace", kwargs={"submission_id": sub.id})
        client.post(reverse("evaluation-start", args=[sub.id]))
        response = client.get(url_ws)
        # Negação de acesso
        assert response.status_code == 403
