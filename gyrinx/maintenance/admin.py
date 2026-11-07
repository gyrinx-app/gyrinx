"""Mount the superuser-only maintenance console on the admin site.

Subclass the active site class so analytics routes remain available. Load
gyrinx.maintenance after gyrinx.analytics; earlier-loading apps must use
maintenance.registry or maintenance.views instead of importing this module.
Wrap registered operation routes here so edition pages share the same gate.
"""

from django.contrib import admin
from django.urls import path

from gyrinx.maintenance.models import Backfill
from gyrinx.maintenance.registry import all_operations, operations
from gyrinx.maintenance.views import (
    backfill_cancel_view,
    backfill_detail_view,
    maintenance_index_view,
    superuser_only,
    write_pause_view,
)

__all__ = ["BackfillAdmin", "MaintenanceAdminSite", "OperationFilter"]


class OperationFilter(admin.SimpleListFilter):
    """Label stored operation slugs from the registry.

    Include slugs from existing records even when their operation is no longer
    registered, keeping those records filterable.
    """

    title = "operation"
    parameter_name = "operation"

    def lookups(self, request, model_admin):
        registered = {op.operation: op.name for op in all_operations()}
        seen = (
            model_admin.model.objects.order_by()
            .values_list("operation", flat=True)
            .distinct()
        )
        return sorted(
            ((slug, registered.get(slug, slug)) for slug in seen),
            key=lambda pair: pair[1],
        )

    def queryset(self, request, queryset):
        value = self.value()
        return queryset.filter(operation=value) if value else queryset


@admin.register(Backfill)
class BackfillAdmin(admin.ModelAdmin):
    """Display task-maintained repair records with an editable status.

    Status edits allow recovery from stalled runs; creation belongs to the
    maintenance trigger pages.
    """

    list_display = [
        "operation_name",
        "status",
        "triggered_by",
        "list_id_scope",
        "created",
    ]
    list_filter = [OperationFilter, "status"]
    readonly_fields = [
        "operation_name",
        "triggered_by",
        "list_id_scope",
        "summary",
        "error",
        "created",
        "modified",
    ]
    fields = readonly_fields + ["status"]

    @admin.display(description="Operation", ordering="operation")
    def operation_name(self, obj):
        return obj.operation_label

    def has_add_permission(self, request):
        return False  # created by the maintenance pages, never by hand


class MaintenanceAdminSite(admin.site.__class__):
    """Add maintenance routes while retaining the active admin site's existing routes."""

    # Use a distinct template name so extending the stock index cannot recurse.
    index_template = "admin/maintenance/admin_index.html"

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "maintenance/",
                self.admin_view(superuser_only(maintenance_index_view)),
                name="maintenance_index",
            ),
            path(
                "maintenance/write-pauses/<slug:scope>/",
                self.admin_view(superuser_only(write_pause_view)),
                name="maintenance_write_pause",
            ),
            path(
                "maintenance/backfill/<uuid:pk>/",
                self.admin_view(superuser_only(backfill_detail_view)),
                name="maintenance_backfill_detail",
            ),
            path(
                "maintenance/backfill/<uuid:pk>/cancel/",
                self.admin_view(superuser_only(backfill_cancel_view)),
                name="maintenance_backfill_cancel",
            ),
        ]
        for op in operations():
            wrapped = self.admin_view(superuser_only(op.view))
            wrapped.write_scope = op.write_scope
            custom.append(path(op.route, wrapped, name=op.url_name))
        return custom + urls


# Install after analytics so this subclass retains its routes.
admin.site.__class__ = MaintenanceAdminSite
