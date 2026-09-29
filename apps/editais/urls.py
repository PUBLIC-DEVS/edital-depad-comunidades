from django.urls import path

from . import views

urlpatterns = [
    path("", views.edital_list, name="edital-list"),
    path("novo/", views.edital_form, name="edital-create"),
    path("<int:edital_id>/", views.edital_detail, name="edital-detail"),
    path("<int:edital_id>/editar/", views.edital_form, name="edital-edit"),
    path("<int:edital_id>/publicar/", views.edital_publish, name="edital-publish"),
    path("<int:edital_id>/duplicar/", views.edital_clone, name="edital-clone"),
    path("<int:edital_id>/status/", views.edital_status, name="edital-status"),
    path("<int:edital_id>/<str:section>/", views.section_list, name="edital-section"),
    path("<int:edital_id>/<str:section>/novo/", views.section_form, name="edital-section-create"),
    path(
        "<int:edital_id>/<str:section>/<int:object_id>/editar/",
        views.section_form,
        name="edital-section-edit",
    ),
    path(
        "<int:edital_id>/<str:section>/<int:object_id>/<str:action>/",
        views.section_action,
        name="edital-section-action",
    ),
]
