from django.contrib import admin

from .models import RankingEntry, RankingExclusion, RankingSnapshot


class ReadOnlyRankingAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def get_readonly_fields(self, request, obj=None):
        return tuple(f.name for f in self.model._meta.fields)


@admin.register(RankingSnapshot)
class RankingSnapshotAdmin(ReadOnlyRankingAdmin):
    list_display = ("edital", "snapshot_type", "generated_by", "created_at")


@admin.register(RankingEntry)
class RankingEntryAdmin(ReadOnlyRankingAdmin):
    list_display = ("snapshot", "target_group", "position", "submission")


@admin.register(RankingExclusion)
class RankingExclusionAdmin(ReadOnlyRankingAdmin):
    list_display = ("snapshot", "submission", "reason_code", "duplicate_of")
