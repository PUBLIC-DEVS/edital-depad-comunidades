import pytest
from django.test import Client
from django.utils import timezone

from apps.accounts.models import User
from apps.editais.models import Edital, Requirement, RequirementCheck
from apps.evaluations.models import CheckResult, Evaluation
from apps.institutions.models import Institution, Municipality
from apps.reporting.services.metrics import DashboardMetricsService
from apps.reviews.models import Review, ReviewItemDecision
from apps.submissions.models import Assignment, Submission


@pytest.mark.django_db
class TestReportingDashboardAndValidation:
    @pytest.fixture
    def setup_data(self):
        coord = User.objects.create_user(
            username="coord_rep",
            email="coord@example.com",
            password="pwd",
            role=User.Role.COORDENADOR,
            first_name="Coordenador",
            last_name="Geral",
        )
        analyst = User.objects.create_user(
            username="ana_rep",
            email="ana@example.com",
            password="pwd",
            role=User.Role.ANALISTA,
            first_name="Analista",
            last_name="Silva",
        )
        rev = User.objects.create_user(
            username="rev_rep",
            email="rev@example.com",
            password="pwd",
            role=User.Role.REVISOR,
            first_name="Revisor",
            last_name="Costa",
        )

        edital = Edital.objects.create(
            name="Edital Nacional 2026",
            number=1,
            year=2026,
            opens_at=timezone.now(),
            closes_at=timezone.now() + timezone.timedelta(days=30),
        )

        muni_sp = Municipality.objects.create(ibge_code="3550308", name="São Paulo", state="SP")
        muni_rj = Municipality.objects.create(
            ibge_code="3304557", name="Rio de Janeiro", state="RJ"
        )

        inst1 = Institution.objects.create(name="Inst 1", cnpj="00000000000191")
        inst2 = Institution.objects.create(name="Inst 2", cnpj="00000000000272")
        inst3 = Institution.objects.create(name="Inst 3", cnpj="00000000000353")

        # Requisitos
        req1 = Requirement.objects.create(
            edital=edital, code="4.2-XVI", name="Certidão Negativa", mandatory=True, order=1
        )
        check1 = RequirementCheck.objects.create(
            requirement=req1, name="CND Federal válida", order=1
        )

        req2 = Requirement.objects.create(
            edital=edital, code="4.2-V", name="Estatuto Social", mandatory=True, order=2
        )
        RequirementCheck.objects.create(requirement=req2, name="Finalidade institucional", order=1)

        # Submissão 1 - G1, distribuída, sob análise
        sub1 = Submission.objects.create(
            edital=edital,
            institution=inst1,
            processo_sei="SEI-001",
            received_at=timezone.now(),
            municipality=muni_sp,
            target_group=Submission.TargetGroup.G1,
            vagas_femininas=10,
            vagas_masculinas=0,
            vagas_maes_nutrizes=5,
            vagas_solicitadas=15,
            capacidade_total=30,
            workflow_status=Submission.WorkflowStatus.UNDER_ANALYSIS,
        )
        Assignment.objects.create(
            submission=sub1, analyst=analyst, assigned_by=coord, status=Assignment.Status.ACTIVE
        )

        # Avaliação com reprovação no 4.2-XVI
        eval1 = Evaluation.objects.create(
            submission=sub1,
            analyst=analyst,
            status=Evaluation.Status.COMPLETED,
            result=Evaluation.Result.INAPTA,
        )
        cr1 = CheckResult.objects.create(
            evaluation=eval1,
            requirement_check=check1,
            status=CheckResult.Status.NAO_ATENDE,
            notes="CND vencida",
        )

        # Submissão 2 - G2, concluída, com contradição proposital para teste de validação (APTA com check reprovado)
        sub2 = Submission.objects.create(
            edital=edital,
            institution=inst2,
            processo_sei="SEI-002",
            received_at=timezone.now(),
            municipality=muni_rj,
            target_group=Submission.TargetGroup.G2,
            vagas_femininas=5,
            vagas_masculinas=5,
            vagas_maes_nutrizes=0,
            vagas_solicitadas=20,  # Inconsistência: 5+5 != 20!
            capacidade_total=10,  # Inconsistência: 20 > 10!
            workflow_status=Submission.WorkflowStatus.ELIGIBLE_FOR_RANKING,
        )
        Assignment.objects.create(
            submission=sub2, analyst=analyst, assigned_by=coord, status=Assignment.Status.ACTIVE
        )
        eval2 = Evaluation.objects.create(
            submission=sub2,
            analyst=analyst,
            status=Evaluation.Status.COMPLETED,
            result=Evaluation.Result.APTA,
        )
        CheckResult.objects.create(
            evaluation=eval2,
            requirement_check=check1,
            status=CheckResult.Status.NAO_ATENDE,  # Contradição!
        )

        # Submissão 3 - Não distribuída, sem município
        sub3 = Submission.objects.create(
            edital=edital,
            institution=inst3,
            processo_sei="SEI-003",
            received_at=timezone.now(),
            municipality=None,
            target_group=Submission.TargetGroup.SEM_GRUPO,
            vagas_solicitadas=10,
            capacidade_total=20,
            workflow_status=Submission.WorkflowStatus.RECEIVED,
        )

        # Divergência de revisor em sub1
        review1 = Review.objects.create(
            evaluation=eval1,
            submission=sub1,
            reviewer=rev,
            status=Review.Status.COMPLETED,
            preliminary_result=Review.PreliminaryResult.PRE_HABILITADO,
            decision_notes="Discordo da inaptidão",
        )
        ReviewItemDecision.objects.create(
            review=review1,
            check_result=cr1,
            agrees_with_analyst=False,
            reviewer_status=CheckResult.Status.ATENDE,
            justification="Documento foi anexado nas fls 35.",
        )

        return {
            "coord": coord,
            "analyst": analyst,
            "rev": rev,
            "edital": edital,
            "sub1": sub1,
            "sub2": sub2,
            "sub3": sub3,
            "req1": req1,
            "check1": check1,
        }

    def test_metrics_service_summary(self, setup_data):
        data = setup_data
        summary = DashboardMetricsService.get_summary_metrics(data["edital"])

        assert summary["total_received"] == 3
        assert summary["distributed_count"] == 2
        assert summary["unassigned_count"] == 1
        assert summary["under_analysis"] == 1
        assert summary["concluded"] == 1
        assert summary["by_group"]["G1"] == 1
        assert summary["by_group"]["G2"] == 1
        assert summary["by_group"]["SEM_GRUPO"] == 1

        # Carga do analista
        assert len(summary["by_analyst"]) == 1
        analyst_entry = summary["by_analyst"][0]
        assert analyst_entry["total_assigned"] == 2

    def test_top_failed_requirements_and_drilldown(self, setup_data):
        data = setup_data
        top_failed = DashboardMetricsService.get_top_failed_requirements(data["edital"])

        assert len(top_failed) >= 1
        assert top_failed[0]["code"] == "4.2-XVI"
        assert top_failed[0]["failure_count"] == 2  # Sub1 e Sub2

        # Submissões reprovadas pelo código
        failing_subs = DashboardMetricsService.get_submissions_failing_requirement(
            "4.2-XVI", data["edital"]
        )
        failing_seis = [s.processo_sei for s in failing_subs]
        assert "SEI-001" in failing_seis
        assert "SEI-002" in failing_seis

    def test_validation_insights_detection(self, setup_data):
        data = setup_data
        insights = DashboardMetricsService.get_validation_insights(data["edital"])

        assert insights["total_anomalies_count"] > 0

        # Contradição grave: apto com item obrigatório reprovado
        assert len(insights["positive_with_failed_items"]) == 1
        assert insights["positive_with_failed_items"][0]["submission"].processo_sei == "SEI-002"

        # Inconsistência de capacidade / vagas
        cap_subs = [
            item["submission"].processo_sei for item in insights["capacity_inconsistencies"]
        ]
        assert "SEI-002" in cap_subs

        # Divergência de revisor
        assert len(insights["reviewer_divergences"]) == 1
        assert (
            insights["reviewer_divergences"][0]["analyst_decision"] == CheckResult.Status.NAO_ATENDE
        )
        assert insights["reviewer_divergences"][0]["reviewer_decision"] == CheckResult.Status.ATENDE

        # Processo sem município
        assert len(insights["missing_municipality"]) == 1
        assert insights["missing_municipality"][0].processo_sei == "SEI-003"

    def test_reporting_views_http(self, setup_data):
        data = setup_data
        client = Client()
        client.force_login(data["coord"])

        # 1. Dashboard
        resp = client.get("/metricas/")
        assert resp.status_code == 200
        assert "Painel Operacional" in resp.content.decode("utf-8")
        assert "4.2-XVI" in resp.content.decode("utf-8")

        # 2. Painel de Validações
        resp_val = client.get("/metricas/validacoes/")
        assert resp_val.status_code == 200
        assert "Contradição Crítica" in resp_val.content.decode("utf-8")
        assert "SEI-002" in resp_val.content.decode("utf-8")

        # 3. Drill-down de Requisito Reprovado
        resp_fail = client.get("/metricas/falhas/4.2-XVI/")
        assert resp_fail.status_code == 200
        assert "Processos Reprovados" in resp_fail.content.decode("utf-8")
        assert "SEI-001" in resp_fail.content.decode("utf-8")

        # 4. Exportação CSV
        resp_csv = client.get("/metricas/exportar/")
        assert resp_csv.status_code == 200
        assert resp_csv["Content-Type"].startswith("text/csv")
        csv_text = resp_csv.content.decode("utf-8")
        assert "Total Recebidos" in csv_text
        assert "Analista Silva" in csv_text
