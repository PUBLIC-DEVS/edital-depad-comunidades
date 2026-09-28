from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from apps.evaluations.views import my_evaluations_view
from apps.reporting.views import dashboard_metrics_view
from config.views import health_check

urlpatterns = [
    path("admin/", admin.site.urls),
    path("health/", health_check, name="health-check"),
    path("login/", auth_views.LoginView.as_view(template_name="accounts/login.html"), name="login"),
    path("logout/", auth_views.LogoutView.as_view(next_page="login"), name="logout"),
    path("processos/", include("apps.submissions.urls")),
    path("avaliacoes/", include("apps.evaluations.urls")),
    path("minhas-analises/", my_evaluations_view, name="my-evaluations"),
    path("revisoes/", include("apps.reviews.urls")),
    path("diligencias/", include("apps.reviews.diligence_urls")),
    path("classificacao/", include("apps.ranking.urls")),
    path("metricas/", include("apps.reporting.urls")),
    path("", dashboard_metrics_view, name="dashboard"),
]
