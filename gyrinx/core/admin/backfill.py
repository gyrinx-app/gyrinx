"""Admin for Backfill audit records.

Read-mostly: records are created by the maintenance trigger pages and
updated by their task chains. The one legitimate edit is flipping a stale
RUNNING record (task runner died mid-chain) to Failed so the maintenance
pages' one-chain-at-a-time guard releases.
"""

from django.contrib import admin

from gyrinx.core.models import Backfill

__all__ = ["BackfillAdmin"]


@admin.register(Backfill)
class BackfillAdmin(admin.ModelAdmin):
    list_display = ["operation", "status", "triggered_by", "list_id_scope", "created"]
    list_filter = ["operation", "status"]
    readonly_fields = [
        "operation",
        "triggered_by",
        "list_id_scope",
        "summary",
        "error",
        "created",
        "modified",
    ]
    fields = readonly_fields + ["status"]

    def has_add_permission(self, request):
        return False  # created by the maintenance pages, never by hand
