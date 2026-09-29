from decimal import Decimal

import pytest
from django.core.exceptions import PermissionDenied
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent
from apps.editais.models import (
    Edital,
    FundingRule,
    ProgramMunicipality,
    Requirement,
    RequirementCheck,
)
from apps.evaluations.models import CheckResult, Evaluation
from apps.institutions.models import Institution, Municipality
from apps.ranking.models import RankingEntry, RankingSnapshot, _build_snapshot
from apps.reviews.models import Diligence, Review
from apps.submissions.models import Assignment, Submission


@pytest.mark.django_db
class TestDomainModels:
    @pytest.fixture
    def user(self):
        return User.objects.create_user(
            username="analista_test",
            email="analista@mds.gov.br",
            role=User.Role.ANALISTA,
        )

    @pytest.fixture
    def municipality(self):
        return Municipality.objects.create(
            ibge_code="5300108",
            name="Brasília",
            state="DF",
        )

    @pytest.fixture
    def institution(self, municipality):
        return Institution.objects.create(
            cnpj="00000000000191",
            name="Instituição Modelo de Teste",
            trade_name="Modelo Teste",
            municipality=municipality,
        )

    @pytest.fixture
    def edital(self):
        now = timezone.now()
        return Edital.objects.create(
            name="Edital Comunidades Terapêuticas",
            number="01",
            year=2024,
            opens_at=now,
            closes_at=now + timezone.timedelta(days=30),
            rules_version="1.0",
        )

    def test_municipality_and_institution(self, municipality, institution):
        assert str(municipality) == "Brasília/DF (5300108)"
        assert institution.formatted_cnpj == "00.000.000/0001-91"
        assert str(institution) == "Instituição Modelo de Teste - 00.000.000/0001-91"

    def test_edital_requirements_and_checks(self, edital):
        req = Requirement.objects.create(
            edital=edital,
            code="4.2-V",
            name="Estatuto Social",
            order=1,
            mandatory=True,
        )
        check1 = RequirementCheck.objects.create(
            requirement=req,
            code="4.2-V-a",
            name="Finalidade de acolhimento",
            order=1,
        )
        assert str(req) == "4.2-V — Estatuto Social"
        assert str(check1) == "4.2-V / 4.2-V-a: Finalidade de acolhimento"

    def test_funding_rule(self, edital):
        rule = FundingRule.objects.create(
            edital=edital,
            vacancy_type="FEMALE",
            monthly_value=Decimal("2000.00"),
            duration_months=12,
        )
        assert rule.monthly_value == Decimal("2000.00")

    def test_program_municipality(self, edital, municipality):
        prog = ProgramMunicipality.objects.create(
            edital=edital,
            municipality=municipality,
            program_name="PRONASCI",
        )
        assert prog.active is True
        assert "PRONASCI" in str(prog)

    def test_submission_and_assignment(self, edital, institution, municipality, user):
        sub = Submission.objects.create(
            edital=edital,
            institution=institution,
            processo_sei="71000.012345/2024-00",
            received_at=timezone.now(),
            municipality=municipality,
            vagas_femininas=10,
            vagas_masculinas=20,
            vagas_maes_nutrizes=5,
            vagas_solicitadas=35,
        )
        assert sub.computed_total_vagas == 35
        assert sub.workflow_status == Submission.WorkflowStatus.RECEIVED

        assignment = Assignment.objects.create(
            submission=sub,
            analyst=user,
            assigned_by=user,
        )
        assert sub.current_assignment == assignment
        assert sub.assigned_analyst == user

    def test_evaluation_and_check_results(self, edital, institution, municipality, user):
        sub = Submission.objects.create(
            edital=edital,
            institution=institution,
            processo_sei="71000.012346/2024-01",
            received_at=timezone.now(),
            municipality=municipality,
        )
        req = Requirement.objects.create(
            edital=edital,
            code="4.2-I",
            name="Requerimento",
            order=1,
        )
        check = RequirementCheck.objects.create(
            requirement=req,
            code="4.2-I-01",
            name="Assinatura do representante",
        )

        eval_obj = Evaluation.objects.create(
            submission=sub,
            analyst=user,
        )
        check_res = CheckResult.objects.create(
            evaluation=eval_obj,
            requirement_check=check,
            status=CheckResult.Status.ATENDE,
            sei_number="DOC-SEI-1234",
        )
        assert check_res.status == CheckResult.Status.ATENDE

    def test_review_and_diligence(self, edital, institution, municipality, user):
        sub = Submission.objects.create(
            edital=edital,
            institution=institution,
            processo_sei="71000.012347/2024-02",
            received_at=timezone.now(),
            municipality=municipality,
        )
        eval_obj = Evaluation.objects.create(
            submission=sub,
            analyst=user,
        )
        rev = Review.objects.create(
            evaluation=eval_obj,
            submission=sub,
            reviewer=user,
            preliminary_result=Review.PreliminaryResult.PRE_HABILITADO,
        )
        assert rev.status == Review.Status.PENDING

        diligence = Diligence.objects.create(
            submission=sub,
            requested_by=user,
            reason="Apresentar certidão atualizada",
            deadline=timezone.now().date() + timezone.timedelta(days=5),
        )
        assert diligence.status == Diligence.Status.OPEN

    def test_ranking_snapshot_and_entry(self, edital, institution, municipality, user):
        sub = Submission.objects.create(
            edital=edital,
            institution=institution,
            processo_sei="71000.012348/2024-03",
            received_at=timezone.now(),
            municipality=municipality,
        )
        snapshot = RankingSnapshot.objects.create(
            edital=edital,
            generated_by=user,
            snapshot_type=RankingSnapshot.SnapshotType.PRELIMINAR,
            rules_version="1.0",
            duplicate_policy="KEEP_EARLIEST_SUBMISSION",
        )
        with _build_snapshot(snapshot):
            entry = RankingEntry.objects.create(
                snapshot=snapshot,
                submission=sub,
                target_group="G1",
                position=1,
                received_at=sub.received_at,
                total_vacancies=15,
                qualification_status="APTA",
            )
        assert entry.position == 1

    def test_audit_event_append_only_enforcement(self, user):
        event = AuditEvent.objects.create(
            actor=user,
            entity_type="Submission",
            entity_id="1",
            action="CREATE",
            metadata={"source": "test"},
        )
        assert event.pk is not None

        # Tentar atualizar deve levantar PermissionDenied
        with pytest.raises(PermissionDenied):
            event.action = "UPDATE"
            event.save()

        # Tentar excluir deve levantar PermissionDenied
        with pytest.raises(PermissionDenied):
            event.delete()
