from django.urls import path

from . import views

urlpatterns = [
    path("", views.submission_list_view, name="submission-list"),
    path("novo/", views.submission_create_view, name="submission-create"),
    path("<int:submission_id>/", views.submission_detail_view, name="submission-detail"),
    path("<int:submission_id>/atribuir/", views.submission_assign_view, name="submission-assign"),
    path("atribuicao-em-lote/", views.submission_bulk_assign_view, name="submission-bulk-assign"),
    path("sugestao-distribuicao/", views.submission_suggest_distribution_view, name="submission-suggest-distribution"),
    path("excecoes/", views.submission_anomalies_view, name="submission-anomalies"),
]
