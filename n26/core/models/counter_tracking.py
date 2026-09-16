"""Installation state for the structured counter journal.

This is a single site-wide switch, rather than game content or an
availability rule. Deployment creates the schema; a recorded maintenance
run establishes every counter's opening balance before enabling writers.
"""

from django.db import models


class CounterTracking(models.Model):
    id = models.PositiveSmallIntegerField(primary_key=True, default=1, editable=False)
    activated_at = models.DateTimeField(null=True, blank=True, editable=False)
    activation_run = models.UUIDField(null=True, blank=True, editable=False)

    class Meta:
        constraints = [
            models.CheckConstraint(
                condition=models.Q(id=1), name="counter_tracking_singleton"
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(activated_at__isnull=True, activation_run__isnull=True)
                    | models.Q(activated_at__isnull=False, activation_run__isnull=False)
                ),
                name="counter_tracking_activation_complete",
            ),
        ]

    def __str__(self):
        state = "active" if self.activated_at else "inactive"
        return f"Counter history: {state}"
