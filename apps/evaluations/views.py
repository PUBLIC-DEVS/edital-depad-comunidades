"""Views para o espaço de trabalho da análise documental."""

import json

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
    require_role,
)
from apps.editais.operational import operational_edital_required
from apps.evaluations.assessment import definition_rows
from apps.evaluations.forms import CheckResultForm
from apps.evaluations.models import Evaluation
from apps.evaluations.services import EvaluationService, InconsistentEvaluationError
from apps.evaluations.validation_rules import ValidationRuleEvaluator
from apps.submissions.models import Submission


@login_required
@require_role(User.Role.ANALISTA)
@operational_edital_required
def my_evaluations_view(request: HttpRequest) -> HttpResponse:
    """Lista as análises atribuídas ao analista logado."""
    # Garante isolamento estrito
    submissions = (
        ScopedQuerySetSelector.for_submissions(request.user)
        .select_related("institution", "municipality", "edital")
        .filter(
            edital=request.operational_edital,
            assignments__analyst=request.user,
            assignments__status="ACTIVE",
        )
        .distinct()
    )

    evaluations_by_sub = {
        e.submission_id: e
        for e in Evaluation.objects.filter(submission__in=submissions).prefetch_related(
            "check_results"
        )
    }

    eval_items = []
    for sub in submissions:
        eval_obj = evaluations_by_sub.get(sub.id)
        results = list(eval_obj.check_results.all()) if eval_obj else []
        eval_items.append(
            {
                "submission": sub,
                "evaluation": eval_obj,
                "evaluated": sum(cr.status != "EM_BRANCO" for cr in results),
                "total": len(results),
            }
        )

    return render(
        request,
        "evaluations/my_evaluations.html",
        {
            "eval_items": eval_items,
            "total_count": len(eval_items),
            "pending_count": sum(not item["evaluation"] for item in eval_items),
            "ongoing_count": sum(
                bool(item["evaluation"] and item["evaluation"].status == "DRAFT")
                for item in eval_items
            ),
            "completed_count": sum(
                bool(item["evaluation"] and item["evaluation"].status == "COMPLETED")
                for item in eval_items
            ),
        },
    )


@login_required
@require_GET
def evaluation_workspace_view(request: HttpRequest, submission_id: int) -> HttpResponse:
    """Espaço de trabalho vertical estruturado para conferência de requisitos do edital."""
    submission = enforce_submission_access(request, submission_id)

    evaluation = (
        Evaluation.objects.select_related(
            "submission__institution", "submission__municipality", "submission__edital"
        )
        .filter(submission=submission)
        .first()
    )
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
        response = render(
            request,
            "evaluations/partials/summary_panel.html",
            {
                **context,
                "draft_saved": valid,
                "validation_errors": errors,
            },
        )
        response["X-Draft-Saved"] = "true" if valid else "false"
        response["X-Draft-Invalid-Fields"] = json.dumps(
            [
                form.add_prefix(field)
                for form in forms.values()
                for field in form.errors
                if field != "__all__"
            ]
        )
        return response
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
            if request.headers.get("HX-Request"):
                response = HttpResponse()
                response["HX-Redirect"] = "/minhas-analises/"
                return response
            return redirect("my-evaluations")
        except InconsistentEvaluationError as exc:
            if request.headers.get("HX-Request"):
                return render(
                    request,
                    "evaluations/partials/summary_panel.html",
                    {
                        **workspace_context(request, evaluation),
                        "validation_errors": [str(exc)],
                    },
                )
            messages.error(request, str(exc))

    return redirect("evaluation-workspace", submission_id=evaluation.submission_id)


def workspace_context(request, evaluation, bound_forms=None):
    can_edit = RolePermissionPolicy.can_edit_evaluation(request.user, evaluation)
    rows = definition_rows(evaluation)
    sections = {}
    outcomes = []
    counts = {"ATENDE": 0, "NAO_ATENDE": 0, "NAO_APLICAVEL": 0, "EM_BRANCO": 0, "NAO_ENVIADO": 0}
    for requirement, definition, result in rows:
        section = sections.setdefault(
            requirement.pk, {"requirement": requirement, "number": len(sections) + 1, "checks": []}
        )
        if result:
            form = (bound_forms or {}).get(result.pk) or CheckResultForm(
                result=result, can_edit=can_edit
            )
            alerts = [
                outcome
                for outcome in ValidationRuleEvaluator.evaluate_result(result)
                if outcome.status != "PASS"
            ]
            outcomes.extend(alerts)
            counts[result.status] = counts.get(result.status, 0) + 1
            section["checks"].append(
                {
                    "check": definition,
                    "result": result,
                    "form": form,
                    "number": f"{section['number']}.{len(section['checks']) + 1}",
                    "validations": alerts,
                    "detail_fields": [
                        field for field in form if field.name not in {"status", "notes"}
                    ],
                    "status_choices": [
                        (value, label)
                        for value, label in form.fields["status"].choices
                        if value not in {"EM_BRANCO", "NAO_ENVIADO"}
                    ],
                }
            )
    assessment = EvaluationService.calculate_assessment(evaluation, rows=rows)
    return {
        "submission": evaluation.submission,
        "evaluation": evaluation,
        "document_sections": list(sections.values()),
        "assessment": assessment,
        "can_edit": can_edit,
        "can_conclude": assessment.is_complete,
        "progress_percent": round(assessment.evaluated_checks * 100 / assessment.total_checks)
        if assessment.total_checks
        else 0,
        "counts": counts,
        "validation_outcomes": outcomes,
    }
