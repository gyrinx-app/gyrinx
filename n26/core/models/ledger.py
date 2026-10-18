"""The ledger — what a gang acquired, what it paid, and how it changed.

Two halves, both kept:

* a **ledger entry**, one per assignment: the assignable it was for, the
  price at the time, discount, what was paid, what it contributes to
  rating, and why it exists;
* **ledger events**, append-only, each recording one change and who made
  it.

Invariant: folding an entry's events reproduces the entry.
``n26.reconcile`` checks it.

An event may also stand alone, about a model or the gang instead of an
assignment, for unpriced changes: a rename, a note, a characteristic set
by hand. The invariant covers entries only, and a standalone event has no
entry to fold into. A model clone's event keeps display-only summary
figures in its machine-readable note, so a paged history can describe the
whole clone from one event. Every event is pinned to its gang, so a gang's
whole history is one ordered query.

Some standalone events do move money: a **transfer** between gangs (such as
a ransom paid to the captor), income, a manual credits adjustment, and the
correction a gang takes when it first gets a budget. None buys anything, so
there is no entry to fold into. The credits recompute reads their deltas
straight off the events, summing the gang's events with and without an
assignment alike.
"""

from django.db import models

from n26.core.fields import ULIDField
from n26.core.models.abstract import Base


class Reason(models.TextChoices):
    """Why an assignment exists. Derived from how it was acquired, not from
    whether money changed hands — free and granted are different things."""

    BOUGHT = "bought", "Bought"
    DEFAULT = "default", "Default equipment"
    GRANTED = "granted", "Granted by something else"
    REWARD = "reward", "Reward"
    FREE = "free", "Free"
    # An owner's own edit to a model: a subtype or rule they added or
    # removed. Priced at nothing; a per-section reset archives these.
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
    #: The open activity this purchase counted against. An activity's spend
    #: is the sum over the purchases pointing at it, and a refund's event
    #: sits on the same assignment, so a refund returns Trade Points to the
    #: activity that paid them, however much later. Null for a purchase the
    #: owner confirmed with no activity open; it counts against nothing.
    activity = models.ForeignKey(
        "n26.Activity",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="purchases",
        help_text=(
            "The activity this purchase counted against — a trip to the "
            "trading post, or founding the gang. Blank for a purchase "
            "made with no activity open."
        ),
    )
    #: The model whose Trade Points paid for this. An allowance can belong
    #: to one model, so spend follows the buyer, not the item's current
    #: host. Moving the item to the stash or another model refunds nothing,
    #: and a later refund returns the points to the buyer. Null when nothing
    #: counted against an activity, and for stash purchases, which no
    #: model's allowance pays for.
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
    #: A clone copies an advancement's contribution but not the advancement
    #: record that names it, so the copy's entry keeps that fact itself.
    cloned_from_advancement = models.BooleanField(
        default=False,
        help_text=(
            "Copied from a contribution an advancement added. The rating "
            "breakdown lists it under Advancements."
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
        """What was acquired, read through the assignment. An amendment that
        swaps the assignable therefore changes what existing history names.
        """
        return self.assignment.assignable

    @property
    def rating_without_override(self):
        """The contribution with manual rating changes removed.

        Hire options and later option changes remain part of this figure.
        The recorded deltas preserve it even after several overrides.
        """
        overrides = self.assignment.ledger_events.filter(
            kind__in=[LedgerEvent.Kind.RATING_SET, LedgerEvent.Kind.RATING_RESET]
        ).aggregate(total=models.Sum("rating_delta", default=0))["total"]
        return self.rating_contribution - overrides


class LedgerEvent(Base):
    """An append-only record of one change and who made it.

    It is about an assignment when money or kit moved, and about a model
    or the gang for unpriced changes such as a rename, a note or a
    characteristic set by hand. Every event is pinned to its gang, so a
    gang's whole history is one indexed query.
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
        # A counter's first machine-readable value. A normal opening starts
        # from zero; a checkpoint records the value a counter already held
        # before it had any machine-readable events.
        COUNTER_OPENED = "counter_opened", "Counter opened"
        COUNTER_CHECKPOINTED = "counter_checkpointed", "Counter checkpointed"
        AMENDED = "amended", "Amended"
        REPRICED = "repriced", "Repriced"
        REMOVED = "removed", "Removed"
        # One removed assignment put back exactly as it was, when an
        # arbitrator unarchives a campaign counter or label. Never a fresh
        # grant: the value or pick it held comes back with it.
        RESTORED = "restored", "Restored"
        REFUNDED = "refunded", "Refunded"
        # Separate from REFUNDED: a refund undoes a purchase and returns what
        # was paid; a sale is a later trade at half the item's rating. The
        # history and reconciliation both need to tell them apart.
        SOLD = "sold", "Sold"
        # Written when an owner's removal assignment is created ("Took away:
        # Mounted"). ``ADDED`` would read as the opposite of what the owner
        # did.
        TOOK_AWAY = "took_away", "Took away"
        # Journal-only: no entry, no deltas, nothing for reconcile to fold.
        # They record owner changes for the history.
        RENAMED = "renamed", "Renamed"
        NOTED = "noted", "Notes edited"
        LORE_EDITED = "lore_edited", "Lore edited"
        IMAGE_SET = "image_set", "Picture set"
        IMAGE_CLEARED = "image_cleared", "Picture removed"
        STAT_SET = "stat_set", "Characteristic set"
        STAT_CLEARED = "stat_cleared", "Characteristic cleared"
        RATING_SET = "rating_set", "Base rating changed"
        RATING_RESET = "rating_reset", "Base rating reset"
        # A clone's entries copy a snapshot of the source instead of
        # replaying purchases against the current library. Per-assignment
        # CLONED events keep each entry's fold correct; one standalone
        # CLONED event is what the history shows.
        CLONED = "cloned", "Cloned"
        # The gang's budget changed after founding. Credits are recomputed
        # as the budget less ledger spend, so a budget change moves the
        # credits a player sees and belongs in the history. When a gang with
        # no budget takes one, this event carries a correction that sets the
        # spend total to the worth of what the gang holds, so spend on items
        # since deleted stops counting. The correction is bookkeeping, not
        # income, and the history shows no figure for it.
        BUDGET_SET = "budget_set", "Budget set"
        # A Trading Post visit opening or closing, recorded without an
        # Activity. Nothing writes this kind; it stays so existing events
        # of this kind still render in the history.
        TRADE_POINTS_SET = "trade_points_set", "Trade Points set"
        # One fighter taking part in a Trading Post visit. Their Trade
        # Points belong to the gang and are counted once, on the activity's
        # opening event, so this event carries none. The note holds the
        # name of the subtype that set their figure, or the figure itself
        # when several did.
        VISITED_TRADING_POST = "visited_post", "Visited the trading post"

        # An activity opening and closing (``n26.core.models.activity``).
        # Neither carries deltas; what the activity did is the events
        # between them. The note holds the activity kind, so history can
        # name it without a join.
        ACTION_OPENED = "action_opened", "Action started"
        ACTION_CLOSED = "action_closed", "Action completed"

        # A fighter using a library action. Payment, completion and correction
        # can carry the credits or rating change made by that lifecycle step.
        ACTION_USE_STARTED = "use_started", "Action use started"
        ACTION_USE_COMPLETED = "use_completed", "Action use completed"
        ACTION_USE_CANCELLED = "use_cancelled", "Action use cancelled"
        ACTION_USE_PAID = "use_paid", "Action use paid"
        ACTION_USE_CORRECTED = "use_corrected", "Action use corrected"
        ACTION_USE_APPLIED_BY_HAND = "use_by_hand", "Action use applied by hand"
        ACTION_USE_REOPENED = "use_reopened", "Action use reopened"
        ACTION_USE_UNDONE = "use_undone", "Action use undone"

        # A gang joining or leaving a campaign. Recorded on the gang; the
        # campaign's log reads the same events.
        JOINED_CAMPAIGN = "joined_campaign", "Joined a campaign"
        LEFT_CAMPAIGN = "left_campaign", "Left a campaign"

        # Credits moving between two gangs, such as a ransom paid to the
        # captor. Positive on the paying gang (spend), negative on the
        # receiving gang (credits in). ``counterpart`` names the other gang
        # when it is a gang in the app; the note gives the reason.
        TRANSFERRED = "transferred", "Credits transferred"

        # A model's status changing: into Recovery, Critically Injured,
        # Captured, Dead, or back to Active. Journal-only: nothing is
        # priced, though a death changes the rating sum and ``settle``
        # repins it. The note holds "was → now", then after a colon what
        # caused it: the result whose effect set it, "Clean House", or
        # nothing when the owner set it directly.
        STATUS_SET = "status_set", "Status set"

        # A table roll, recorded when it is made: before anything is picked
        # and whether or not anything ever is. The pick that follows names
        # this event (``Assignment.roll``). A roll with no pick stays in the
        # history on its own, so a re-roll shows as two rolls. ``roll`` and
        # ``dice`` hold the result; ``slot`` is what it was rolled for.
        ROLLED = "rolled", "Rolled"

        # A campaign's asset coming to the gang or leaving it. Journal-only:
        # the gang holds the asset and never owns it, so there is no entry
        # and nothing for reconcile to fold. GRANTED still covers what a
        # campaign type gives at joining, which is an assignment.
        GAINED = "gained", "Gained"
        LOST = "lost", "Lost"
        INCOME = "income", "Income"
        # Credits added or removed by hand, for whatever the app does not
        # record itself. Its own kind so the history does not call it
        # income; negative is credits in, positive is credits out.
        CREDITS_ADJUSTED = "credits_adjusted", "Credits adjusted"
        POST_BATTLE = "post_battle", "Post-battle results"

    assignment = models.ForeignKey(
        "n26.Assignment",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ledger_events",
    )
    #: The model a journal-only event is about, if any. Never set with
    #: ``assignment``: the assignment already identifies its model, and two
    #: subjects could disagree.
    miniature = models.ForeignKey(
        "n26.Miniature",
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="ledger_events",
    )
    #: The campaign asset a journal-only event is about, if any: a holding
    #: this gang gained or lost. Never set with ``assignment`` or
    #: ``miniature``, for the same reason. SET_NULL if the asset is removed
    #: from the campaign; the note keeps its name for the history.
    campaign_asset = models.ForeignKey(
        "n26.CampaignAsset",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    #: Snapshot of the gained holding's type, kept if its campaign asset is deleted.
    received_asset_type = ULIDField(null=True, blank=True, editable=False, default=None)
    # A holding roll is usable only in the ownership period that made it.
    holding_revision = models.PositiveIntegerField(null=True, blank=True)
    #: Set on every event at write. It could be derived from the
    #: assignment's roots or the model's membership; storing it makes a
    #: gang's ordered history one query, without a join per event.
    gang = models.ForeignKey(
        "n26.Gang", on_delete=models.CASCADE, related_name="ledger_events"
    )
    #: The campaign the gang was in when this happened, if any. Taken from
    #: the gang's membership at write time, not passed by callers, so a
    #: campaign's log is one indexed read of what its gangs did while in it.
    #: SET_NULL: the event still belongs to the gang if the campaign is
    #: deleted.
    campaign = models.ForeignKey(
        "n26.Campaign",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gang_events",
    )
    #: The battle this happened in, if any. Set only when recording a
    #: battle's outcome; purchases and hires between battles leave it null.
    #: SET_NULL: the event still belongs to the gang if the battle is
    #: deleted.
    battle = models.ForeignKey(
        "n26.Battle",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="gang_events",
    )
    post_battle_revision = models.ForeignKey(
        "n26.PostBattleRevision",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_events",
    )
    post_battle_occurrence = models.UUIDField(null=True, blank=True, db_index=True)
    kind = models.CharField(max_length=20, choices=Kind)
    #: Shared by every event one operation wrote, such as a hire and
    #: everything it brought, or a reset and everything it undid. The
    #: history shows events with the same batch as one change. Null means
    #: no batch was recorded, and the history shows each event alone.
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
    #: The action use this event belongs to. This is provenance, not another
    #: subject: ``assignment`` or ``miniature`` still says what changed.
    action_record = models.ForeignKey(
        "n26.ActionRecord",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ledger_events",
    )
    #: Every debit accepted together carries one payment id. An action with no
    #: payment has no group, and unfinished actions write no payment events.
    payment_id = models.UUIDField(null=True, blank=True, db_index=True)
    #: Machine-readable counter history. All three are present together; the
    #: signed delta is the movement that actually happened after the zero floor.
    counter_before = models.PositiveIntegerField(null=True, blank=True)
    counter_delta = models.IntegerField(null=True, blank=True)
    counter_after = models.PositiveIntegerField(null=True, blank=True)
    #: A correction points back to the exact event it reverses. The original
    #: event remains append-only.
    reversal_of = models.ForeignKey(
        "self",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reversals",
    )
    #: Exact tier or result assignments before and after a recorded change.
    #: Archiving preserves the link; deletion requires this event to go too.
    before_pick = models.ForeignKey(
        "n26.Assignment",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="ledger_events_before_pick",
    )
    after_pick = models.ForeignKey(
        "n26.Assignment",
        on_delete=models.RESTRICT,
        null=True,
        blank=True,
        related_name="ledger_events_after_pick",
    )
    note = models.CharField(max_length=255, blank=True)
    #: The rolled result a table is read by: 24 on a D66, 8 on a 2D6. Null
    #: on other kinds. Stored as a column so nothing has to parse the note
    #: to find it.
    roll = models.PositiveSmallIntegerField(null=True, blank=True)
    #: The die that roll was of, as the table named it at the time — a
    #: table may change its die later, and the record keeps what was
    #: actually rolled. The library's closed set of dice; not declared
    #: as choices here because the library imports this app.
    dice = models.CharField(max_length=8, blank=True, default="")
    #: The Slot a roll was made for. SET_NULL keeps the roll if the Slot is
    #: deleted.
    slot = models.ForeignKey(
        "library.Slot",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="+",
    )
    #: The status transition this choice was rolled for. Null for tables not
    #: tied to a status change, and on rolls recorded without a revision.
    status_revision = models.PositiveIntegerField(null=True, blank=True)
    #: The other gang in a transfer: the payee or the payer. Null when the
    #: other party is not a gang in the app. SET_NULL keeps the payment if
    #: that gang is deleted.
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
        ordering = ["created", "pk"]
        constraints = [
            # At most one of the three subjects is set: any two of them
            # could disagree about what the record is about.
            models.CheckConstraint(
                condition=models.Q(assignment__isnull=True, miniature__isnull=True)
                | models.Q(assignment__isnull=True, campaign_asset__isnull=True)
                | models.Q(miniature__isnull=True, campaign_asset__isnull=True),
                name="ledger_event_about_at_most_one",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(
                        counter_before__isnull=True,
                        counter_delta__isnull=True,
                        counter_after__isnull=True,
                    )
                    | models.Q(
                        counter_before__isnull=False,
                        counter_delta__isnull=False,
                        counter_after__isnull=False,
                    )
                ),
                name="ledger_event_counter_movement_is_whole",
            ),
            models.CheckConstraint(
                condition=(
                    (
                        models.Q(
                            counter_before__isnull=True,
                            counter_delta__isnull=True,
                            counter_after__isnull=True,
                        )
                        & ~models.Q(
                            kind__in=[
                                "counter_opened",
                                "counter_checkpointed",
                            ]
                        )
                    )
                    | models.Q(
                        counter_before__isnull=False,
                        counter_delta__isnull=False,
                        counter_after__isnull=False,
                        kind__in=[
                            "counter_opened",
                            "counter_checkpointed",
                            "tallied",
                        ],
                    )
                ),
                name="ledger_event_counter_movement_kind_v2",
            ),
            models.CheckConstraint(
                condition=models.Q(counter_before__isnull=True)
                | models.Q(assignment__isnull=False),
                name="ledger_event_counter_has_assignment",
            ),
            models.CheckConstraint(
                condition=(
                    models.Q(counter_before__isnull=True)
                    | models.Q(
                        counter_after=models.F("counter_before")
                        + models.F("counter_delta")
                    )
                ),
                name="ledger_event_counter_movement_adds_up",
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
