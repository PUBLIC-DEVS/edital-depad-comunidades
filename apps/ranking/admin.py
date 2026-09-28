from django.contrib import admin

from .models import RankingEntry, RankingSnapshot


class RankingEntryInline(admin.TabularInline):
    model = RankingEntry
    extra = 0
    readonly_fields = (
        "submission",
        "target_group",
        "position",
        "received_at",
        "total_vacancies",
        "is_duplicate_suppressed",
    )


@admin.register(RankingSnapshot)
class RankingSnapshotAdmin(admin.ModelAdmin):
    list_display = (
        "edital",
        "snapshot_type",
        "rules_version",
        "duplicate_policy",
        "generated_by",
        "created_at",
    )
    list_filter = ("edital", "snapshot_type")
    inlines = [RankingEntryInline]


@admin.register(RankingEntry)
class RankingEntryAdmin(admin.ModelAdmin):
    list_display = (
        "snapshot",
        "target_group",
        "position",
        "submission",
        "received_at",
        "is_duplicate_suppressed",
    )
    list_filter = ("target_group", "is_duplicate_suppressed", "snapshot__snapshot_type")
    search_fields = ("submission__processo_sei",)
