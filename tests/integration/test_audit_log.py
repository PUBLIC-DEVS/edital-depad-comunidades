"""Regressão do log unificado (auditoria + acessos) e seu visualizador."""

import pytest
from django.urls import reverse

from apps.audit.models import AuditEvent

pytestmark = pytest.mark.django_db


def test_page_access_creates_access_event(client, domain):
    client.force_login(domain["admin"])
    before = AuditEvent.objects.filter(action="ACCESS").count()
    response = client.get(reverse("audit-log"))
    assert response.status_code == 200
    events = AuditEvent.objects.filter(action="ACCESS")
    assert events.count() == before + 1
    event = events.order_by("-timestamp").first()
    assert event.entity_type == "Página"
    assert event.entity_id == reverse("audit-log")
    assert event.is_access
    assert event.category_label == "[acesso]"


def test_stream_endpoint_not_logged(client, domain):
    """O polling de auto-refresh não pode floodar o log de acessos."""
    client.force_login(domain["admin"])
    before = AuditEvent.objects.filter(action="ACCESS").count()
    assert client.get(reverse("audit-log-stream")).status_code == 200
    assert AuditEvent.objects.filter(action="ACCESS").count() == before


def test_modification_event_category(domain):
    event = AuditEvent.objects.create(
        actor=domain["admin"],
        entity_type="User",
        entity_id="1",
        action="UPDATE",
        field="role",
        old_value="CONSULTA",
        new_value="ANALISTA",
    )
    assert not event.is_access
    assert event.category_label == "[modificação]"


def test_log_viewer_is_admin_only(client, domain):
    client.force_login(domain["consulta"])
    assert client.get(reverse("audit-log")).status_code == 403
    assert client.get(reverse("audit-export")).status_code == 403
    client.force_login(domain["reviewer"])
    assert client.get(reverse("audit-log")).status_code == 403


def test_export_csv(client, domain):
    AuditEvent.objects.create(
        actor=domain["admin"], entity_type="User", entity_id="1", action="UPDATE"
    )
    client.force_login(domain["admin"])
    response = client.get(reverse("audit-export"))
    assert response.status_code == 200
    assert "text/csv" in response["Content-Type"]
    assert "attachment" in response.get("Content-Disposition", "")
    content = b"".join(response.streaming_content).decode("utf-8", "ignore")
    assert "timestamp;categoria;usuario" in content


def test_category_filter(client, domain):
    AuditEvent.objects.create(
        actor=domain["admin"], entity_type="User", entity_id="1", action="UPDATE"
    )
    client.force_login(domain["admin"])
    only_access = client.get(reverse("audit-log"), {"cat": "acesso"})
    only_mod = client.get(reverse("audit-log"), {"cat": "modificacao"})
    assert only_access.status_code == 200
    assert only_mod.status_code == 200
