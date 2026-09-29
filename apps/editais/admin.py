from django.contrib import admin

from .models import Edital, FundingRule, ProgramMunicipality, Requirement, RequirementCheck


class RequirementCheckInline(admin.TabularInline):
    model = RequirementCheck
    extra = 1


@admin.register(Edital)
class EditalAdmin(admin.ModelAdmin):
    list_display = ("number", "year", "name", "status", "rules_version", "duplicate_policy")
    list_filter = ("status", "year")
    search_fields = ("number", "name")


@admin.register(ProgramMunicipality)
class ProgramMunicipalityAdmin(admin.ModelAdmin):
    list_display = ("municipality", "program_name", "edital", "active")
    list_filter = ("program_name", "active", "municipality__state")
    search_fields = ("municipality__name", "municipality__ibge_code", "program_name")


@admin.register(FundingRule)
class FundingRuleAdmin(admin.ModelAdmin):
    list_display = (
        "edital",
        "vacancy_type",
        "monthly_value",
        "duration_months",
    )
    list_filter = ("edital", "vacancy_type")


@admin.register(Requirement)
class RequirementAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "edital", "order", "mandatory", "active")
    list_filter = ("edital", "mandatory", "active")
    search_fields = ("code", "name")
    inlines = [RequirementCheckInline]


@admin.register(RequirementCheck)
class RequirementCheckAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "requirement", "order", "active")
    list_filter = ("requirement__edital", "active")
    search_fields = ("code", "name")
