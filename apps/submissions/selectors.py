"""Spreadsheet-like operational list shared by home and process distribution."""

from django.core.paginator import Paginator
from django.db.models import Prefetch, Q

from apps.accounts.models import User
from apps.accounts.permissions import RolePermissionPolicy, ScopedQuerySetSelector
from apps.submissions.models import Assignment

STATUS_LABELS = {
    "RECEIVED": "Recebida",
    "ASSIGNED": "Distribuída",
    "UNDER_ANALYSIS": "Em análise",
    "PENDING_REVIEW": "Em revisão",
    "ELIGIBLE_FOR_RANKING": "Apta",
    "INELIGIBLE": "Inapta",
    "RANKED": "Classificada",
    "CLOSED": "Encerrada",
}


def operational_process_context(request, *, distribute=True):
    edital = request.operational_edital
    qs = (
        ScopedQuerySetSelector.for_submissions(request.user)
        .filter(edital=edital)
        .select_related("institution", "municipality", "edital", "evaluation")
        .prefetch_related(
            Prefetch(
                "assignments",
                queryset=Assignment.objects.filter(status="ACTIVE").select_related("analyst"),
                to_attr="active_assignments",
            )
        )
    )
    search = request.GET.get("q", "").strip()
    if search:
        qs = qs.filter(
            Q(processo_sei__icontains=search)
            | Q(institution__name__icontains=search)
            | Q(institution__cnpj__icontains=search)
        )
    filters = {
        key: request.GET.get(key, "").strip()
        for key in ("status", "group", "analyst", "uf", "municipality")
    }
    if filters["status"]:
        qs = qs.filter(workflow_status=filters["status"])
    if filters["group"]:
        qs = qs.filter(target_group=filters["group"])
    if filters["analyst"]:
        qs = (
            qs.filter(assignments__analyst_id=int(filters["analyst"]), assignments__status="ACTIVE")
            if filters["analyst"].isdecimal()
            else qs.none()
        )
    if filters["uf"]:
        qs = qs.filter(municipality__state=filters["uf"].upper())
    if filters["municipality"]:
        qs = qs.filter(municipality__name__icontains=filters["municipality"])
    page = Paginator(qs.order_by("received_at", "processo_sei"), 25).get_page(
        request.GET.get("page")
    )
    for sub in page:
        sub.operational_status = STATUS_LABELS.get(sub.workflow_status, "Registro histórico")
        sub.operational_analyst = (
            sub.active_assignments[0].analyst if sub.active_assignments else None
        )
        sub.can_assign = sub.workflow_status in {"RECEIVED", "ASSIGNED"} and not hasattr(
            sub, "evaluation"
        )
    query = request.GET.copy()
    query.pop("page", None)
    query.pop("edital", None)
    return {
        "edital": edital,
        "page_obj": page,
        "search_query": search,
        **{f"{key}_filter": value for key, value in filters.items()},
        "workflow_statuses": STATUS_LABELS.items(),
        "total_count": page.paginator.count,
        "target_groups": list(edital.target_groups.filter(active=True).values_list("code", "name")),
        "analysts": User.objects.filter(role="ANALISTA", is_active=True).order_by(
            "first_name", "username"
        ),
        "can_distribute": distribute
        and RolePermissionPolicy.can_distribute_submissions(request.user),
        "filter_query": query.urlencode(),
    }
