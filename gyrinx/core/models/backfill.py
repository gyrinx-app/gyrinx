"""Backfill: audit record of an admin-triggered one-off data repair.

Bare ``models.Model`` rather than ``AppBase`` because this is a system-meta
model with no notion of ownership / archive / user-content history. See
``CampaignContentPack`` (#1801) for the same precedent.
"""

import uuid

from django.contrib.auth import get_user_model
from django.db import models
from simple_history.models import HistoricalRecords

User = get_user_model()

__all__ = ["Backfill"]


class Backfill(models.Model):
    class Operation(models.TextChoices):
        MIGRATE_PERSISTENT_STASH = (
            "migrate_persistent_stash",
            "Migrate persistent stash items (#1825)",
        )

    class Status(models.TextChoices):
        DONE = "done", "Done"
        FAILED = "failed", "Failed"

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created = models.DateTimeField(auto_now_add=True, db_index=True)
    modified = models.DateTimeField(auto_now=True)

    operation = models.CharField(max_length=64, choices=Operation.choices)
    triggered_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True, related_name="+"
    )
    list_id_scope = models.UUIDField(
        null=True,
        blank=True,
        help_text="If set, the run was scoped to this single List.",
    )

    status = models.CharField(
        max_length=16, choices=Status.choices, default=Status.DONE
    )
    summary = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True, default="")

    history = HistoricalRecords()

    class Meta:
        ordering = ["-created"]
        verbose_name = "backfill"
        verbose_name_plural = "backfills"

    def __str__(self):
        ts = self.created.isoformat(timespec="seconds") if self.created else "?"
        return f"{self.get_operation_display()} @ {ts} — {self.get_status_display()}"
