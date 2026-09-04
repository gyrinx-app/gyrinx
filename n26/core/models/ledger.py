"""The ledger — what a gang acquired, what it paid, and how it changed.

Two halves, both kept:

* a **ledger entry**, one per assignment: the assignable it was for, the
  price at the time, discount, what was paid, what it contributes to
  rating, and why it exists;
* **ledger events**, append-only, each recording one change and who made
  it.

The invariant that keeps them honest: folding an entry's events reproduces
the entry. ``n26.reconcile`` checks it.

An event may also stand alone — about a model or the gang itself rather
than an assignment — for acts the books do not price: a rename, a note,
a characteristic set by hand. The invariant is quantified over entries,
so a standalone event is outside it by construction: it has no entry to
fold into and carries no deltas to fold. Together the events are the
gang's history, and every one is pinned to its gang so the whole story
reads in one query, in order.
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
    # The owner's own change to what the model is — a subtype or rule
    # they added or took away themselves. Priced at nothing, and what a
    # per-section reset archives.
    EDITED = "edited", "Edited by the owner"


class LedgerEntry(Base):
    """One entry per assignment: what it was for and what was paid."""

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
    """One append-only record of a change, with who made it.

    About an assignment where money or kit moved; about a model or the
    gang itself for what the books do not price — a rename, a note, a
    characteristic set by hand. Whatever it is about, it is pinned to
    its gang, so a gang's whole history is one indexed query.
    """

    class Kind(models.TextChoices):
        PURCHASED = "purchased", "Purchased"
        ADDED = "added", "Added"
        GRANTED = "granted", "Granted"
        # Granted by built-in propagation (``n26.core.propagation``).
        # Its own kind so the history can say why the item appeared.
        CAUGHT_UP = "caught_up", "Caught up"
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
        # The arrival of an owner's removal: "Took away: Mounted" is
        # what happened, where the plain ``added`` would read as the
        # opposite of what the owner did.
        TOOK_AWAY = "took_away", "Took away"
        # Journal-only acts: no entry, no deltas, nothing for reconcile
        # to fold. They exist so the history can say what the owner did.
        RENAMED = "renamed", "Renamed"
        NOTED = "noted", "Notes edited"
        LORE_EDITED = "lore_edited", "Lore edited"
        IMAGE_SET = "image_set", "Picture set"
        IMAGE_CLEARED = "image_cleared", "Picture removed"
        STAT_SET = "stat_set", "Characteristic set"
        STAT_CLEARED = "stat_cleared", "Characteristic cleared"
        # What the gang may spend, changed after the founding. It moves no
        # money of its own — the credits that follow are recomputed from
        # the budget less what the ledger says was spent — but it changes
        # what every later purchase is measured against, so a reader owed
        # an explanation of "where did my credits go" is owed this too.
        BUDGET_SET = "budget_set", "Budget set"
        # A Visit Trading Post action opening or closing. Like the budget
        # it moves nothing of its own, and unlike it the event is the
        # boundary the spending is measured from: what a visit has left
        # is what it added less every Trade Point the log records after
        # it, so writing one both opens a visit and closes the one before.
        TRADE_POINTS_SET = "trade_points_set", "Trade Points set"
        # One fighter performing that action. The Trade Points they add
        # are the gang's, counted once on the event above, so this
        # carries none of its own — it says who went, which is what
        # answers "has this model already used their action" and what a
        # receipt names. The note holds what the card said raised their
        # figure — the rank's name, where one rank raised it, and the
        # figure itself where several things did — since that is what
        # they added rather than what they are now.
        VISITED_TRADING_POST = "visited_post", "Visited the trading post"

        # An action opening and closing (``n26.core.models.action``).
        # Neither moves anything of its own: what an action did is the
        # log between the two. The note holds the kind, so a reader of
        # the history can be told which action without a join.
        ACTION_OPENED = "action_opened", "Action started"
        ACTION_CLOSED = "action_closed", "Action completed"

        # Where the gang plays. Its own acts, because a gang joining or
        # leaving is something that happened to the gang — the campaign it
        # names reads them too, which is how one record serves both.
        JOINED_CAMPAIGN = "joined_campaign", "Joined a campaign"
        LEFT_CAMPAIGN = "left_campaign", "Left a campaign"

    assignment = models.ForeignKey(
        "n26.Assignment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ledger_events",
    )
    #: The model a journal-only event is about, where it is about one.
    #: Never set beside ``assignment`` — an assignment already knows its
    #: model, and two answers to "what is this about" could disagree.
    miniature = models.ForeignKey(
        "n26.Miniature",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ledger_events",
    )
    #: Set on every event at write. The history's anchor: derivable from
    #: the assignment's roots or the model's membership, but a reader of
    #: "everything done to this gang, in order" should not need a join
    #: per event to ask it.
    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.CASCADE, related_name="ledger_events"
    )
    #: The campaign the gang was playing when this happened, where it was
    #: playing one. Written from the gang's own membership rather than by any
    #: caller, so nothing has to remember to say it, and a campaign's log is
    #: one indexed read of what its gangs did while they were in it. Set to
    #: nothing if the campaign goes: the act still happened to the gang.
    campaign = models.ForeignKey(
        "n26.Campaign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gang_events",
    )
    #: The battle this happened in, where it happened in one. Set only by
    #: something recording a battle's outcome; the ordinary run of buying and
    #: hiring between fights names none. Set to nothing if the battle goes:
    #: the act still happened to the gang.
    battle = models.ForeignKey(
        "n26.Battle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gang_events",
    )
    kind = models.CharField(max_length=20, choices=Kind)
    #: One mark per operation, shared by every event it wrote. Events
    #: sharing a mark were one act — a hire and everything it brought, a
    #: reset and everything it undid — and a reader of the history is
    #: shown them as one. Null means the act's mark was never recorded,
    #: and each event stands on its own.
    batch = models.UUIDField(null=True, blank=True, editable=False)
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
        constraints = [
            models.CheckConstraint(
                condition=models.Q(assignment__isnull=True)
                | models.Q(miniature__isnull=True),
                name="ledger_event_about_at_most_one",
            ),
        ]
        indexes = [
            # What a campaign's gangs did while they were in it, in order.
            models.Index(fields=["campaign", "created"], name="ledger_event_camp_idx"),
        ]

    def __str__(self):
        return f"{self.get_kind_display()}: {self.about}"

    @property
    def about(self):
        """What the record concerns: the thing acquired, the model acted
        on, or — neither set — the gang itself."""
        if self.assignment_id is not None:
            return self.assignment.assignable
        if self.miniature_id is not None:
            return self.miniature
        return self.gang
