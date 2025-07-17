from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.shortcuts import render
from django.utils.translation import gettext as _

from gyrinx.core.models.auth import UserProfile


@admin.action(description="Add selected users to group")
def add_users_to_group(modeladmin, request, queryset):
    selected = queryset.values_list("pk", flat=True)

    if request.POST.get("post"):
        group_id = request.POST.get("group")

        if not group_id:
            modeladmin.message_user(
                request,
                _("Please select a group."),
                messages.ERROR,
            )
            return None

        try:
            group = Group.objects.get(pk=group_id)
            users_added = 0

            for user in queryset:
                if not user.groups.filter(pk=group.pk).exists():
                    user.groups.add(group)
                    users_added += 1

            if users_added:
                modeladmin.message_user(
                    request,
                    _("%(count)d user(s) were added to group '%(group)s'.")
                    % {
                        "count": users_added,
                        "group": group.name,
                    },
                    messages.SUCCESS,
                )
            else:
                modeladmin.message_user(
                    request,
                    _("All selected users were already in group '%(group)s'.")
                    % {
                        "group": group.name,
                    },
                    messages.INFO,
                )

        except Group.DoesNotExist:
            modeladmin.message_user(
                request,
                _("The selected group does not exist."),
                messages.ERROR,
            )
        except Exception as e:
            modeladmin.message_user(
                request,
                _("An error occurred: %s") % str(e),
                messages.ERROR,
            )

        return None

    # GET request - show selection form
    groups = Group.objects.all().order_by("name")

    if not groups.exists():
        modeladmin.message_user(
            request,
            _("No groups exist. Please create a group first."),
            messages.WARNING,
        )
        return None

    title = _("Add users to group")
    subtitle = _("Select a group to add the selected users to")

    context = {
        **modeladmin.admin_site.each_context(request),
        "title": title,
        "subtitle": subtitle,
        "queryset": queryset,
        "groups": groups,
        "action_name": "add_users_to_group",
        "selected": selected,
    }
    request.current_app = modeladmin.admin_site.name
    return render(
        request,
        "core/admin/add_users_to_group.html",
        context,
    )


# Unregister the default admin classes
admin.site.unregister(User)
admin.site.unregister(Group)


# Register with our custom admin classes
@admin.action(description="Remove selected users from group")
def remove_users_from_group(modeladmin, request, queryset):
    selected = queryset.values_list("pk", flat=True)

    if request.POST.get("post"):
        group_id = request.POST.get("group")

        if not group_id:
            modeladmin.message_user(
                request,
                _("Please select a group."),
                messages.ERROR,
            )
            return None

        try:
            group = Group.objects.get(pk=group_id)
            users_removed = 0

            for user in queryset:
                if user.groups.filter(pk=group.pk).exists():
                    user.groups.remove(group)
                    users_removed += 1

            if users_removed:
                modeladmin.message_user(
                    request,
                    _("%(count)d user(s) were removed from group '%(group)s'.")
                    % {
                        "count": users_removed,
                        "group": group.name,
                    },
                    messages.SUCCESS,
                )
            else:
                modeladmin.message_user(
                    request,
                    _("None of the selected users were in group '%(group)s'.")
                    % {
                        "group": group.name,
                    },
                    messages.INFO,
                )

        except Group.DoesNotExist:
            modeladmin.message_user(
                request,
                _("The selected group does not exist."),
                messages.ERROR,
            )
        except Exception as e:
            modeladmin.message_user(
                request,
                _("An error occurred: %s") % str(e),
                messages.ERROR,
            )

        return None

    # GET request - show selection form
    groups = Group.objects.all().order_by("name")

    if not groups.exists():
        modeladmin.message_user(
            request,
            _("No groups exist. Please create a group first."),
            messages.WARNING,
        )
        return None

    title = _("Remove users from group")
    subtitle = _("Select a group to remove the selected users from")

    context = {
        **modeladmin.admin_site.each_context(request),
        "title": title,
        "subtitle": subtitle,
        "queryset": queryset,
        "groups": groups,
        "action_name": "remove_users_from_group",
        "selected": selected,
    }
    request.current_app = modeladmin.admin_site.name
    return render(
        request,
        "core/admin/remove_users_from_group.html",
        context,
    )


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    list_display = ["user", "user__email", "tos_agreed_at"]
    search_fields = ["user__username", "user__email"]
    readonly_fields = ["tos_agreed_at"]

    def has_add_permission(self, request):
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    actions = list(BaseUserAdmin.actions) + [
        add_users_to_group,
        remove_users_from_group,
    ]


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin):
    pass
