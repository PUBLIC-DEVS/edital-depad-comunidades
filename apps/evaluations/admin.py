from django.contrib import admin

from .models import CheckResult, Evaluation


class CheckResultInline(admin.TabularInline):
    model = CheckResult
    extra = 0
    fields = ("requirement_check", "status", "sei_number", "pages", "valid_until", "numeric_value")


@admin.register(Evaluation)
class EvaluationAdmin(admin.ModelAdmin):
    list_display = ("submission", "analyst", "status", "result", "started_at", "completed_at")
    list_filter = ("status", "result", "analyst")
    search_fields = ("submission__processo_sei", "analyst__username")
    inlines = [CheckResultInline]


@admin.register(CheckResult)
class CheckResultAdmin(admin.ModelAdmin):
    list_display = ("evaluation", "requirement_check", "status", "sei_number", "valid_until")
    list_filter = ("status", "requirement_check__requirement")
    search_fields = ("evaluation__submission__processo_sei", "requirement_check__code")
