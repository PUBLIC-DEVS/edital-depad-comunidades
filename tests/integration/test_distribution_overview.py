"""Regressão da visão consolidada de distribuições dos processos."""

import pytest
from django.urls import reverse

from tests.operational_helpers import publish_fixture

pytestmark = pytest.mark.django_db


@pytest.mark.parametrize(
    "role,allowed",
    [
        ("admin", True),
        ("coord", True),
        ("distributor", True),
        ("consulta", False),
        ("analyst", False),
        ("reviewer", False),
    ],
)
def test_distribution_overview_permissions(client, domain, role, allowed):
    publish_fixture(domain["edital"])
    client.force_login(domain[role])
    response = client.get(reverse("distribution-overview"))
    assert response.status_code == (200 if allowed else 403)


def test_distribution_overview_lists_assigned_analyst(client, domain):
    publish_fixture(domain["edital"])
    client.force_login(domain["admin"])
    body = client.get(reverse("distribution-overview")).content.decode()
    assert "Distribuições dos processos" in body
    assert "Carga por analista" in body
    # a submissão do fixture está atribuída ao analista
    assert domain["analyst"].username in body


def test_distribution_overview_filter_without_assignment(client, domain):
    publish_fixture(domain["edital"])
    client.force_login(domain["admin"])
    # com analista: a submissão atribuída aparece
    with_analyst = client.get(reverse("distribution-overview"), {"dist": "com"})
    assert with_analyst.status_code == 200
    assert domain["sub"].processo_sei in with_analyst.content.decode()
    # sem distribuição: a submissão atribuída NÃO aparece
    without = client.get(reverse("distribution-overview"), {"dist": "sem"})
    assert domain["sub"].processo_sei not in without.content.decode()
