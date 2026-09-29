"""Views para filas de revisão e gestão de diligências."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db.models import Q
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.permissions import RolePermissionPolicy, require_role
from apps.editais.models import Requirement
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
    requirements = (
        Requirement.objects.filter(edital=review.submission.edital, active=True)
        .prefetch_related("checks")
        .order_by("order", "code")
    )

    decisions_map = {
        d.check_result_id: d for d in review.item_decisions.select_related("check_result")
    }

    results_map = {
        cr.requirement_check_id: cr
        for cr in evaluation.check_results.select_related("requirement_check")
    }

    req_sections = []
    for req in requirements:
        checks_data = []
        for check in req.checks.filter(active=True).order_by("order", "code"):
            res = results_map.get(check.id)
            dec = decisions_map.get(res.id) if res else None
            checks_data.append({"check": check, "result": res, "decision": dec})
        req_sections.append({"requirement": req, "checks": checks_data})

    conclude_form = ReviewConcludeForm(instance=review)
    can_edit = RolePermissionPolicy.can_edit_review(request.user, review)

    context = {
        "review": review,
        "submission": review.submission,
        "evaluation": evaluation,
        "req_sections": req_sections,
        "conclude_form": conclude_form,
        "can_edit": can_edit,
        "can_claim": review.status == Review.Status.PENDING and review.reviewer_id is None,
    }
    return render(request, "reviews/detail.html", context)


@login_required
@require_role(User.Role.REVISOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
@require_POST
def review_claim_view(request, review_id):
    review = get_object_or_404(Review, pk=review_id)
    ReviewService.claim_review(review, request.user)
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
                f"Decisão registrada para o item {decision.check_result.requirement_check.code}.",
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
            ReviewService.conclude_review(
                review=review,
                preliminary_result=form.cleaned_data["preliminary_result"],
                decision_notes=form.cleaned_data["decision_notes"],
                actor=request.user,
            )
            messages.success(
                request,
                f"Revisão do processo {review.submission.processo_sei} concluída com sucesso.",
            )
            return redirect("review-list")
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
        form = DiligenceCreateForm(request.POST)
        if form.is_valid():
            reason = form.cleaned_data["reason"]
            deadline = form.cleaned_data["deadline"]
            WorkflowService.open_diligence(
                submission=submission,
                requested_by=request.user,
                reason=reason,
                deadline=deadline,
            )
            messages.success(
                request, f"Diligência aberta para o processo {submission.processo_sei}."
            )
            return redirect("diligence-list")
    else:
        form = DiligenceCreateForm()

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
            WorkflowService.conclude_diligence(
                diligence=diligence,
                actor=request.user,
                result=form.cleaned_data["result"],
                response_text=form.cleaned_data["response"],
            )
            messages.success(
                request, f"Diligência do processo {diligence.submission.processo_sei} concluída."
            )
            return redirect("diligence-list")
    else:
        form = DiligenceResponseForm(instance=diligence)

    return render(
        request,
        "reviews/diligence_detail.html",
        {"diligence": diligence, "form": form},
    )
