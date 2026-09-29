from django.urls import path

from . import views

urlpatterns = [
    path("<int:review_id>/assumir/", views.review_claim_view, name="review-claim"),
    path("", views.review_list_view, name="review-list"),
    path("<int:review_id>/", views.review_detail_view, name="review-detail"),
    path(
        "<int:review_id>/item/<int:check_result_id>/",
        views.review_item_decision_view,
        name="review-item-decision",
    ),
    path("<int:review_id>/concluir/", views.review_conclude_view, name="review-conclude"),
]
