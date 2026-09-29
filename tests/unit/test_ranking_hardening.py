import pytest
from django.contrib import admin
from django.core.exceptions import PermissionDenied, ValidationError
from django.test import RequestFactory
from django.utils import timezone

from apps.audit.models import AuditEvent
from apps.institutions.models import Institution
from apps.ranking.models import RankingEntry, RankingSnapshot
from apps.ranking.services import RankingService
from apps.submissions.models import Submission

pytestmark = pytest.mark.django_db


def sub(domain, sei, status="ELIGIBLE_FOR_RANKING", institution=None, minutes=1, vacancies=10):
    return Submission.objects.create(
        edital=domain["edital"],
        institution=institution or domain["sub"].institution,
        processo_sei=sei,
        municipality=domain["sub"].municipality,
        received_at=domain["sub"].received_at + timezone.timedelta(minutes=minutes),
        vagas_masculinas=vacancies,
        workflow_status=status,
    )


def test_ineligible_first_duplicate_blocks_later_and_has_no_position(domain):
    second = sub(domain, "TEST-B")
    snapshot = RankingService.generate_snapshot(domain["edital"], domain["coord"])
    assert not snapshot.entries.exists()
    exclusion = snapshot.exclusions.get(submission=second)
    assert exclusion.reason_code == "DUPLICATE_SUPPRESSED"
    assert exclusion.duplicate_of == domain["sub"]
    assert snapshot.exclusions.get(submission=domain["sub"]).reason_code == "NOT_ELIGIBLE"


def test_eligible_duplicate_scope_is_explicit(domain):
    domain["edital"].duplicate_scope = "ELIGIBLE"
    domain["edital"].save()
    second = sub(domain, "TEST-B")
    snapshot = RankingService.generate_snapshot(domain["edital"], domain["coord"])
    assert snapshot.entries.get().submission == second


def test_only_valid_entries_receive_consecutive_positions_and_audit(domain):
    first = domain["sub"]
    first.workflow_status = "ELIGIBLE_FOR_RANKING"
    first.save()
    sub(domain, "TEST-B")
    other = Institution.objects.create(cnpj="00000000000272", name="Other")
    third = sub(domain, "TEST-C", institution=other, minutes=2)
    fourth = Institution.objects.create(cnpj="00000000000353", name="Closed")
    sub(domain, "TEST-D", "CLOSED", fourth, 3)
    snapshot = RankingService.generate_snapshot(domain["edital"], domain["coord"])
    assert list(snapshot.entries.values_list("position", flat=True)) == [1, 2]
    assert snapshot.entries.count() == 2
    assert AuditEvent.objects.filter(
        entity_type="Submission",
        entity_id=str(third.pk),
        action="WORKFLOW_TRANSITION",
        new_value="RANKED",
    ).exists()
    first.refresh_from_db()
    assert first.target_group == "G3"
    assert AuditEvent.objects.filter(action="CLASSIFICATION_CHANGE").exists()


@pytest.mark.parametrize(
    "operation",
    [
        "snapshot_save",
        "entry_save",
        "snapshot_delete",
        "entry_delete",
        "query_update",
        "query_delete",
        "entry_add",
    ],
)
def test_ranking_immutable_in_common_orm_paths(domain, operation):
    domain["sub"].workflow_status = "ELIGIBLE_FOR_RANKING"
    domain["sub"].save()
    snapshot = RankingService.generate_snapshot(domain["edital"], domain["coord"])
    entry = snapshot.entries.get()
    with pytest.raises(PermissionDenied):
        if operation == "snapshot_save":
            snapshot.description = "tampered"
            snapshot.save()
        elif operation == "entry_save":
            entry.position = 4
            entry.save()
        elif operation == "snapshot_delete":
            snapshot.delete()
        elif operation == "entry_delete":
            entry.delete()
        elif operation == "query_update":
            RankingSnapshot.objects.filter(pk=snapshot.pk).update(description="tampered")
        elif operation == "query_delete":
            RankingEntry.objects.filter(pk=entry.pk).delete()
        else:
            RankingEntry.objects.create(
                snapshot=snapshot,
                submission=domain["sub"],
                target_group="G3",
                position=3,
                received_at=domain["sub"].received_at,
            )
    snapshot.refresh_from_db()
    entry.refresh_from_db()
    assert entry.position == 1
    assert snapshot.description != "tampered"


def test_ranking_admin_is_read_only(domain):
    request = RequestFactory().get("/admin/")
    request.user = domain["admin"]
    for model in (RankingEntry, RankingSnapshot):
        model_admin = admin.site._registry[model]
        assert not model_admin.has_change_permission(request)
        assert not model_admin.has_delete_permission(request)
        assert not model_admin.has_add_permission(request)


def test_absolute_tie_requires_configured_policy(domain):
    domain["sub"].workflow_status = "ELIGIBLE_FOR_RANKING"
    domain["sub"].save()
    other = Institution.objects.create(cnpj="00000000000272", name="Other")
    sub(domain, "TEST-B", institution=other, minutes=0)
    with pytest.raises(ValidationError, match="OPEN BUSINESS QUESTION"):
        RankingService.generate_snapshot(domain["edital"], domain["coord"])
    assert not RankingSnapshot.objects.exists()
