"""Views para o espaço de trabalho da análise documental."""

from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_GET, require_POST

from apps.accounts.models import User
from apps.accounts.permissions import (
    RolePermissionPolicy,
    ScopedQuerySetSelector,
    enforce_evaluation_edit_access,
    enforce_submission_access,
)
from apps.editais.models import Requirement
from apps.evaluations.models import CheckResult, Evaluation
from apps.evaluations.services import EvaluationService, InconsistentEvaluationError
from apps.submissions.models import Submission


@login_required
def my_evaluations_view(request: HttpRequest) -> HttpResponse:
    """Lista as análises atribuídas ao analista logado."""
    # Garante isolamento estrito
    submissions = (
        ScopedQuerySetSelector.for_submissions(request.user)
        .select_related("institution", "municipality", "edital")
        .filter(assignments__analyst=request.user, assignments__status="ACTIVE")
        .distinct()
    )

    evaluations_by_sub = {
        e.submission_id: e for e in Evaluation.objects.filter(submission__in=submissions)
    }

    eval_items = []
    for sub in submissions:
        eval_obj = evaluations_by_sub.get(sub.id)
        eval_items.append({"submission": sub, "evaluation": eval_obj})

    return render(
        request,
        "evaluations/my_evaluations.html",
        {"eval_items": eval_items, "total_count": len(eval_items)},
    )


@login_required
@require_GET
def evaluation_workspace_view(request: HttpRequest, submission_id: int) -> HttpResponse:
    """Espaço de trabalho vertical estruturado para conferência de requisitos do edital."""
    submission = enforce_submission_access(request, submission_id)

    evaluation = Evaluation.objects.filter(submission=submission).first()
    if evaluation is None:
        can_start = (
            request.user.role == User.Role.ANALISTA
            and submission.assigned_analyst == request.user
            and submission.workflow_status == Submission.WorkflowStatus.ASSIGNED
        )
        return render(
            request,
            "evaluations/not_started.html",
            {"submission": submission, "can_start": can_start},
        )

    # Carrega requisitos e checagens estruturadas
    requirements = (
        Requirement.objects.filter(edital=submission.edital, active=True)
        .prefetch_related("checks")
        .order_by("order", "code")
    )

    results_map = {
        cr.requirement_check_id: cr
        for cr in evaluation.check_results.select_related("requirement_check")
    }

    # Estrutura dados para o template vertical
    req_sections = []
    for req in requirements:
        checks_data = []
        for check in req.checks.filter(active=True).order_by("order", "code"):
            res = results_map.get(check.id)
            checks_data.append({"check": check, "result": res})
        req_sections.append({"requirement": req, "checks": checks_data})

    assessment = EvaluationService.calculate_assessment(evaluation)
    can_edit = RolePermissionPolicy.can_edit_evaluation(request.user, evaluation)

    context = {
        "submission": submission,
        "evaluation": evaluation,
        "req_sections": req_sections,
        "assessment": assessment,
        "can_edit": can_edit,
        "check_statuses": CheckResult.Status.choices,
    }
    return render(request, "evaluations/workspace.html", context)


@login_required
@require_POST
def evaluation_start_view(request, submission_id):
    submission = enforce_submission_access(request, submission_id)
    EvaluationService.start_evaluation(submission, request.user)
    return redirect("evaluation-workspace", submission_id=submission.pk)


@login_required
@require_POST
def evaluation_save_draft_view(request: HttpRequest, evaluation_id: int) -> HttpResponse:
    """Salva rascunho de preenchimento via POST normal ou HTMX."""
    evaluation = enforce_evaluation_edit_access(request, evaluation_id)

    if request.method == "POST":
        payloads = []
        for cr in evaluation.check_results.all():
            cid = cr.requirement_check_id
            prefix = f"check_{cid}_"
            if f"{prefix}status" in request.POST:
                num_val = request.POST.get(f"{prefix}numeric_value", "").strip()
                val_dec = Decimal(num_val.replace(",", ".")) if num_val else None

                payloads.append(
                    {
                        "requirement_check_id": cid,
                        "status": request.POST.get(f"{prefix}status", CheckResult.Status.EM_BRANCO),
                        "sei_number": request.POST.get(f"{prefix}sei_number", "").strip(),
                        "pages": request.POST.get(f"{prefix}pages", "").strip(),
                        "document_cnpj": request.POST.get(f"{prefix}document_cnpj", "").strip(),
                        "valid_until": request.POST.get(f"{prefix}valid_until") or None,
                        "numeric_value": val_dec,
                        "notes": request.POST.get(f"{prefix}notes", "").strip(),
                    }
                )

        general_notes = request.POST.get("general_notes", "")
        assessment = EvaluationService.save_draft(
            evaluation=evaluation,
            check_payloads=payloads,
            actor=request.user,
            general_notes=general_notes,
        )

        if request.headers.get("HX-Request"):
            return render(
                request,
                "evaluations/partials/summary_panel.html",
                {
                    "evaluation": evaluation,
                    "assessment": assessment,
                    "can_edit": True,
                    "draft_saved": True,
                },
            )

        messages.success(request, "Rascunho da análise salvo com sucesso.")
    return redirect("evaluation-workspace", submission_id=evaluation.submission_id)


@login_required
@require_POST
def evaluation_conclude_view(request: HttpRequest, evaluation_id: int) -> HttpResponse:
    """Conclui a avaliação documental após validação formal de consistência."""
    evaluation = enforce_evaluation_edit_access(request, evaluation_id)

    if request.method == "POST":
        notes = request.POST.get("general_notes", "")
        try:
            EvaluationService.conclude_evaluation(evaluation, actor=request.user, notes=notes)
            messages.success(
                request,
                f"Análise do processo {evaluation.submission.processo_sei} concluída com sucesso com parecer '{evaluation.get_result_display()}'.",
            )
            return redirect("my-evaluations")
        except InconsistentEvaluationError as exc:
            messages.error(request, str(exc))

    return redirect("evaluation-workspace", submission_id=evaluation.submission_id)
