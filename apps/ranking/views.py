"""Views para visualização, filtros e geração de snapshots de classificação e ranking."""

import csv

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import HttpRequest, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render

from apps.accounts.models import User
from apps.accounts.permissions import RolePermissionPolicy, require_role
from apps.editais.models import Edital
from apps.ranking.models import RankingSnapshot
from apps.ranking.services import RankingService


@login_required
def ranking_view(request: HttpRequest) -> HttpResponse:
    """Exibe o ranking oficial com filtros por edital, grupo e histórico de snapshots."""
    edital_id = request.GET.get("edital")
    if edital_id:
        edital = get_object_or_404(Edital, id=edital_id)
    else:
        edital = Edital.objects.order_by("-year", "-number").first()

    group_filter = request.GET.get("group", "").strip()
    snapshot_id = request.GET.get("snapshot_id")

    latest_snapshot = None
    if edital:
        if snapshot_id:
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

    can_generate = RolePermissionPolicy.can_generate_ranking(request.user)

    context = {
        "edital": edital,
        "editais": Edital.objects.all().order_by("-year", "-number"),
        "latest_snapshot": latest_snapshot,
        "entries": entries,
        "group_filter": group_filter,
        "target_groups": ["G1", "G2", "G3"],
        "can_generate": can_generate,
        "snapshot_types": RankingSnapshot.SnapshotType.choices,
    }
    return render(request, "ranking/index.html", context)


@login_required
@require_role(User.Role.COORDENADOR, User.Role.ADMINISTRADOR)
def ranking_generate_snapshot_view(request: HttpRequest) -> HttpResponse:
    """Gera um novo snapshot imutável de ranking para o edital selecionado."""
    if request.method == "POST":
        edital_id = request.POST.get("edital_id")
        edital = get_object_or_404(Edital, id=edital_id)
        snapshot_type = request.POST.get("snapshot_type", RankingSnapshot.SnapshotType.PRELIMINAR)
        description = request.POST.get("description", "").strip()

        snapshot = RankingService.generate_snapshot(
            edital=edital,
            actor=request.user,
            snapshot_type=snapshot_type,
            description=description,
        )

        messages.success(
            request,
            f"Snapshot de Ranking '{snapshot.get_snapshot_type_display()}' gerado com sucesso com {snapshot.entries.count()} inscrições.",
        )
        return redirect(f"/classificacao/?edital={edital.id}&snapshot_id={snapshot.id}")
    return redirect("ranking-index")


@login_required
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
def ranking_export_csv_view(request: HttpRequest, snapshot_id: int) -> HttpResponse:
    """Exporta o snapshot oficial em formato CSV delimitado por ponto e vírgula."""
    snapshot = get_object_or_404(RankingSnapshot, id=snapshot_id)
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
                entry.submission.processo_sei,
                entry.submission.institution.name,
                entry.submission.institution.formatted_cnpj,
                entry.submission.municipality.name,
                entry.submission.municipality.state,
                entry.received_at.strftime("%d/%m/%Y %H:%M:%S"),
                entry.total_vacancies,
                entry.qualification_status,
                "SIM" if entry.is_duplicate_suppressed else "NÃO",
                entry.tie_breaker_notes,
            ]
        )

    return response
