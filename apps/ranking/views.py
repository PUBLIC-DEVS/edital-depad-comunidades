"""Views para visualização, filtros e geração de snapshots de classificação e ranking."""

import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.http import Http404, HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.models import User
from apps.accounts.permissions import RolePermissionPolicy, require_role
from apps.editais.models import Edital
from apps.ranking.models import RankingSnapshot
from apps.ranking.services import RankingService


@login_required
@require_role(User.Role.COORDENADOR, User.Role.ADMINISTRADOR, User.Role.CONSULTA)
def ranking_view(request: HttpRequest) -> HttpResponse:
    """Exibe o ranking oficial com filtros por edital, grupo e histórico de snapshots."""
    edital_id = request.GET.get("edital")
    if edital_id:
        if not edital_id.isdecimal():
            raise Http404
        edital = get_object_or_404(Edital, id=int(edital_id))
    else:
        edital = Edital.objects.order_by("-year", "-number").first()

    group_filter = request.GET.get("group", "").strip()
    snapshot_id = request.GET.get("snapshot_id")

    latest_snapshot = None
    if edital:
        if snapshot_id:
            if not snapshot_id.isdecimal():
                raise Http404
            latest_snapshot = RankingSnapshot.objects.filter(edital=edital, id=snapshot_id).first()
        else:
            latest_snapshot = (
                RankingSnapshot.objects.filter(edital=edital).order_by("-created_at").first()
            )

    entries = []
    if latest_snapshot:
        qs = latest_snapshot.entries.select_related(
            "submission",
            "submission__institution",
            "submission__municipality",
        ).order_by("target_group", "position")
        if group_filter:
            qs = qs.filter(target_group=group_filter)
        entries = list(qs)

    can_generate = bool(
        edital
        and edital.status in {Edital.Status.ACTIVE, Edital.Status.CLOSED}
        and RolePermissionPolicy.can_generate_ranking(request.user)
    )

    context = {
        "edital": edital,
        "editais": Edital.objects.all().order_by("-year", "-number"),
        "latest_snapshot": latest_snapshot,
        "entries": entries,
        "group_filter": group_filter,
        "target_groups": list(
            edital.target_groups.filter(active=True).values_list("code", flat=True)
        )
        if edital
        else [],
        "can_generate": can_generate,
        "snapshot_types": RankingSnapshot.SnapshotType.choices,
    }
    return render(request, "ranking/index.html", context)


@login_required
@require_role(User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
@require_POST
def ranking_generate_snapshot_view(request: HttpRequest) -> HttpResponse:
    """Gera um novo snapshot imutável de ranking para o edital selecionado."""
    if request.method == "POST":
        edital_id = request.POST.get("edital_id")
        if not edital_id or not edital_id.isdecimal():
            raise Http404
        edital = get_object_or_404(Edital, id=int(edital_id))
        snapshot_type = request.POST.get("snapshot_type", RankingSnapshot.SnapshotType.PRELIMINAR)
        description = request.POST.get("description", "").strip()

        try:
            if edital.status not in {Edital.Status.ACTIVE, Edital.Status.CLOSED}:
                raise ValidationError(
                    "Publique o edital antes de classificar; editais arquivados são somente leitura."
                )
            snapshot = RankingService.generate_snapshot(
                edital=edital,
                actor=request.user,
                snapshot_type=snapshot_type,
                description=description,
            )
        except ValidationError as exc:
            messages.error(request, str(exc))
            return redirect(f"/classificacao/?edital={edital.id}")

        messages.success(
            request,
            f"Snapshot de Ranking '{snapshot.get_snapshot_type_display()}' gerado com sucesso com {snapshot.entries.count()} inscrições.",
        )
        return redirect(f"/classificacao/?edital={edital.id}&snapshot_id={snapshot.id}")
    return redirect("ranking-index")


@login_required
@require_role(User.Role.COORDENADOR, User.Role.ADMINISTRADOR, User.Role.CONSULTA)
def ranking_snapshots_history_view(request: HttpRequest) -> HttpResponse:
    """Exibe o histórico auditável de snapshots de classificação gerados."""
    snapshots = (
        RankingSnapshot.objects.all()
        .select_related("edital", "generated_by")
        .order_by("-created_at")
    )
    return render(
        request,
        "ranking/history.html",
        {"snapshots": snapshots, "total_count": snapshots.count()},
    )


@login_required
@require_role(User.Role.COORDENADOR, User.Role.ADMINISTRADOR, User.Role.CONSULTA)
def ranking_export_csv_view(request: HttpRequest, snapshot_id: int) -> HttpResponse:
    """Exporta o snapshot oficial em formato CSV delimitado por ponto e vírgula."""
    snapshot = get_object_or_404(RankingSnapshot, id=snapshot_id)
    if not snapshot.policy_metadata.get("eligible_statuses"):
        return HttpResponse(
            "Snapshot anterior ao hardening: conteúdo não validado para exportação oficial.",
            status=409,
        )
    entries = snapshot.entries.select_related(
        "submission",
        "submission__institution",
        "submission__municipality",
    ).order_by("target_group", "position")

    response = HttpResponse(content_type="text/csv; charset=utf-8-sig")
    filename = (
        f"ranking_{snapshot.edital.number}_{snapshot.edital.year}_{snapshot.snapshot_type}.csv"
    )
    response["Content-Disposition"] = f'attachment; filename="{filename}"'

    writer = csv.writer(response, delimiter=";")
    writer.writerow(
        [
            "Posição",
            "Grupo",
            "Processo SEI",
            "Instituição",
            "CNPJ",
            "Município",
            "UF",
            "Recebimento",
            "Vagas",
            "Status de Qualificação",
            "Duplicidade Suprimida",
            "Critérios de Desempate",
        ]
    )

    for entry in entries:
        writer.writerow(
            [
                entry.position,
                entry.target_group,
                entry.snapshot_data.get("processo_sei", entry.submission.processo_sei),
                entry.snapshot_data.get("institution", ""),
                entry.snapshot_data.get("cnpj", ""),
                entry.snapshot_data.get("municipality", ""),
                entry.snapshot_data.get("state", ""),
                entry.received_at.strftime("%d/%m/%Y %H:%M:%S"),
                entry.total_vacancies,
                entry.qualification_status,
                "SIM" if entry.is_duplicate_suppressed else "NÃO",
                entry.tie_breaker_notes,
            ]
        )

    return response
