from django.conf import settings
from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.accounts.views import ms_callback, ms_login
from apps.evaluations.views import my_evaluations_view
from config.views import dashboard, health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("administracao/", include("apps.administration.urls")),
    path("admin-editais/", include("apps.editais.operational_urls")),
    path("health/", health_check, name="health-check"),
    path(
        "login/",
        auth_views.LoginView.as_view(
            template_name="accounts/login.html",
            extra_context={"microsoft_login_enabled": settings.AUTH_ADAPTER.lower() == "microsoft"},
        ),
        name="login",
    ),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("auth/microsoft/login/", ms_login, name="microsoft-login"),
    path("auth/microsoft/callback/", ms_callback, name="microsoft-callback"),
    path("processos/", include("apps.submissions.urls")),
    path("avaliacoes/", include("apps.evaluations.urls")),
    path("minhas-analises/", my_evaluations_view, name="my-evaluations"),
    path("revisoes/", include("apps.reviews.urls")),
    path("diligencias/", include("apps.reviews.diligence_urls")),
    path("classificacao/", include("apps.ranking.urls")),
    path("metricas/", include("apps.reporting.urls")),
    path("", dashboard, name="dashboard"),
]
