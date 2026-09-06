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
fold into and carries no deltas to fold. A model clone keeps presentation-only
summary figures in its machine-readable note so a paged history can tell the
whole act from one record. Together the events are the gang's history, and
every one is pinned to its gang so the whole story reads in one query, in
order.

One standalone event does move money: a **transfer** between gangs — a
ransom paid to the captor. It buys nothing, so there is no entry for it
to fold into; its credits delta is read straight off the event by the
credits recompute, which sums the gang's events with and without an
assignment alike.
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
    #: The action this purchase counted against, where one was open —
    #: a trip to the trading post, founding and equipping the gang. What
    #: an action has spent is the sum over the purchases pointing at it,
    #: and a refund's event sits on the same assignment, so handing
    #: something back returns its Trade Points to the action that paid
    #: for them however long afterwards it happens. Blank for a purchase
    #: made with nothing open: the owner said they meant it, and it
    #: counts against nothing.
    action = models.ForeignKey(
        "n26.Action",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchases",
        help_text=(
            "The action this purchase counted against — a trip to the "
            "trading post, or founding the gang. Blank for a purchase "
            "made with no action open."
        ),
    )
    #: Whose Trade Points these were. An allowance may belong to one
    #: model rather than to the gang — what a fighter is given to spend
    #: as it joins — and what it has spent has to follow the buyer, never
    #: the thing bought: moving a gun into the stash or handing it to
    #: somebody else does not refund the points, and refunding it there
    #: returns them to whoever spent them. Blank where nothing was
    #: recorded against an action, and for a purchase into the stash,
    #: which nobody's allowance pays for.
    spent_by = models.ForeignKey(
        "n26.Miniature",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
        db_index=True,
        help_text=(
            "The model whose Trade Points this purchase spent. Blank for "
            "a purchase that counted against no action, or one into the "
            "stash."
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
        # A clone's entries open from a snapshot rather than from purchases
        # replayed against today's library. Assignment-level records keep the
        # ledger fold honest; one standalone record tells the visible act.
        CLONED = "cloned", "Cloned"
        # What the gang may spend, changed after the founding. It moves no
        # money of its own — the credits that follow are recomputed from
        # the budget less what the ledger says was spent — but it changes
        # what every later purchase is measured against, so a reader owed
        # an explanation of "where did my credits go" is owed this too.
        BUDGET_SET = "budget_set", "Budget set"
        # A Visit Trading Post action opening or closing, from before it
        # was an action row. Nothing writes one now — the pair below say
        # it for every kind of action — and the kind stays so that a
        # gang's older history still has a word for what it did.
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
        # the history can be told which action without a join, and the
        # figure the act carried where it carried one — what a visit
        # brought, and what it still had when it ended.
        ACTION_OPENED = "action_opened", "Action started"
        ACTION_CLOSED = "action_closed", "Action completed"

        # Where the gang plays. Its own acts, because a gang joining or
        # leaving is something that happened to the gang — the campaign it
        # names reads them too, which is how one record serves both.
        JOINED_CAMPAIGN = "joined_campaign", "Joined a campaign"
        LEFT_CAMPAIGN = "left_campaign", "Left a campaign"

        # Credits moving between two gangs — a ransom paid to the captor.
        # The one standalone kind that carries a credits delta: positive
        # on the gang that paid (spend), negative on the gang that
        # received (credits in). ``counterpart`` names the other gang,
        # where it is a gang the app knows; the note says why.
        TRANSFERRED = "transferred", "Credits transferred"

        # A model's status changing — into Recovery, Critically Injured,
        # Captured, Dead, or back to Active. Journal-only: nothing is
        # priced, though a death changes what the rating sums to, and
        # ``settle`` repins it. The note holds "was → now", and after a
        # colon what did it — the result whose effect set it, or "Clean
        # House", or nothing for the owner's own hand.
        STATUS_SET = "status_set", "Status set"

        # A roll on a roll table, put on the record the moment it is
        # made — before anything is picked for it, and whether or not
        # anything ever is. The pick that follows names this event, so
        # a roll nothing followed stands on its own in the history, which
        # is what a second roll looks like to whoever reads it. ``roll``
        # and ``dice`` say what came up; ``slot`` says what it was for.
        ROLLED = "rolled", "Rolled"

        # A campaign's asset coming to the gang or leaving it. Journal-only:
        # the gang holds the asset and never owns it, so there is no entry
        # and nothing for reconcile to fold. GRANTED stays for what a
        # campaign type gives at joining, which is an assignment.
        GAINED = "gained", "Gained"
        LOST = "lost", "Lost"

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
    #: The campaign's asset a journal-only event is about, where it is about
    #: one — a holding this gang gained or lost. Never set beside
    #: ``assignment`` or ``miniature``, for the same reason those two are
    #: never set together. Set to nothing if the asset is removed from the
    #: campaign; the note keeps the name, so the line still says what the
    #: gang gained or lost.
    campaign_asset = models.ForeignKey(
        "n26.CampaignAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
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
    #: What a roll came to, on an event recording one — the number a
    #: table is read by, so 24 on a D66 and 8 on a 2D6. Columns rather
    #: than words in the note, so nothing has to parse a sentence to
    #: find the figure again. Empty on every other kind.
    roll = models.PositiveSmallIntegerField(null=True, blank=True)
    #: The die that roll was of, as the table named it at the time — a
    #: table may change its die later, and the record keeps what was
    #: actually rolled. The library's closed set of dice; not declared
    #: as choices here because the library imports this app.
    dice = models.CharField(max_length=8, blank=True, default="")
    #: The choice a roll was made for. Set to nothing if the slot goes:
    #: the roll still happened.
    slot = models.ForeignKey(
        "library.Slot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    #: The other gang in a transfer — who was paid, or who paid. Empty
    #: where the credits left for somebody the app does not know, and
    #: set to nothing if that gang goes: the payment still happened.
    counterpart = models.ForeignKey(
        "n26.Gang",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )

    class Meta:
        verbose_name = "ledger event"
        verbose_name_plural = "ledger events"
        ordering = ["created"]
        constraints = [
            # At most one of the three subjects is set: any two of them
            # could disagree about what the record is about.
            models.CheckConstraint(
                condition=models.Q(assignment__isnull=True, miniature__isnull=True)
                | models.Q(assignment__isnull=True, campaign_asset__isnull=True)
                | models.Q(miniature__isnull=True, campaign_asset__isnull=True),
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
        on, the campaign's asset gained or lost, or — none set — the
        gang itself."""
        if self.assignment_id is not None:
            return self.assignment.assignable
        if self.miniature_id is not None:
            return self.miniature
        if self.campaign_asset_id is not None:
            return self.campaign_asset
        return self.gang
