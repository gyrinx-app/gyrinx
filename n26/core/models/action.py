"""Actions — a thing a gang opens, does over several clicks, and closes.

The books give a gang acts that are not one click: founding and equipping
it, a trip to the trading post. Each has a beginning and an end, purchases
in between that count against it, and a state a screen has to be able to
name. A row here is one of those, from the click that opened it to the
click that closed it.

The row is thin on purpose. What an action *did* is the ledger, as
everything else in this edition is: ``opened`` and ``closed`` name the two
events, and the story between them is what the log holds in that stretch.
Both events are about the gang rather than any assignment, so folding an
entry's events still reproduces the entry (``n26.core.reconcile``) and
nothing here is inside that arithmetic.

One of each kind at a time, held by the database rather than by whoever
remembered to look: a gang cannot be founding twice, and a second visit
opened while the first was still open would leave every purchase in
between unable to say which one it counted against.
"""

from django.db import models

from n26.core.models.abstract import Base


class Action(Base):
    """One act a gang opened, and — once it is done — closed."""

    class Kind(models.TextChoices):
        FOUNDING = "founding", "Found and equip gang"
        TRADING_POST_VISIT = "trading_post_visit", "Visit Trading Post"

    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.CASCADE, related_name="actions"
    )
    kind = models.CharField(max_length=32, choices=Kind)
    #: The event that opened this. Cascades, because the event is the act:
    #: an action whose opening is gone is a record of nothing. Nothing
    #: deletes a gang's events but the gang itself going, which takes the
    #: action either way. Which kind of event it is follows from the act:
    #: one that writes a boundary of its own points at that rather than
    #: at a second event saying the same thing twice.
    opened = models.ForeignKey(
        "n26.LedgerEvent", on_delete=models.CASCADE, related_name="+"
    )
    #: The event that closed it, and the whole of what "open" means:
    #: nothing here while the action is still being performed.
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
            "The Trade Points this action added to the gang. Empty for an "
            "action that adds none."
        ),
    )

    class Meta:
        verbose_name = "action"
        verbose_name_plural = "actions"
        ordering = ["created"]
        constraints = [
            # One at a time, per kind, per gang. A purchase counts against
            # the open action of its kind, so two would leave it with no
            # answer to which.
            models.UniqueConstraint(
                fields=["gang", "kind"],
                condition=models.Q(closed__isnull=True),
                name="one_open_action_of_each_kind",
            ),
        ]

    def __str__(self):
        return f"{self.gang.name}: {self.get_kind_display()}"

    @property
    def is_open(self):
        return self.closed_id is None
