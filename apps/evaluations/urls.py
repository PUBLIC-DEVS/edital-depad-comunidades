from django.urls import path

from . import views

urlpatterns = [
    path(
        "processo/<int:submission_id>/",
        views.evaluation_workspace_view,
        name="evaluation-workspace",
    ),
    path(
        "<int:evaluation_id>/salvar-rascunho/",
        views.evaluation_save_draft_view,
        name="evaluation-save-draft",
    ),
    path(
        "<int:evaluation_id>/concluir/", views.evaluation_conclude_view, name="evaluation-conclude"
    ),
]
