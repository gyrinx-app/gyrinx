"""Saved campaign cycles, immutable plans and committed transition deliveries.

Plan steps are immutable structured data. Saved cycles have independent identities
and order, so replacing a plan or editing dates cannot recreate linked history.
"""

from django.core.exceptions import ValidationError
from django.db import models
from django.urls import reverse

from n26.core.models.abstract import Archived, Base, Owned


class CampaignScheduleTemplate(Base, Owned):
    """A reusable phase and schedule definition copied into a campaign."""

    name = models.CharField(max_length=200)
    system_key = models.SlugField(max_length=100, blank=True, default="")
    definition = models.JSONField(default=dict)

    class Meta:
        ordering = ["name", "id"]
        constraints = [
            models.UniqueConstraint(
                fields=["system_key"],
                condition=~models.Q(system_key=""),
                name="cycle_template_system_key_once",
            ),
            models.CheckConstraint(
                condition=models.Q(system_key="") | models.Q(owner__isnull=True),
                name="cycle_system_template_has_no_owner",
            ),
        ]

    def __str__(self):
        return self.name

    def clean(self):
        super().clean()
        from n26.core.cycle_data import template_from_data
        from n26.core.schedule import ScheduleError

        try:
            template_from_data(self.name, self.definition)
        except ScheduleError as exc:
            raise ValidationError({"definition": str(exc)}) from exc


class CampaignPhase(Base, Archived):
    campaign = models.ForeignKey(
        "n26.Campaign", on_delete=models.CASCADE, related_name="cycle_phases"
    )
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True, default="")
    effects = models.TextField(blank=True, default="")
    rewards = models.JSONField(default=dict)

    class Meta:
        ordering = ["created", "id"]

    def __str__(self):
        return self.name


class CampaignPlan(Base):
    class Mode(models.TextChoices):
        FIXED = "fixed", "Fixed"
        REPEATING = "repeating", "Repeating"

    campaign = models.ForeignKey(
        "n26.Campaign", on_delete=models.CASCADE, related_name="cycle_plans"
    )
    mode = models.CharField(max_length=12, choices=Mode)
    starts_after_order = models.PositiveIntegerField(default=0)
    start_position = models.PositiveIntegerField(default=0)
    steps = models.JSONField(default=list)

    class Meta:
        ordering = ["created", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(mode__in=["fixed", "repeating"]),
                name="cycle_plan_mode_known",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("A saved plan revision cannot be edited.")
        return super().save(*args, **kwargs)


class CampaignCycle(Base, Archived):
    campaign = models.ForeignKey(
        "n26.Campaign", on_delete=models.CASCADE, related_name="cycles"
    )
    phase = models.ForeignKey(
        CampaignPhase, on_delete=models.RESTRICT, related_name="cycles"
    )
    order = models.PositiveIntegerField()
    custom_name = models.CharField(max_length=200, blank=True, default="")
    starts_on = models.DateField(null=True, blank=True)
    ends_on = models.DateField(null=True, blank=True)
    description = models.TextField(blank=True, default="")
    effects = models.TextField(blank=True, default="")
    source_plan = models.ForeignKey(
        CampaignPlan, on_delete=models.RESTRICT, related_name="saved_cycles"
    )
    source_position = models.PositiveIntegerField()
    source_step = models.CharField(max_length=26)
    repetition = models.PositiveIntegerField(default=0)
    step_position = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ["order"]
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "order"], name="cycle_campaign_order_once"
            ),
            models.UniqueConstraint(
                fields=["source_plan", "source_position"], name="cycle_source_once"
            ),
            models.CheckConstraint(
                condition=models.Q(order__gt=0), name="cycle_order_positive"
            ),
            models.CheckConstraint(
                condition=models.Q(starts_on__isnull=True)
                | models.Q(ends_on__isnull=True)
                | models.Q(ends_on__gte=models.F("starts_on")),
                name="cycle_date_range_valid",
            ),
        ]

    @property
    def name(self):
        return self.custom_name or f"Cycle {self.order}"

    def __str__(self):
        return self.name

    def get_absolute_url(self):
        return reverse("n26-campaign-cycle", args=[self.campaign_id, self.pk])

    def clean(self):
        super().clean()
        errors = {}
        if self.phase_id and self.phase.campaign_id != self.campaign_id:
            errors["phase"] = "Select a phase from this campaign."
        if self.source_plan_id and self.source_plan.campaign_id != self.campaign_id:
            errors["source_plan"] = "Select a plan from this campaign."
        if errors:
            raise ValidationError(errors)


class CampaignSchedule(Base):
    campaign = models.OneToOneField(
        "n26.Campaign", on_delete=models.CASCADE, related_name="cycle_schedule"
    )
    current_cycle = models.ForeignKey(
        CampaignCycle,
        on_delete=models.RESTRICT,
        related_name="current_in",
        null=True,
        blank=True,
    )
    active_plan = models.ForeignKey(
        CampaignPlan, on_delete=models.RESTRICT, related_name="active_in"
    )
    next_position = models.PositiveIntegerField(default=0)
    revision = models.PositiveIntegerField(default=0)
    date_settings = models.JSONField(default=dict)

    def clean(self):
        super().clean()
        errors = {}
        if self.current_cycle_id and self.current_cycle.campaign_id != self.campaign_id:
            errors["current_cycle"] = "Select a cycle from this campaign."
        if self.active_plan_id and self.active_plan.campaign_id != self.campaign_id:
            errors["active_plan"] = "Select a plan from this campaign."
        if errors:
            raise ValidationError(errors)


class CampaignCycleCommand(Base):
    campaign = models.ForeignKey(
        "n26.Campaign", on_delete=models.CASCADE, related_name="cycle_commands"
    )
    actor = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    request_key = models.UUIDField()
    kind = models.CharField(max_length=32)
    inputs = models.JSONField(default=dict)
    result = models.JSONField(default=dict)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["campaign", "request_key"], name="cycle_command_once"
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("A saved cycle command cannot be edited.")
        return super().save(*args, **kwargs)


class CampaignCycleTransition(Base):
    class Kind(models.TextChoices):
        STARTED = "started", "Cycle started"
        ADVANCED = "advanced", "Cycle advanced"
        PHASE_CHANGED = "phase_changed", "Phase changed"
        FINISHED = "finished", "Campaign finished"

    campaign = models.ForeignKey(
        "n26.Campaign", on_delete=models.CASCADE, related_name="cycle_transitions"
    )
    command = models.OneToOneField(
        CampaignCycleCommand,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="transition",
    )
    kind = models.CharField(max_length=16, choices=Kind)
    previous_cycle = models.ForeignKey(
        CampaignCycle,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="ending_transitions",
    )
    current_cycle = models.ForeignKey(
        CampaignCycle, on_delete=models.RESTRICT, related_name="starting_transitions"
    )
    previous_phase = models.ForeignKey(
        CampaignPhase,
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="leaving_transitions",
    )
    current_phase = models.ForeignKey(
        CampaignPhase, on_delete=models.RESTRICT, related_name="entering_transitions"
    )
    actor = models.ForeignKey(
        "auth.User", on_delete=models.SET_NULL, null=True, related_name="+"
    )
    occurred_at = models.DateTimeField()
    receipt = models.JSONField(default=dict)

    class Meta:
        ordering = ["occurred_at", "id"]
        constraints = [
            models.CheckConstraint(
                condition=models.Q(
                    kind__in=["started", "advanced", "phase_changed", "finished"]
                ),
                name="cycle_transition_kind_known",
            ),
        ]

    def save(self, *args, **kwargs):
        if not self._state.adding:
            raise ValidationError("A committed cycle transition cannot be edited.")
        return super().save(*args, **kwargs)


class CampaignCycleDelivery(Base):
    transition = models.ForeignKey(
        CampaignCycleTransition, on_delete=models.CASCADE, related_name="deliveries"
    )
    recipient = models.ForeignKey(
        "auth.User", on_delete=models.CASCADE, related_name="+"
    )
    subject = models.CharField(max_length=255)
    content = models.TextField(blank=True, default="")
    notification_id = models.UUIDField(null=True, blank=True)
    delivered_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=["transition", "recipient"], name="cycle_delivery_once"
            ),
            models.CheckConstraint(
                condition=models.Q(
                    notification_id__isnull=True, delivered_at__isnull=True
                )
                | models.Q(notification_id__isnull=False, delivered_at__isnull=False),
                name="cycle_delivery_result_complete",
            ),
        ]
        indexes = [
            models.Index(
                fields=["created"],
                condition=models.Q(delivered_at__isnull=True),
                name="cycle_delivery_pending_idx",
            ),
        ]
