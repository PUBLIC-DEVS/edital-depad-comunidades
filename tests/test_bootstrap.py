import pytest
from django.urls import reverse

from apps.accounts.adapters import LocalAuthAdapter, get_auth_adapter
from apps.accounts.models import User


@pytest.mark.django_db
class TestBootstrapFoundation:
    def test_health_check_endpoint(self, client):
        response = client.get(reverse("health-check"))
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["database"] == "connected"

    def test_custom_user_creation(self):
        user = User.objects.create_user(
            username="analista1",
            email="analista1@mds.gov.br",
            password="securePassword123!",
            role=User.Role.ANALISTA,
        )
        assert user.pk is not None
        assert user.role == User.Role.ANALISTA
        assert user.is_analyst is True
        assert user.is_reviewer is False
        assert user.is_coordinator is False
        assert str(user) == f"analista1 ({user.get_role_display()})"

    def test_superuser_creation(self):
        admin = User.objects.create_superuser(
            username="admin_user",
            email="admin@mds.gov.br",
            password="adminPassword123!",
        )
        assert admin.is_superuser is True
        assert admin.is_staff is True
        assert admin.role == User.Role.ADMINISTRADOR
        assert admin.is_admin_role is True

    def test_admin_page_renders(self, client):
        response = client.get("/admin/login/?next=/admin/")
        assert response.status_code == 200

    def test_login_page_renders(self, client):
        response = client.get(reverse("login"))
        assert response.status_code == 200

    def test_local_auth_adapter_resolution(self):
        adapter = get_auth_adapter()
        assert isinstance(adapter, LocalAuthAdapter)
