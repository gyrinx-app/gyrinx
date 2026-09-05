"""Operations — the only place player data is written.

An operation is a small set of changes that apply together: hire a model,
buy a weapon, remove something. Everything inside one runs in a single
transaction, and when it closes, the pinned numbers it disturbed are
rewritten:

* every affected model's rating,
* the gang's rating and credits.

They are rewritten by **recomputing**, not by adding deltas. A delta drifts
the moment a code path forgets one and nothing notices for months; a
recompute at the boundary is right by construction, and ``n26.reconcile``
still catches anything that bypassed the boundary entirely.

Not every operation moves money. A rename, a notes edit, a
characteristic set by hand price nothing — they go through here anyway,
because they are part of the gang's story and each writes a journal
event, so the history can say who did what and when. The line is the
story, not the money: device preferences (a print config, a display
set) are nobody's history and stay plain saves.

Use it as a context manager::

    with operation(gang, actor=player) as op:
        yolanda = op.hire(hunt_champion, "Yolanda", paid=130)
        op.give_weapon(yolanda, combat_shotgun, paid=60)
"""

from contextlib import contextmanager
from dataclasses import dataclass
from uuid import uuid4

from django.db import transaction

from n26.core.models import (
    Assignment,
    CampaignAsset,
    LedgerEntry,
    LedgerEvent,
    Miniature,
    ProfileRole,
    Reason,
)
from n26.core.status import Status

#: The least a sale ever returns. Half of a knife is nothing, and nobody
#: hands a knife over for nothing.
MINIMUM_PROCEEDS = 5


@dataclass(frozen=True)
class _CloneResult:
    """Destination assignments and models made from a clone plan."""

    primary: Miniature | None
    assignments: dict
    miniatures: dict


def proceeds_for(rating):
    """What selling something worth ``rating`` puts back in the gang's hand.

    Half, rounded up, never under :data:`MINIMUM_PROCEEDS`. Worth, not
    outlay: a sword haggled down to 60 is still a hundred credits of sword,
    and rating is what the gang owns.
    """
    return max(MINIMUM_PROCEEDS, -(-rating // 2))


def sale_of(assignment, keeping=()):
    """What selling this would move: the assignments that go, and what
    comes back.

    Asked before the act as well as during it, so the confirmation quotes
    the figure the sale will actually pay rather than a second arithmetic
    that could disagree with it.

    ``keeping`` names children being unbolted into the stash rather than
    sold — each with whatever hangs off it. A sale that leaves the sight
    behind is a sale of the gun alone, and pays for the gun alone, so a
    confirmation offering that choice has to be able to price it.
    """
    kept = {row.pk for child in keeping for row in [child, *subtree(child)]}
    rows = [
        row
        for row in [assignment, *subtree(assignment)]
        if not row.archived and row.pk not in kept
    ]
    rating = sum(row.rating for row in rows)
    return rows, rating, proceeds_for(rating)


def detachable_children(assignment):
    """What hangs off this that could be kept instead of going with it.

    Selling a gun sells everything on it. An accessory need not be part
    of that bargain: it is gear in its own right, so it can be unbolted
    into the stash first and fitted to another gun later, and the seller
    is asked which they meant.

    Two sorts of child are never on offer. A firing line is the weapon's
    own (:func:`n26.core.owned.is_detachable`). And anything the weapon
    *brought* — a sight that came with it as standard — belongs to the
    package rather than to the gang: what caused it goes, so it goes.
    """
    from n26.core.owned import can_unbolt

    return [
        child
        for child in assignment.children.all()
        if not child.archived and can_unbolt(child)
    ]


def refund_of(assignment):
    """What refunding this would move: the assignments that go, and what
    comes back.

    Asked before the act as well as during it, for the same reason
    :func:`sale_of` is — a confirmation that quotes its own arithmetic is
    a confirmation that can disagree with the click underneath it.

    What comes back is what was **paid**, every credit of it, across the
    whole subtree: a gun's ammo was bought on the same click and is
    refunded on this one. That is a different number from a sale's, which
    is half of what the thing is *worth*, and the two part company the
    moment anything is discounted or given away.
    """
    rows = [row for row in [assignment, *subtree(assignment)] if not row.archived]
    paid = sum(
        entry.paid
        for row in rows
        if (entry := getattr(row, "ledger_entry", None)) is not None
    )
    return rows, paid


class Refusal(Exception):
    """An operation will not do this, and the message says why.

    Raised inside the operation, so the transaction unwinds and nothing
    is left half-written. A view catches it, shows the sentence, and
    sends the reader back to the page they clicked on — so the sentence
    is written for the player who clicked the button.

    What belongs here is an act some control really offered and the
    app declines: an overspend, a pick that cannot settle the
    choice it was given. What does not is a content bug or a caller
    mistake — nobody can click their way to one, the sentence would mean
    nothing to a player, and an unhandled error is the right answer.
    """


class LibraryError(Exception):
    """The library asks for something no operation can do.

    A content bug, not a player's act: nobody clicked their way to it
    and no sentence would help them. It is not a ``Refusal``, which a
    view shows to the player, and not a ``ValueError``, which a view
    reads as a tampered link — so it surfaces as the error it is, and
    the operation unwinds whole.
    """


class NotEnoughCredits(Refusal):
    """A spend would take the gang below zero credits.

    Raised at the operation boundary, so the whole operation rolls back —
    nothing is half-bought. This is the one *rule* we enforce rather than
    inform about: the founding budget "may not be exceeded", and the
    alternative is a database IntegrityError with nobody's name on it.
    Allowing debt is simply raising or clearing the budget.
    """

    def __init__(self, gang, shortfall):
        self.gang = gang
        self.shortfall = shortfall
        super().__init__(
            f"Not enough credits: this spend leaves {gang.name} {shortfall}¢ "
            f"short of their {gang.starting_credits}¢ budget."
        )


class AlreadyInACampaign(Refusal):
    """A gang plays one campaign at a time.

    Not a rule of the game so much as of the record: two open memberships
    would leave every event the gang wrote unable to say which campaign it
    belonged to, and the campaign logs reading each other's acts.
    """

    def __init__(self, gang, campaign):
        self.gang = gang
        self.campaign = campaign
        super().__init__(
            f"{gang.name} is already playing {campaign.name}. "
            "A gang plays one campaign at a time — leave that one first."
        )


class NotOnOffer(Refusal):
    """The thing picked cannot settle the choice that was offered.

    A choice names one kind of thing and only that kind settles it: a
    slot asking for a skill is not settled by the powers filed beside
    them in the same collection, because a slot reads as resolved only
    where what was chosen matches the offer. The pick screen lists what
    may be chosen (``n26.core.browse.offered_by``), so a click that
    lands here is a
    stale page or a hand-made address rather than a choice worth writing.
    """

    def __init__(self, anchor, chosen, message=""):
        self.anchor = anchor
        self.chosen = chosen
        super().__init__(
            message
            or (
                f"{anchor.assignable} does not offer a choice of "
                f"{type(chosen)._meta.verbose_name}."
            )
        )


#: Stands for "this operation has not looked yet", so that a gang playing no
#: campaign is asked about once rather than on every event it writes.
_UNASKED = object()

#: The note on a roll that was made at the table and entered, which is
#: how the record tells one from a roll the page generated.
ROLL_ENTERED = "Rolled at the table and entered here."

#: The reason on a status change Clean House made, which is how the
#: history tells the cycle's end from the owner's own hand.
CLEAN_HOUSE = "Clean House"


def _movement_note(moved, reason):
    """A tally's note: what moved, then why, inside the column's width.

    The movement is the half that has to survive — an audit reads the
    number, and the reason is the reader's own words about it — so a
    reason too long to fit is what gives way. A caller can hand over a
    great deal more than the column holds: an assignable's name and its
    annotation are 200 characters each, and a rule that tallies passes
    the pair of them as its reason.
    """
    from n26.core.models import LedgerEvent

    if not reason:
        return moved
    room = LedgerEvent._meta.get_field("note").max_length - len(moved) - len(": ")
    if len(reason) > room:
        reason = reason[: max(0, room - 1)] + "…"
    return f"{moved}: {reason}"


class Operation:
    """Collects what it touched, so the boundary knows what to repin."""

    #: A pet whose profile brings a pet whose profile brings a pet is a
    #: content bug, not a use case.
    MAX_STORED_EFFECT_DEPTH = 3

    def __init__(self, gang, actor=None, batch=None):
        self.gang = gang
        self.actor = actor
        # Every event this operation writes carries the same mark, so
        # the history can tell one act's records from its neighbours'. A
        # caller writing one act across two gangs — an asset handed from
        # one to the other — passes the mark in, so both halves share it.
        self.batch = batch or uuid4()
        self._miniatures = {}
        self._effect_depth = 0
        self._campaign = _UNASKED

    def touched(self, miniature):
        if miniature is not None:
            self._miniatures[miniature.pk] = miniature

    # --- primitives ------------------------------------------------------

    def assign(
        self,
        assignable,
        *,
        gang=None,
        miniature=None,
        parent=None,
        stash=None,
        caused_by=None,
        chosen_for=None,
        chosen_for_slot=None,
        chosen_for_offer=None,
        materialised_from=None,
        materialised_for=None,
        paid=0,
        list_price=None,
        discount=0,
        trade_points=0,
        rating=None,
        reason=None,
        bought_from=None,
        action=None,
        spent_by=None,
        note="",
        removes=False,
        kind=None,
        roll=None,
    ):
        """Write one assignment: an assignable, a host, and a cause.

        Those are the three components of every assignment. ``assignable``
        is what is held; the host is the specific object it sits on — a
        model, the gang, a parent item, or the stash — and ``caused_by`` is
        what brought it, so removing the cause removes this too. The
        ledger entry and the opening event are written in the same breath,
        which is why nothing outside an operation may create one.

        ``chosen_for`` names the choice this settles, where it settles
        one — the assignment that asked, so a card reads what was chosen
        rather than guessing from what kind of thing it is.
        ``chosen_for_slot`` and ``chosen_for_offer`` name which of that
        assignment's choices, for the case where one asks more than once —
        the first for a slot's question, the second for an offer's.

        ``materialised_from`` and ``materialised_for`` are the provenance
        of a built-in: which set membership this copy came from, and for
        which carrier. Only ``reconcile_defaults`` sets them.

        ``action`` is the open action this counted against, where the
        surface that bought it says one applies. What an action has
        spent is the sum over what points at it. ``spent_by`` is whose
        Trade Points those were, where the allowance was one model's own
        rather than the gang's.

        ``roll`` is the ledger event recording the roll this pick came
        from, where a table was rolled for it. It has to be a roll made
        for the choice the pick settles, with no standing pick already
        naming it; ``_choose_for_slot`` is where that is checked.
        """
        assignment = Assignment.objects.create(
            assignable=assignable,
            gang=gang,
            miniature=miniature,
            parent=parent,
            stash=stash,
            caused_by=caused_by,
            chosen_for=chosen_for,
            chosen_for_slot=chosen_for_slot,
            chosen_for_offer=chosen_for_offer,
            materialised_from=materialised_from,
            materialised_for=materialised_for,
            removes=removes,
            roll=roll,
        )
        if list_price is None:
            list_price = paid + discount
        if rating is None:
            # A discount is a deal on the real price, so the thing still
            # counts at full value; a collection's own price has no discount
            # — it IS the price, so it is also the rating. Whatever number
            # lands here is pinned on this assignment for good: moving the
            # thing later never re-prices it.
            rating = list_price
        if reason is None:
            reason = _reason_for(paid, caused_by)

        LedgerEntry.objects.create(
            assignment=assignment,
            list_price=list_price,
            discount=discount,
            paid=paid,
            trade_points=trade_points,
            rating_contribution=rating,
            reason=reason,
            bought_from=bought_from,
            action=action,
            spent_by=spent_by,
            note=note,
        )
        self.event(
            assignment,
            kind if kind is not None else _kind_for(paid, caused_by),
            credits_delta=paid,
            trade_points_delta=trade_points,
            rating_delta=rating,
            note=note,
        )
        self.touched(assignment.miniature_root)
        # A removal is not an arrival: the thing named is being taken
        # away, so nothing it would write on arrival may run.
        if not removes:
            self._run_stored_effects(assignment, assignable)
        return assignment

    def _run_stored_effects(self, assignment, assignable):
        """Execute anything this assignable writes rather than computes.

        Each effect owns its own ``perform``, the way each scope owns its
        ``targets`` — the operation just hands itself over.
        """
        modifiers = getattr(assignable, "modifiers", None)
        if modifiers is None or self._effect_depth >= self.MAX_STORED_EFFECT_DEPTH:
            return
        self._effect_depth += 1
        try:
            for modifier in modifiers.all():
                effect = modifier.effect
                if effect is not None and getattr(effect, "is_stored", False):
                    effect.perform(self, assignment)
        finally:
            self._effect_depth -= 1

    def event(self, about, kind, **deltas):
        """Append to the log. Nothing already written is ever altered.

        ``about`` is the assignment or the model the record concerns —
        or a campaign's asset the gang gained or lost, or ``None``,
        for an act on the gang itself. Every event is pinned to its gang,
        so a gang's whole history is one query, in order: this
        operation's gang, or — opened without one — the gang at the top
        of the assignment's own chain.

        Where the gang is playing a campaign, the event names it too.
        That is read here rather than passed in, so no caller has to
        remember, and a campaign's log holds everything its gangs did
        while they were in it rather than only the acts somebody thought
        to mark.
        """
        assignment = about if isinstance(about, Assignment) else None
        gang = self.gang
        if gang is None and assignment is not None:
            gang = assignment.gang_root
        if gang is None and isinstance(about, Miniature):
            membership = getattr(about, "membership", None)
            gang = membership.gang if membership else None
        return LedgerEvent.objects.create(
            assignment=assignment,
            miniature=about if isinstance(about, Miniature) else None,
            campaign_asset=about if isinstance(about, CampaignAsset) else None,
            gang=gang,
            campaign=self._campaign_of(gang),
            kind=kind,
            batch=self.batch,
            actor=self.actor,
            **deltas,
        )

    def _campaign_of(self, gang):
        """The campaign this gang is playing, asked once per operation.

        A gang joining is itself an event, and it is written after the
        membership, so the answer is looked up when it is first needed
        rather than when the operation opened.
        """
        from n26.core.models import CampaignMembership

        if gang is None:
            return None
        if self._campaign is _UNASKED:
            membership = (
                CampaignMembership.objects.filter(gang=gang, left__isnull=True)
                .select_related("campaign")
                .first()
            )
            self._campaign = membership.campaign if membership else None
        return self._campaign

    def join_campaign(self, campaign):
        """Put this operation's gang into a campaign, and say so in its history.

        A gang plays one campaign at a time, so joining a second while still in
        the first is refused rather than quietly recorded — the database holds
        the same line, and a player owed an explanation is better served by the
        sentence than by a constraint error.

        A campaign's budget stops nobody: it is a size the table agreed on,
        and a gang bigger than it joins and is said to be bigger. What
        counts against the budget is the gang's wealth — see
        :func:`over_budget` — and the screens that add a gang say so.

        Joining gives the gang the campaign's two types — the shared one it
        was founded on and its own additions — as gang-hosted assignments,
        granted, with their built-ins landing in the same breath: on N26
        core a gang comes away holding a Settlement and a Reputation counter
        at 0, each caused by the type's carrier. The membership points at
        both carriers, so what the campaign gave can be found again. The
        event is the gang's own, and names the campaign, so it reads in both
        histories from one record.
        """
        from n26.core.models import CampaignMembership

        gang = self.gang
        open_now = CampaignMembership.objects.filter(
            gang=gang, left__isnull=True
        ).select_related("campaign")
        already = open_now.first()
        if already is not None:
            if already.campaign_id == campaign.pk:
                return already
            raise AlreadyInACampaign(gang, already.campaign)

        membership = CampaignMembership.objects.create(campaign=campaign, gang=gang)
        # Set before the event is written, so the event that records the
        # joining names the campaign it joined — and so the carriers and
        # their built-ins, written next, name it too.
        self._campaign = campaign
        self.event(None, LedgerEvent.Kind.JOINED_CAMPAIGN)
        membership.type_carrier = self._carry(campaign.campaign_type)
        membership.additions_carrier = self._carry(campaign.additions)
        membership.save(update_fields=["type_carrier", "additions_carrier", "modified"])
        return membership

    def _carry(self, campaign_type):
        """Put one campaign type on the gang, with what it brings.

        The same shape as a founding — a free gang-hosted assignment whose
        built-ins arrive caused by it — but granted rather than added:
        the gang did not choose the type, the campaign did. Nothing is
        priced, so the gang's rating is untouched.
        """
        carrier = self.assign(
            campaign_type,
            gang=self.gang,
            paid=0,
            reason=Reason.GRANTED,
            kind=LedgerEvent.Kind.GRANTED,
        )
        self.reconcile_defaults(carrier, gang=self.gang)
        return carrier

    def leave_campaign(self):
        """Take this operation's gang out of whatever campaign it is playing.

        Leaving closes the membership rather than deleting it: what a gang did
        while it was in a campaign stays true, and the campaign's log keeps
        reading. A gang playing nothing leaves nothing, and records nothing.
        """
        from n26.core.models import CampaignMembership

        membership = (
            CampaignMembership.objects.filter(gang=self.gang, left__isnull=True)
            .select_related("campaign")
            .first()
        )
        if membership is None:
            return None

        # Settled before the membership closes: what this operation is asked
        # about the gang's campaign is answered by looking for an open
        # membership, and in a moment there will not be one — so the event
        # that records the leaving would not be able to name what was left.
        self._campaign = membership.campaign
        membership.left = _now()
        membership.save(update_fields=["left", "modified"])
        self.event(None, LedgerEvent.Kind.LEFT_CAMPAIGN)
        self._campaign = None
        return membership

    def rename(self, miniature, name):
        """Give one model a new name, and say so in the history.

        The name is the owner's prose, so nothing here is priced — the
        event stands alone, no entry behind it. The note keeps both
        names, which is the whole of what a reader of the history wants
        from a rename.
        """
        was = miniature.name
        if was == name:
            return miniature
        miniature.name = name
        miniature.save(update_fields=["name", "modified"])
        self.event(miniature, LedgerEvent.Kind.RENAMED, note=f"{was} → {name}"[:255])
        return miniature

    def set_status(self, miniature, status, note=""):
        """Put a model into a status — In Recovery, Captured, Dead — and
        say so in the history.

        Nothing is priced, so the event stands alone; but a death changes
        what the rating sums to, so the model is marked touched and
        ``settle`` repins it. The note keeps both statuses and, after a
        colon, what did it — the result whose effect set it, "Clean
        House", or nothing for the owner's own hand. The same status
        again is nothing to do and writes nothing.
        """
        status = Status(status)
        was = Status(miniature.status)
        if was == status:
            return miniature
        miniature.status = status
        miniature.save(update_fields=["status", "modified"])
        self.touched(miniature)
        self.event(
            miniature,
            LedgerEvent.Kind.STATUS_SET,
            note=_movement_note(f"{was} → {status}", note),
        )
        return miniature

    def transfer(self, to, credits, note="", about=None):
        """Pay another gang: credits leave this one and arrive at ``to``.

        Two events, one on each gang, each naming the other as its
        counterpart and carrying the same note. This gang's carries the
        spend as a positive delta, and its ``settle`` refuses the whole
        act if the credits would go below zero — the rules' "or the model
        dies" is then the caller's next question. The other gang's event
        is written in an operation of its own, inside this transaction,
        so its numbers are repinned too; a gang with no budget records
        the receipt and counts nothing, as it counts nothing for what it
        spends.

        ``to`` may be None for a payment to somebody the app does not
        know — a gang at the table that is not on Gyrinx. The credits
        still leave. ``about`` is the model the payment concerned, where
        it concerned one.
        """
        if credits <= 0:
            raise Refusal("A transfer has to move at least one credit.")
        if to is not None and to.pk == self.gang.pk:
            raise Refusal("A gang cannot pay itself.")
        paid = self.event(
            about,
            LedgerEvent.Kind.TRANSFERRED,
            credits_delta=credits,
            counterpart=to,
            note=note,
        )
        if to is not None:
            with operation(to, actor=self.actor) as theirs:
                theirs.event(
                    None,
                    LedgerEvent.Kind.TRANSFERRED,
                    credits_delta=-credits,
                    counterpart=self.gang,
                    note=note,
                )
        return paid

    def clean_house(self):
        """The end of the cycle: every model In Recovery is Active again.

        One event per model, all in this operation's batch, so the
        history tells them as one act. Returns the models cleared.
        """
        from n26.core.models import Miniature

        cleared = list(
            Miniature.objects.filter(
                membership__gang=self.gang,
                membership__archived=False,
                status=Status.RECOVERY,
            )
        )
        for miniature in cleared:
            self.set_status(miniature, Status.ACTIVE, note=CLEAN_HOUSE)
        return cleared

    def rename_gang(self, name):
        """Give the gang a new name, and say so in its own history.

        The same act as renaming a model, one level up: the event stands
        alone, about the gang rather than anything on it. The gang is
        this operation's own — the one it was opened on — so there is no
        second answer to which gang is being renamed.
        """
        gang = self.gang
        was = gang.name
        if was == name:
            return gang
        gang.name = name
        gang.save(update_fields=["name", "modified"])
        self.event(None, LedgerEvent.Kind.RENAMED, note=f"{was} → {name}"[:255])
        return gang

    def set_budget(self, credits):
        """Change what this operation's gang may spend, and record it.

        ``credits`` is the new budget, or ``None`` for no ceiling at all.
        Nothing is priced here and no credits move: what the gang has
        left is recomputed by ``settle`` from this figure less what the
        ledger says was spent, which is also what refuses a budget the
        spending history cannot fit. The note keeps both figures, since
        the whole of what a reader wants from a budget change is what it
        was and what it became.
        """
        gang = self.gang
        was = gang.starting_credits
        if was == credits:
            return gang
        gang.starting_credits = credits
        gang.save(update_fields=["starting_credits", "modified"])
        self.event(
            None,
            LedgerEvent.Kind.BUDGET_SET,
            note=f"{_budget_word(was)} → {_budget_word(credits)}"[:255],
        )
        return gang

    def _refuse_if_open(self, kind):
        """One of each kind at a time, and say which where there is one.

        Nothing spent while two of a kind were open could say which of
        them it counted against, so the second is refused rather than
        recorded. Decided on what stands under the gang's own line,
        which the operation took before any of this ran.
        """
        already = self.gang.open_action(kind)
        if already is not None:
            raise Refusal(
                f"Complete the open {already.get_kind_display()} action "
                "before starting another."
            )

    def open_action(self, kind, trade_points=None):
        """Start one of this gang's actions, and say so in its history.

        An action is a thing performed over several clicks — founding and
        equipping the gang, a trip to the trading post — so it is opened
        here and closed later. The event written first is what the row
        points at: the act is the record, and the row is the state that
        record leaves behind.

        ``trade_points`` is what performing this brought, where it brings
        anything. Nothing is priced and no money moves. The figure rides
        the event's note as well as the row, so the history can say what
        the gang set out with without reading a second table.
        """
        from n26.core.models import Action
        from n26.core.models.action import note_for

        gang = self.gang
        self._refuse_if_open(kind)
        opened = self.event(
            None,
            LedgerEvent.Kind.ACTION_OPENED,
            note=note_for(kind, trade_points),
        )
        action = Action.objects.create(
            gang=gang, kind=kind, opened=opened, trade_points=trade_points
        )
        gang.forget_open_actions()
        return action

    def close_action(self, action):
        """Finish an action, and say so in its history.

        What it did stays where it was written — the log between the two
        events — so closing changes nothing but the state: from here the
        gang may start another of the same kind.

        What the act still had rides the closing event's note, where it
        had anything to have: the book takes a visit's unspent Trade
        Points away when it ends, and a log that recorded only the
        ending would leave a reader no way to see what they lost.

        The row is read again here, under the gang's own line, because
        the caller's copy was read before that line was taken: two
        clicks on one button arrive together often enough, and closing
        an act twice would write it a second ending and orphan the
        first. The read is scoped to this operation's gang as well as to
        the row, so an action belonging to another gang is not closed
        here and its ending is not written into this gang's history.

        Either miss — already closed, or not this gang's — does nothing
        and returns None, so the caller can say so rather than report an
        act that did not happen.
        """
        from n26.core.models import Action
        from n26.core.models.action import note_for
        from n26.core.reconcile import trade_points_spent_for

        fresh = Action.objects.filter(
            pk=action.pk, gang=self.gang, closed__isnull=True
        ).first()
        if fresh is None:
            return None
        left = None
        if fresh.trade_points is not None:
            left = fresh.trade_points - trade_points_spent_for(fresh)
        closed = self.event(
            None,
            LedgerEvent.Kind.ACTION_CLOSED,
            note=note_for(fresh.kind, left),
        )
        fresh.closed = closed
        fresh.save(update_fields=["closed", "modified"])
        self.gang.forget_open_actions()
        return fresh

    def visit_trading_post(self, visitors=(), brought=None):
        """Open a Visit Trading Post action, performed by these fighters.

        What they add between them becomes what the gang has to spend;
        two ranks add Trade Points and the rest add none, which is
        not the same as not going — one fighter going is what opens the
        post at all.

        Nothing is priced and nothing moves. What the visit has spent is
        the purchases pointing back at its row, so the book's "unspent
        Trade Points are lost" needs nothing taken away: closing the row
        stops anything else counting against it, and a later visit is a
        different row with a figure of its own.

        Each fighter's own event says they went, in the same batch as
        the one that opened the action, so a receipt can name them and
        the gang's history can say what each model did with their
        action.

        ``brought`` overrides what they add up to. The operation takes
        what it is given, the way a purchase does: a territory that adds
        a point, or an arbitrator's own figure, is the same act with a
        different number, and neither is something this should have to
        know about.
        """
        from n26.core.models import Action
        from n26.core.trading import minted

        kind = Action.Kind.TRADING_POST_VISIT
        # Refused before the boundary is written: a second visit opened
        # over an open one would lose what the first still had, and
        # leave every purchase between them unable to say which of the
        # two it counted against.
        self._refuse_if_open(kind)
        going = [visitor for visitor in visitors if visitor.visiting]
        amount = minted(going) if brought is None else brought
        self.open_action(kind, trade_points=amount)
        for visitor in going:
            self.event(
                visitor.miniature,
                LedgerEvent.Kind.VISITED_TRADING_POST,
                note=visitor.rank[:255],
            )
        return self.gang

    def leave_trading_post(self):
        """Close the open visit. What it had left is lost, as the book says.

        The post shuts with it. In the book a gang with no visit open
        may not buy from the Trading Post at all; here that is said
        rather than enforced — a purchase with no action open records
        its Trade Points against none, once the owner has said they
        meant it. The shut state is its own state all the same, because
        "no visit" and "a visit that has spent everything" are different
        things and the screens say so differently.

        Nothing open is nothing to leave, and nothing is written. Read
        under the gang's own line, which the operation took before this
        ran, so two clicks on one button end the visit once: the second
        finds it closed rather than writing the gang a second ending.
        """
        from n26.core.models import Action

        open_now = self.gang.open_action(Action.Kind.TRADING_POST_VISIT)
        if open_now is None:
            return self.gang
        self.close_action(open_now)
        return self.gang

    def edit_notes(self, miniature, notes):
        """Store the owner's notes as written, and say they changed.

        The history records that the notes moved and never what they
        say: the words are the owner's, and the journal is a list of
        acts, not a copy of the prose.
        """
        return self._write_prose(miniature, "notes", notes, LedgerEvent.Kind.NOTED)

    def edit_lore(self, miniature, lore):
        """Store the model's story as written, and say it changed.

        As ``edit_notes``: the journal records the act and never the
        prose.
        """
        return self._write_prose(miniature, "lore", lore, LedgerEvent.Kind.LORE_EDITED)

    def set_image(self, miniature, upload, clear=False):
        """Give one model a picture, or take it away.

        ``upload`` replaces whatever was there; ``clear`` alone removes
        it. Neither given, nothing happens — the common case of saving
        the form around the picture.
        """
        return self._write_picture(miniature, upload, clear)

    def edit_gang_notes(self, notes):
        """The gang's own notes, as ``edit_notes`` keeps a model's."""
        return self._write_prose(self.gang, "notes", notes, LedgerEvent.Kind.NOTED)

    def edit_gang_lore(self, lore):
        """The gang's story, as ``edit_lore`` keeps a model's."""
        return self._write_prose(self.gang, "lore", lore, LedgerEvent.Kind.LORE_EDITED)

    def set_gang_image(self, upload, clear=False):
        """The gang's picture, handled as ``set_image`` handles a model's."""
        return self._write_picture(self.gang, upload, clear)

    def _write_prose(self, subject, field, value, kind):
        """One written field on the gang or a model, changed and said.

        An unchanged field writes nothing at all — no save, no event —
        so saving a form around an untouched box leaves no trace.
        """
        if getattr(subject, field) == value:
            return subject
        setattr(subject, field, value)
        subject.save(update_fields=[field, "modified"])
        about = subject if isinstance(subject, Miniature) else None
        self.event(about, kind)
        return subject

    def _write_picture(self, subject, upload, clear):
        """The picture on the gang or a model, replaced or removed.

        The old file is left in storage: an address someone shared
        keeps working, and files are cheap where a broken image on a
        page is not.
        """
        about = subject if isinstance(subject, Miniature) else None
        if upload:
            subject.image = upload
            subject.save(update_fields=["image", "modified"])
            self.event(about, LedgerEvent.Kind.IMAGE_SET)
        elif clear and subject.image:
            subject.image = ""
            subject.save(update_fields=["image", "modified"])
            self.event(about, LedgerEvent.Kind.IMAGE_CLEARED)
        return subject

    def set_stats(self, miniature, changes):
        """Set or clear the characteristics an owner has taken over.

        ``changes`` is what the form worked out actually moved — each a
        ``(type_stat, value, said)``, where an empty value clears the
        override so the entry's own print stands again, and ``said`` is
        the sentence the history keeps. Nothing here is priced: the
        override replaces a printed value, and what the gang is worth
        never followed from a characteristic.
        """
        from n26.core.models import StatOverride

        for type_stat, value, said in changes:
            held = StatOverride.objects.filter(
                miniature=miniature, statline_type_stat=type_stat
            )
            if not value:
                held.delete()
                self.event(miniature, LedgerEvent.Kind.STAT_CLEARED, note=said)
                continue
            override = held.first() or StatOverride(
                miniature=miniature, statline_type_stat=type_stat
            )
            override.value = value
            override.save()
            self.event(miniature, LedgerEvent.Kind.STAT_SET, note=said)
        return miniature

    def take_away(self, miniature, thing):
        """The owner removes a subtype or rule from what the model shows.

        Stored as an assignment with ``removes`` set — the carrier of
        the owner's decision, ledgered like any acquisition — and
        compiled at read time to an unconditional removal, so what it
        cancels is suppressed rather than written to. Archiving this
        assignment brings the thing back; a purchase in the thing's
        name is never hidden by it (``n26.core.effects``).
        """
        return self.assign(
            thing,
            miniature=miniature,
            paid=0,
            reason=Reason.EDITED,
            removes=True,
            kind=LedgerEvent.Kind.TOOK_AWAY,
        )

    def reset_edits(self, miniature, field):
        """Archive the owner's own edits of one kind, adds and removals
        both, so the model reads as the content says again.

        ``field`` is the assignable column the section holds —
        ``"subtype"`` or ``"rule"``. Each archive writes its own event,
        so the reset is in the history like everything else.
        """
        edits = list(
            Assignment.objects.filter(
                miniature_root=miniature,
                archived=False,
                ledger_entry__reason=Reason.EDITED,
                **{f"{field}__isnull": False},
            )
        )
        for assignment in edits:
            self.remove(assignment, note="reset")
        return edits

    def remove(self, assignment, note=""):
        """Take something away — and everything it brought with it.

        Archives rather than deletes: the ledger is append-only, so the
        record of having owned the thing survives. Its rating stops counting
        because rating sums skip archived assignments; the entry keeps
        saying what the thing was worth.

        Already gone means nothing to do: see :func:`_under_the_lock`.
        """
        assignment = _under_the_lock(assignment)
        if assignment.archived:
            return None
        for target in [assignment, *subtree(assignment)]:
            if target.archived:
                continue
            self.touched(target.miniature_root)
            target.archived = True
            target.archived_at = _now()
            target.save(update_fields=["archived", "archived_at", "modified"])
            self.event(target, LedgerEvent.Kind.REMOVED, note=note)
        return assignment

    def refund(self, assignment, note=""):
        """Take something back and return what was paid for it.

        Removal and refund are deliberately different acts: ``remove``
        archives and keeps the money spent; this archives the same subtree
        *and* gives the credits back. ``sell`` is the third of them, and
        returns half of what the thing is worth rather than what was paid.

        Each refunded line's entry is settled to zero with a matching
        event, so folding the events still reproduces the entry and the
        gang's recomputed credits rise by exactly what was returned. Lines
        nobody paid for are simply removed. Trade Points come back the
        same way, and a refund taken on the same trip as the purchase
        puts them back in the allowance; once a new allowance is set,
        neither the spending nor its undoing counts any more — the trip
        a refund belongs to is the trip the purchase belonged to, not
        whenever the owner got round to handing it back.

        Already gone means nothing comes back: see :func:`_under_the_lock`.
        """
        assignment = _under_the_lock(assignment)
        if assignment.archived:
            return None
        rows, _ = refund_of(assignment)
        for target in rows:
            self.touched(target.miniature_root)
            target.archived = True
            target.archived_at = _now()
            target.save(update_fields=["archived", "archived_at", "modified"])

            entry = getattr(target, "ledger_entry", None)
            if entry is None or entry.paid == 0:
                self.event(target, LedgerEvent.Kind.REMOVED, note=note)
                continue
            self.event(
                target,
                LedgerEvent.Kind.REFUNDED,
                credits_delta=-entry.paid,
                trade_points_delta=-entry.trade_points,
                rating_delta=-entry.rating_contribution,
                note=note,
            )
            # Settle the entry: the discount absorbs what was paid, so
            # paid = list_price - discount still holds at zero.
            entry.discount += entry.paid
            entry.paid = 0
            entry.trade_points = 0
            entry.rating_contribution = 0
            entry.save(
                update_fields=[
                    "discount",
                    "paid",
                    "trade_points",
                    "rating_contribution",
                    "modified",
                ]
            )
        return assignment

    def sell(self, assignment, note=""):
        """Sell something on, and put half of what it is worth in the bank.

        The third act beside ``remove`` and ``refund``: removal archives and
        keeps the money spent, a refund undoes the purchase and returns
        every credit of it, and a sale is a later trade — the thing goes,
        and what comes back is :func:`proceeds_for` of its **rating**, not
        of what was paid for it. Those two part company the moment anything
        is discounted, and rating is what the gang owns.

        The subtree is sold with it and counts towards the figure: a gun's
        paid ammo and its sight go with the gun, so what the gang is giving
        up is the whole of it. Every line archives, so none of them counts
        towards rating any more; each entry keeps saying what its thing was
        worth, because it was worth that.

        The credits land on the sold line's own entry, whose ``paid`` drops
        by what came back — a sale makes the gang less out of pocket for
        the thing than it was, and the discount absorbs the difference so
        that ``paid = list_price - discount`` still holds. Folding the
        events therefore still reproduces the entry, which is the invariant
        ``n26.reconcile`` exists to check.

        Returns what the gang was paid, or None for something already
        gone: see :func:`_under_the_lock`.
        """
        assignment = _under_the_lock(assignment)
        if assignment.archived:
            return None
        rows, _, proceeds = sale_of(assignment)
        for target in rows:
            self.touched(target.miniature_root)
            target.archived = True
            target.archived_at = _now()
            target.save(update_fields=["archived", "archived_at", "modified"])
            # One sale, one payment: the lines that rode along are sold
            # too, but the money is the root's — a buyer pays for the gun
            # with the sight on it, not twice.
            self.event(
                target,
                LedgerEvent.Kind.SOLD,
                credits_delta=-proceeds if target is assignment else 0,
                note=note,
            )
        entry = getattr(assignment, "ledger_entry", None)
        if entry is not None:
            entry.paid -= proceeds
            entry.discount += proceeds
            entry.save(update_fields=["discount", "paid", "modified"])
        return proceeds

    # --- composites ------------------------------------------------------

    def clone_miniature(self, source, *, name=None):
        """Copy one model's standing state into this operation's gang.

        A clone is a snapshot, not another performance of the acquisitions
        that built the source.  The low-level copier therefore writes fresh
        assignments and ledger openings without running stored effects again.
        """
        from n26.core.cloning import (
            clone_event_note,
            clone_name,
            plan_miniature_clone,
        )

        if source.membership.gang_id != self.gang.pk:
            raise ValueError("A model can only be cloned within its own gang.")
        source = (
            Miniature.objects.select_related(
                "membership__gang",
                "membership__caused_by__miniature_root__membership",
            )
            .filter(
                pk=source.pk,
                membership__gang=self.gang,
                membership__archived=False,
                membership__gang__archived=False,
            )
            .first()
        )
        if source is None:
            raise Refusal("That model can no longer be cloned.")
        plan = plan_miniature_clone(source)
        source = plan.primary
        if source is None:
            raise ValueError("A model clone plan needs a primary model.")
        if source.membership.caused_by_id is not None:
            owner = source.owned_by
            next_step = (
                f"Clone {owner.name} to include both models."
                if owner is not None and not owner.membership.archived
                else "Clone the gang to include this model."
            )
            raise Refusal(f"{source.name} cannot be cloned on its own. {next_step}")
        result = self._materialise_clone_plan(
            plan,
            primary_name=name or clone_name(source.name),
        )
        clone = result.primary
        if clone is None:
            raise ValueError("A model clone plan did not create its primary model.")
        # Assignment-level openings keep every copied ledger entry
        # reconcilable. The journal-only record's note carries presentation
        # totals so a paged history need not pull the whole snapshot merely to
        # tell this one visible act; they are not deltas and cannot be counted
        # as a second movement of money.
        self.event(
            clone,
            LedgerEvent.Kind.CLONED,
            note=clone_event_note(
                source.name,
                credits=plan.copied_spend,
                rating=plan.copied_rating,
            ),
        )
        return clone

    def _materialise_clone_plan(self, plan, *, primary_name=None):
        """Write a read-side clone plan without replaying stored effects."""
        from n26.core.models import (
            AssignmentSet,
            ChosenProfileOption,
            CounterValue,
            PrintConfig,
            StatOverride,
        )

        assignment_map = {}
        miniature_map = {}
        memberships = {model.membership_id for model in plan.miniatures}
        planned = {assignment.pk for assignment in plan.assignments}
        preserving_external_anchors = plan.source_gang.pk == self.gang.pk

        # Memberships are gang-hosted, so they can be written before the
        # models that point back at them.  That is the same two-step shape as
        # hire(), with the destination identity new at every level.
        for source in plan.assignments:
            if source.pk in memberships:
                assignment_map[source.pk] = self._clone_assignment_shell(
                    source,
                    gang=self.gang,
                )

        for source in plan.miniatures:
            membership = assignment_map.get(source.membership_id)
            if membership is None:
                raise ValueError("A cloned model needs its membership assignment.")
            name = (
                primary_name
                if plan.primary is not None and source.pk == plan.primary.pk
                else source.name
            )
            clone = Miniature.objects.create(
                name=name,
                owner=self.gang.owner,
                xp=source.xp,
                xp_target=source.xp_target,
                notes=source.notes,
                lore=source.lore,
                image=source.image.name,
                membership=membership,
            )
            miniature_map[source.pk] = clone
            membership.miniature_root = clone
            membership.save(update_fields=["miniature_root", "modified"])
            self.touched(clone)

        pending = [
            assignment
            for assignment in plan.assignments
            if assignment.pk not in assignment_map
        ]
        while pending:
            waiting = []
            made = 0
            for source in pending:
                if source.pk in plan.guards:
                    carrier = assignment_map.get(source.materialised_for_id)
                    if carrier is None:
                        waiting.append(source)
                        continue
                    if carrier.miniature_root_id is not None:
                        host = {"miniature": carrier.miniature_root}
                    elif carrier.stash_root_id is not None:
                        host = {"stash": self.gang.stash}
                    else:
                        host = {"gang": self.gang}
                elif source.parent_id is not None:
                    parent = self._clone_link(
                        source.parent,
                        assignment_map,
                        preserve_external=preserving_external_anchors,
                    )
                    if parent is None:
                        if source.parent_id in planned:
                            waiting.append(source)
                            continue
                        raise ValueError(
                            "A cloned assignment points to a parent outside its graph."
                        )
                    host = {"parent": parent}
                elif source.miniature_id is not None:
                    miniature = miniature_map.get(source.miniature_id)
                    if miniature is None:
                        raise ValueError(
                            "A cloned assignment has no cloned model host."
                        )
                    host = {"miniature": miniature}
                elif source.stash_id is not None:
                    stash = getattr(self.gang, "stash", None)
                    if stash is None:
                        raise ValueError("A cloned stash assignment needs a stash.")
                    host = {"stash": stash}
                else:
                    host = {"gang": self.gang}
                assignment_map[source.pk] = self._clone_assignment_shell(
                    source,
                    archived=source.archived or source.pk in plan.guards,
                    **host,
                )
                made += 1
            if waiting and not made:
                raise ValueError(
                    "A cloned assignment points to a host outside its graph."
                )
            pending = waiting

        for source in plan.assignments:
            clone = assignment_map[source.pk]
            is_guard = source.pk in plan.guards
            clone.caused_by = self._clone_link(
                source.caused_by,
                assignment_map,
                preserve_external=preserving_external_anchors and not is_guard,
            )
            clone.chosen_for = self._clone_link(
                source.chosen_for,
                assignment_map,
                preserve_external=preserving_external_anchors and not is_guard,
            )
            materialised_for = assignment_map.get(source.materialised_for_id)
            if materialised_for is not None:
                clone.materialised_from_id = source.materialised_from_id
                clone.materialised_for = materialised_for
            if not is_guard and source.miniature_root_id in miniature_map:
                clone.miniature_root = miniature_map[source.miniature_root_id]
            clone.save()
            self._clone_ledger(source, clone, neutral=source.pk in plan.neutral)

            role = getattr(source, "profile_role", None)
            if role is not None:
                ProfileRole.objects.create(assignment=clone, role=role.role)
            ChosenProfileOption.objects.bulk_create(
                [
                    ChosenProfileOption(
                        assignment=clone,
                        default_set=option.default_set,
                    )
                    for option in source.chosen_options.all()
                ]
            )
            counter = getattr(source, "counter_value", None)
            if counter is not None:
                CounterValue.objects.create(assignment=clone, value=counter.value)

        for source in plan.miniatures:
            clone = miniature_map[source.pk]
            StatOverride.objects.bulk_create(
                [
                    StatOverride(
                        miniature=clone,
                        statline_type_stat=override.statline_type_stat,
                        value=override.value,
                    )
                    for override in source.stat_overrides.all()
                ]
            )
            for source_set in source.assignment_sets.all():
                cloned_set = AssignmentSet.objects.create(
                    miniature=clone,
                    name=source_set.name,
                )
                cloned_set.assignments.set(
                    assignment_map[assignment.pk]
                    for assignment in source_set.assignments.all()
                    if assignment.pk in assignment_map
                )

        for source_config in plan.print_configs:
            config = PrintConfig.objects.create(
                gang=self.gang,
                name=source_config.name,
                include_header=source_config.include_header,
                include_stash=source_config.include_stash,
                include_notes=source_config.include_notes,
            )
            config.miniatures.set(
                miniature_map[miniature.pk]
                for miniature in source_config.miniatures.all()
                if miniature.pk in miniature_map
            )
            config.assignments.set(
                assignment_map[assignment.pk]
                for assignment in source_config.assignments.all()
                if assignment.pk in assignment_map
            )

        return _CloneResult(
            primary=miniature_map.get(getattr(plan.primary, "pk", None)),
            assignments=assignment_map,
            miniatures=miniature_map,
        )

    def _clone_link(self, source, assignment_map, *, preserve_external):
        """Map a graph link, retaining a live gang-wide anchor in place."""
        if source is None:
            return None
        if mapped := assignment_map.get(source.pk):
            return mapped
        if (
            preserve_external
            and source.gang_root_id == self.gang.pk
            and source.miniature_root_id is None
            and source.stash_root_id is None
            and not source.archived
        ):
            return source
        return None

    def _clone_assignment_shell(self, source, *, archived=None, **host):
        """Write identity, assignable and host; graph links follow later."""
        from n26.core.models.assignment import ASSIGNABLE_FIELDS

        is_archived = source.archived if archived is None else archived
        assignable = {
            f"{field}_id": getattr(source, f"{field}_id")
            for field in ASSIGNABLE_FIELDS
            if getattr(source, f"{field}_id") is not None
        }
        return Assignment.objects.create(
            **assignable,
            **host,
            chosen_for_slot_id=source.chosen_for_slot_id,
            chosen_for_offer_id=source.chosen_for_offer_id,
            removes=source.removes,
            archived=is_archived,
            archived_at=_now() if is_archived else None,
        )

    def _clone_ledger(self, source, clone, *, neutral=False):
        """Give a cloned assignment one fresh opening that reconciles."""
        entry = getattr(source, "ledger_entry", None)
        values = (
            {
                "list_price": 0 if neutral else entry.list_price,
                "discount": 0 if neutral else entry.discount,
                "paid": 0 if neutral else entry.paid,
                # A clone buys a standing snapshot for the same credits. Trade
                # Points belonged to the source's visit, not this acquisition.
                "trade_points": 0,
                "rating_contribution": 0 if neutral else entry.rating_contribution,
                "reason": entry.reason,
                "bought_from_id": entry.bought_from_id,
                "note": entry.note,
            }
            if entry is not None
            else {
                "list_price": 0,
                "discount": 0,
                "paid": 0,
                "trade_points": 0,
                "rating_contribution": 0,
                "reason": Reason.FREE,
                "bought_from_id": None,
                "note": "",
            }
        )
        LedgerEntry.objects.create(assignment=clone, **values)
        self.event(
            clone,
            LedgerEvent.Kind.CLONED,
            credits_delta=values["paid"],
            trade_points_delta=values["trade_points"],
            rating_delta=values["rating_contribution"],
        )

    def hire(self, profile, model_name, paid=None, owner=None, option=None, **kwargs):
        """Hire a model: a gang-hosted assignment naming a profile.

        That assignment is the membership — hosted on the gang, pointing
        at the profile, carrying what was paid — and the model points back
        at it. Its ``miniature_root`` says whose membership it is, so the
        profile sets that model's base rating even though the gang is the
        host.

        ``option`` names what was chosen — one set, or a list of sets when
        the profile offers several groups. Omitted, each one-of group's
        default applies and the any-of groups add nothing. The built-ins
        and every chosen set materialise as free assignments hosted on the
        new model and caused by the membership, and the sets' prices fold
        into the membership's line — the items themselves are free, the
        package carries the money.
        """
        taken = (
            profile.resolve_selection(option)
            if hasattr(profile, "resolve_selection")
            else []
        )
        if paid is None:
            paid = (
                # ``taken`` resolves to itself, so pricing never re-reads
                # the groups differently from what materialises below.
                profile.price_with(taken)
                if hasattr(profile, "price_with")
                else profile.price
            )
        membership = self.assign(profile, gang=self.gang, paid=paid, **kwargs)
        miniature = Miniature.objects.create(
            name=model_name, owner=owner or self.gang.owner, membership=membership
        )
        # The hire is hosted on the gang but is about this model, so it counts
        # towards the model's rating.
        membership.miniature_root = miniature
        membership.save(update_fields=["miniature_root", "modified"])
        ProfileRole.objects.create(assignment=membership, role=ProfileRole.Role.PRIMARY)
        self.touched(miniature)
        self._record_options(membership, taken)
        self.reconcile_defaults(membership)
        return miniature

    def found(self, gang_type, taken=(), **kwargs):
        """Give the gang its type: the founding assignment and its built-ins.

        What ``hire`` is to a model, one level up. The assignment is free
        — founding *grants* a budget where hiring *spends* one, and the
        budget bounds the ledger rather than appearing in it — but it is
        an assignment all the same, so the gang's equipment list arrives
        caused by it and its gang-wide modifiers have a carrier that
        every member's card can find.
        """
        from n26.core.models import Action, Stash

        founding = self.assign(gang_type, gang=self.gang, paid=0, **kwargs)
        self.gang.founding = founding
        self.gang.save(update_fields=["founding", "modified"])
        Stash.objects.get_or_create(gang=self.gang)
        # Founding and equipping the gang is an act the owner performs over
        # many clicks, so it opens here and the owner closes it when they
        # are done. A gang founded again — its type corrected where the
        # founding assignment had gone — keeps the action it already has.
        if self.gang.open_action(Action.Kind.FOUNDING) is None:
            self.open_action(Action.Kind.FOUNDING)
        self._record_options(founding, taken)
        self.reconcile_defaults(founding, gang=self.gang)
        return founding

    def refound(self, gang_type):
        """Say the gang is a different type, keeping the act that founded it.

        Founding is something the owner did, and the founding assignment
        carries the ledger entry and the history event that say so.
        Repointing that assignment keeps both: the gang's history still
        opens with its own creation, on its own date and in its owner's
        name, and now names the type the gang really is. Founding again
        instead would delete that act — the entry and the event cascade
        with the assignment — and write a new one in whatever name did
        the founding.

        The new type's built-ins arrive caused by that same founding. A
        gang with no founding at all is simply founded.

        Refused where the founding already granted something. Taking the
        old type's kit away means unwinding purchases that hang off it
        and saying in the ledger that they went, which is a refund's job
        — deleting the rows here would take their entries and events
        with them and say nothing, and the ledger is written to once and
        never altered.
        """
        from n26.core.models import Stash

        # Refused before anything is written, in memory as much as in the
        # database: a caller that catches this and carries on would
        # otherwise hold a gang saying it is something the database says
        # it is not.
        founding = self.gang.founding
        if founding is not None and (
            founding.caused.exists() or founding.chosen_options.exists()
        ):
            raise Refusal(
                f"You cannot change {self.gang}'s type. Its founding type gave "
                "it things, and those would have to be given back first."
            )
        # The gang says what it is as well as its founding, and the two
        # disagreeing is a gang whose pages and whose history describe
        # different types.
        self.gang.gang_type = gang_type
        self.gang.save(update_fields=["gang_type", "modified"])
        if founding is None:
            return self.found(gang_type)
        founding.gang_type = gang_type
        founding.save()
        Stash.objects.get_or_create(gang=self.gang)
        self.reconcile_defaults(founding, gang=self.gang)
        return founding

    def rechoose(self, carrier, option=None, note=""):
        """Change which of its options an assignment's thing is taken with.

        The later edit ``ChosenProfileOption`` is stored for: a hire took
        a set at purchase, and the owner changes their mind. The new
        selection resolves exactly as the hire's did — one-of groups fall
        back to their heads, a set the thing does not offer is refused —
        so what this prices is what materialises. Naming the selection
        already held is a no-op.

        The sets no longer taken leave the way a refund leaves: their
        materialised assignments archive, anything *paid* inside their
        subtrees comes back, and anything they caused — a spawned model —
        goes with them. The sets newly taken materialise exactly as at
        hire: free assignments caused by the carrier, the built-ins
        untouched.

        The price difference lands on the carrier's own entry as one
        amendment, on paid and list and rating alike — an option is a way
        the thing itself is built, so purchase's surcharge rule holds in
        both directions — and the discount stands: what was agreed at the
        table never moves. ``settle`` refuses an upgrade the gang cannot
        afford, unwinding the whole change.
        """
        thing = carrier.assignable
        taken = (
            thing.resolve_selection(option)
            if hasattr(thing, "resolve_selection")
            else []
        )
        recorded = list(carrier.chosen_options.select_related("default_set"))
        before = [row.default_set for row in recorded]
        after_pks = {chosen.pk for chosen in taken}
        before_pks = {chosen.pk for chosen in before}
        if after_pks == before_pks:
            return carrier

        for row in recorded:
            if row.default_set.pk in after_pks:
                continue
            for granted in self._granted_rows(carrier, row.default_set):
                self.refund(
                    granted, note=note or f"No longer takes {row.default_set.name}"
                )
            row.delete()
        arriving = [chosen for chosen in taken if chosen.pk not in before_pks]
        # The founding is gang-hosted and about no model; a membership is
        # gang-hosted too but about its model, which is where its grants
        # belong — the same split the hire makes.
        gang = (
            carrier.gang
            if carrier.miniature_root_id is None and carrier.gang_id is not None
            else None
        )
        self._record_options(carrier, arriving)
        # The arriving sets are fresh: their copies from an earlier
        # taking were archived by that set leaving, and re-taking the
        # set must bring its kit again.
        self.reconcile_defaults(carrier, gang=gang, built_ins=False, fresh=arriving)

        delta = sum(chosen.price for chosen in taken) - sum(
            chosen.price for chosen in before
        )
        if delta:
            entry = getattr(carrier, "ledger_entry", None)
            if entry is not None:
                entry.paid += delta
                entry.list_price += delta
                entry.rating_contribution += delta
                entry.save(
                    update_fields=[
                        "paid",
                        "list_price",
                        "rating_contribution",
                        "modified",
                    ]
                )
            self.event(
                carrier,
                LedgerEvent.Kind.AMENDED,
                credits_delta=delta,
                rating_delta=delta,
                note=note,
            )
        self.touched(carrier.miniature_root)
        return carrier

    def _granted_rows(self, carrier, default_set):
        """The live assignments one chosen set materialised, one per member.

        Provenance answers directly: each materialised copy names the
        member it came from and the carrier it came for, so the set's
        grants are the copies whose member belongs to it — archived
        members included, because a copy an author's removal left
        standing still leaves when its set is no longer taken.

        Ammo is the one kind provenance does not cover, and its copies
        are found by the shape they were written in, below.
        """
        from n26.core.builtins import copies_of_set

        tagged = list(copies_of_set(default_set, carrier))
        rows = [copy for copy in tagged if not copy.archived]
        rows.extend(self._ammo_rows_without_provenance(carrier, default_set, tagged))
        return rows

    def _ammo_rows_without_provenance(self, carrier, default_set, tagged):
        """The set's ammo grants among lines with no provenance recorded.

        A granted firing line is written in the same shape as a weapon's
        own free lines, so it is the one kind of grant never tagged with
        provenance and the one kind still read by shape: the newest live
        line on the host, caused by a gun, as many as the set granted and
        provenance has not already accounted for. Every other kind
        answers by provenance alone — an untagged copy of anything else
        is the owner's own business and is never seized.

        Every tagged copy counts against the wanted number, archived
        included: a grant the owner parted with is settled, not something
        to seize a look-alike for. And only live members count: an
        archived member may never have materialised for this carrier.
        """
        from n26.core.models import Reason
        from n26.library.models import WeaponProfile

        wanted = {}
        for member in default_set.members.filter(archived=False):
            assignable = member.assignable
            if isinstance(assignable, WeaponProfile):
                wanted[assignable] = wanted.get(assignable, 0) + 1
        for copy in tagged:
            if copy.assignable in wanted:
                wanted[copy.assignable] -= 1

        rows = []
        for assignable, count in wanted.items():
            if count <= 0:
                continue
            matches = Assignment.objects.filter(
                weapon_profile=assignable,
                archived=False,
                materialised_from__isnull=True,
                ledger_entry__reason=Reason.DEFAULT,
                gang_root=carrier.gang_root,
                miniature_root=carrier.miniature_root,
                # Granted ammo is caused by its gun, not by the carrier.
                caused_by__isnull=False,
            )
            rows.extend(matches.order_by("-pk")[:count])
        return rows

    def _record_options(self, carrier, taken):
        """Record the sets taken with an acquisition, on the carrier.

        Written before reconciling, because the plan reads what is
        recorded — recording a set is what makes its members owed.
        """
        from n26.core.models import ChosenProfileOption

        for chosen in taken:
            ChosenProfileOption.objects.get_or_create(
                assignment=carrier, default_set=chosen
            )

    def reconcile_defaults(
        self,
        carrier,
        kinds=None,
        gang=None,
        built_ins=True,
        strict=True,
        fresh=(),
        event_kind=None,
        omit=(),
        _chain=(),
    ):
        """Create what the carrier's sets say is missing, and nothing else.

        ``carrier`` is the assignment that brought the thing in — a
        model's membership, a bought mount's own assignment, a gang's
        founding. Its sets are its thing's built-ins and the option sets
        recorded as taken (``_record_options``); a member is satisfied
        when a copy naming it and this carrier exists, archived included
        — the owner parted with the thing, and it is never re-granted
        behind their back. Run twice, the second pass creates nothing,
        which is what lets a set change reach carriers acquired long ago.

        Everything created is **caused by** the carrier and hosted
        alongside it, so removing the carrier removes all of it, and a
        card draws the grants as ordinary lines with the carrier as
        their source. Pass ``gang`` for a gang-hosted carrier, which has
        no model to hang things on. A satisfied member is skipped before
        ``assign`` runs at all: stored effects fire inside it, and a
        false "missing" would breed a second pet.

        Nothing is ever replaced: the option not taken is simply never
        created. A thing that may be swapped for something else is an
        *option*, not a built-in.

        A weapon-profile member is an extra ammo type: it stacks on its
        weapon's assignment — the same shape ``buy_weapon_profile``
        writes — and that weapon may arrive from any of these sets, so
        ammo is placed after every weapon has been. An anchored member
        names its gun member (``gun_member``), and the line lands on
        that member's own live copy for this carrier; an unanchored one
        rides whatever live matching weapon the host holds, newest
        first — how an option set arms a gun the built-ins bring. Ammo
        with no gun to land on is a content bug at acquisition
        (``strict``) and a recorded skip on a later reconcile — a
        carrier must not be unrepairable because one member is.

        A slot member brings the choice open. Where the member also
        names a starting pick, the pick is written in the same breath,
        settling the slot exactly as a click would — changing it later
        is the ordinary rechoose. An already-settled slot is a satisfied
        member: its pick stands untouched.

        ``kinds`` narrows what materialises (derived from the carrier's
        role when not given — a Legacy profile brings its lists but not
        a second set of free kit). ``fresh`` names sets being taken
        right now, judged by live copies alone: archived copies guard
        against unattended re-grants, and taking a set is an acquisition
        (``plan_defaults``). A bare reconcile passes neither.

        ``event_kind`` is the history's word for each grant. Left None,
        a grant reads as any caused assignment does; the propagation
        pass says its grants arrived by catch-up, so a reader asking
        why a thing appeared long after the hire gets the answer.

        ``omit`` names members, by primary key, the caller has judged
        the carrier already holds another way. Each is treated as
        satisfied and recorded among the skips with that reason, so
        nothing is created for it and the outcome still says so.

        A copy created here is itself an arrival, and a thing with
        built-ins of its own brings them wherever it arrives — a subtype
        granted by a profile brings the counters built into the subtype.
        Each copy created here is reconciled as a carrier in turn, under
        the same narrowing, its grants caused by the copy — so the
        outcome returned covers every level, and a grant's ``caused_by``
        is its own carrier, not always the one passed in. That is the
        provenance the propagation pass writes when it visits the copy
        later, so the two agree. The nesting is the library's own, and a
        library that nests a thing inside itself is a content bug: at
        acquisition (``strict``) the chain is refused in words rather
        than followed off the end of the stack, and on a later reconcile
        it is a recorded skip.
        """
        from n26.core.builtins import (
            ReconcileOutcome,
            copies_of,
            kinds_for,
            plan_defaults,
        )
        from n26.core.models import CounterValue, Reason
        from n26.library.models import Weapon, WeaponProfile

        narrowed = kinds if kinds is not None else kinds_for(carrier)
        omitted = set(omit)
        plan = plan_defaults(
            carrier, kinds=narrowed, built_ins=built_ins, fresh=fresh, omit=omitted
        )

        miniature = None if gang is not None else carrier.miniature_root
        if gang is not None:
            host = {"gang": gang}
        elif miniature is not None:
            host = {"miniature": miniature}
        else:
            # A stash purchase's option set lands in the stash beside it —
            # the Trazior's chosen deployment option rides the stash,
            # and whatever it *spawns* (``OpAddsMiniature``) is a gang
            # member like any other.
            host = {"stash": carrier.stash_root}

        created = []
        skipped = []
        ammo = [
            entry
            for entry in plan.entries
            if isinstance(entry.member.assignable, WeaponProfile)
            and entry.member.pk not in omitted
        ]
        for entry in plan.entries:
            member = entry.member
            assignable = member.assignable
            if member.pk in omitted:
                skipped.append((entry, f"{assignable} is already held another way."))
                continue
            if isinstance(assignable, WeaponProfile):
                continue
            if entry.satisfied:
                continue
            assignment = self.assign(
                assignable,
                caused_by=carrier,
                materialised_from=member,
                materialised_for=carrier,
                paid=0,
                reason=Reason.DEFAULT,
                kind=event_kind,
                **host,
            )
            created.append(assignment)
            if isinstance(assignable, Weapon):
                self._grant_free_profiles(assignable, assignment)
            elif member.default_pickable_id is not None:
                # A slot arriving already settled. The pick goes
                # where the slot says, which need not be where the
                # slot itself landed.
                self._choose_for_slot(assignment, assignable, member.default_pickable)
            elif member.counter_id is not None:
                # A counter opens at its member's amount — Starting XP.
                CounterValue.objects.create(assignment=assignment, value=member.amount)

        for entry in ammo:
            if entry.satisfied:
                continue
            member = entry.member
            weapon_profile = member.assignable
            if member.gun_member_id is not None:
                # The member names its gun, so the line lands on that
                # member's own live copy for this carrier — the receipt,
                # not a guess by type.
                gun = (
                    copies_of(member.gun_member, carrier, include_archived=False)
                    .order_by("-pk")
                    .first()
                )
            else:
                # An unnamed gun means whatever matching weapon the host
                # holds — a set chosen after the hire arms a gun the
                # built-ins brought, or one the owner gave by hand.
                gun = (
                    Assignment.objects.filter(
                        weapon=weapon_profile.weapon,
                        archived=False,
                        gang_root=carrier.gang_root,
                        miniature_root=carrier.miniature_root,
                    )
                    .order_by("-pk")
                    .first()
                )
            if gun is None:
                if strict:
                    # A content bug, not a player mistake: the set names
                    # ammo for a weapon nothing here brings.
                    raise LibraryError(
                        f"{carrier.assignable} grants {weapon_profile}, but "
                        f"nothing it brings is its weapon "
                        f"({weapon_profile.weapon})."
                    )
                why = (
                    f"{weapon_profile} rides a {weapon_profile.weapon} "
                    f"whose copy for this carrier is no longer standing."
                    if member.gun_member_id is not None
                    else f"{weapon_profile} is ammo for "
                    f"{weapon_profile.weapon}, and nothing this "
                    f"carrier's host holds is that weapon."
                )
                skipped.append((entry, why))
                continue
            # Caused by the weapon, like its free profiles: the card says
            # "from the grenade launcher array", not "from the profile".
            # Provenance names the member and the carrier all the same —
            # it records which set membership this satisfies, and the gun
            # is only where the copy landed.
            created.append(
                self.assign(
                    weapon_profile,
                    parent=gun,
                    caused_by=gun,
                    materialised_from=member,
                    materialised_for=carrier,
                    paid=0,
                    reason=Reason.DEFAULT,
                    kind=event_kind,
                )
            )
        # After ammo, so a copy of any kind created in this pass is an
        # arrival in its own right, ammo included.
        chain = (*_chain, carrier.assignable)
        entry_for = {entry.member.pk: entry for entry in plan.entries}
        for assignment in list(created):
            thing = assignment.assignable
            if thing.built_ins_id is None:
                continue
            if thing in chain:
                why = (
                    "Built-ins nest in a circle: "
                    + " → ".join(str(link) for link in (*chain, thing))
                    + "."
                )
                if strict:
                    raise LibraryError(why)
                skipped.append((entry_for[assignment.materialised_from_id], why))
                continue
            nested = self.reconcile_defaults(
                assignment,
                kinds=narrowed,
                gang=gang,
                strict=strict,
                event_kind=event_kind,
                _chain=chain,
            )
            created.extend(nested.created)
            skipped.extend(nested.skipped)

        return ReconcileOutcome(
            carrier=carrier, plan=plan, created=created, skipped=skipped
        )

    def choose(self, anchor, chosen, slot=None, offer=None, **kwargs):
        """Make a choice — pick a specialism, pick a gang legacy.

        ``anchor`` is the assignment that asked: the one whose assignable
        carries a modifier offering the choice (the Specialist subtype's),
        the line a chain of grants stands on where the offerer was itself
        granted, or a **slot's** own assignment. What was chosen is a free
        assignment caused by it, so removing what asked takes the answer
        along, and it points back through ``chosen_for`` so the card reads
        the choice as settled.

        ``slot`` and ``offer`` name which choice is being settled where
        the anchor cannot say. What a modifier *gave* has no assignment of
        its own, so the anchor is the written line it stands on — which
        may carry no offer itself, and may carry several — and the one
        being answered is named here.

        Something of a kind the choice does not name is refused
        (:class:`NotOnOffer`), because it would settle nothing: the row
        resolves by the same match, so the choice would stay open with
        a stray assignment beside it. Within the kind nothing is checked — a
        narrowed offer shortens the list a picker draws and is not a rule,
        so an owner may still hand over something off-list.
        """
        from n26.core import select
        from n26.library.models import Slot
        from n26.library.models.modifier import OffersChoice

        if offer is None:
            # A slot's own assignment says which choice it is without being
            # told; a named offer has already said.
            if slot is None and isinstance(anchor.assignable, Slot):
                slot = anchor.assignable
            if slot is not None:
                return self._choose_for_slot(anchor, slot, chosen, **kwargs)
        if kwargs.get("roll") is not None:
            # Only a slot's table is rolled on; an offer has no dice, so a
            # roll handed to one is a caller's mistake, not a refusal.
            raise ValueError("Only a choice backed by a slot is rolled for.")

        asked = (
            [offer]
            if offer is not None
            else [
                modifier.effect
                for modifier in anchor.assignable.modifiers.all()
                if isinstance(modifier.effect, OffersChoice)
            ]
        )
        matched = [
            effect
            for effect in asked
            if effect.selector().matches(select.matchable(chosen))
        ]
        if not matched:
            raise NotOnOffer(anchor, chosen)
        # What was chosen lands on the host the offer names: the bearer
        # of the question by default — a fighter's choice on the fighter, a
        # gang's (a Venator's ranked trees) on the gang — or the gang,
        # when the offer says so (the Outcast Leader picks the
        # legacy; the gang carries it, and it dies with the Leader
        # through the caused_by cascade). An explicit host wins over all
        # of it — a *gang-carried* offer scoped to fighters ("Leaders
        # and Champions each select a skill") puts a slot on every
        # matching card, and the caller says whose is being settled:
        # ``choose(founding, skill, miniature=leader)``.
        if not any(key in kwargs for key in ("miniature", "gang", "stash", "parent")):
            if any(
                offer.will_be_assigned_to == OffersChoice.WillBeAssignedTo.GANG
                for offer in matched
            ):
                kwargs |= {"gang": anchor.gang or anchor.gang_root}
            else:
                # The same ladder _choose_for_slot climbs: a bearer where
                # there is one, the stash for a stashed carrier, the gang
                # last — never four empty hosts, whatever holds the anchor.
                bearer = anchor.miniature or anchor.member_or_none()
                if bearer:
                    kwargs |= {"miniature": bearer}
                elif anchor.stash_id or anchor.stash_root_id:
                    kwargs |= {"stash": anchor.stash or anchor.stash_root}
                else:
                    kwargs |= {"gang": anchor.gang or anchor.gang_root}
        return self.assign(
            chosen,
            caused_by=anchor,
            # Which question this answers. One line may ask twice over one
            # kind, and nothing about the answer tells the two apart, so a
            # caller that knows says — and where the line asks once there
            # is only one question it can be.
            chosen_for_offer=offer or (matched[0] if len(matched) == 1 else None),
            paid=0,
            reason=Reason.GRANTED,
            **kwargs,
        )

    def _choose_for_slot(self, anchor, slot, chosen, roll=None, **kwargs):
        """Settle one slot: write the pick, pointing back at what asked.

        The pick names both the assignment that asked and the slot it
        settles. One assignment may ask twice — a thing giving two choices
        of one slot type — and the pair says which of them this answers.

        The one check is the slot type — a Gang Legacy choice is settled
        by a Gang Legacy pickable and by nothing else, because the row
        reads as settled by the same match and anything else would leave
        the choice open with a stray assignment beside it. Which
        pickables the picklist offers is not checked: a shorter list
        informs, and an owner may still hand over something off it.

        Where the pick lands is the slot's own business — the bearer, or
        the gang where the slot says so (the Leader is asked and the gang
        holds the answer). An explicit host wins over both, which is how
        a slot the gang holds is settled for one particular fighter.

        A choice that arrived in the stash has no bearer to land on, and
        its pick belongs with the item rather than with the gang: a
        thing bought unassigned takes what was chosen for it along when
        somebody finally carries it.

        ``roll`` is the event :meth:`roll` wrote, where the table was
        rolled for this pick. It has to be a roll for this very choice
        and one nothing has been picked for yet — a roll is applied
        once, and the second click is refused in words rather than
        writing a second pick. Which row the roll landed on is not
        checked: the rules substitute results ("counts as Out Cold"),
        and the record shows the roll beside whatever was picked.
        """
        from n26.library.models import Pickable, Slot

        if roll is not None:
            if roll.kind != LedgerEvent.Kind.ROLLED or roll.slot_id != slot.pk:
                raise Refusal(
                    f"That roll was not made for {slot.choice_label}. "
                    "Roll again for this choice."
                )
            # One standing pick per roll. A pick taken back frees its
            # roll, and the check runs under the gang's lock, so two
            # clicks for one gang are read one after the other.
            if Assignment.objects.filter(roll=roll, archived=False).exists():
                raise Refusal(
                    f"That roll of {roll.roll} has already been applied. "
                    "Roll again for another result."
                )
            kwargs |= {"roll": roll}
        if not isinstance(chosen, Pickable) or chosen.slot_type_id != slot.slot_type_id:
            raise NotOnOffer(
                anchor,
                chosen,
                message=(
                    f"{chosen} cannot be a pick for {slot.choice_label} — "
                    f"that choice takes {slot.slot_type} pickables."
                ),
            )
        if not any(key in kwargs for key in ("miniature", "gang", "stash", "parent")):
            if slot.assigned_to == Slot.WillBeAssignedTo.GANG:
                kwargs |= {"gang": anchor.gang or anchor.gang_root}
            else:
                bearer = anchor.miniature or anchor.member_or_none()
                stash = anchor.stash or anchor.stash_root
                if bearer is not None:
                    kwargs |= {"miniature": bearer}
                elif stash is not None:
                    kwargs |= {"stash": stash}
                else:
                    kwargs |= {"gang": anchor.gang or anchor.gang_root}
        if roll is not None:
            # A roll belongs to the card it was made on: this gang's, and
            # the model the pick lands on (or no model, for the gang's
            # own choice). Checked here as well as by the page, so no
            # caller can hand one fighter's roll to another's pick.
            gang = anchor.gang or anchor.gang_root
            host = kwargs.get("miniature")
            if roll.gang_id != gang.pk or roll.miniature_id != (
                host.pk if host is not None else None
            ):
                raise Refusal(
                    "That roll was made for a different card. "
                    "Roll again for this choice."
                )
        return self.assign(
            chosen,
            caused_by=anchor,
            chosen_for=anchor,
            chosen_for_slot=slot,
            paid=0,
            reason=Reason.GRANTED,
            **kwargs,
        )

    def add_legacy_profile(self, miniature, profile, **kwargs):
        """A second profile on a model — the Venator case.

        A Legacy is an *association*, not a second hire: it brings the
        other profile's **equipment lists** — a Venator uses their
        Legacy's list — and nothing else. No free weapons, no subtypes,
        no second helping of default kit.
        """
        assignment = self.assign(profile, miniature=miniature, **kwargs)
        ProfileRole.objects.create(assignment=assignment, role=ProfileRole.Role.LEGACY)
        # The Legacy role narrows what reconciling grants to the lists
        # alone (``n26.core.builtins.kinds_for``), so it is written first.
        self.reconcile_defaults(assignment)
        return assignment

    def give_weapon(self, miniature, weapon, paid=0, free_profiles=True, **kwargs):
        """Assign a weapon to a model, copying its free profiles onto it."""
        assignment = self.assign(weapon, miniature=miniature, paid=paid, **kwargs)
        if free_profiles:
            self._grant_free_profiles(weapon, assignment)
        return assignment

    def _grant_free_profiles(self, weapon, assignment, sold_separately=frozenset()):
        """A weapon's free profiles ride along with it, however it arrived.

        Bought or granted as default equipment, a weapon is the same weapon:
        without this its card line would have no statline and no traits.

        ``sold_separately`` names the profiles the listing behind this
        purchase prices as rows of their own. Those are not the weapon —
        they are the next thing the buyer may pay for — so granting them
        here would hand over free what the listing charges 55 credits
        for, and leave a second copy when the buyer pays anyway.
        """
        for profile in weapon.profiles.filter(price=0):
            if profile.pk in sold_separately:
                continue
            self.assign(
                profile,
                parent=assignment,
                caused_by=assignment,
                paid=0,
                reason=Reason.DEFAULT,
            )

    def buy(
        self,
        holder,
        line=None,
        *,
        thing=None,
        entry=None,
        paid=None,
        trade_points=None,
        action=None,
        option=None,
        **kwargs,
    ):
        """Buy something for a model — a browsed line, or freely.

        ``line`` is what browsing produced, and it *is* the purchase: the
        thing, the effective price in credits, the Trade Points where this
        surface charges them, and the entry that priced it (None on a
        derived collection — that is fine, the ledger just has no entry to
        point at). Nothing is checked; the line pre-fills what the ledger
        remembers, and any of it may be overridden at purchase.

        ``option`` names what was chosen where the thing offers a choice —
        a mount swapping its weapon. Its built-ins and the sets taken
        materialise on the model, caused by the purchase, so selling the
        thing takes them with it. Pricing composes the same way a hire's
        does: the item's own price (or the list's override of it), plus
        its built-ins, plus every set taken.

        The get-out is unchanged: pass ``thing`` with no line and any
        price you like — off-list, hand-set, the owner's call.

        ``action`` is the open action this counts against, decided by the
        surface: a trip to the trading post, founding and equipping the
        gang. None where none is open, which is a purchase that counts
        against nothing — allowed, once the owner has said they meant it.
        The buyer is recorded alongside it, because an allowance may be
        one model's own and what it has spent must follow the model that
        spent it rather than wherever the thing ends up.

        ``holder`` is a model, the gang's stash, or an assignment the
        purchase hangs off. Buying into the stash is the same purchase
        with a different destination, and a stashed weapon keeps its free
        profiles so it moves onto a model whole. Buying onto an
        assignment is how a weapon's paid ammo is bought: a profile
        belongs to one particular gun, not to the fighter carrying it.
        """
        from n26.core.models import Assignment, Stash
        from n26.library.models import Weapon
        from n26.library.models.collection import price_of

        if isinstance(holder, Stash):
            # Nobody's allowance buys into the stash: it is the gang's
            # spare kit, and what it holds was never given to a model.
            host, buyer = {"stash": holder}, None
        elif isinstance(holder, Assignment):
            # A weapon's paid rounds hang off the gun, and it is the
            # model carrying the gun whose points they came out of.
            host, buyer = {"parent": holder}, holder.miniature_root
        else:
            host, buyer = {"miniature": holder}, holder

        if line is not None:
            thing = line.thing
            entry = line.entry if entry is None else entry
            if trade_points is None and line.charges_trade_points:
                trade_points = line.trade_points
        elif entry is not None and thing is None:
            thing = entry.assignable
        if thing is None:
            raise ValueError("Buying needs a browsed line or a thing.")

        taken = (
            thing.resolve_selection(option)
            if hasattr(thing, "resolve_selection")
            else []
        )
        if paid is None:
            if hasattr(thing, "price_with"):
                # An entry overrides the item's own price; what it comes
                # with keeps its own.
                override = entry.price_override if entry is not None else None
                paid = thing.price_with(taken, base=override)
            elif line is not None:
                paid = line.credits
            else:
                paid = price_of(thing, entry).credits
        if trade_points is None:
            trade_points = 0

        bought = self.assign(
            thing,
            paid=paid,
            trade_points=trade_points,
            bought_from=entry,
            action=action,
            # Recorded only where something counted it: with no action
            # open the purchase counts against nothing, and naming a
            # buyer would claim an allowance nobody spent.
            spent_by=buyer if action is not None else None,
            **host,
            **kwargs,
        )
        if isinstance(thing, Weapon):
            self._grant_free_profiles(
                thing, bought, sold_separately=_sold_separately(line, entry, thing)
            )
        if hasattr(thing, "resolve_selection"):
            self._record_options(bought, taken)
            self.reconcile_defaults(bought)
        return bought

    def select(self, miniature, thing, note=""):
        """Take on something a model *is* — a skill, a power.

        Free, and recorded as a reward. No credits move: what a fighter
        selects is earned rather than bought, and a purchase is not the
        way to it. What it adds to the gang's rating is the thing's own
        reference price, which is nothing for a skill the rules hand
        out and whatever content says for one that is worth something.

        Nothing causes it. A skill is not a consequence of the assignment whose
        grid placed the set it came from, so swapping a profile — or
        dropping the wargear that opened a set up — never takes one back.
        That is the difference between this and ``choose``,
        where what was chosen belongs to the offer and dies with it.
        """
        from n26.library.models.collection import price_of

        return self.assign(
            thing,
            miniature=miniature,
            paid=0,
            rating=price_of(thing).credits,
            reason=Reason.REWARD,
            note=note,
        )

    def roll(self, slot, *, miniature=None, rolled=None, rng=None, note=""):
        """Roll on a choice's table and put the roll on the record.

        The roll is written the moment it is made, before anything is
        picked for it and whether or not anything ever is: once the dice
        are down the result stands, and a roll that was made and then
        rolled again should read that way. The event is about the model
        whose card the choice was on, or the gang for the gang's own
        choices, and names the slot so the pick that follows can be
        checked against it.

        ``rolled`` is a roll made at the table and entered here rather
        than generated; it goes on the record the same way, with the
        note saying so, and has to be a roll the die can make. ``rng``
        is for a test that wants the dice loaded.

        A slot whose list is not a roll table has nothing to roll; no
        page draws a control for one, so that is a caller's mistake
        rather than a refusal.
        """
        from n26.library.models import Dice

        picklist = slot.picklist
        if not picklist.dice:
            raise ValueError(f"{slot.choice_label} is not rolled for.")
        dice = Dice(picklist.dice)
        if rolled is None:
            rolled = Dice.roll(dice, rng)
        elif rolled not in Dice.rolls(dice):
            raise Refusal(f"You cannot roll {rolled} on a {dice.label}.")
        else:
            note = note or ROLL_ENTERED
        return self.event(
            miniature,
            LedgerEvent.Kind.ROLLED,
            roll=rolled,
            dice=dice.value,
            slot=slot,
            note=note,
        )

    def tally(self, assignment, change, note=""):
        """Change a counter's value — the only writer it has.

        ``change`` is signed; the value floors at zero. Every change is a
        ledger event, so the history of a Kill Count reads like the
        history of anything else the gang owns — and carries what moved
        and where it landed, which is what a reader auditing a number is
        looking for. ``note`` is why, where the caller knows.
        """
        from n26.core.models import CounterValue, LedgerEvent

        held, _ = CounterValue.objects.get_or_create(assignment=assignment)
        before = held.value
        held.value = max(0, held.value + change)
        held.save(update_fields=["value", "modified"])
        # What moved and where it landed, so the history can be read
        # against the number on the card. The movement recorded is the
        # one that happened rather than the one asked for: a subtraction
        # that would go below zero stops at zero.
        moved = f"{held.value - before:+d} → {held.value}"
        self.event(
            assignment,
            LedgerEvent.Kind.TALLIED,
            note=_movement_note(moved, note),
        )
        return held.value

    def move(self, assignment, to, note=""):
        """Re-home an assignment — model to stash, stash to model, onto a gun.

        The rulebook's equipment redistribution: stash gear "can be moved
        to any number of Model Cards". The subtree rides along (roots are
        rewritten down the chain), the pinned rating rides untouched — a
        move never re-prices — and a MOVED event records who did it.

        ``to`` is a model, the gang's stash, or **another assignment**,
        which is how an accessory is bolted onto a weapon: it hangs off
        that weapon's assignment, so re-homing it is giving it a new parent
        rather than a new host. The same act either way — nothing is
        bought, nothing is charged, and what the thing is worth does not
        move with it.

        What cannot be re-homed is a part that *is* what it hangs off
        (:func:`n26.core.owned.is_detachable`) — a weapon's firing line
        names one gun and is nothing away from it.
        """
        from n26.core.models import Assignment, LedgerEvent, Miniature, Stash
        from n26.core.owned import is_detachable

        if assignment.parent_id is not None and not is_detachable(
            assignment.assignable
        ):
            raise Refusal(
                f"{assignment.assignable} is part of "
                f"{assignment.parent.assignable} — move that instead."
            )
        self.touched(assignment.miniature_root)
        assignment.gang = None
        assignment.miniature = assignment.stash = assignment.parent = None
        if isinstance(to, Stash):
            assignment.stash = to
        elif isinstance(to, Miniature):
            assignment.miniature = to
        elif isinstance(to, Assignment):
            # Hanging a thing off itself, or off something already hanging
            # off it, would make a loop with no root — the denormalised
            # roots would have nowhere to come from. No control offers it.
            if to.pk == assignment.pk or any(
                row.pk == to.pk for row in subtree(assignment)
            ):
                raise ValueError("Cannot attach something to itself.")
            assignment.parent = to
        else:
            raise ValueError(f"Cannot move something onto {to!r}.")
        assignment.save()
        for row in subtree(assignment):
            row.save()  # roots re-derive from the parent chain
        self.touched(assignment.miniature_root)
        self.event(assignment, LedgerEvent.Kind.MOVED, note=note)
        return assignment

    def buy_weapon_profile(self, weapon_assignment, weapon_profile, **kwargs):
        """Buy an extra, paid profile for a weapon already assigned."""
        return self.assign(
            weapon_profile,
            parent=weapon_assignment,
            paid=weapon_profile.price,
            **kwargs,
        )

    # --- boundary --------------------------------------------------------

    def settle(self):
        """Rewrite the pinned numbers this operation disturbed.

        This is also where an overspend is refused: raising here unwinds
        the whole operation's transaction, so a too-expensive hire leaves
        nothing half-written behind.
        """
        for miniature in self._miniatures.values():
            miniature.repin_rating()
        if self.gang is not None:
            # What the gang read about its own open actions is dropped
            # here as well as at each writer: the instance goes on being
            # used after the operation closes, and an act that opened or
            # closed one must not leave it answering from before.
            self.gang.forget_open_actions()
            stash = getattr(self.gang, "stash", None)
            if stash is not None:
                stash.repin_rating()
            self.gang.repin_rating()
            remaining = self.gang.recompute_credits()
            if remaining is not None and remaining < 0:
                raise NotEnoughCredits(self.gang, shortfall=-remaining)
            self.gang.repin_credits()


def _budget_word(credits):
    """A budget as the history says it: a figure, or no ceiling at all."""
    return "unlimited" if credits is None else f"{credits}¢"


def _reason_for(paid, caused_by):
    """Why this exists: something granted it, it was bought, or it was free.

    "Granted" means another assignment brought it — a mount granting a
    subtype. Something free that nobody granted is just free.
    """
    if caused_by is not None:
        return Reason.GRANTED
    return Reason.BOUGHT if paid else Reason.FREE


def _kind_for(paid, caused_by):
    if paid:
        return LedgerEvent.Kind.PURCHASED
    return LedgerEvent.Kind.GRANTED if caused_by is not None else LedgerEvent.Kind.ADDED


def _now():
    from django.utils import timezone

    return timezone.now()


def _under_the_lock(assignment):
    """The root of a removal, read again now that the gang's line is held.

    A caller loads what it means to remove, refund or sell before the
    operation begins, and so before :func:`_hold` — two clicks of the same
    button each load a live, paid-for line, and the second waits its turn
    holding a copy that still says so. Acting on that copy would archive
    a thing already archived and hand its money back a second time, with
    the entry settled to zero twice while its events fold to minus what
    it was worth. So the act reads the row afresh, entry beside it, and
    every removal treats an already-archived root as done: nothing
    written, and None returned so a caller can say so rather than report
    an act that did not happen. The rows beneath it are always read
    fresh, so they need no such care.
    """
    from n26.core.models import Assignment

    return Assignment.objects.select_related("ledger_entry").get(pk=assignment.pk)


def subtree(assignment):
    """Everything hanging off an assignment: its children and what it caused."""
    found = {}
    frontier = [assignment]
    while frontier:
        current = frontier.pop()
        for related in [*current.children.all(), *current.caused.all()]:
            if related.pk not in found:
                found[related.pk] = related
                frontier.append(related)
    return list(found.values())


def _sold_separately(line, entry, weapon):
    """The profile ids the listing behind a purchase sells apart from the gun.

    A listing that names an ammo type as a row of its own — priced its
    own way — is selling it, not including it. A purchase made through a
    collection entry asks that collection which of this weapon's
    profiles it lists; a swept line carries the same split as its parts.
    A purchase with no listing behind it — a hire's built-in weapon, an
    owner's hand-set gift — includes everything, which is what content
    means by a zero-priced profile.
    """
    from n26.library.models import CollectionEntry, WeaponProfile

    if entry is not None:
        return set(
            CollectionEntry.objects.filter(
                collection_id=entry.collection_id,
                weapon_profile__weapon=weapon,
            ).values_list("weapon_profile_id", flat=True)
        )
    if line is not None:
        return {
            part.thing.pk
            for part in getattr(line, "parts", ())
            if isinstance(part.thing, WeaponProfile)
            and part.thing.weapon_id == weapon.pk
        }
    return frozenset()


def _hold(gang):
    """Take the gang's own line, before this operation touches anything.

    Every operation ends by rewriting the gang's pinned numbers, so all
    of them take this line either way. Taking it first gives every writer
    one order: one gang's work settles an act at a time, each act reads
    what the act before it wrote, and no two wait on each other's rows in
    opposite orders.

    Held for the length of the transaction, and only against others
    taking it — one gang at a time, while every other gang goes on
    untouched.
    """
    from n26.core.models import Gang

    Gang.objects.select_for_update().filter(pk=gang.pk).first()


def clone_gang(source, *, name, owner, actor=None):
    """Create an independent snapshot of one live gang.

    The source is locked while its plan is read.  A clone carries current
    possessions and current cash, not the source's past acts, campaign, or an
    open Visit Trading Post action.
    """
    from n26.core.cloning import clone_event_note, plan_gang_clone
    from n26.core.models import Action, Gang, Stash

    with transaction.atomic():
        source = (
            Gang.objects.select_for_update()
            .filter(pk=source.pk, archived=False)
            .first()
        )
        if source is None:
            raise Refusal("That gang can no longer be cloned.")
        plan = plan_gang_clone(source)
        remaining = source.recompute_credits()
        opening_budget = (
            None if source.starting_credits is None else remaining + plan.copied_spend
        )
        clone = Gang.objects.create(
            name=name,
            gang_type=source.gang_type,
            owner=owner,
            starting_credits=opening_budget,
            credits=opening_budget or 0,
            colour=source.colour,
            notes=source.notes,
            lore=source.lore,
            image=source.image.name,
        )
        Stash.objects.create(gang=clone)
        with operation(clone, actor=actor) as op:
            result = op._materialise_clone_plan(plan)
            clone.founding = result.assignments.get(source.founding_id)
            clone.save(update_fields=["founding", "modified"])
            op.event(None, LedgerEvent.Kind.CLONED, note=clone_event_note(source.name))
            op.open_action(Action.Kind.FOUNDING)
        return clone


@contextmanager
def operation(gang, actor=None, batch=None):
    """One transaction; pinned numbers rewritten when it closes."""
    op = Operation(gang, actor=actor, batch=batch)
    with transaction.atomic():
        if gang is not None and gang.pk is not None:
            _hold(gang)
            # Anything the gang read before its line was taken can
            # already be stale — two clicks on one button arrive
            # together often enough. What is decided in here is decided
            # on what stands under that line.
            gang.forget_open_actions()
        yield op
        op.settle()
