"""The ledger — what a gang acquired, what it cost, and how it changed.

Two halves, both kept:

* a **ledger entry**, one per assignment: the assignable it was for, the
  price at the time, discount, what was paid, what it contributes to
  rating, and why it exists;
* **ledger events**, append-only, each recording one change and who made
  it.

The invariant that keeps them honest: folding an entry's events reproduces
the entry. ``n26.reconcile`` checks it.
"""

from django.db import models

from n26.core.models.abstract import Base


class Reason(models.TextChoices):
    """Why an assignment exists. Derived from how it was acquired, not from
    whether money changed hands — free and granted are different things."""

    BOUGHT = "bought", "Bought"
    DEFAULT = "default", "Default equipment"
    GRANTED = "granted", "Granted by something else"
    REWARD = "reward", "Reward"
    FREE = "free", "Free"


class LedgerEntry(Base):
    """One row per assignment: what it was for and what it cost."""

    assignment = models.OneToOneField(
        "n26.Assignment", on_delete=models.CASCADE, related_name="ledger_entry"
    )
    list_price = models.IntegerField(
        default=0, help_text="The price at the time, before any discount."
    )
    discount = models.IntegerField(default=0)
    paid = models.IntegerField(default=0)
    trade_points = models.IntegerField(
        default=0, help_text="Trade Points spent, for Trading Post purchases."
    )
    rating_contribution = models.IntegerField(
        default=0, help_text="What this adds to rating. May differ from paid."
    )
    reason = models.CharField(max_length=20, choices=Reason, default=Reason.BOUGHT)
    bought_from = models.ForeignKey(
        "library.CollectionEntry",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchases",
        help_text=(
            "The collection entry this was bought through, when it was — "
            "the money's provenance. Blank for free-form purchases: the "
            "get-out is a purchase with no entry."
        ),
    )
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "ledger entry"
        verbose_name_plural = "ledger entries"
        ordering = ["created"]

    def __str__(self):
        return f"{self.assignable}: {self.paid}cr ({self.get_reason_display()})"

    @property
    def assignable(self):
        """What was acquired. Read through the assignment — one source of truth.

        Note for later: if an assignment is ever *amended* (Death of a Leader
        swapping a profile), this will follow the new assignable rather than
        remember the old one. See design/assignables.md, open questions.
        """
        return self.assignment.assignable


class LedgerEvent(Base):
    """One append-only record of a change, with who made it."""

    class Kind(models.TextChoices):
        PURCHASED = "purchased", "Purchased"
        ADDED = "added", "Added"
        GRANTED = "granted", "Granted"
        MOVED = "moved", "Moved"
        TALLIED = "tallied", "Tallied"
        AMENDED = "amended", "Amended"
        REPRICED = "repriced", "Repriced"
        REMOVED = "removed", "Removed"
        REFUNDED = "refunded", "Refunded"
        # Its own kind, not a small refund: a refund undoes a purchase and
        # hands back what was paid, a sale is a later trade at half of what
        # the thing is worth. The ledger is asked which of the two happened
        # — by a reader, and by anyone reconciling the books — and only a
        # kind of its own can answer.
        SOLD = "sold", "Sold"

    assignment = models.ForeignKey(
        "n26.Assignment", on_delete=models.CASCADE, related_name="ledger_events"
    )
    kind = models.CharField(max_length=20, choices=Kind)
    actor = models.ForeignKey(
        "auth.User",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        help_text="Who did this — whoever acted, for the audit trail.",
    )
    credits_delta = models.IntegerField(default=0)
    trade_points_delta = models.IntegerField(default=0)
    rating_delta = models.IntegerField(default=0)
    note = models.CharField(max_length=255, blank=True)

    class Meta:
        verbose_name = "ledger event"
        verbose_name_plural = "ledger events"
        ordering = ["created"]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.assignment.assignable}"
