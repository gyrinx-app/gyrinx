import csv

from allauth.account.admin import EmailAddressAdmin as AllauthEmailAddressAdmin
from allauth.account.internal.flows.email_verification import get_email_verification_url
from allauth.account.models import EmailAddress
from django import forms
from django.contrib import admin, messages
from django.contrib.auth.admin import GroupAdmin as BaseGroupAdmin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import Group, User
from django.http import HttpResponse
from django.shortcuts import render
from django.urls import path
from django.utils.html import format_html
from django.utils.safestring import mark_safe
from django.utils.translation import gettext as _

from gyrinx import artwork
from gyrinx.accounts.models import Badge, BadgeGrant, UserProfile

#: Where uploaded badge artwork lands in the site's storage.
BADGE_UPLOAD_PREFIX = "badges/"


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


@admin.action(description="Add selected users to group")
def add_profiles_to_group(modeladmin, request, queryset):
    selected = queryset.values_list("pk", flat=True)

    if request.POST.get("post") == "yes":
        group_pk = request.POST.get("group")
        try:
            group = Group.objects.get(pk=group_pk)
            users = User.objects.filter(profile__pk__in=selected)
            already_in = set(
                group.user_set.filter(id__in=users).values_list("id", flat=True)
            )
            to_add = users.exclude(id__in=already_in)
            count = to_add.count()
            if count:
                group.user_set.add(*to_add)
            modeladmin.message_user(
                request,
                f"Added {count} user(s) to {group.name}"
                f" ({len(already_in)} already in group).",
                messages.SUCCESS if count else messages.INFO,
            )
        except Group.DoesNotExist:
            modeladmin.message_user(
                request, "The selected group does not exist.", messages.ERROR
            )
        return None

    # Build a user queryset for display in the template.
    users_qs = User.objects.filter(profile__pk__in=selected).order_by("username")

    context = {
        **modeladmin.admin_site.each_context(request),
        "title": "Add users to group",
        "subtitle": "Select a group to add the selected users to",
        "queryset": users_qs,
        "groups": Group.objects.order_by("name"),
        "action_name": "add_profiles_to_group",
        "selected": selected,
    }
    return render(request, "core/admin/add_users_to_group.html", context)


def _grant_badge(modeladmin, request, users, selected, action_name):
    """Grant one badge to a set of people, behind a confirmation page.

    Shared by the action on people and the one on profiles, because the only
    thing that differs between them is how the selection was made.

    Re-granting is not an error: the second run reports how many already had it
    rather than refusing the lot, which is what makes it safe to run again after
    adding a few more names to the list.
    """
    if request.POST.get("post") == "yes":
        badge = Badge.objects.filter(pk=request.POST.get("badge")).first()
        if badge is None:
            modeladmin.message_user(
                request, "That badge does not exist.", messages.ERROR
            )
            return None

        reason = (request.POST.get("reason") or "").strip()
        granted = 0
        for user in users:
            # Matches the partial unique constraint exactly — a lookup that
            # missed a row would trip the constraint instead of being a no-op.
            _, created = BadgeGrant.objects.get_or_create(
                badge=badge,
                user=user,
                audience=BadgeGrant.Audience.USER,
                defaults={"granted_by": request.user, "reason": reason},
            )
            granted += 1 if created else 0

        already = len(users) - granted
        modeladmin.message_user(
            request,
            f"Granted {badge.title} to {granted} person(s) ({already} already had it).",
            messages.SUCCESS if granted else messages.INFO,
        )
        return None

    context = {
        **modeladmin.admin_site.each_context(request),
        "title": "Grant a badge",
        "subtitle": "Choose the badge to grant to the selected people",
        "users": users,
        "badges": Badge.objects.filter(archived=False).order_by("title"),
        "action_name": action_name,
        "selected": selected,
    }
    request.current_app = modeladmin.admin_site.name
    return render(request, "admin/grant_badge.html", context)


@admin.action(description="Grant a badge to selected users")
def grant_badge_to_users(modeladmin, request, queryset):
    selected = list(queryset.values_list("pk", flat=True))
    users = list(User.objects.filter(pk__in=selected).order_by("username"))
    return _grant_badge(modeladmin, request, users, selected, "grant_badge_to_users")


@admin.action(description="Grant a badge to selected users")
def grant_badge_to_profiles(modeladmin, request, queryset):
    selected = list(queryset.values_list("pk", flat=True))
    users = list(User.objects.filter(profile__pk__in=selected).order_by("username"))
    return _grant_badge(modeladmin, request, users, selected, "grant_badge_to_profiles")


class BadgeForm(forms.ModelForm):
    """The badge's two ways to artwork: upload a drawing, or name one.

    The upload control stores nothing of its own — it puts the file in the
    site's storage and writes the resulting address into ``artwork_url``, which
    is the only thing the row keeps.
    """

    artwork_upload = forms.FileField(
        required=False,
        label="Upload a drawing",
        help_text=(
            "An SVG file. Uploading one stores it and fills in the address "
            "above, replacing whatever is there."
        ),
        widget=forms.ClearableFileInput(attrs={"accept": ".svg,image/svg+xml"}),
    )

    class Meta:
        model = Badge
        fields = "__all__"

    def clean(self):
        cleaned = super().clean()
        artwork.clean_onto(
            self,
            cleaned,
            "artwork_url",
            "artwork_upload",
            prefix=BADGE_UPLOAD_PREFIX,
        )
        return cleaned


def resolve_people(text):
    """Split pasted text into the people it names, and what it didn't match.

    Takes usernames or email addresses, one per line or comma-separated, and
    matches either case-insensitively. Returns the people found and the lines
    that found nobody — reporting the misses matters more than it sounds,
    because a mistyped name in a pasted list would otherwise be a person who
    quietly never gets their badge.
    """
    identifiers = [
        part.strip()
        for line in (text or "").splitlines()
        for part in line.split(",")
        if part.strip()
    ]

    people, missing = [], []
    seen = set()
    for identifier in identifiers:
        person = User.objects.filter(username__iexact=identifier).first()
        if person is None:
            person = User.objects.filter(email__iexact=identifier).first()
        if person is None:
            missing.append(identifier)
        elif person.pk not in seen:
            seen.add(person.pk)
            people.append(person)
    return people, missing


@admin.register(Badge)
class BadgeAdmin(admin.ModelAdmin):
    form = BadgeForm
    list_display = ["preview", "title", "slug", "rank", "auto_display", "held_by"]
    list_display_links = ["title"]
    list_filter = ["archived", "auto_display"]
    search_fields = ["title", "slug", "description"]
    prepopulated_fields = {"slug": ["title"]}
    change_list_template = "admin/badge_change_list.html"

    def get_urls(self):
        return [
            path(
                "grant-to-list/",
                self.admin_site.admin_view(self.grant_to_list_view),
                name="accounts_badge_grant_to_list",
            ),
            *super().get_urls(),
        ]

    def grant_to_list_view(self, request):
        """Grant a badge to a pasted list of people.

        The selection-based action needs every recipient found and ticked in the
        changelist, which does not fit a cohort that arrives as a list of names
        from somewhere else entirely.
        """
        granted, already, missing, people = 0, 0, [], []
        pasted = ""

        if request.method == "POST":
            pasted = request.POST.get("people", "")
            badge = Badge.objects.filter(pk=request.POST.get("badge")).first()
            reason = (request.POST.get("reason") or "").strip()
            people, missing = resolve_people(pasted)

            if badge is None:
                self.message_user(request, "Choose a badge.", messages.ERROR)
            else:
                for person in people:
                    _, created = BadgeGrant.objects.get_or_create(
                        badge=badge,
                        user=person,
                        audience=BadgeGrant.Audience.USER,
                        defaults={"granted_by": request.user, "reason": reason},
                    )
                    granted += 1 if created else 0
                already = len(people) - granted
                self.message_user(
                    request,
                    f"Granted {badge.title} to {granted} person(s)"
                    f" ({already} already had it, {len(missing)} not found).",
                    messages.SUCCESS if granted else messages.WARNING,
                )

        context = {
            **self.admin_site.each_context(request),
            "title": "Grant a badge to a list of people",
            "badges": Badge.objects.filter(archived=False).order_by("title"),
            "missing": missing,
            "pasted": pasted,
            "opts": self.model._meta,
        }
        return render(request, "admin/grant_badge_to_list.html", context)

    @admin.display(description="Badge")
    def preview(self, obj):
        """The artwork itself — an address tells a reader nothing."""
        svg = obj.as_def().inline_svg()
        if not svg:
            return "—"
        return format_html(
            '<span style="display:inline-block;width:1.5rem;height:1.5rem">{}</span>',
            mark_safe(svg),  # nosec B308 B703 - sanitised by as_def().inline_svg()
        )

    @admin.display(description="Granted to")
    def held_by(self, obj):
        if obj.grants.filter(audience=BadgeGrant.Audience.EVERYONE).exists():
            return "Everyone"
        return obj.grants.filter(audience=BadgeGrant.Audience.USER).count()


@admin.register(BadgeGrant)
class BadgeGrantAdmin(admin.ModelAdmin):
    list_display = ["badge", "audience", "user", "created", "granted_by"]
    list_filter = ["audience", "badge"]
    search_fields = ["user__username", "user__email", "badge__title"]
    autocomplete_fields = ["user", "granted_by"]
    list_select_related = ["badge", "user", "granted_by"]

    def save_model(self, request, obj, form, change):
        if not change and obj.granted_by_id is None:
            obj.granted_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(UserProfile)
class UserProfileAdmin(admin.ModelAdmin):
    actions = [add_profiles_to_group, grant_badge_to_profiles]
    list_display = [
        "user",
        "user_email",
        "patreon_email",
        "tos_agreed_at",
        "patreon_status",
        "patreon_tier",
        "selected_badge",
        "timezone",
    ]
    search_fields = [
        "user__username",
        "user__email",
        "patreon_email",
        "patreon_member_id",
    ]
    readonly_fields = [
        "tos_agreed_at",
        "patreon_status",
        "patreon_tier",
        "patreon_member_id",
        "patreon_email",
    ]
    list_filter = ["patreon_status", "patreon_tier"]

    @admin.display(description="Email")
    def user_email(self, obj):
        return obj.user.email

    def has_add_permission(self, request):
        return False


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    actions = list(BaseUserAdmin.actions) + [
        add_users_to_group,
        remove_users_from_group,
        grant_badge_to_users,
    ]


@admin.register(Group)
class GroupAdmin(BaseGroupAdmin):
    pass


@admin.action(description="Show verification links for selected email addresses")
def show_verification_links(modeladmin, request, queryset):
    """
    Show email verification links for unverified email addresses.
    This allows manual sending of verification emails when automatic emails are blocked.
    """
    selected = queryset.values_list("pk", flat=True)

    # Check if this is a CSV download request
    if request.POST.get("download_csv"):
        response = HttpResponse(content_type="text/csv")
        response["Content-Disposition"] = (
            'attachment; filename="verification_links.csv"'
        )

        writer = csv.writer(response)
        writer.writerow(["Email Address", "Status", "Verification Link"])

        for email_address in queryset:
            if not email_address.verified:
                # Create a new email confirmation
                confirmation = email_address.send_confirmation(request, signup=False)
                # Generate the verification URL
                verification_url = get_email_verification_url(request, confirmation)
                writer.writerow([email_address.email, "Unverified", verification_url])
            else:
                writer.writerow([email_address.email, "Already Verified", ""])

        return response

    # Build verification data for the template
    verification_data = []

    for email_address in queryset:
        item = {
            "email": email_address.email,
            "already_verified": email_address.verified,
            "verification_url": None,
        }

        if not email_address.verified:
            # Create a new email confirmation
            confirmation = email_address.send_confirmation(request, signup=False)
            # Generate the verification URL
            item["verification_url"] = get_email_verification_url(request, confirmation)

        verification_data.append(item)

    # Render the template with the verification data
    context = {
        **modeladmin.admin_site.each_context(request),
        "title": _("Email Verification Links"),
        "verification_data": verification_data,
        "selected": selected,
    }
    request.current_app = modeladmin.admin_site.name
    return render(
        request,
        "core/admin/show_verification_links.html",
        context,
    )


# Unregister allauth's default EmailAddress admin if it exists
try:
    admin.site.unregister(EmailAddress)
except admin.sites.NotRegistered:
    pass


@admin.register(EmailAddress)
class EmailAddressAdmin(AllauthEmailAddressAdmin):
    # Extend allauth's EmailAddressAdmin to add our custom action
    actions = AllauthEmailAddressAdmin.actions + [show_verification_links]

    def has_add_permission(self, request):
        # Disable manual addition of email addresses for security
        return False
