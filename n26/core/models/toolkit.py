"""Campaign interventions, per-gang choices and retryable inbox deliveries."""

from django.db import models
from django.urls import reverse

from n26.core.models.abstract import Base

TAG_ICONS = (
    "crosshair",
    "gem",
    "badge-cent",
    "sprout",
    "siren",
    "octagon-x",
    "user-round-shield",
    "parasol",
    "key-round",
    "paintbrush",
    "printer",
    "library-big",
)
ALERT_EVENTS = (
    ("gang_added", "A player adds a gang"),
    ("battle_outcome", "A battle outcome is logged"),
    ("battle_created", "A battle is created"),
    ("fighter_deleted", "A fighter is deleted from a roster"),
    ("gang_removed", "A player removes a gang"),
    ("offer_selected", "A player selects an intervention offer"),
    ("asset_owner_changed", "An asset changes owner"),
)


class ToolkitCommand(Base):
    campaign = models.ForeignKey("n26.Campaign", on_delete=models.CASCADE)
    actor = models.ForeignKey("auth.User", on_delete=models.CASCADE)
    request_key = models.UUIDField()
    action = models.CharField(max_length=32)
    payload = models.JSONField()
    next_url = models.CharField(max_length=500)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "actor", "request_key"],
                name="toolkit_command_identity",
            )
        ]


class Intervention(Base):
    campaign = models.ForeignKey(
        "n26.Campaign", on_delete=models.CASCADE, related_name="interventions"
    )
    actor = models.ForeignKey("auth.User", on_delete=models.PROTECT)
    purpose = models.CharField(
        max_length=20,
        default="intervention",
        choices=[("intervention", "Intervention"), ("tags", "Tags")],
    )
    title = models.CharField(max_length=200)
    narrative = models.TextField(blank=True)
    mode = models.CharField(
        max_length=12,
        choices=[("bundle", "All rewards"), ("choice", "A choice of rewards")],
    )
    choices = models.PositiveSmallIntegerField(default=1)
    rewards = models.JSONField(default=list)
    inform_all = models.BooleanField(default=False)

    def get_absolute_url(self):
        return reverse("n26-toolkit-intervention", args=[self.campaign_id, self.pk])


class InterventionReceipt(Base):
    intervention = models.ForeignKey(
        Intervention, on_delete=models.CASCADE, related_name="receipts"
    )
    gang = models.ForeignKey(
        "n26.Gang",
        on_delete=models.PROTECT,
        related_name="interventions",
        null=True,
        blank=True,
    )
    player = models.ForeignKey(
        "auth.User",
        on_delete=models.PROTECT,
        related_name="n26_interventions",
        null=True,
        blank=True,
    )
    selected = models.JSONField(default=list)
    resolved_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["intervention", "gang"], name="one_intervention_per_gang"
            ),
            models.UniqueConstraint(
                fields=["intervention", "player"], name="one_intervention_per_player"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(gang__isnull=False, player__isnull=True)
                    | models.Q(gang__isnull=True, player__isnull=False)
                ),
                name="intervention_has_one_recipient",
            ),
        ]

    def get_absolute_url(self):
        return self.intervention.get_absolute_url()


class CampaignTag(Base):
    campaign = models.ForeignKey(
        "n26.Campaign", on_delete=models.CASCADE, related_name="gang_tags"
    )
    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.CASCADE, null=True, blank=True
    )
    player = models.ForeignKey(
        "auth.User",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="n26_campaign_tags",
    )
    receipt = models.ForeignKey(InterventionReceipt, on_delete=models.PROTECT)
    name = models.CharField(max_length=80)
    icon = models.CharField(max_length=30, choices=[(x, x) for x in TAG_ICONS])
    info = models.CharField(max_length=1000, blank=True)
    removed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=(
                    models.Q(gang__isnull=False, player__isnull=True)
                    | models.Q(gang__isnull=True, player__isnull=False)
                ),
                name="campaign_tag_has_one_recipient",
            )
        ]


class ToolkitAlert(Base):
    campaign = models.ForeignKey(
        "n26.Campaign", on_delete=models.CASCADE, related_name="toolkit_alerts"
    )
    event = models.CharField(max_length=32, choices=ALERT_EVENTS)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "event"], name="one_toolkit_alert_per_event"
            )
        ]


class ToolkitDelivery(Base):
    campaign = models.ForeignKey("n26.Campaign", on_delete=models.CASCADE)
    recipient = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="+"
    )
    sender = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    identity = models.CharField(max_length=200)
    subject = models.CharField(max_length=255)
    content = models.TextField()
    href = models.CharField(max_length=500)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["identity", "recipient"], name="toolkit_delivery_identity"
            )
        ]

    def get_absolute_url(self):
        return self.href

    @classmethod
    def notification_choices(cls, deliveries, viewer):
        from n26.core.toolkit_inbox import offers_for

        return offers_for(deliveries, viewer)

    def notification_context(self, sender):
        from n26.core.people import person_link

        badges = {}
        person = person_link(sender, badges) if sender else None
        if person:
            person["badge"] = badges.get(person.get("badge"))
        return {
            "campaignName": self.campaign.name,
            "campaignHref": reverse("n26-campaign", args=[self.campaign_id]),
            "sender": person,
        }


class ToolkitAlertSettings(Base):
    campaign = models.OneToOneField(
        "n26.Campaign", on_delete=models.CASCADE, related_name="toolkit_alert_settings"
    )
    immediate = models.BooleanField(default=True)
    report_days = models.PositiveSmallIntegerField(null=True, blank=True)
    window_start = models.DateTimeField(null=True, blank=True)
    next_report_at = models.DateTimeField(null=True, blank=True, db_index=True)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(report_days__isnull=True)
                | models.Q(report_days__gte=1, report_days__lte=365),
                name="toolkit_report_days_range",
            )
        ]


class ToolkitAlertEvent(Base):
    campaign = models.ForeignKey(
        "n26.Campaign", on_delete=models.CASCADE, related_name="toolkit_alert_events"
    )
    event = models.CharField(max_length=32, choices=ALERT_EVENTS)
    identity = models.CharField(max_length=200)
    occurred_at = models.DateTimeField(db_index=True)
    text = models.TextField()
    actor = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, blank=True
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "event", "identity"],
                name="toolkit_alert_event_identity",
            )
        ]
        indexes = [
            models.Index(
                fields=["campaign", "occurred_at"], name="toolkit_report_events_idx"
            )
        ]
