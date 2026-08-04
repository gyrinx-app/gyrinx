"""Backfill: audit record of an admin-triggered one-off data repair.

Bare ``models.Model`` rather than ``AppBase`` because this is a system-meta
model with no notion of ownership / archive / user-content history. See
``CampaignContentPack`` (#1801) for the same precedent.
"""

import uuid

from django.contrib.auth import get_user_model
from django.db import models

User = get_user_model()

__all__ = ["Backfill"]


class Backfill(models.Model):
    class Operation(models.TextChoices):
        MIGRATE_PERSISTENT_STASH = (
            "migrate_persistent_stash",
            "Migrate persistent stash items (#1825)",
        )
        RECONCILE_LISTS = (
            "reconcile_lists",
            "Reconcile list cost caches (#1826 Phase 8)",
        )
        BACKFILL_PINS = (
            "backfill_pins",
            "Backfill acquisition receipts (#1826 Phase 8)",
        )
        FIX_STAT_ADVANCEMENTS = (
            "fix_stat_advancements",
            "Finish the stat-advancement cleanup (#2070)",
        )
        NORMALISE_STAT_FORMATS = (
            "normalise_stat_formats",
            "Normalise legacy stat-column formats (#1861 Track C1)",
        )
        MATERIALISE_STATLINES = (
            "materialise_statlines",
            "Materialise statlines for legacy templates (#1861 Track C1)",
        )

    class Status(models.TextChoices):
        # Long-running operations execute on the task runner and report
        # progress into `summary` batch by batch; RUNNING is their state
        # between trigger and the final DONE/FAILED update.
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"
        # Operator-requested stop. The self-re-enqueueing task chain checks the
        # record at the top of each batch and bails when it sees this, so the
        # chain winds down within one batch. Terminal, like DONE/FAILED.
        CANCELLED = "cancelled", "Cancelled"

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

    # No HistoricalRecords: this row IS the audit record, and its `summary` is a
    # running progress blob rewritten every batch (the reconcile per-list detail
    # grows through the run). Historising it would copy the whole ever-growing
    # JSONB into a historical row on each of a run's hundreds of batch saves —
    # O(n²) storage for no audit value.

    class Meta:
        ordering = ["-created"]
        verbose_name = "backfill"
        verbose_name_plural = "backfills"

    def __str__(self):
        ts = self.created.isoformat(timespec="seconds") if self.created else "?"
        return f"{self.get_operation_display()} @ {ts} — {self.get_status_display()}"
