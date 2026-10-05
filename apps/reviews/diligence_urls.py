from django.urls import path

from apps.editais.operational import disabled_diligence

urlpatterns = [
    path("", disabled_diligence, name="diligence-list"),
    path("nova/<int:submission_id>/", disabled_diligence, name="diligence-create"),
    path("<int:diligence_id>/", disabled_diligence, name="diligence-detail"),
]
