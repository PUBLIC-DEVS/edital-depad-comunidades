import pytest
from django.utils import timezone

from apps.accounts.models import User
from apps.editais.models import Edital, ProgramMunicipality
from apps.institutions.models import Institution, Municipality
from apps.ranking.models import RankingSnapshot
from apps.ranking.services import ClassificationService, RankingService
from apps.submissions.models import Submission
from tests.group_configuration import configure_example_groups


@pytest.mark.django_db
class TestClassificationAndRankingService:
    @pytest.fixture
    def setup_data(self):
        user = User.objects.create_user(
            username="coord_rank", email="rank@mds.gov.br", role=User.Role.COORDENADOR
        )
        now = timezone.now()
        edital = Edital.objects.create(
            name="Edital Ranking",
            number="04",
            year=2024,
            opens_at=now,
            closes_at=now + timezone.timedelta(days=30),
            rules_version="1.0",
        )
        program = configure_example_groups(edital)
        mun_pronasci = Municipality.objects.create(
            ibge_code="3304557", name="Rio de Janeiro", state="RJ"
        )
        mun_normal = Municipality.objects.create(
            ibge_code="3106200", name="Belo Horizonte", state="MG"
        )

        # Vincula Rio de Janeiro ao PRONASCI no edital
        ProgramMunicipality.objects.create(
            edital=edital,
            municipality=mun_pronasci,
            program_name="PRONASCI",
            program=program,
            active=True,
        )

        inst1 = Institution.objects.create(
            cnpj="00000000000191", name="OSC Feminina", municipality=mun_normal
        )
        inst2 = Institution.objects.create(
            cnpj="00000000000272", name="OSC Pronasci", municipality=mun_pronasci
        )
        inst3 = Institution.objects.create(
            cnpj="00000000000353", name="OSC Geral", municipality=mun_normal
        )
        inst4 = Institution.objects.create(
            cnpj="00000000000434", name="OSC Sem Vagas", municipality=mun_normal
        )

        return {
            "user": user,
            "edital": edital,
            "mun_pronasci": mun_pronasci,
            "mun_normal": mun_normal,
            "inst1": inst1,
            "inst2": inst2,
            "inst3": inst3,
            "inst4": inst4,
            "now": now,
        }

    def test_classification_logic(self, setup_data):
        now = setup_data["now"]
        # G1: Vagas femininas ou nutrizes > 0
        s1 = Submission.objects.create(
            edital=setup_data["edital"],
            institution=setup_data["inst1"],
            processo_sei="71000.001",
            received_at=now,
            municipality=setup_data["mun_normal"],
            vagas_femininas=10,
            vagas_masculinas=15,
        )
        assert ClassificationService.classify_submission(s1) == "G1"

        # G2: Sem feminino, com masculino, município PRONASCI (por código IBGE)
        s2 = Submission.objects.create(
            edital=setup_data["edital"],
            institution=setup_data["inst2"],
            processo_sei="71000.002",
            received_at=now,
            municipality=setup_data["mun_pronasci"],
            vagas_femininas=0,
            vagas_masculinas=20,
        )
        assert ClassificationService.classify_submission(s2) == "G2"

        # G3: Sem feminino, com masculino, município NÃO PRONASCI
        s3 = Submission.objects.create(
            edital=setup_data["edital"],
            institution=setup_data["inst3"],
            processo_sei="71000.003",
            received_at=now,
            municipality=setup_data["mun_normal"],
            vagas_femininas=0,
            vagas_masculinas=20,
        )
        assert ClassificationService.classify_submission(s3) == "G3"

        # SEM_GRUPO: Vagas zeradas
        s4 = Submission.objects.create(
            edital=setup_data["edital"],
            institution=setup_data["inst4"],
            processo_sei="71000.004",
            received_at=now,
            municipality=setup_data["mun_normal"],
            vagas_femininas=0,
            vagas_masculinas=0,
        )
        assert ClassificationService.classify_submission(s4) == "SEM_GRUPO"

    def test_ranking_snapshot_generation_and_ordering(self, setup_data):
        now = setup_data["now"]
        edital = setup_data["edital"]
        user = setup_data["user"]

        # Duas submissões em G3 com horários distintos
        s_g3_first = Submission.objects.create(
            edital=edital,
            institution=setup_data["inst1"],
            processo_sei="71000.010",
            received_at=now - timezone.timedelta(hours=2),
            municipality=setup_data["mun_normal"],
            vagas_masculinas=10,
            workflow_status=Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
        )
        s_g3_second = Submission.objects.create(
            edital=edital,
            institution=setup_data["inst3"],
            processo_sei="71000.020",
            received_at=now - timezone.timedelta(hours=1),
            municipality=setup_data["mun_normal"],
            vagas_masculinas=15,
            workflow_status=Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
        )

        snapshot = RankingService.generate_snapshot(
            edital=edital,
            actor=user,
            snapshot_type=RankingSnapshot.SnapshotType.PRELIMINAR,
        )

        assert snapshot.pk is not None
        assert snapshot.is_immutable is True

        entries = list(snapshot.entries.filter(target_group="G3").order_by("position"))
        assert len(entries) == 2
        assert entries[0].submission == s_g3_first
        assert entries[0].position == 1
        assert entries[1].submission == s_g3_second
        assert entries[1].position == 2

        s_g3_first.refresh_from_db()
        assert s_g3_first.workflow_status == Submission.WorkflowStatus.RANKED
