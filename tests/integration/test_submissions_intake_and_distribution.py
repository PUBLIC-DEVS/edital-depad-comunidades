import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.editais.models import Edital
from apps.institutions.models import Institution, Municipality
from apps.submissions.models import Assignment, Submission
from apps.submissions.services.distribution import DistributionService
from apps.submissions.services.validation import SubmissionAnomalyDetector


@pytest.mark.django_db
class TestSubmissionsIntakeAndDistribution:
    @pytest.fixture
    def setup_data(self):
        distrib = User.objects.create_user(
            username="distrib_intake",
            email="distrib_intake@mds.gov.br",
            role=User.Role.DISTRIBUIDOR,
        )
        analyst1 = User.objects.create_user(
            username="analista_distrib1",
            email="ad1@mds.gov.br",
            role=User.Role.ANALISTA,
        )
        analyst2 = User.objects.create_user(
            username="analista_distrib2",
            email="ad2@mds.gov.br",
            role=User.Role.ANALISTA,
        )
        mun = Municipality.objects.create(ibge_code="3550308", name="São Paulo", state="SP")
        inst = Institution.objects.create(
            cnpj="00000000000191", name="OSC Matriz", municipality=mun
        )
        now = timezone.now()
        edital = Edital.objects.create(
            name="Edital Intake", number="10", year=2024, opens_at=now, closes_at=now
        )

        return {
            "distrib": distrib,
            "analyst1": analyst1,
            "analyst2": analyst2,
            "mun": mun,
            "inst": inst,
            "edital": edital,
            "now": now,
        }

    def test_anomaly_detection_rules(self, setup_data):
        # 1. Submissão com CNPJ inválido e vagas inconsistentes
        bad_inst = Institution.objects.create(
            cnpj="00000000000199",  # DV errado
            name="OSC Inválida",
            municipality=setup_data["mun"],
        )
        sub = Submission.objects.create(
            edital=setup_data["edital"],
            institution=bad_inst,
            processo_sei="71000.888",
            received_at=setup_data["now"],
            municipality=setup_data["mun"],
            vagas_femininas=5,
            vagas_masculinas=5,
            vagas_solicitadas=20,  # 5 + 5 != 20
        )
        alerts = SubmissionAnomalyDetector.check_submission(sub)
        alert_codes = [a.code for a in alerts]
        assert "INVALID_CNPJ" in alert_codes
        assert "INCONSISTENT_VACANCIES" in alert_codes

    def test_distribution_service_workload_and_suggestion(self, setup_data):
        analyst1 = setup_data["analyst1"]
        analyst2 = setup_data["analyst2"]

        # Dá 2 processos ativos para analista 1
        for i in range(2):
            s = Submission.objects.create(
                edital=setup_data["edital"],
                institution=setup_data["inst"],
                processo_sei=f"71000.10{i}",
                received_at=setup_data["now"],
                municipality=setup_data["mun"],
                workflow_status=Submission.WorkflowStatus.ASSIGNED,
            )
            Assignment.objects.create(
                submission=s,
                analyst=analyst1,
                assigned_by=setup_data["distrib"],
                status=Assignment.Status.ACTIVE,
            )

        # Analista 2 tem 0 processos ativos. A sugestão balanceada deve priorizar analista 2!
        new_sub = Submission.objects.create(
            edital=setup_data["edital"],
            institution=setup_data["inst"],
            processo_sei="71000.999",
            received_at=setup_data["now"],
            municipality=setup_data["mun"],
            workflow_status=Submission.WorkflowStatus.RECEIVED,
        )

        suggestions = DistributionService.suggest_balanced_distribution([new_sub.id])
        assert len(suggestions) == 1
        assert suggestions[0].suggested_analyst_id == analyst2.id

    def test_bulk_assignment(self, setup_data):
        analyst1 = setup_data["analyst1"]
        distrib = setup_data["distrib"]
        subs = [
            Submission.objects.create(
                edital=setup_data["edital"],
                institution=setup_data["inst"],
                processo_sei=f"71000.20{i}",
                received_at=setup_data["now"],
                municipality=setup_data["mun"],
                workflow_status=Submission.WorkflowStatus.RECEIVED,
            )
            for i in range(3)
        ]
        sub_ids = [s.id for s in subs]

        assigned_count = DistributionService.bulk_assign(
            submission_ids=sub_ids,
            analyst_id=analyst1.id,
            assigned_by=distrib,
            reason="Carga de testes",
        )
        assert assigned_count == 3
        for s in subs:
            s.refresh_from_db()
            assert s.workflow_status == Submission.WorkflowStatus.ASSIGNED
            assert s.assigned_analyst == analyst1

    def test_submission_views_with_client(self, client, setup_data):
        from tests.operational_helpers import publish_fixture

        publish_fixture(setup_data["edital"])
        client.force_login(setup_data["distrib"])
        # Lista
        response = client.get(reverse("submission-list"))
        assert response.status_code == 200

        # HTMX partial
        response_htmx = client.get(reverse("submission-list"), HTTP_HX_REQUEST="true")
        assert response_htmx.status_code == 200

        # Exceções
        response_exc = client.get(reverse("submission-anomalies"))
        assert response_exc.status_code == 200

    def test_vacancy_range_and_matriz_filial_anomaly_alerts(self, setup_data):
        filial_inst = Institution.objects.create(
            cnpj="00000000000272",
            name="OSC Filial",
            municipality=setup_data["mun"],
        )
        sub_matriz = Submission.objects.create(
            edital=setup_data["edital"],
            institution=setup_data["inst"],
            processo_sei="71000.MATRIZ/2024",
            received_at=setup_data["now"],
            municipality=setup_data["mun"],
            vagas_femininas=2,
            vagas_maes_nutrizes=2,  # Soma = 4 (< 5) -> deve gerar alerta MIN_VACANCIES_FEMALE_MOTHERS
            vagas_masculinas=8,  # < 10 -> deve gerar alerta MALE_VACANCIES_OUT_OF_RANGE
            vagas_solicitadas=12,
        )
        sub_filial = Submission.objects.create(
            edital=setup_data["edital"],
            institution=filial_inst,
            processo_sei="71000.FILIAL/2024",
            received_at=setup_data["now"],
            municipality=setup_data["mun"],
            vagas_femininas=3,
            vagas_maes_nutrizes=2,  # Soma = 5 (OK)
            vagas_masculinas=65,  # > 60 -> deve gerar alerta MALE_VACANCIES_OUT_OF_RANGE
            vagas_solicitadas=70,
        )

        alerts_matriz = SubmissionAnomalyDetector.check_submission(sub_matriz)
        codes_matriz = [a.code for a in alerts_matriz]
        assert "MIN_VACANCIES_FEMALE_MOTHERS" in codes_matriz
        assert "MALE_VACANCIES_OUT_OF_RANGE" in codes_matriz
        assert "SAME_CNPJ_ROOT_MATRIZ_FILIAL" in codes_matriz

        alerts_filial = SubmissionAnomalyDetector.check_submission(sub_filial)
        codes_filial = [a.code for a in alerts_filial]
        assert "MIN_VACANCIES_FEMALE_MOTHERS" not in codes_filial
        assert "MALE_VACANCIES_OUT_OF_RANGE" in codes_filial
        assert "SAME_CNPJ_ROOT_MATRIZ_FILIAL" in codes_filial

    def test_submission_intake_form_separated_date_and_time_does_not_block_vacancy_alerts(
        self, setup_data
    ):
        from apps.submissions.forms import SubmissionIntakeForm
        from tests.operational_helpers import publish_fixture

        publish_fixture(setup_data["edital"])

        form = SubmissionIntakeForm(
            data={
                "edital": setup_data["edital"].pk,
                "processo_sei": "71000.SEPARADO/2024",
                "received_date": "2026-04-15",
                "received_time": "14:35",
                "institution_cnpj": "00.000.000/0001-91",
                "institution_name": "OSC Matriz",
                "municipality": setup_data["mun"].pk,
                "vagas_femininas": 2,
                "vagas_maes_nutrizes": 1,  # Soma 3 (< 5), mas não bloqueia o salvamento
                "vagas_masculinas": 5,  # < 10, mas não bloqueia o salvamento
                "vagas_solicitadas": 8,
                "capacidade_total": 20,
            }
        )
        assert form.is_valid(), form.errors
        submission = form.save()
        assert submission.received_date.isoformat() == "2026-04-15"
        assert submission.received_time.strftime("%H:%M") == "14:35"
        assert submission.total_vagas == 8

