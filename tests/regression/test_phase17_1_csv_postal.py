import csv
import io
from decimal import Decimal

import pytest
from django.urls import reverse

from apps.audit.models import AuditEvent
from apps.csv_utils import sanitize_csv_cell
from apps.institutions.models import Institution
from apps.ranking.services import RankingService


@pytest.mark.parametrize(
    "value", ["=SUM(1,1)", "+cmd", "-1+2", "@foo", "\t=1", "\r=1", "  =1", "\x00@foo", "\ufeff=1"]
)
def test_csv_formula_strings_are_neutralized(value):
    assert sanitize_csv_cell(value) == "'" + value


@pytest.mark.parametrize("value", ["OSC regular", "123", "'=safe", "", None, -10, Decimal("-1.5")])
def test_csv_regular_text_and_real_numbers_are_preserved(value):
    assert sanitize_csv_cell(value) == value


@pytest.mark.django_db
def test_csv_export_routes_neutralize_user_values(client, domain):
    domain["sub"].institution.name = "=SUM(1,1)"
    domain["sub"].institution.save()
    sub = domain["sub"]
    sub.workflow_status = "ELIGIBLE_FOR_RANKING"
    sub.save()
    snapshot = RankingService.generate_snapshot(domain["edital"], domain["coord"])
    client.force_login(domain["coord"])
    response = client.get(reverse("ranking-export-csv", args=[snapshot.pk]))
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.content.decode("utf-8-sig")), delimiter=";"))
    assert rows[1][3] == "'=SUM(1,1)"
    domain["analyst"].first_name = "\t=1"
    domain["analyst"].save()
    response = client.get(reverse("reporting:export-csv"))
    assert response.status_code == 200
    rows = list(csv.reader(io.StringIO(response.content.decode()), delimiter=";"))
    assert any(row and row[0] == "'=1" for row in rows)


@pytest.mark.django_db
def test_institution_postal_create_edit_and_audit(client, domain):
    client.force_login(domain["admin"])
    data = {"cnpj": "11222333000181", "name": "CEP entidade", "postal_code": "01000000"}
    response = client.post(reverse("catalog-create", args=["instituicoes"]), data)
    assert response.status_code == 302
    institution = Institution.objects.get(cnpj=data["cnpj"])
    assert institution.postal_code == "01000-000"
    url = reverse("catalog-edit", args=["instituicoes", institution.pk])
    response = client.get(url)
    assert response.status_code == 200
    assert 'name="postal_code"' in response.content.decode()
    assert client.post(url, {**data, "postal_code": "02000-000"}).status_code == 302
    institution.refresh_from_db()
    assert institution.postal_code == "02000-000"
    event = AuditEvent.objects.get(
        entity_type="Institution", entity_id=str(institution.pk), field="postal_code"
    )
    assert event.old_value == "01000-000"
    assert event.new_value == "02000-000"
    response = client.post(url, {**data, "postal_code": "ABC"})
    assert response.status_code == 200
    institution.refresh_from_db()
    assert institution.postal_code == "02000-000"


@pytest.mark.django_db
@pytest.mark.parametrize("role", ["analyst", "consulta", "reviewer"])
def test_institution_postal_edit_denied(client, domain, role):
    client.force_login(domain[role])
    response = client.post(
        reverse("catalog-edit", args=["instituicoes", domain["sub"].institution_id]),
        {
            "cnpj": domain["sub"].institution.cnpj,
            "name": "Não autorizado",
            "postal_code": "01000-000",
        },
    )
    assert response.status_code == 403
    domain["sub"].institution.refresh_from_db()
    assert domain["sub"].institution.postal_code == ""
