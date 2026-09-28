from django.urls import path

from . import views

urlpatterns = [
    path("", views.diligence_list_view, name="diligence-list"),
    path("nova/<int:submission_id>/", views.diligence_create_view, name="diligence-create"),
    path("<int:diligence_id>/", views.diligence_detail_view, name="diligence-detail"),
]
