from django.urls import path

from . import views

app_name = "reporting"

urlpatterns = [
    path("", views.dashboard_metrics_view, name="dashboard"),
    path("validacoes/", views.validation_insights_view, name="validations"),
    path("falhas/<str:code>/", views.failed_requirement_processes_view, name="failed-requirement"),
    path("exportar/", views.metrics_export_csv_view, name="export-csv"),
]
