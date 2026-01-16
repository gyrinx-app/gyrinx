"""
Admin interface for task execution monitoring.

Provides read-only views of task executions and state transitions
for debugging and monitoring purposes.
"""

from django.contrib import admin
from django.utils.html import format_html

from gyrinx.core.models.state_machine import StateTransition
from gyrinx.tasks.models import TaskExecution


@admin.register(TaskExecution)
class TaskExecutionAdmin(admin.ModelAdmin):
    """Admin view for task executions."""

    list_display = [
        "id_short",
        "task_name",
        "status_badge",
        "enqueued_at",
        "started_at",
        "finished_at",
        "duration_display",
    ]
    list_filter = ["status", "task_name"]
    search_fields = ["id", "task_name"]
    readonly_fields = [
        "id",
        "task_name",
        "status",
        "args",
        "kwargs",
        "return_value",
        "error_message",
        "error_traceback",
        "enqueued_at",
        "started_at",
        "finished_at",
        "created",
        "modified",
    ]
    ordering = ["-enqueued_at"]
    date_hierarchy = "enqueued_at"

    fieldsets = (
        (
            "Task Info",
            {
                "fields": ("id", "task_name", "status", "args", "kwargs"),
            },
        ),
        (
            "Timing",
            {
                "fields": ("enqueued_at", "started_at", "finished_at"),
            },
        ),
        (
            "Result",
            {
                "fields": ("return_value",),
                "classes": ("collapse",),
            },
        ),
        (
            "Error Details",
            {
                "fields": ("error_message", "error_traceback"),
                "classes": ("collapse",),
            },
        ),
        (
            "Metadata",
            {
                "fields": ("created", "modified"),
                "classes": ("collapse",),
            },
        ),
    )

    def has_add_permission(self, request):
        """Disable adding tasks through admin."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing tasks through admin."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Allow deletion for cleanup purposes."""
        return True

    @admin.display(description="ID")
    def id_short(self, obj):
        """Display shortened UUID."""
        return str(obj.id)[:8]

    @admin.display(description="Status")
    def status_badge(self, obj):
        """Display status with color-coded badge."""
        colors = {
            "READY": "#6c757d",  # gray
            "RUNNING": "#0d6efd",  # blue
            "SUCCESSFUL": "#198754",  # green
            "FAILED": "#dc3545",  # red
        }
        color = colors.get(obj.status, "#6c757d")
        return format_html(
            '<span style="background-color: {}; color: white; padding: 2px 8px; '
            'border-radius: 3px; font-size: 11px;">{}</span>',
            color,
            obj.status,
        )

    @admin.display(description="Duration")
    def duration_display(self, obj):
        """Display task duration if available."""
        duration = obj.duration
        if duration:
            total_seconds = duration.total_seconds()
            if total_seconds < 1:
                return f"{total_seconds * 1000:.0f}ms"
            elif total_seconds < 60:
                return f"{total_seconds:.2f}s"
            else:
                minutes = int(total_seconds // 60)
                seconds = total_seconds % 60
                return f"{minutes}m {seconds:.0f}s"
        return "-"


@admin.register(StateTransition)
class StateTransitionAdmin(admin.ModelAdmin):
    """Admin view for state transitions."""

    list_display = [
        "id",
        "content_type",
        "object_id_short",
        "transition_display",
        "transitioned_at",
    ]
    list_filter = ["content_type", "to_status", "from_status"]
    search_fields = ["object_id"]
    readonly_fields = [
        "id",
        "content_type",
        "object_id",
        "from_status",
        "to_status",
        "transitioned_at",
        "metadata",
    ]
    ordering = ["-transitioned_at"]
    date_hierarchy = "transitioned_at"

    def has_add_permission(self, request):
        """Disable adding transitions through admin."""
        return False

    def has_change_permission(self, request, obj=None):
        """Disable editing transitions through admin."""
        return False

    def has_delete_permission(self, request, obj=None):
        """Disable deleting transitions through admin."""
        return False

    @admin.display(description="Object ID")
    def object_id_short(self, obj):
        """Display shortened UUID."""
        return str(obj.object_id)[:8]

    @admin.display(description="Transition")
    def transition_display(self, obj):
        """Display transition as arrow."""
        if obj.from_status:
            return f"{obj.from_status} → {obj.to_status}"
        return f"(initial) → {obj.to_status}"
