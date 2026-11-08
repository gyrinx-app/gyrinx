"""Track gang activities that span requests through opening and closing events.

Purchases record the activity whose allowance they use. Boundary events
name the gang or model rather than an assignment, so they do not affect
ledger-entry reconciliation.

Constraints permit one open activity per gang and kind, or per model and
kind for hire-time activities, to keep purchase attribution unambiguous.
"""

from django.db import models

from n26.core.models.abstract import Base


class Activity(Base):
    class Kind(models.TextChoices):
        FOUNDING = "founding", "Spend founding TP"
        HIRE_TIME = "hire_time_tp", "Spend hire-time TP"
        TRADING_POST_VISIT = "trading_post_visit", "Visit Trading Post"

    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.CASCADE, related_name="activities"
    )
    miniature = models.ForeignKey(
        "n26.Miniature",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="activities",
        help_text="The model spending its hire-time Trade Points. Empty for gang actions.",
    )
    kind = models.CharField(max_length=32, choices=Kind)
    #: CASCADE: an activity means nothing without its opening event.
    opened = models.ForeignKey(
        "n26.LedgerEvent", on_delete=models.CASCADE, related_name="+"
    )
    #: Null while the activity is open. Whether an activity is open
    #: depends on this field alone.
    closed = models.ForeignKey(
        "n26.LedgerEvent",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="+",
    )
    trade_points = models.PositiveIntegerField(
        null=True,
        blank=True,
        help_text=(
            "The Trade Points this activity added to the gang. Empty for an "
            "activity that adds none."
        ),
    )

    class Meta:
        verbose_name = "activity"
        verbose_name_plural = "activities"
        ordering = ["created"]
        constraints = [
            # Permit one open activity per gang and kind so purchase attribution is unambiguous.
            models.UniqueConstraint(
                fields=["gang", "kind"],
                condition=models.Q(closed__isnull=True, miniature__isnull=True),
                name="one_open_activity_of_each_kind",
            ),
            models.UniqueConstraint(
                fields=["gang", "kind", "miniature"],
                condition=models.Q(closed__isnull=True, miniature__isnull=False),
                name="one_open_activity_per_model_kind",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(kind="hire_time_tp", miniature__isnull=False)
                    | (
                        models.Q(miniature__isnull=True)
                        & ~models.Q(kind="hire_time_tp")
                    )
                ),
                name="activity_target_matches_kind",
            ),
        ]

    def __str__(self):
        return f"{self.gang.name}: {self.get_kind_display()}"

    @property
    def is_open(self):
        return self.closed_id is None


def note_for(kind, figure=None):
    """Encode the activity kind and optional Trade Point figure in its journal note.

    Keeping the kind in the note lets history identify the activity without a join.
    """
    if figure is None:
        return str(kind)
    return f"{kind} {figure}"


def read_note(note):
    """Split an activity note into the kind's label and its figure.

    The label is empty when the note names an unknown kind, so the history
    can say an activity started without guessing which. The figure is None
    when the note has none.
    """
    kind, _, figure = note.partition(" ")
    try:
        name = Activity.Kind(kind).label
    except ValueError:
        return "", None
    try:
        return name, int(figure)
    except ValueError:
        return name, None
