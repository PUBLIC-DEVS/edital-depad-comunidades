from django.contrib import admin

from apps.audit.admin_support import ReadOnlyOperationalAdmin

from .models import Diligence, Review, ReviewItemDecision


class ReviewItemDecisionInline(ReadOnlyOperationalAdmin, admin.TabularInline):
    model = ReviewItemDecision
    extra = 0


@admin.register(Review)
class ReviewAdmin(ReadOnlyOperationalAdmin, admin.ModelAdmin):
    list_display = (
        "submission",
        "reviewer",
        "status",
        "preliminary_result",
        "created_at",
        "completed_at",
    )
    list_filter = ("status", "preliminary_result", "reviewer")
    search_fields = ("submission__processo_sei", "reviewer__username")
    inlines = [ReviewItemDecisionInline]


@admin.register(Diligence)
class DiligenceAdmin(ReadOnlyOperationalAdmin, admin.ModelAdmin):
    list_display = ("submission", "requested_by", "deadline", "status", "result", "requested_at")
    list_filter = ("status", "result")
    search_fields = ("submission__processo_sei", "requested_by__username")
