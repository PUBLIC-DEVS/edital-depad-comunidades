import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.editais.models import Edital
from apps.institutions.models import Institution, Municipality
from apps.reviews.models import Diligence
from apps.submissions.models import Assignment, Submission
from apps.submissions.services import (
    InvalidWorkflowTransitionError,
    WorkflowService,
)


@pytest.mark.django_db
class TestWorkflowService:
    @pytest.fixture
    def setup_data(self):
        user1 = User.objects.create_user(
            username="analista_wf1", email="wf1@mds.gov.br", role=User.Role.ANALISTA
        )
        user2 = User.objects.create_user(
            username="analista_wf2", email="wf2@mds.gov.br", role=User.Role.ANALISTA
        )
        coord = User.objects.create_user(
            username="coord_wf", email="coord@mds.gov.br", role=User.Role.COORDENADOR
        )

        mun = Municipality.objects.create(ibge_code="5208707", name="Goiânia", state="GO")
        inst = Institution.objects.create(
            cnpj="00000000000191", name="Entidade GO", municipality=mun
        )
        now = timezone.now()
        edital = Edital.objects.create(
            name="Edital 2024",
            number="01",
            year=2024,
            opens_at=now,
            closes_at=now + timezone.timedelta(days=30),
        )
        sub = Submission.objects.create(
            edital=edital,
            institution=inst,
            processo_sei="71000.999/2024",
            received_at=now,
            municipality=mun,
            workflow_status=Submission.WorkflowStatus.RECEIVED,
        )
        return {"sub": sub, "user1": user1, "user2": user2, "coord": coord}

    def test_valid_transition_and_audit(self, setup_data):
        sub = setup_data["sub"]
        coord = setup_data["coord"]

        WorkflowService.transition(
            submission=sub,
            target_status=Submission.WorkflowStatus.ASSIGNED,
            actor=coord,
            reason="Iniciando distribuição",
        )
        sub.refresh_from_db()
        assert sub.workflow_status == Submission.WorkflowStatus.ASSIGNED

        event = AuditEvent.objects.filter(entity_type="Submission", entity_id=str(sub.id)).first()
        assert event is not None
        assert event.action == "WORKFLOW_TRANSITION"
        assert event.old_value == Submission.WorkflowStatus.RECEIVED
        assert event.new_value == Submission.WorkflowStatus.ASSIGNED
        assert event.metadata["reason"] == "Iniciando distribuição"

    def test_invalid_transition_raises_error(self, setup_data):
        sub = setup_data["sub"]
        coord = setup_data["coord"]

        # Não pode ir de RECEIVED direto para RANKED
        with pytest.raises(InvalidWorkflowTransitionError):
            WorkflowService.transition(
                submission=sub,
                target_status=Submission.WorkflowStatus.RANKED,
                actor=coord,
            )

    def test_assign_and_reassign_analyst(self, setup_data):
        sub = setup_data["sub"]
        coord = setup_data["coord"]
        user1 = setup_data["user1"]
        user2 = setup_data["user2"]

        # Primeira atribuição
        asgn1 = WorkflowService.assign_analyst(sub, user1, coord, reason="Primeira carga")
        sub.refresh_from_db()
        assert sub.workflow_status == Submission.WorkflowStatus.ASSIGNED
        assert sub.assigned_analyst == user1
        assert asgn1.status == Assignment.Status.ACTIVE

        # Redistribuição
        asgn2 = WorkflowService.reassign_analyst(sub, user2, coord, reason="Rebalanceamento")
        sub.refresh_from_db()
        asgn1.refresh_from_db()

        assert asgn1.status == Assignment.Status.REASSIGNED
        assert asgn1.ended_at is not None
        assert asgn2.status == Assignment.Status.ACTIVE
        assert sub.assigned_analyst == user2

    def test_diligence_lifecycle_disabled(self, setup_data):
        from django.core.exceptions import ValidationError

        sub, coord = setup_data["sub"], setup_data["coord"]
        WorkflowService.transition(sub, Submission.WorkflowStatus.ASSIGNED, coord)
        WorkflowService.transition(sub, Submission.WorkflowStatus.UNDER_ANALYSIS, coord)
        with pytest.raises(ValidationError, match="desativad"):
            WorkflowService.open_diligence(sub, coord, "Falta certidão", timezone.now().date())
        sub.refresh_from_db()
        assert sub.workflow_status == "UNDER_ANALYSIS"
        assert not Diligence.objects.exists()
