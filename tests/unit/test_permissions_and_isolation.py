import pytest
from django.core.exceptions import PermissionDenied
from django.http import HttpRequest
from django.utils import timezone

from apps.accounts.models import User
from apps.accounts.permissions import (
    RolePermissionPolicy,
    ScopedQuerySetSelector,
    enforce_evaluation_edit_access,
    enforce_submission_access,
    require_role,
)
from apps.editais.models import Edital
from apps.evaluations.models import Evaluation
from apps.institutions.models import Institution, Municipality
from apps.submissions.models import Assignment, Submission


@pytest.mark.django_db
class TestPermissionsAndAnalystIsolation:
    @pytest.fixture
    def setup_users(self):
        analyst_a = User.objects.create_user(
            username="analista_a",
            email="a@mds.gov.br",
            role=User.Role.ANALISTA,
        )
        analyst_b = User.objects.create_user(
            username="analista_b",
            email="b@mds.gov.br",
            role=User.Role.ANALISTA,
        )
        coord = User.objects.create_user(
            username="coord_user",
            email="coord@mds.gov.br",
            role=User.Role.COORDENADOR,
        )
        distrib = User.objects.create_user(
            username="distrib_user",
            email="distrib@mds.gov.br",
            role=User.Role.DISTRIBUIDOR,
        )
        revisor = User.objects.create_user(
            username="revisor_user",
            email="revisor@mds.gov.br",
            role=User.Role.REVISOR,
        )
        consulta = User.objects.create_user(
            username="consulta_user",
            email="consulta@mds.gov.br",
            role=User.Role.CONSULTA,
        )
        return {
            "a": analyst_a,
            "b": analyst_b,
            "coord": coord,
            "distrib": distrib,
            "revisor": revisor,
            "consulta": consulta,
        }

    @pytest.fixture
    def setup_submissions(self, setup_users):
        mun = Municipality.objects.create(ibge_code="3550308", name="SP", state="SP")
        inst = Institution.objects.create(cnpj="00000000000191", name="OSC Alpha", municipality=mun)
        now = timezone.now()
        edital = Edital.objects.create(
            name="Edital", number="01", year=2024, opens_at=now, closes_at=now
        )

        sub_a = Submission.objects.create(
            edital=edital,
            institution=inst,
            processo_sei="71000.001",
            received_at=now,
            municipality=mun,
            workflow_status=Submission.WorkflowStatus.ASSIGNED,
        )
        Assignment.objects.create(
            submission=sub_a,
            analyst=setup_users["a"],
            assigned_by=setup_users["coord"],
            status=Assignment.Status.ACTIVE,
        )

        sub_b = Submission.objects.create(
            edital=edital,
            institution=inst,
            processo_sei="71000.002",
            received_at=now,
            municipality=mun,
            workflow_status=Submission.WorkflowStatus.ASSIGNED,
        )
        Assignment.objects.create(
            submission=sub_b,
            analyst=setup_users["b"],
            assigned_by=setup_users["coord"],
            status=Assignment.Status.ACTIVE,
        )

        eval_a = Evaluation.objects.create(
            submission=sub_a,
            analyst=setup_users["a"],
            status=Evaluation.Status.DRAFT,
        )
        eval_b = Evaluation.objects.create(
            submission=sub_b,
            analyst=setup_users["b"],
            status=Evaluation.Status.DRAFT,
        )

        return {
            "sub_a": sub_a,
            "sub_b": sub_b,
            "eval_a": eval_a,
            "eval_b": eval_b,
        }

    def test_analyst_queryset_isolation(self, setup_users, setup_submissions):
        # Analista A só vê o processo A
        qs_a = ScopedQuerySetSelector.for_submissions(setup_users["a"])
        assert qs_a.count() == 1
        assert setup_submissions["sub_a"] in qs_a
        assert setup_submissions["sub_b"] not in qs_a

        # Analista B só vê o processo B
        qs_b = ScopedQuerySetSelector.for_submissions(setup_users["b"])
        assert qs_b.count() == 1
        assert setup_submissions["sub_b"] in qs_b
        assert setup_submissions["sub_a"] not in qs_b

        # Coordenador vê ambos
        qs_coord = ScopedQuerySetSelector.for_submissions(setup_users["coord"])
        assert qs_coord.count() == 2

    def test_analyst_cannot_access_other_analyst_submission(self, setup_users, setup_submissions):
        request = HttpRequest()
        request.user = setup_users["a"]

        # Acessar a própria submissão funciona
        res = enforce_submission_access(request, setup_submissions["sub_a"].id)
        assert res == setup_submissions["sub_a"]

        # Tentar acessar submissão do analista B levanta PermissionDenied
        with pytest.raises(PermissionDenied):
            enforce_submission_access(request, setup_submissions["sub_b"].id)

    def test_analyst_cannot_edit_other_analyst_evaluation(self, setup_users, setup_submissions):
        request = HttpRequest()
        request.user = setup_users["a"]

        # Editar própria avaliação em rascunho funciona
        res = enforce_evaluation_edit_access(request, setup_submissions["eval_a"].id)
        assert res == setup_submissions["eval_a"]

        # Tentar editar avaliação do analista B levanta PermissionDenied
        with pytest.raises(PermissionDenied):
            enforce_evaluation_edit_access(request, setup_submissions["eval_b"].id)

    def test_analyst_cannot_edit_concluded_evaluation(self, setup_users, setup_submissions):
        request = HttpRequest()
        request.user = setup_users["a"]
        eval_a = setup_submissions["eval_a"]

        # Marca como concluída
        eval_a.status = Evaluation.Status.COMPLETED
        eval_a.save()

        # Agora o próprio analista não pode mais editar
        with pytest.raises(PermissionDenied):
            enforce_evaluation_edit_access(request, eval_a.id)

    def test_role_permission_policies(self, setup_users):
        assert RolePermissionPolicy.can_distribute_submissions(setup_users["distrib"]) is True
        assert RolePermissionPolicy.can_distribute_submissions(setup_users["coord"]) is True
        assert RolePermissionPolicy.can_distribute_submissions(setup_users["a"]) is False

        assert RolePermissionPolicy.can_generate_ranking(setup_users["coord"]) is True
        assert RolePermissionPolicy.can_generate_ranking(setup_users["a"]) is False

        assert RolePermissionPolicy.can_conduct_review(setup_users["revisor"]) is True
        assert RolePermissionPolicy.can_conduct_review(setup_users["a"]) is False

    def test_require_role_decorator(self, setup_users):
        @require_role(User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
        def dummy_view(request):
            return "OK"

        req_coord = HttpRequest()
        req_coord.user = setup_users["coord"]
        assert dummy_view(req_coord) == "OK"

        req_analyst = HttpRequest()
        req_analyst.user = setup_users["a"]
        with pytest.raises(PermissionDenied):
            dummy_view(req_analyst)
