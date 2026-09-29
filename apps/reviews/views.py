"""Views para filas de revisão e gestão de diligências."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.permissions import RolePermissionPolicy, require_role
from apps.evaluations.assessment import blocking_results, definition_rows
from apps.evaluations.models import CheckResult
from apps.reviews.forms import DiligenceCreateForm, DiligenceResponseForm, ReviewConcludeForm
from apps.reviews.models import Diligence, Review
from apps.reviews.services import ReviewService
from apps.submissions.models import Submission
from apps.submissions.services.workflow import WorkflowService


@login_required
@require_role(User.Role.REVISOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
def review_list_view(request: HttpRequest) -> HttpResponse:
    """Fila de revisão de processos com parecer emitido pelo analista."""
    status_filter = request.GET.get("status", "").strip()
    search = request.GET.get("q", "").strip()

    qs = (
        Review.objects.all()
        .select_related(
            "submission",
            "submission__institution",
            "evaluation",
            "evaluation__analyst",
            "reviewer",
        )
        .order_by("-created_at")
    )

    if request.user.role == User.Role.REVISOR and not request.user.is_superuser:
        qs = qs.filter(Q(reviewer=request.user) | Q(reviewer__isnull=True))

    if status_filter:
        qs = qs.filter(status=status_filter)
    if search:
        qs = qs.filter(submission__processo_sei__icontains=search)

    return render(
        request,
        "reviews/list.html",
        {
            "reviews": qs,
            "status_filter": status_filter,
            "search": search,
            "total_count": qs.count(),
        },
    )


@login_required
@require_role(User.Role.REVISOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
def review_detail_view(request: HttpRequest, review_id: int) -> HttpResponse:
    """Tela de conferência de revisão com análise original somente-leitura e decisões item a item."""
    review = get_object_or_404(
        Review.objects.select_related(
            "submission",
            "submission__institution",
            "submission__municipality",
            "evaluation",
            "evaluation__analyst",
        ),
        id=review_id,
    )

    evaluation = review.evaluation
    if (
        request.user.role == User.Role.REVISOR
        and review.reviewer_id not in (None, request.user.pk)
        and not request.user.is_superuser
    ):
        raise PermissionDenied("Revisão atribuída a outro responsável.")
    decisions_map = {d.check_result_id: d for d in review.item_decisions.all()}
    sections = {}
    for req, definition, result in definition_rows(evaluation):
        section = sections.setdefault(req.pk, {"requirement": req, "checks": []})
        if result:
            section["checks"].append(
                {
                    "check": definition,
                    "result": result,
                    "decision": decisions_map.get(result.pk),
                    "status_choices": [
                        (v, label)
                        for v, label in CheckResult.Status.choices
                        if v in definition.allowed_statuses
                    ],
                }
            )
    req_sections = list(sections.values())

    conclude_form = ReviewConcludeForm(instance=review)
    can_edit = RolePermissionPolicy.can_edit_review(request.user, review)
    unresolved_checks = [
        result for result in blocking_results(evaluation) if result.pk not in decisions_map
    ]

    context = {
        "review": review,
        "submission": review.submission,
        "evaluation": evaluation,
        "req_sections": req_sections,
        "conclude_form": conclude_form,
        "can_edit": can_edit,
        "can_claim": review.status == Review.Status.PENDING and review.reviewer_id is None,
        "unresolved_checks": unresolved_checks,
    }
    return render(request, "reviews/detail.html", context)


@login_required
@require_role(User.Role.REVISOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
@require_POST
def review_claim_view(request, review_id):
    review = get_object_or_404(Review, pk=review_id)
    try:
        ReviewService.claim_review(review, request.user)
    except ValidationError as exc:
        messages.error(request, "; ".join(exc.messages))
    return redirect("review-detail", review_id=review.pk)


@login_required
@require_role(User.Role.REVISOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
@require_POST
def review_item_decision_view(
    request: HttpRequest,
    review_id: int,
    check_result_id: int,
) -> HttpResponse:
    """Salva decisão individual de confirmação ou divergência de um item."""
    review = get_object_or_404(Review, id=review_id)
    ReviewService.enforce_edit(review, request.user)
    if review.status != Review.Status.PENDING:
        messages.error(request, "Revisão já concluída não pode ser alterada.")
        return redirect("review-detail", review_id=review.id)

    if request.method == "POST":
        agrees = request.POST.get("agrees_with_analyst") == "true"
        status_revisor = request.POST.get("reviewer_status", "").strip()
        justification = request.POST.get("justification", "").strip()

        try:
            decision = ReviewService.record_item_decision(
                review=review,
                check_result_id=check_result_id,
                agrees_with_analyst=agrees,
                reviewer_status=status_revisor,
                justification=justification,
                actor=request.user,
            )
            messages.success(
                request,
                f"Decisão registrada para o item {decision.check_result.definition.code}.",
            )
        except ValidationError as exc:
            messages.error(request, str(exc))

    return redirect("review-detail", review_id=review.id)


@login_required
@require_role(User.Role.REVISOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
@require_POST
def review_conclude_view(request: HttpRequest, review_id: int) -> HttpResponse:
    """Conclui a revisão e emite o parecer oficial."""
    review = get_object_or_404(Review, id=review_id)
    ReviewService.enforce_edit(review, request.user)
    if request.method == "POST":
        form = ReviewConcludeForm(request.POST, instance=review)
        if form.is_valid():
            try:
                ReviewService.conclude_review(
                    review=review,
                    preliminary_result=form.cleaned_data["preliminary_result"],
                    decision_notes=form.cleaned_data["decision_notes"],
                    actor=request.user,
                )
            except ValidationError as exc:
                messages.error(request, "; ".join(exc.messages))
            else:
                messages.success(request, "Revisão concluída com sucesso.")
                return redirect("review-list")
        else:
            messages.error(request, "Informe um resultado e parecer válidos.")
    return redirect("review-detail", review_id=review.id)


@login_required
@require_role(User.Role.REVISOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
def diligence_list_view(request: HttpRequest) -> HttpResponse:
    """Fila e acompanhamento de diligências abertas no edital."""
    diligences = (
        Diligence.objects.all()
        .select_related("submission", "submission__institution", "requested_by")
        .order_by("-requested_at")
    )
    if request.user.role == User.Role.REVISOR and not request.user.is_superuser:
        diligences = diligences.filter(submission__reviews__reviewer=request.user).distinct()
    return render(
        request,
        "reviews/diligence_list.html",
        {"diligences": diligences, "total_count": diligences.count()},
    )


@login_required
@require_role(User.Role.REVISOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
def diligence_create_view(request: HttpRequest, submission_id: int) -> HttpResponse:
    """Abertura de diligência para um processo."""
    submission = get_object_or_404(Submission, id=submission_id)
    WorkflowService.enforce_diligence_actor(submission, request.user)

    if request.method == "POST":
        form = DiligenceCreateForm(request.POST, actor=request.user)
        if form.is_valid():
            reason = form.cleaned_data["reason"]
            deadline = form.cleaned_data["deadline"]
            try:
                WorkflowService.open_diligence(
                    submission=submission,
                    requested_by=request.user,
                    reason=reason,
                    deadline=deadline,
                    unsatisfied_return_status=form.cleaned_data.get("unsatisfied_return_status")
                    or None,
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(
                    request, f"Diligência aberta para o processo {submission.processo_sei}."
                )
                return redirect("diligence-list")
    else:
        form = DiligenceCreateForm(actor=request.user)

    return render(
        request,
        "reviews/diligence_create.html",
        {"form": form, "submission": submission},
    )


@login_required
@require_role(User.Role.REVISOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
def diligence_detail_view(request: HttpRequest, diligence_id: int) -> HttpResponse:
    """Registro de resposta e conclusão do julgamento da diligência."""
    diligence = get_object_or_404(
        Diligence.objects.select_related("submission", "submission__institution", "requested_by"),
        id=diligence_id,
    )
    WorkflowService.enforce_diligence_actor(diligence.submission, request.user)

    if request.method == "POST":
        form = DiligenceResponseForm(request.POST, instance=diligence)
        if form.is_valid():
            try:
                WorkflowService.conclude_diligence(
                    diligence=diligence,
                    actor=request.user,
                    result=form.cleaned_data["result"],
                    response_text=form.cleaned_data["response"],
                )
            except ValidationError as exc:
                form.add_error(None, exc)
            else:
                messages.success(
                    request,
                    f"Diligência do processo {diligence.submission.processo_sei} concluída.",
                )
                return redirect("diligence-list")
    else:
        form = DiligenceResponseForm(instance=diligence)

    return render(
        request,
        "reviews/diligence_detail.html",
        {"diligence": diligence, "form": form},
    )
