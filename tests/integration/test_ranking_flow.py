import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.editais.models import Edital, ProgramMunicipality
from apps.institutions.models import Institution, Municipality
from apps.ranking.models import RankingSnapshot
from apps.submissions.models import Submission


@pytest.mark.django_db
class TestRankingFlowIntegration:
    @pytest.fixture
    def setup_data(self):
        coord = User.objects.create_user(
            username="coord_rk_flow", email="c_rk@mds.gov.br", role=User.Role.COORDENADOR
        )
        analyst = User.objects.create_user(
            username="analyst_rk_flow", email="a_rk@mds.gov.br", role=User.Role.ANALISTA
        )

        now = timezone.now()
        edital = Edital.objects.create(
            name="Edital Ranking Flow",
            number="05",
            year=2024,
            opens_at=now,
            closes_at=now + timezone.timedelta(days=30),
            rules_version="1.0",
            duplicate_policy=Edital.DuplicatePolicy.KEEP_EARLIEST_SUBMISSION,
        )
        mun_pronasci = Municipality.objects.create(
            ibge_code="3304557", name="Rio de Janeiro", state="RJ"
        )
        mun_normal = Municipality.objects.create(
            ibge_code="3106200", name="Belo Horizonte", state="MG"
        )

        ProgramMunicipality.objects.create(
            edital=edital,
            municipality=mun_pronasci,
            program_name="PRONASCI",
            active=True,
        )

        return {
            "coord": coord,
            "analyst": analyst,
            "edital": edital,
            "mun_pronasci": mun_pronasci,
            "mun_normal": mun_normal,
            "now": now,
        }

    def test_complete_ranking_generation_flow(self, client, setup_data):
        edital = setup_data["edital"]
        coord = setup_data["coord"]
        now = setup_data["now"]

        inst1 = Institution.objects.create(
            cnpj="00000000000191", name="OSC 1", municipality=setup_data["mun_normal"]
        )
        inst2 = Institution.objects.create(
            cnpj="00000000000272", name="OSC 2", municipality=setup_data["mun_pronasci"]
        )
        inst3 = Institution.objects.create(
            cnpj="00000000000353", name="OSC 3", municipality=setup_data["mun_normal"]
        )

        # Submissão G1
        sub_g1 = Submission.objects.create(
            edital=edital,
            institution=inst1,
            processo_sei="71000.001",
            received_at=now - timezone.timedelta(hours=5),
            municipality=setup_data["mun_normal"],
            vagas_femininas=10,
            vagas_solicitadas=10,
            workflow_status=Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
        )

        # Submissão G2 (PRONASCI)
        sub_g2 = Submission.objects.create(
            edital=edital,
            institution=inst2,
            processo_sei="71000.002",
            received_at=now - timezone.timedelta(hours=4),
            municipality=setup_data["mun_pronasci"],
            vagas_masculinas=20,
            vagas_solicitadas=20,
            workflow_status=Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
        )

        # Duas submissões G3 com empate de timestamp para testar desempate determinístico por SEI
        sub_g3_tie1 = Submission.objects.create(
            edital=edital,
            institution=inst3,
            processo_sei="71000.003",
            received_at=now - timezone.timedelta(hours=3),
            municipality=setup_data["mun_normal"],
            vagas_masculinas=15,
            vagas_solicitadas=15,
            workflow_status=Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
        )
        inst4 = Institution.objects.create(
            cnpj="00000000000434", name="OSC 4", municipality=setup_data["mun_normal"]
        )
        sub_g3_tie2 = Submission.objects.create(
            edital=edital,
            institution=inst4,
            processo_sei="71000.004",
            received_at=now - timezone.timedelta(hours=3),  # Mesmo timestamp
            municipality=setup_data["mun_normal"],
            vagas_masculinas=15,
            vagas_solicitadas=15,
            workflow_status=Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
        )

        # Submissão da OSC 1 duplicada (segunda submissão mais recente)
        sub_dup = Submission.objects.create(
            edital=edital,
            institution=inst1,
            processo_sei="71000.005",
            received_at=now - timezone.timedelta(hours=1),
            municipality=setup_data["mun_normal"],
            vagas_femininas=10,
            vagas_solicitadas=10,
            workflow_status=Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
        )

        client.force_login(coord)
        # Dispara geração via view
        res = client.post(
            reverse("ranking-generate-snapshot"),
            {
                "edital_id": edital.id,
                "snapshot_type": RankingSnapshot.SnapshotType.PRELIMINAR,
                "description": "Teste preliminar completo",
            },
        )
        assert res.status_code == 302

        snapshot = RankingSnapshot.objects.filter(edital=edital).latest("created_at")
        assert snapshot.snapshot_type == RankingSnapshot.SnapshotType.PRELIMINAR

        entries_g1 = list(snapshot.entries.filter(target_group="G1").order_by("position"))
        entries_g2 = list(snapshot.entries.filter(target_group="G2").order_by("position"))
        entries_g3 = list(snapshot.entries.filter(target_group="G3").order_by("position"))

        # G1 deve ter sub_g1 na posição 1 (não suprimida) e sub_dup como duplicidade suprimida
        assert len(entries_g1) == 2
        assert entries_g1[0].submission == sub_g1
        assert entries_g1[0].is_duplicate_suppressed is False
        assert entries_g1[1].submission == sub_dup
        assert entries_g1[1].is_duplicate_suppressed is True

        # G2 deve ter sub_g2
        assert len(entries_g2) == 1
        assert entries_g2[0].submission == sub_g2

        # G3 deve desempatar deterministamente pelo SEI
        assert len(entries_g3) == 2
        assert entries_g3[0].submission == sub_g3_tie1
        assert entries_g3[1].submission == sub_g3_tie2

        # Teste da view de ranking
        res_view = client.get(reverse("ranking-index"))
        assert res_view.status_code == 200
        assert "71000.001" in res_view.content.decode("utf-8")

        # Teste de exportação CSV
        url_csv = reverse("ranking-export-csv", kwargs={"snapshot_id": snapshot.id})
        res_csv = client.get(url_csv)
        assert res_csv.status_code == 200
        assert "text/csv" in res_csv["Content-Type"]
        content = res_csv.content.decode("utf-8-sig")
        assert "71000.001" in content
        assert "71000.002" in content

    def test_analyst_cannot_generate_snapshot(self, client, setup_data):
        analyst = setup_data["analyst"]
        edital = setup_data["edital"]
        client.force_login(analyst)

        # Analista tentando gerar snapshot recebe 403
        res = client.post(
            reverse("ranking-generate-snapshot"),
            {"edital_id": edital.id, "snapshot_type": "PRELIMINAR"},
        )
        assert res.status_code == 403
