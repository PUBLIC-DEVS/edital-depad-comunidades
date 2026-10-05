from django.urls import path

from . import views

urlpatterns = [
    path("", views.ranking_view, name="ranking-index"),
    path("gerar-snapshot/", views.ranking_generate_snapshot_view, name="ranking-generate-snapshot"),
    path("historico/", views.ranking_snapshots_history_view, name="ranking-history"),
    path("<int:snapshot_id>/exportar/", views.ranking_export_csv_view, name="ranking-export-csv"),
]
