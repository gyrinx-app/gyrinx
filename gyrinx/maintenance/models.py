"""Backfill: audit record of an admin-triggered one-off data repair.

Platform-side, because the repair console is: a run has a trigger, a scope, a
status, a progress blob and an outcome whatever it was repairing. Which repairs
exist is the edition's business — ``operation`` holds a bare slug and the label
comes from ``gyrinx.maintenance.registry``, so an edition can add a repair
without a platform migration.

Bare ``models.Model`` rather than ``AppBase`` because this is a system-meta
model with no notion of ownership / archive / user-content history. See
``CampaignContentPack`` (#1801) for the same precedent.

The table is still ``core_backfill``: the model moved packages, the rows did
not. See ``gyrinx/maintenance/migrations/0001_move_backfill_to_maintenance.py``.
"""

import uuid

from django.contrib.auth import get_user_model
from django.db import models

from gyrinx.maintenance.registry import operation_label

User = get_user_model()

__all__ = ["Backfill"]


class Backfill(models.Model):
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

    # No choices: the set of repairs is contributed at runtime by whichever
    # edition is installed. Retired operations stay registered (label only) so
    # their historical records keep rendering a name.
    operation = models.CharField(max_length=64)
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
        # Pinned: the rows predate the move out of `core` and did not move with
        # the model.
        db_table = "core_backfill"
        ordering = ["-created"]
        verbose_name = "backfill"
        verbose_name_plural = "backfills"

    @property
    def operation_label(self) -> str:
        """Human name for this run's operation, or the raw slug if unknown.

        Stands in for the ``get_operation_display()`` this field would have if
        its choices were static. A slug survives its registration disappearing —
        old records still render, just without a friendly name.
        """
        return operation_label(self.operation)

    def __str__(self):
        ts = self.created.isoformat(timespec="seconds") if self.created else "?"
        return f"{self.operation_label} @ {ts} — {self.get_status_display()}"
