"""Views para o espaço de trabalho da análise documental."""

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
from apps.evaluations.assessment import definition_rows
from apps.evaluations.forms import CheckResultForm
from apps.evaluations.models import Evaluation
from apps.evaluations.services import EvaluationService, InconsistentEvaluationError
from apps.evaluations.validation_rules import ValidationRuleEvaluator
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

    context = workspace_context(request, evaluation)
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

    forms = {}
    payloads = []
    valid = True
    allowed_prefixes = set()
    for result in evaluation.check_results.select_related("requirement_check", "requirement"):
        allowed_prefixes.add(f"{result.input_prefix}status")
        if f"{result.input_prefix}status" not in request.POST:
            continue
        form = CheckResultForm(request.POST, result=result)
        forms[result.pk] = form
        if form.is_valid():
            payloads.append(form.payload())
        else:
            valid = False
    unexpected = [
        key
        for key in request.POST
        if key.startswith(("check_", "requirement_"))
        and key.endswith("_status")
        and key not in allowed_prefixes
    ]
    errors = []
    if unexpected:
        valid = False
        errors.append("Item enviado não pertence à avaliação.")
    if valid:
        from django.core.exceptions import ValidationError

        try:
            EvaluationService.save_draft(
                evaluation, payloads, request.user, request.POST.get("general_notes")
            )
        except ValidationError as exc:
            valid = False
            errors.extend(exc.messages)
    evaluation.refresh_from_db()
    if not valid:
        errors.extend(
            str(error)
            for form in forms.values()
            for values in form.errors.values()
            for error in values
        )
    if request.headers.get("HX-Request"):
        context = workspace_context(request, evaluation)
        return render(
            request,
            "evaluations/partials/summary_panel.html",
            {
                **context,
                "draft_saved": valid,
                "validation_errors": errors,
            },
        )
    if not valid:
        return render(
            request,
            "evaluations/workspace.html",
            {**workspace_context(request, evaluation, forms), "validation_errors": errors},
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


def workspace_context(request, evaluation, bound_forms=None):
    can_edit = RolePermissionPolicy.can_edit_evaluation(request.user, evaluation)
    macros = {}
    for requirement, definition, result in definition_rows(evaluation):
        section_name = requirement.presentation_section.strip() or "Documentos e requisitos"
        macro = macros.setdefault(section_name, {"title": section_name, "requirements": {}})
        section = macro["requirements"].setdefault(
            requirement.pk,
            {"requirement": requirement, "checks": []},
        )
        if result:
            form = (bound_forms or {}).get(result.pk) or CheckResultForm(
                result=result, can_edit=can_edit
            )
            outcomes = ValidationRuleEvaluator.evaluate_result(result)
            section["checks"].append(
                {
                    "check": definition,
                    "result": result,
                    "form": form,
                    "validations": outcomes,
                }
            )
    outcome_list = [
        outcome
        for result in evaluation.check_results.select_related(
            "evaluation__submission__edital", "evaluation__submission__institution"
        )
        for outcome in ValidationRuleEvaluator.evaluate_result(result)
    ]
    blockers = [
        outcome
        for outcome in outcome_list
        if outcome.rule.blocks_completion
        and outcome.rule.severity == "CRITICAL"
        and outcome.status != "PASS"
    ]
    return {
        "submission": evaluation.submission,
        "evaluation": evaluation,
        "macro_sections": [
            {
                "title": macro["title"],
                "requirements": list(macro["requirements"].values()),
            }
            for macro in macros.values()
        ],
        "assessment": EvaluationService.calculate_assessment(evaluation),
        "can_edit": can_edit,
        "can_request_diligence": request.user.is_superuser
        or request.user.role in {User.Role.COORDENADOR, User.Role.ADMINISTRADOR}
        or (
            request.user.role == User.Role.REVISOR
            and hasattr(evaluation, "review")
            and evaluation.review.reviewer_id == request.user.pk
            and evaluation.review.status == "PENDING"
        ),
        "validation_outcomes": outcome_list,
        "validation_blockers": blockers,
        "validation_critical_count": sum(
            1
            for outcome in outcome_list
            if outcome.rule.severity == "CRITICAL" and outcome.status != "PASS"
        ),
        "validation_warning_count": sum(
            1
            for outcome in outcome_list
            if outcome.rule.severity == "WARNING" and outcome.status != "PASS"
        ),
        "can_conclude": EvaluationService.calculate_assessment(evaluation).is_complete
        and not blockers,
    }
