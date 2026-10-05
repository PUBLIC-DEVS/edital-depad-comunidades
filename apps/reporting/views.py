"""Views para o painel de métricas operacionais e conferência de validações."""

from django.contrib.auth.decorators import login_required
from django.http import HttpResponse
from django.shortcuts import render

from apps.accounts.permissions import require_role
from apps.csv_utils import SafeCsvWriter
from apps.editais.models import Requirement
from apps.editais.operational import operational_edital_required
from apps.reporting.charts import operational_charts
from apps.reporting.services.metrics import DashboardMetricsService
from apps.submissions.selectors import operational_process_context


@login_required
@require_role("ADMINISTRADOR", "COORDENADOR", "CONSULTA", "REVISOR")
@operational_edital_required
def operational_home_view(request):
    context = operational_process_context(request, distribute=False)
    context["summary"] = DashboardMetricsService.get_summary_metrics(request.operational_edital)
    return render(request, "reporting/home.html", context)


@login_required
@require_role("ADMINISTRADOR", "COORDENADOR", "CONSULTA", "REVISOR")
@operational_edital_required
def dashboard_metrics_view(request):
    edital = request.operational_edital
    summary = DashboardMetricsService.get_summary_metrics(edital)
    return render(
        request,
        "reporting/dashboard.html",
        {
            "edital": edital,
            "selected_edital": edital,
            "summary": summary,
            **operational_charts(summary, DashboardMetricsService.get_top_failed_checks(edital)),
        },
    )


@login_required
@require_role("ADMINISTRADOR", "COORDENADOR", "CONSULTA", "REVISOR")
@operational_edital_required
def validation_insights_view(request):
    """Exibe o painel de conferência, exceções e auditoria de validações."""
    selected_edital = request.operational_edital

    insights = DashboardMetricsService.get_validation_insights(selected_edital)

    context = {
        "title": "Painel de Validação e Exceções",
        "selected_edital": selected_edital,
        "insights": insights,
    }
    return render(request, "reporting/validations.html", context)


@login_required
@require_role("ADMINISTRADOR", "COORDENADOR", "CONSULTA", "REVISOR")
@operational_edital_required
def failed_requirement_processes_view(request, code: str):
    """Lista detalhada de processos reprovados em um requisito específico."""
    selected_edital = request.operational_edital

    requirements = Requirement.objects.filter(code=code)
    if selected_edital:
        requirements = requirements.filter(edital=selected_edital)
    requirement = requirements.first()
    submissions = DashboardMetricsService.get_submissions_failing_requirement(code, selected_edital)

    context = {
        "title": f"Processos Reprovados — Requisito {code}",
        "code": code,
        "requirement": requirement,
        "submissions": submissions,
        "selected_edital": selected_edital,
    }
    return render(request, "reporting/failed_requirement.html", context)


@login_required
@require_role(["ADMINISTRADOR", "COORDENADOR", "CONSULTA", "REVISOR"])
@operational_edital_required
def metrics_export_csv_view(request):
    """Exporta resumo de métricas e carga de analistas em formato CSV auditável."""
    selected_edital = request.operational_edital

    summary = DashboardMetricsService.get_summary_metrics(selected_edital)

    response = HttpResponse(content_type="text/csv; charset=utf-8")
    filename = f"metricas_edital_{selected_edital.number if selected_edital else 'geral'}.csv"
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = SafeCsvWriter(response, delimiter=";")
    writer.writerow(["Métrica / Categoria", "Valor"])
    writer.writerow(["Total Recebidos", summary["total_received"]])
    writer.writerow(["Distribuídos", summary["distributed_count"]])
    writer.writerow(["Não Distribuídos", summary["unassigned_count"]])
    writer.writerow(["Em Análise", summary["under_analysis"]])
    writer.writerow(["Em Revisão", summary["pending_review"]])
    writer.writerow(["Concluídos", summary["concluded"]])
    writer.writerow(["Aptas", summary["apt_count"]])
    writer.writerow(["Inaptas / Inelegíveis", summary["inapt_count"]])
    writer.writerow([])
    writer.writerow(["Grupo", "Total de Processos"])
    for grp, cnt in summary["by_group"].items():
        writer.writerow([grp, cnt])

    writer.writerow([])
    writer.writerow(["Analista", "Total Atribuídos", "Em Análise", "Concluídos"])
    for a in summary["by_analyst"]:
        writer.writerow(
            [
                a["analyst"].get_full_name() or a["analyst"].username,
                a["total_assigned"],
                a["under_analysis"],
                a["concluded"],
            ]
        )

    writer.writerow([])
    return response
