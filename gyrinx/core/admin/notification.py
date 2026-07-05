"""Admin for notifications, including a broadcast (create-to-many) view."""

from django import forms
from django.contrib import admin, messages
from django.contrib.auth import get_user_model
from django.core.exceptions import PermissionDenied
from django.db import models
from django.shortcuts import redirect, render
from django.urls import path

from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.notification import (
    Notification,
    NotificationType,
    notify_many,
)
from gyrinx.core.widgets import TinyMCEWithUpload

User = get_user_model()

__all__ = ["NotificationAdmin", "NotificationAdminForm", "BroadcastForm"]


class NotificationAdminForm(forms.ModelForm):
    class Meta:
        model = Notification
        fields = "__all__"
        labels = {"owner": "Recipient"}


class BroadcastForm(forms.Form):
    AUDIENCE_ALL = "all_active"
    AUDIENCE_WITH_LIST = "with_list"
    AUDIENCE_CAMPAIGN = "campaign"
    AUDIENCE_CHOICES = [
        (AUDIENCE_ALL, "All active users"),
        (AUDIENCE_WITH_LIST, "Users with a list"),
        (AUDIENCE_CAMPAIGN, "Participants of a campaign"),
    ]

    subject = forms.CharField(max_length=255)
    content = forms.CharField(widget=TinyMCEWithUpload, required=False)
    notification_type = forms.ChoiceField(
        choices=NotificationType.choices, initial=NotificationType.GENERAL
    )
    audience = forms.ChoiceField(choices=AUDIENCE_CHOICES)
    campaign = forms.ModelChoiceField(
        queryset=Campaign.objects.all(),
        required=False,
        help_text="Required when audience is 'Participants of a campaign'.",
    )
    send_as_system = forms.BooleanField(
        required=False,
        initial=True,
        label="Send as Gyrinx (system)",
        help_text="Show a Gyrinx badge instead of your username. Uncheck to attribute it to yourself.",
    )
    show_as_banner = forms.BooleanField(required=False)
    banner_colour = forms.CharField(max_length=20, initial="info", required=False)
    icon = forms.CharField(max_length=50, required=False)

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("audience") == self.AUDIENCE_CAMPAIGN and not cleaned.get(
            "campaign"
        ):
            self.add_error("campaign", "Choose a campaign for this audience.")
        return cleaned

    def get_recipients(self):
        audience = self.cleaned_data["audience"]
        if audience == self.AUDIENCE_ALL:
            return User.objects.filter(is_active=True)
        if audience == self.AUDIENCE_WITH_LIST:
            return User.objects.filter(list__isnull=False).distinct()
        # Campaign participants: list owners in the campaign + the arbitrator.
        campaign = self.cleaned_data["campaign"]
        ids = set(campaign.lists.values_list("owner_id", flat=True))
        if campaign.owner_id:
            ids.add(campaign.owner_id)
        ids.discard(None)
        return User.objects.filter(pk__in=ids)


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    form = NotificationAdminForm
    change_list_template = "admin/core/notification/change_list.html"
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
    autocomplete_fields = ["owner", "sender", "related_list", "related_campaign"]
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
                name="core_notification_broadcast",
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
                    form.get_recipients(),
                    subject=form.cleaned_data["subject"],
                    content=form.cleaned_data["content"],
                    sender=sender,
                    notification_type=form.cleaned_data["notification_type"],
                    show_as_banner=form.cleaned_data["show_as_banner"],
                    banner_colour=form.cleaned_data["banner_colour"] or "info",
                    icon=form.cleaned_data["icon"],
                )
                messages.success(request, f"Sent {count} notifications.")
                return redirect("admin:core_notification_changelist")
        else:
            form = BroadcastForm()

        context = {
            **self.admin_site.each_context(request),
            "title": "Broadcast notification",
            "form": form,
            "opts": self.model._meta,
        }
        return render(request, "admin/core/notification/broadcast.html", context)
