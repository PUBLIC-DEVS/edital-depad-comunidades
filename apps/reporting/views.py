"""Views para o painel de métricas operacionais e conferência de validações."""

from django.contrib.auth.decorators import login_required
from django.http import Http404, HttpResponse
from django.shortcuts import get_object_or_404, render

from apps.accounts.permissions import require_role
from apps.csv_utils import SafeCsvWriter
from apps.editais.models import Edital, Requirement
from apps.reporting.services.metrics import DashboardMetricsService


@login_required
@require_role("ADMINISTRADOR", "COORDENADOR", "CONSULTA")
def dashboard_metrics_view(request):
    """Exibe o painel operacional consolidado com métricas agregadas em tempo real."""
    edital_id = request.GET.get("edital")
    selected_edital = None
    if edital_id:
        if not edital_id.isdecimal():
            raise Http404
        selected_edital = get_object_or_404(Edital, id=int(edital_id))

    editais = Edital.objects.all().order_by("-year", "-number")
    summary = DashboardMetricsService.get_summary_metrics(selected_edital)
    top_failures = DashboardMetricsService.get_top_failed_requirements(selected_edital, limit=8)
    insights = DashboardMetricsService.get_validation_insights(selected_edital)

    context = {
        "title": "Painel Operacional e Métricas",
        "editais": editais,
        "selected_edital": selected_edital,
        "summary": summary,
        "top_failures": top_failures,
        "anomalies_count": insights["total_anomalies_count"],
    }
    return render(request, "reporting/dashboard.html", context)


@login_required
@require_role("ADMINISTRADOR", "COORDENADOR", "CONSULTA")
def validation_insights_view(request):
    """Exibe o painel de conferência, exceções e auditoria de validações."""
    edital_id = request.GET.get("edital")
    selected_edital = None
    if edital_id:
        if not edital_id.isdecimal():
            raise Http404
        selected_edital = get_object_or_404(Edital, id=int(edital_id))

    editais = Edital.objects.all().order_by("-year", "-number")
    insights = DashboardMetricsService.get_validation_insights(selected_edital)

    context = {
        "title": "Painel de Validação e Exceções",
        "editais": editais,
        "selected_edital": selected_edital,
        "insights": insights,
    }
    return render(request, "reporting/validations.html", context)


@login_required
@require_role("ADMINISTRADOR", "COORDENADOR", "CONSULTA")
def failed_requirement_processes_view(request, code: str):
    """Lista detalhada de processos reprovados em um requisito específico."""
    edital_id = request.GET.get("edital")
    selected_edital = None
    if edital_id:
        if not edital_id.isdecimal():
            raise Http404
        selected_edital = get_object_or_404(Edital, id=int(edital_id))

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
@require_role(["ADMINISTRADOR", "COORDENADOR", "CONSULTA"])
def metrics_export_csv_view(request):
    """Exporta resumo de métricas e carga de analistas em formato CSV auditável."""
    edital_id = request.GET.get("edital")
    selected_edital = None
    if edital_id:
        if not edital_id.isdecimal():
            raise Http404
        selected_edital = get_object_or_404(Edital, id=int(edital_id))

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
    writer.writerow(["Em Diligência", summary["pending_diligence"]])
    writer.writerow(["Concluídos", summary["concluded"]])
    for result, count in summary["initial_results"].items():
        writer.writerow([f"Análise inicial: {result}", count])
    for result, count in summary["consolidated_results"].items():
        writer.writerow([f"Workflow: {summary['consolidated_labels'][result]}", count])
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
    writer.writerow(["UF", "Total de Processos"])
    for u in summary["by_uf"]:
        writer.writerow([u["state"], u["count"]])

    return response
