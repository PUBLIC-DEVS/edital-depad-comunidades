"""Views para gestão, triagem e distribuição de processos."""

import csv
import io

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied, ValidationError
from django.db import transaction
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.permissions import (
    RolePermissionPolicy,
    ScopedQuerySetSelector,
    enforce_submission_access,
    require_role,
)
from apps.audit.models import AuditEvent
from apps.editais.models import Edital
from apps.editais.operational import operational_edital_required
from apps.institutions.models import Municipality
from apps.ranking.services import ClassificationService
from apps.submissions.forms import (
    BulkAssignmentForm,
    ParticipationRestrictionForm,
    SingleAssignmentForm,
    SubmissionCnpjCorrectionForm,
    SubmissionIntakeForm,
)
from apps.submissions.models import ParticipationRestriction, Submission
from apps.submissions.selectors import operational_process_context
from apps.submissions.services.distribution import DistributionService
from apps.submissions.services.eligibility import ParticipationEligibilityService
from apps.submissions.services.identity import SubmissionIdentityService
from apps.submissions.services.intake import SubmissionIntakeService
from apps.submissions.services.validation import SubmissionAnomalyDetector
from apps.submissions.services.workflow import WorkflowService


@login_required
@require_role(
    User.Role.DISTRIBUIDOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR, User.Role.CONSULTA
)
@operational_edital_required
def submission_list_view(request: HttpRequest) -> HttpResponse:
    context = operational_process_context(request)
    if request.headers.get("HX-Request") and not request.headers.get("HX-Boosted"):
        return render(request, "submissions/partials/table.html", context)
    return render(request, "submissions/list.html", context)


@login_required
@require_role(User.Role.DISTRIBUIDOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
@transaction.atomic
@operational_edital_required
def submission_create_view(request: HttpRequest) -> HttpResponse:
    """Cadastro manual ou recepção de novo processo no edital."""
    if request.method == "POST":
        form = SubmissionIntakeForm(request.POST, operational_edital=request.operational_edital)
        if form.is_valid():
            intake = SubmissionIntakeService.create_submission(form, request.user)
            submission, restrictions = intake.submission, intake.restrictions
            if restrictions:
                messages.error(
                    request,
                    "CNPJ com contrato/restrição ativa. A participação foi bloqueada antes da análise.",
                )
            else:
                messages.success(
                    request, f"Processo {submission.processo_sei} cadastrado com sucesso."
                )
            return redirect("submission-detail", submission_id=submission.id)
    else:
        form = SubmissionIntakeForm(operational_edital=request.operational_edital)

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
    restricted = ParticipationEligibilityService.is_restricted(submission)
    if (
        RolePermissionPolicy.can_distribute_submissions(request.user)
        and not restricted
        and submission.workflow_status in {"RECEIVED", "ASSIGNED"}
        and not hasattr(submission, "evaluation")
    ):
        assignment_form = SingleAssignmentForm()

    context = {
        "submission": submission,
        "alerts": alerts,
        "assignment_history": assignment_history,
        "assignment_form": assignment_form,
        "can_distribute": RolePermissionPolicy.can_distribute_submissions(request.user),
        "restricted": restricted,
        "can_release_restriction": (
            request.user.is_superuser or request.user.role in {"ADMINISTRADOR", "COORDENADOR"}
        )
        and ParticipationEligibilityService.is_preanalysis_block(submission)
        and not restricted,
        "can_edit": RolePermissionPolicy.can_distribute_submissions(request.user)
        and not hasattr(submission, "evaluation")
        and submission.edital.status == "ACTIVE",
        "can_correct_cnpj": (
            request.user.is_superuser
            or request.user.role
            in {
                User.Role.ADMINISTRADOR,
                User.Role.COORDENADOR,
            }
        )
        and (
            not hasattr(submission, "evaluation")
            or (
                submission.evaluation.status == "DRAFT"
                and submission.workflow_status == "UNDER_ANALYSIS"
            )
        ),
    }
    return render(request, "submissions/detail.html", context)


@login_required
@require_role(User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
@require_POST
def submission_cnpj_correction_view(request, submission_id):
    submission = enforce_submission_access(request, submission_id)
    form = SubmissionCnpjCorrectionForm(request.POST)
    if form.is_valid():
        try:
            SubmissionIdentityService.correct_cnpj(
                submission,
                form.cleaned_data["cnpj"],
                form.cleaned_data["reason"],
                request.user,
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(
                request,
                "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc),
            )
        else:
            messages.success(request, "CNPJ corrigido com justificativa e trilha de auditoria.")
    else:
        errors = [message for values in form.errors.values() for message in values]
        messages.error(request, "; ".join(errors))
    return redirect("submission-detail", submission_id=submission_id)


@login_required
@require_role(User.Role.DISTRIBUIDOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
@require_POST
def submission_assign_view(request: HttpRequest, submission_id: int) -> HttpResponse:
    """Atribui ou redistribui um processo individualmente."""
    submission = enforce_submission_access(request, submission_id)
    if request.method == "POST":
        form = SingleAssignmentForm(request.POST)
        if form.is_valid():
            analyst = form.cleaned_data["analyst"]
            reason = form.cleaned_data["reason"]
            try:
                WorkflowService.assign_analyst(submission, analyst, request.user, reason)
            except (PermissionDenied, ValidationError) as exc:
                messages.error(
                    request,
                    "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc),
                )
            else:
                messages.success(request, f"Processo atribuído a {analyst.username}.")
    return redirect("submission-detail", submission_id=submission.id)


@login_required
@require_role(User.Role.DISTRIBUIDOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
@require_POST
def submission_bulk_assign_view(request: HttpRequest) -> HttpResponse:
    """Atribui múltiplos processos selecionados a um analista."""
    if request.method == "POST":
        form = BulkAssignmentForm(request.POST)
        if form.is_valid():
            ids_raw = form.cleaned_data["selected_ids"]
            submission_ids = [int(i.strip()) for i in ids_raw.split(",") if i.strip().isdigit()]
            analyst = form.cleaned_data["analyst"]
            reason = form.cleaned_data["reason"]

            try:
                count = DistributionService.bulk_assign(
                    submission_ids=submission_ids,
                    analyst_id=analyst.pk,
                    assigned_by=request.user,
                    reason=reason,
                )
            except (PermissionDenied, ValidationError) as exc:
                messages.error(
                    request,
                    "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc),
                )
            else:
                messages.success(request, f"{count} processos atribuídos a {analyst.username}.")
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
@require_role(User.Role.DISTRIBUIDOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
def submission_anomalies_view(request: HttpRequest) -> HttpResponse:
    """Fila de exceções e anomalias cadastrais/processuais."""
    base_qs = ScopedQuerySetSelector.for_submissions(request.user).select_related(
        "institution", "municipality", "edital"
    )

    anomalous_submissions = []
    for sub in base_qs:
        alerts = SubmissionAnomalyDetector.check_submission(sub)
        filter_type = request.GET.get("tipo", "")
        if filter_type:
            alerts = [alert for alert in alerts if alert.code == filter_type]
        if alerts:
            sub.alerts = alerts
            anomalous_submissions.append(sub)

    return render(
        request,
        "submissions/anomalies.html",
        {
            "submissions": anomalous_submissions,
            "total_anomalies": len(anomalous_submissions),
            "filter_type": request.GET.get("tipo", ""),
            "exception_types": (
                "ACTIVE_CONTRACT_RESTRICTION",
                "DUPLICATE_CNPJ",
                "INVALID_CNPJ",
                "NO_TARGET_GROUP",
            ),
        },
    )


@login_required
@require_role(User.Role.DISTRIBUIDOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
def restriction_list_view(request):
    return render(
        request,
        "submissions/restrictions.html",
        {
            "restrictions": ParticipationRestriction.objects.select_related(
                "edital", "created_by"
            ).order_by("-created_at"),
        },
    )


@login_required
@require_role(User.Role.DISTRIBUIDOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
def restriction_form_view(request, restriction_id=None):
    restriction = (
        get_object_or_404(ParticipationRestriction, pk=restriction_id)
        if restriction_id
        else ParticipationRestriction()
    )
    form = ParticipationRestrictionForm(request.POST or None, instance=restriction)
    if request.method == "POST" and form.is_valid():
        instance = form.save(commit=False)
        try:
            if restriction_id:
                ParticipationEligibilityService.update_restriction(instance, request.user)
            else:
                ParticipationEligibilityService.create_restriction(instance, request.user)
        except ValidationError as exc:
            form.add_error(None, "; ".join(exc.messages))
        else:
            messages.success(request, "Restrição salva e auditada.")
            return redirect("restriction-list")
    return render(
        request,
        "administration/form.html",
        {
            "form": form,
            "title": "Editar restrição" if restriction_id else "Nova restrição de participação",
            "back_url": "/processos/restricoes/",
        },
    )


@login_required
@require_role(User.Role.DISTRIBUIDOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
@transaction.atomic
def submission_edit_view(request, submission_id):
    submission = enforce_submission_access(request, submission_id)
    submission = Submission.objects.select_for_update().get(pk=submission.pk)
    if hasattr(submission, "evaluation") or submission.edital.status != Edital.Status.ACTIVE:
        messages.error(
            request,
            "Edição administrativa bloqueada após início da análise ou encerramento do edital.",
        )
        return redirect("submission-detail", submission_id=submission.pk)
    old_values = {
        field.name: getattr(submission, field.attname) for field in Submission._meta.concrete_fields
    }
    form = SubmissionIntakeForm(request.POST or None, instance=submission)
    if request.method == "POST" and form.is_valid():
        submission = form.save()
        for field in Submission._meta.concrete_fields:
            if field.name in {"created_at", "updated_at"}:
                continue
            new = getattr(submission, field.attname)
            if old_values[field.name] != new:
                AuditEvent.objects.create(
                    actor=request.user,
                    entity_type="Submission",
                    entity_id=str(submission.pk),
                    action="ADMIN_EDIT",
                    field=field.name,
                    old_value=str(old_values[field.name]),
                    new_value=str(new),
                )
        ClassificationService.classify_and_update(submission, request.user)
        messages.success(request, "Dados do processo atualizados.")
        return redirect("submission-detail", submission_id=submission.pk)
    return render(
        request,
        "administration/form.html",
        {"form": form, "title": "Editar processo", "back_url": f"/processos/{submission.pk}/"},
    )


@login_required
@require_role(User.Role.DISTRIBUIDOR, User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
@operational_edital_required
def submission_import_csv_view(request):
    """Import a UTF-8 CSV into a published edital; every row uses the ordinary intake form."""
    edital = request.operational_edital
    errors = []
    if request.method == "POST":
        upload = request.FILES.get("file")
        if not edital:
            errors.append("Selecione um edital ativo.")
        if not upload or upload.size > 5_000_000:
            errors.append("Envie um CSV UTF-8 de até 5 MB.")
        if not errors:
            try:
                stream = io.StringIO(upload.read().decode("utf-8-sig"), newline="")
                rows = list(csv.DictReader(stream))
            except (UnicodeError, csv.Error) as exc:
                errors.append(f"CSV inválido: {exc}")
                rows = []
            expected = {
                "processo_sei",
                "recebido_em",
                "cnpj",
                "instituicao",
                "ibge",
                "vagas_femininas",
                "vagas_masculinas",
                "vagas_maes_nutrizes",
                "vagas_solicitadas",
                "capacidade_total",
            }
            optional = {"grupo_codigo", "contato_email", "contato_telefone", "endereco"}
            headers = (
                set(csv.DictReader(io.StringIO(stream.getvalue())).fieldnames or [])
                if not errors
                else set()
            )
            if not rows or not expected.issubset(headers):
                errors.append(
                    "CSV vazio ou sem colunas obrigatórias: " + ", ".join(sorted(expected))
                )
            elif headers - expected - optional:
                errors.append(
                    "Colunas não reconhecidas: " + ", ".join(sorted(headers - expected - optional))
                )
            elif any(None in row or any(value is None for value in row.values()) for row in rows):
                errors.append("CSV com número incorreto de colunas em alguma linha.")
            if len(rows) > 1000:
                errors.append("Máximo de 1000 processos por importação.")
            if not errors:

                class CsvRowError(Exception):
                    pass

                try:
                    with transaction.atomic():
                        for row_number, row in enumerate(rows, 2):
                            municipality = Municipality.objects.filter(
                                ibge_code=(row.get("ibge") or "").strip()
                            ).first()
                            if municipality is None:
                                raise CsvRowError(
                                    f"Linha {row_number}: código IBGE não cadastrado."
                                )
                            group_code = (row.get("grupo_codigo") or "").strip()
                            group = edital.target_groups.filter(
                                code=group_code, active=True
                            ).first()
                            if group_code and group is None:
                                raise CsvRowError(
                                    f"Linha {row_number}: grupo não pertence ao edital."
                                )
                            if (
                                group_code
                                and edital.classification_policy.policy_type
                                != "MANUAL_TARGET_POLICY_V1"
                            ):
                                raise CsvRowError(
                                    f"Linha {row_number}: grupo_codigo só é aceito em classificação manual."
                                )
                            data = {
                                "edital": edital.pk,
                                "municipality": municipality.pk,
                                "processo_sei": row.get("processo_sei", ""),
                                "received_at": row.get("recebido_em", ""),
                                "institution_cnpj": row.get("cnpj", ""),
                                "institution_name": row.get("instituicao", ""),
                                "institution_email": row.get("contato_email", ""),
                                "institution_phone": row.get("contato_telefone", ""),
                                "institution_address": row.get("endereco", ""),
                                "vagas_femininas": row.get("vagas_femininas", "0"),
                                "vagas_masculinas": row.get("vagas_masculinas", "0"),
                                "vagas_maes_nutrizes": row.get("vagas_maes_nutrizes", "0"),
                                "vagas_solicitadas": row.get("vagas_solicitadas", "0"),
                                "capacidade_total": row.get("capacidade_total", "0"),
                                "target_group_definition": group.pk if group else "",
                            }
                            form = SubmissionIntakeForm(data)
                            if not form.is_valid():
                                raise CsvRowError(
                                    f"Linha {row_number}: "
                                    + "; ".join(
                                        f"{field}: {', '.join(values)}"
                                        for field, values in form.errors.items()
                                    )
                                )
                            SubmissionIntakeService.create_submission(
                                form, request.user, source="CSV", source_row=row_number
                            )
                except (CsvRowError, ValidationError) as exc:
                    errors.append(str(exc))
                else:
                    messages.success(request, f"{len(rows)} processos importados e enquadrados.")
                    return redirect("submission-list")
    return render(
        request,
        "submissions/import_csv.html",
        {
            "errors": errors,
            "edital": edital,
        },
    )


@login_required
@require_role(User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
@require_POST
def submission_restriction_release_view(request, submission_id):
    submission = enforce_submission_access(request, submission_id)
    reason = request.POST.get("reason", "")
    if request.POST.get("confirm") != "on":
        messages.error(request, "Confirme a liberação formal do processo.")
    else:
        try:
            ParticipationEligibilityService.release_preanalysis_block(
                submission, request.user, reason
            )
        except (PermissionDenied, ValidationError) as exc:
            messages.error(
                request, "; ".join(exc.messages) if isinstance(exc, ValidationError) else str(exc)
            )
        else:
            messages.success(request, "Processo liberado para nova distribuição, com auditoria.")
    return redirect("submission-detail", submission_id=submission_id)
