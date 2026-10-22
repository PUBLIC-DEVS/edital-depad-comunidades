from django.urls import path

from . import views

urlpatterns = [
    path("", views.audit_log_view, name="audit-log"),
    path("stream/", views.audit_log_stream_view, name="audit-log-stream"),
    path("exportar/", views.audit_export_csv_view, name="audit-export"),
]
