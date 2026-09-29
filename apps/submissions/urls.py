from django.urls import path

from . import views

urlpatterns = [
    path("", views.submission_list_view, name="submission-list"),
    path("restricoes/", views.restriction_list_view, name="restriction-list"),
    path("restricoes/novo/", views.restriction_form_view, name="restriction-create"),
    path(
        "restricoes/<int:restriction_id>/editar/",
        views.restriction_form_view,
        name="restriction-edit",
    ),
    path("importar-csv/", views.submission_import_csv_view, name="submission-import-csv"),
    path("novo/", views.submission_create_view, name="submission-create"),
    path(
        "<int:submission_id>/corrigir-cnpj/",
        views.submission_cnpj_correction_view,
        name="submission-cnpj-correction",
    ),
    path("<int:submission_id>/", views.submission_detail_view, name="submission-detail"),
    path("<int:submission_id>/editar/", views.submission_edit_view, name="submission-edit"),
    path("<int:submission_id>/atribuir/", views.submission_assign_view, name="submission-assign"),
    path("atribuicao-em-lote/", views.submission_bulk_assign_view, name="submission-bulk-assign"),
    path(
        "sugestao-distribuicao/",
        views.submission_suggest_distribution_view,
        name="submission-suggest-distribution",
    ),
    path("excecoes/", views.submission_anomalies_view, name="submission-anomalies"),
]
