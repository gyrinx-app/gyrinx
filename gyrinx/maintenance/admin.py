"""Mounts the maintenance console on the admin site.

Pattern mirrors ``gyrinx/analytics/admin.py``: subclass whatever admin.site is
currently using (so the chain composes — analytics's routes survive), add new
custom routes via ``get_urls``, then monkey-patch ``admin.site.__class__``.

For this to compose, the ``gyrinx.maintenance`` app must be listed AFTER
``gyrinx.analytics`` in ``INSTALLED_APPS``. Because this module patches the site
the moment it is imported, nothing that loads earlier — an edition's admin
package, in particular — may import it. The pieces an edition needs live in
``gyrinx.maintenance.registry`` and ``gyrinx.maintenance.views``.

The console's own pages are in ``views.py``; the repairs it can run come from
the registry, so this module knows nothing about any particular edition. All
routes are **superuser-gated** here (the standard ``admin_view`` wrapper only
enforces ``is_staff``; mutation-capable views need tighter control), which means
a registered operation cannot accidentally be published ungated.
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
)

__all__ = ["BackfillAdmin", "MaintenanceAdminSite", "OperationFilter"]


class OperationFilter(admin.SimpleListFilter):
    """Filter by operation, showing names rather than slugs.

    ``operation`` has no choices — the repairs come from the registry — so
    Django's own field filter would list bare slugs. Lookups are the slugs
    actually present in the data, labelled from the registry, so a record left
    behind by an edition that is no longer installed stays filterable.
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
    """Read-mostly: records are created by the maintenance trigger pages and
    updated by their task chains. The one legitimate edit is flipping a stale
    RUNNING record (task runner died mid-chain) to Failed so the maintenance
    pages' one-chain-at-a-time guard releases."""

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
    """Adds /admin/maintenance/* routes on top of whatever admin.site already is."""

    # Admin home shows a Maintenance banner to those who can use it
    # (superusers). The template extends the stock index — a different
    # template NAME, so no extends-recursion.
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
        custom += [
            path(
                op.route,
                self.admin_view(superuser_only(op.view)),
                name=op.url_name,
            )
            for op in operations()
        ]
        return custom + urls


# Install on the live admin site. Order in INSTALLED_APPS must place this app
# AFTER gyrinx.analytics so the chain composes (analytics's routes survive).
admin.site.__class__ = MaintenanceAdminSite
