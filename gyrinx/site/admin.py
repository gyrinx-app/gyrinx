"""Admin for notifications, including a broadcast (create-to-many) view.

Banner and ImpersonationLog are still registered from ``n23.core.admin``; only
the notification admin has been brought over so far.

Who a broadcast can be addressed to is not decided here: audiences come from
``gyrinx.site.registry``, which the platform seeds with "all active users" and
each edition extends with its own (see ``n23/core/admin/broadcast.py``). That
is what keeps this module free of edition imports.
"""

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import models
from django.shortcuts import redirect, render
from django.urls import path

from gyrinx.site.models import (
    ChangelogEntry,
    ChangelogEntryTag,
    Notification,
    NotificationType,
    notify_many,
)
from gyrinx.site.registry import broadcast_audiences, get_broadcast_audience
from gyrinx.widgets import TinyMCEWithUpload

User = get_user_model()

__all__ = [
    "ChangelogEntryAdmin",
    "ChangelogEntryTagAdmin",
    "NotificationAdmin",
    "NotificationAdminForm",
    "BroadcastForm",
]


class NotificationAdminForm(forms.ModelForm):
    class Meta:
        model = Notification
        fields = "__all__"
        labels = {"owner": "Recipient"}


class BroadcastForm(forms.Form):
    """The broadcast composer. Its audience options come from the registry.

    Audience choices and any fields those audiences need are built per instance
    rather than declared on the class, because an edition may not have finished
    registering when this module is first imported.
    """

    subject = forms.CharField(max_length=255)
    content = forms.CharField(widget=TinyMCEWithUpload, required=False)
    notification_type = forms.ChoiceField(
        choices=NotificationType.choices, initial=NotificationType.GENERAL
    )
    audience = forms.ChoiceField(choices=())
    send_as_system = forms.BooleanField(
        required=False,
        initial=True,
        label="Send as Gyrinx (system)",
        help_text="Show a Gyrinx badge instead of your username. Uncheck to attribute it to yourself.",
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        audiences = broadcast_audiences()
        self.fields["audience"].choices = [(a.key, a.label) for a in audiences]
        # Qualifier fields are optional at field level and enforced in clean()
        # only for the audience that owns them — otherwise picking "all active
        # users" would demand a campaign.
        qualifiers = []
        for audience in audiences:
            if audience.field_name and audience.field:
                field = audience.field()
                field.required = False
                self.fields[audience.field_name] = field
                qualifiers.append(audience.field_name)
        # Keep each qualifier next to the dropdown that governs it, rather than
        # trailing after the send-as-system checkbox.
        self.order_fields(
            ["subject", "content", "notification_type", "audience", *qualifiers]
        )

    def clean(self):
        cleaned = super().clean()
        audience = get_broadcast_audience(cleaned.get("audience"))
        if audience and audience.field_name and not cleaned.get(audience.field_name):
            self.add_error(audience.field_name, audience.field_required_error)
        return cleaned

    def get_recipients(self):
        audience = get_broadcast_audience(self.cleaned_data["audience"])
        return audience.recipients(self.cleaned_data)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    form = NotificationAdminForm
    change_list_template = "admin/gyrinxsite/notification/change_list.html"
    formfield_overrides = {models.TextField: {"widget": TinyMCEWithUpload}}
    list_display = [
        "subject",
        "owner",
        "notification_type",
        "is_read",
        "archived",
        "show_as_banner",
        "created",
    ]
    list_filter = [
        "notification_type",
        "is_read",
        "archived",
        "show_as_banner",
        "created",
    ]
    search_fields = ["subject", "content", "owner__username"]
    autocomplete_fields = ["owner", "sender"]
    readonly_fields = ["created", "modified", "read_at"]

    def save_model(self, request, obj, form, change):
        # Default the recipient to the current admin on create if unset.
        if not change and obj.owner_id is None:
            obj.owner = request.user
        super().save_model(request, obj, form, change)

    def get_urls(self):
        urls = super().get_urls()
        custom = [
            path(
                "broadcast/",
                self.admin_site.admin_view(self.broadcast_view),
                name="gyrinxsite_notification_broadcast",
            ),
        ]
        return custom + urls

    def broadcast_view(self, request):
        if not request.user.is_superuser:
            raise PermissionDenied

        if request.method == "POST":
            form = BroadcastForm(request.POST)
            if form.is_valid():
                sender = None if form.cleaned_data["send_as_system"] else request.user
                count = notify_many(
                    form.get_recipients().iterator(),
                    subject=form.cleaned_data["subject"],
                    content=form.cleaned_data["content"],
                    sender=sender,
                    notification_type=form.cleaned_data["notification_type"],
                )
                messages.success(request, f"Sent {count} notifications.")
                return redirect("admin:gyrinxsite_notification_changelist")
        else:
            form = BroadcastForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "Broadcast notification",
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/gyrinxsite/notification/broadcast.html", context)


@admin.register(ChangelogEntryTag)
class ChangelogEntryTagAdmin(admin.ModelAdmin):
    list_display = ("name",)
    search_fields = ("name",)


@admin.register(ChangelogEntry)
class ChangelogEntryAdmin(admin.ModelAdmin):
    """Write the changelog where everything else is written: the body is
    rich text through the same TinyMCE the rest of the admin uses."""

    list_display = ("date", "title", "tag_names")
    list_filter = ("tags",)
    ordering = ("-date", "-created")
    search_fields = ("title",)
    filter_horizontal = ("tags",)
    formfield_overrides = {
        models.TextField: {"widget": TinyMCEWithUpload},
    }

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("tags")

    @admin.display(description="Tags")
    def tag_names(self, obj):
        return ", ".join(tag.name for tag in obj.tags.all())
