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
