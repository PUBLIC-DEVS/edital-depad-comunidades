"""Views para gestão, triagem e distribuição de processos."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render

from apps.accounts.models import User
from apps.accounts.permissions import (
    RolePermissionPolicy,
    ScopedQuerySetSelector,
    enforce_submission_access,
    require_role,
)
from apps.ranking.services import ClassificationService
from apps.submissions.forms import BulkAssignmentForm, SingleAssignmentForm, SubmissionIntakeForm
from apps.submissions.models import Assignment, Submission
from apps.submissions.services.distribution import DistributionService
from apps.submissions.services.validation import SubmissionAnomalyDetector
from apps.submissions.services.workflow import WorkflowService


@login_required
def submission_list_view(request: HttpRequest) -> HttpResponse:
    """Fila principal de processos e distribuição com filtros, busca e suporte a HTMX."""
    base_qs = (
        ScopedQuerySetSelector.for_submissions(request.user)
        .select_related("institution", "municipality", "edital")
        .prefetch_related("assignments__analyst")
    )

    # Filtros
    search_query = request.GET.get("q", "").strip()
    if search_query:
        base_qs = base_qs.filter(
            Q(processo_sei__icontains=search_query)
            | Q(institution__name__icontains=search_query)
            | Q(institution__cnpj__icontains=search_query)
            | Q(municipality__name__icontains=search_query)
        )

    status_filter = request.GET.get("status", "").strip()
    if status_filter:
        base_qs = base_qs.filter(workflow_status=status_filter)

    group_filter = request.GET.get("group", "").strip()
    if group_filter:
        base_qs = base_qs.filter(target_group=group_filter)

    analyst_filter = request.GET.get("analyst", "").strip()
    if analyst_filter and RolePermissionPolicy.can_view_all_submissions(request.user):
        base_qs = base_qs.filter(
            assignments__analyst_id=analyst_filter,
            assignments__status=Assignment.Status.ACTIVE,
        )

    uf_filter = request.GET.get("uf", "").strip()
    if uf_filter:
        base_qs = base_qs.filter(municipality__state=uf_filter.upper())

    # Paginação
    paginator = Paginator(base_qs, 25)
    page_number = request.GET.get("page", 1)
    page_obj = paginator.get_page(page_number)

    # Anexa alertas de validação para os itens da página atual
    for sub in page_obj.object_list:
        sub.alerts = SubmissionAnomalyDetector.check_submission(sub)

    context = {
        "page_obj": page_obj,
        "search_query": search_query,
        "status_filter": status_filter,
        "group_filter": group_filter,
        "analyst_filter": analyst_filter,
        "uf_filter": uf_filter,
        "workflow_statuses": Submission.WorkflowStatus.choices,
        "target_groups": Submission.TargetGroup.choices,
        "analysts": User.objects.filter(role=User.Role.ANALISTA, is_active=True),
        "can_distribute": RolePermissionPolicy.can_distribute_submissions(request.user),
        "total_count": paginator.count,
    }

    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return render(request, "submissions/partials/table.html", context)

    return render(request, "submissions/list.html", context)


@login_required
@require_role(User.Role.DISTRIBUIDOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
def submission_create_view(request: HttpRequest) -> HttpResponse:
    """Cadastro manual ou recepção de novo processo no edital."""
    if request.method == "POST":
        form = SubmissionIntakeForm(request.POST)
        if form.is_valid():
            submission = form.save()
            # Enquadramento automático preliminar
            ClassificationService.classify_and_update(submission)
            messages.success(request, f"Processo {submission.processo_sei} cadastrado com sucesso.")
            return redirect("submission-detail", submission_id=submission.id)
    else:
        form = SubmissionIntakeForm()

    return render(request, "submissions/create.html", {"form": form})


@login_required
def submission_detail_view(request: HttpRequest, submission_id: int) -> HttpResponse:
    """Exibição detalhada de um processo, atribuições, anomalias e histórico."""
    submission = enforce_submission_access(request, submission_id)
    alerts = SubmissionAnomalyDetector.check_submission(submission)
    assignment_history = submission.assignments.select_related("analyst", "assigned_by").order_by(
        "-assigned_at"
    )

    assignment_form = None
    if RolePermissionPolicy.can_distribute_submissions(request.user):
        assignment_form = SingleAssignmentForm()

    context = {
        "submission": submission,
        "alerts": alerts,
        "assignment_history": assignment_history,
        "assignment_form": assignment_form,
        "can_distribute": RolePermissionPolicy.can_distribute_submissions(request.user),
    }
    return render(request, "submissions/detail.html", context)


@login_required
@require_role(User.Role.DISTRIBUIDOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
def submission_assign_view(request: HttpRequest, submission_id: int) -> HttpResponse:
    """Atribui ou redistribui um processo individualmente."""
    submission = enforce_submission_access(request, submission_id)
    if request.method == "POST":
        form = SingleAssignmentForm(request.POST)
        if form.is_valid():
            analyst = form.cleaned_data["analyst"]
            reason = form.cleaned_data["reason"]
            WorkflowService.assign_analyst(
                submission=submission,
                analyst=analyst,
                assigned_by=request.user,
                reason=reason,
            )
            messages.success(
                request,
                f"Processo {submission.processo_sei} atribuído com sucesso ao analista {analyst.username}.",
            )
    return redirect("submission-detail", submission_id=submission.id)


@login_required
@require_role(User.Role.DISTRIBUIDOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
def submission_bulk_assign_view(request: HttpRequest) -> HttpResponse:
    """Atribui múltiplos processos selecionados a um analista."""
    if request.method == "POST":
        form = BulkAssignmentForm(request.POST)
        if form.is_valid():
            ids_raw = form.cleaned_data["selected_ids"]
            submission_ids = [int(i.strip()) for i in ids_raw.split(",") if i.strip().isdigit()]
            analyst = form.cleaned_data["analyst"]
            reason = form.cleaned_data["reason"]

            count = DistributionService.bulk_assign(
                submission_ids=submission_ids,
                analyst_id=analyst.id,
                assigned_by=request.user,
                reason=reason,
            )
            messages.success(
                request,
                f"{count} processos foram atribuídos com sucesso ao analista {analyst.username}.",
            )
        else:
            messages.error(
                request,
                "Erro ao processar atribuição em lote. Selecione processos e analista válidos.",
            )
    return redirect("submission-list")


@login_required
@require_role(User.Role.DISTRIBUIDOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
def submission_suggest_distribution_view(request: HttpRequest) -> HttpResponse:
    """Sugere distribuição balanceada com base na carga ativa atual dos analistas (sem aplicar automaticamente)."""
    ids_raw = request.GET.get("ids", "")
    submission_ids = [int(i.strip()) for i in ids_raw.split(",") if i.strip().isdigit()]
    suggestions = DistributionService.suggest_balanced_distribution(submission_ids)
    return render(
        request,
        "submissions/partials/distribution_suggestion.html",
        {"suggestions": suggestions},
    )


@login_required
def submission_anomalies_view(request: HttpRequest) -> HttpResponse:
    """Fila de exceções e anomalias cadastrais/processuais."""
    base_qs = ScopedQuerySetSelector.for_submissions(request.user).select_related(
        "institution", "municipality", "edital"
    )

    anomalous_submissions = []
    for sub in base_qs:
        alerts = SubmissionAnomalyDetector.check_submission(sub)
        if alerts:
            sub.alerts = alerts
            anomalous_submissions.append(sub)

    return render(
        request,
        "submissions/anomalies.html",
        {
            "submissions": anomalous_submissions,
            "total_anomalies": len(anomalous_submissions),
        },
    )
