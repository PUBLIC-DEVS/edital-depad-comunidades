"""Test-only URLconf for retained configuration views, absent from product routes."""

from django.urls import include, path

from config.urls import urlpatterns as operational_patterns

urlpatterns = [path("admin-editais/", include("apps.editais.urls"))] + [
    pattern for pattern in operational_patterns if str(pattern.pattern) != "admin-editais/"
]
