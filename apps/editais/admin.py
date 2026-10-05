from django.contrib import admin

from .models import (
    ClassificationPolicy,
    Edital,
    EditalConfigurationSnapshot,
    FundingRule,
    Program,
    ProgramMunicipality,
    Requirement,
    RequirementCheck,
    TargetGroup,
)


class PublishedRuleAdminMixin:
    def has_change_permission(self, request, obj=None):
        if obj is not None:
            edital = obj if isinstance(obj, Edital) else obj.configuration_edital
            if not edital.configuration_editable:
                return False
        return super().has_change_permission(request, obj)

    def has_delete_permission(self, request, obj=None):
        if obj is not None:
            edital = obj if isinstance(obj, Edital) else obj.configuration_edital
            if not edital.configuration_editable:
                return False
        return super().has_delete_permission(request, obj)


class RequirementCheckInline(admin.TabularInline):
    model = RequirementCheck
    extra = 1


@admin.register(Edital)
class EditalAdmin(PublishedRuleAdminMixin, admin.ModelAdmin):
    list_display = ("number", "year", "name", "status", "rules_version", "duplicate_policy")
    list_filter = ("status", "year")
    search_fields = ("number", "name")


@admin.register(ProgramMunicipality)
class ProgramMunicipalityAdmin(PublishedRuleAdminMixin, admin.ModelAdmin):
    list_display = ("municipality", "program_name", "edital", "active")
    list_filter = ("program_name", "active", "municipality__state")
    search_fields = ("municipality__name", "municipality__ibge_code", "program_name")


@admin.register(FundingRule)
class FundingRuleAdmin(PublishedRuleAdminMixin, admin.ModelAdmin):
    list_display = (
        "edital",
        "vacancy_type",
        "monthly_value",
        "duration_months",
    )
    list_filter = ("edital", "vacancy_type")


@admin.register(Requirement)
class RequirementAdmin(PublishedRuleAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "edital", "order", "mandatory", "active")
    list_filter = ("edital", "mandatory", "active")
    search_fields = ("code", "name")
    inlines = [RequirementCheckInline]


@admin.register(RequirementCheck)
class RequirementCheckAdmin(PublishedRuleAdminMixin, admin.ModelAdmin):
    list_display = ("code", "name", "requirement", "order", "active")
    list_filter = ("requirement__edital", "active")
    search_fields = ("code", "name")


@admin.register(TargetGroup)
class TargetGroupAdmin(PublishedRuleAdminMixin, admin.ModelAdmin):
    list_display = ("edital", "code", "name", "order", "active")


@admin.register(ClassificationPolicy)
class ClassificationPolicyAdmin(PublishedRuleAdminMixin, admin.ModelAdmin):
    list_display = ("edital", "policy_type")


@admin.register(Program)
class ProgramAdmin(admin.ModelAdmin):
    list_display = ("code", "name", "active")


@admin.register(EditalConfigurationSnapshot)
class EditalConfigurationSnapshotAdmin(admin.ModelAdmin):
    list_display = ("edital", "rules_version", "published_at", "published_by")
    readonly_fields = ("edital", "rules_version", "configuration", "published_at", "published_by")

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
