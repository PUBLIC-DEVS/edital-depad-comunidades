import csv
import io

import pytest
from django.urls import reverse
from django.utils import timezone

from apps.accounts.models import User
from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db


@pytest.fixture
def audit_admin(client):
    admin = User.objects.create_user(username="audit-admin", role=User.Role.ADMINISTRADOR)
    client.force_login(admin)
    return admin


@pytest.mark.parametrize("prefix", ["=", "+", "-", "@", "\t=", "\ufeff=", "\r\n="])
def test_export_neutralizes_formulas_in_all_user_supplied_cells(client, audit_admin, prefix):
    formula = f"{prefix}1+1"
    audit_admin.username = formula
    audit_admin.email = formula
    audit_admin.save(update_fields=["username", "email"])
    AuditEvent.objects.create(
        actor=audit_admin,
        entity_type=formula,
        entity_id=formula,
        action=formula,
        field=formula,
        old_value=formula,
        new_value=formula,
        metadata=formula,
    )

    response = client.get(reverse("audit-export"))

    assert response.status_code == 200
    content = b"".join(response.streaming_content).decode("utf-8")
    rows = list(csv.reader(io.StringIO(content), delimiter=";"))
    assert len(rows) == 2
    assert rows[1][2:] == ["'" + formula] * 9


@pytest.mark.parametrize("endpoint", ["audit-log", "audit-log-stream", "audit-export"])
@pytest.mark.parametrize("field", ["from", "to"])
@pytest.mark.parametrize("invalid_date", ["2026-02-30", "2026-13-01", "not-a-date"])
def test_invalid_date_filter_does_not_crash(client, audit_admin, endpoint, field, invalid_date):
    event = AuditEvent.objects.create(entity_type="Entity", entity_id="date-test", action="UPDATE")

    response = client.get(reverse(endpoint), {field: invalid_date})

    assert response.status_code == 200
    if response.streaming:
        assert b"date-test" in b"".join(response.streaming_content)
    else:
        assert event in response.context["page"].object_list


@pytest.mark.parametrize("endpoint", ["audit-log", "audit-log-stream", "audit-export"])
def test_valid_date_range_filters_results(client, audit_admin, endpoint):
    event = AuditEvent.objects.create(entity_type="Entity", entity_id="date-test", action="UPDATE")
    today = timezone.localdate(event.timestamp).isoformat()

    response = client.get(reverse(endpoint), {"from": today, "to": today})
    assert response.status_code == 200
    if response.streaming:
        assert b"date-test" in b"".join(response.streaming_content)
    else:
        assert event in response.context["page"].object_list

    response = client.get(reverse(endpoint), {"to": "1900-01-01"})
    assert response.status_code == 200
    if response.streaming:
        assert b"date-test" not in b"".join(response.streaming_content)
    else:
        assert event not in response.context["page"].object_list


@pytest.mark.parametrize("endpoint", ["audit-log", "audit-log-stream"])
def test_audit_log_renders_system_events_without_actor(client, audit_admin, endpoint):
    AuditEvent.objects.create(
        actor=None,
        entity_type="System",
        entity_id="sys-event-01",
        action="SYSTEM_BOOT",
    )

    response = client.get(reverse(endpoint))

    assert response.status_code == 200
    body = response.content.decode("utf-8")
    assert "SISTEMA" in body
    assert "sys-event-01" in body
