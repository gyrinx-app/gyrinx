"""Backfill records audit admin-triggered data repairs.

Edition registrations provide operation labels without platform migrations.
The model has no content owner or archive state. Keep the core_backfill table
name and existing records when changing the Python package.
"""

import uuid

from django.contrib.auth import get_user_model
from django.db import models

from gyrinx.maintenance.registry import operation_label

User = get_user_model()

__all__ = ["Backfill"]


class Backfill(models.Model):
    class Status(models.TextChoices):
        # Background batches update summary while the run is RUNNING.
        RUNNING = "running", "Running"
        DONE = "done", "Done"
        FAILED = "failed", "Failed"
        # Batch tasks check CANCELLED before starting each batch.
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

    # This record provides the audit trail. Copying its growing summary into
    # history after every batch would require quadratic storage.

    class Meta:
        # Preserve the existing table and its records.
        db_table = "core_backfill"
        ordering = ["-created"]
        verbose_name = "backfill"
        verbose_name_plural = "backfills"

    @property
    def operation_label(self) -> str:
        """Return the registered operation label, falling back to its stored slug."""
        return operation_label(self.operation)

    def __str__(self):
        ts = self.created.isoformat(timespec="seconds") if self.created else "?"
        return f"{self.operation_label} @ {ts} — {self.get_status_display()}"
