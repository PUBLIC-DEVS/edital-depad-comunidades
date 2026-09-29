from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="administration-index"),
    path("instituicoes/<int:institution_id>/", views.institution_detail, name="institution-detail"),
    path("<str:catalog>/", views.catalog_list, name="catalog-list"),
    path("<str:catalog>/novo/", views.catalog_form, name="catalog-create"),
    path("<str:catalog>/<int:object_id>/editar/", views.catalog_form, name="catalog-edit"),
]
