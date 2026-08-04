from django.contrib import admin

from n23.core.models import ImpersonationLog


@admin.register(ImpersonationLog)
class ImpersonationLogAdmin(admin.ModelAdmin):
    """Read-only view of impersonation sessions (audit trail)."""

    list_display = ["owner", "target", "created", "ended_at", "ended_reason"]
    list_filter = ["ended_reason", "created"]
    search_fields = ["owner__username", "target__username"]
    readonly_fields = [
        "owner",
        "target",
        "created",
        "modified",
        "ended_at",
        "ended_reason",
    ]
    ordering = ["-created"]

    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
