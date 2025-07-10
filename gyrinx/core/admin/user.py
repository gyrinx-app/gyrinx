from django import forms
from django.contrib import admin

from gyrinx.content.models import ContentBadge
from gyrinx.core.models import CoreUserBadgeAssignment

from .base import BaseAdmin


class CoreUserBadgeAssignmentForm(forms.ModelForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Order badges by active status and name
        self.fields["badge"].queryset = ContentBadge.objects.filter(
            active=True
        ).order_by("name")

    class Meta:
        model = CoreUserBadgeAssignment
        fields = "__all__"


@admin.register(CoreUserBadgeAssignment)
class CoreUserBadgeAssignmentAdmin(BaseAdmin):
    form = CoreUserBadgeAssignmentForm
    list_display = ["user", "badge", "is_active", "created"]
    list_display_links = ["user"]
    list_filter = ["is_active", "badge", "created"]
    search_fields = [
        "user__username",
        "user__email",
        "badge__name",
        "badge__display_text",
    ]
    actions = ["make_active", "make_inactive"]

    @admin.action(description="Make selected badges active")
    def make_active(self, request, queryset):
        # Group by user to handle one at a time
        users = {}
        for assignment in queryset:
            if assignment.user not in users:
                users[assignment.user] = []
            users[assignment.user].append(assignment)

        updated_count = 0
        for user, assignments in users.items():
            # Only make the first one active for each user
            if assignments:
                assignments[0].is_active = True
                assignments[0].save()
                updated_count += 1

        self.message_user(
            request,
            f"{updated_count} badge(s) made active. Only one badge per user can be active.",
        )

    @admin.action(description="Make selected badges inactive")
    def make_inactive(self, request, queryset):
        updated_count = queryset.update(is_active=False)
        self.message_user(request, f"{updated_count} badge(s) made inactive.")
