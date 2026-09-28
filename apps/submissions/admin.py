from django.contrib import admin

from .models import Assignment, Submission


class AssignmentInline(admin.TabularInline):
    model = Assignment
    extra = 0
    readonly_fields = ("assigned_at",)


@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = (
        "processo_sei",
        "institution",
        "municipality",
        "received_at",
        "workflow_status",
        "target_group",
        "vagas_solicitadas",
    )
    list_filter = ("edital", "workflow_status", "target_group", "municipality__state")
    search_fields = ("processo_sei", "institution__name", "institution__cnpj")
    inlines = [AssignmentInline]


@admin.register(Assignment)
class AssignmentAdmin(admin.ModelAdmin):
    list_display = ("submission", "analyst", "assigned_by", "assigned_at", "status")
    list_filter = ("status", "analyst")
    search_fields = ("submission__processo_sei", "analyst__username")
