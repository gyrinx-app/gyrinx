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

Use it as a context manager::

    with operation(gang, actor=player) as op:
        yolanda = op.hire(hunt_champion, "Yolanda", paid=130)
        op.give_weapon(yolanda, combat_shotgun, paid=60)
"""

from contextlib import contextmanager

from django.db import transaction

from n26.core.models import (
    Assignment,
    LedgerEntry,
    LedgerEvent,
    Miniature,
    ProfileRole,
    Reason,
)

#: The least a sale ever returns. Half of a knife is nothing, and nobody
#: hands a knife over for nothing.
MINIMUM_PROCEEDS = 5


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
    from n26.core.owned import is_detachable

    return [
        child
        for child in assignment.children.all()
        if not child.archived
        and child.caused_by_id is None
        and is_detachable(child.assignable)
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
    domain declines: an overspend, a pick that cannot settle the
    choice it was given. What does not is a content bug or a caller
    mistake — nobody can click their way to one, the sentence would mean
    nothing to a player, and an unhandled error is the right answer.
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
            f"Not enough credits: this spend leaves {gang.name} {shortfall}cr "
            f"short of their {gang.starting_credits}cr budget."
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


class Operation:
    """Collects what it touched, so the boundary knows what to repin."""

    #: A pet whose profile brings a pet whose profile brings a pet is a
    #: content bug, not a use case.
    MAX_STORED_EFFECT_DEPTH = 3

    def __init__(self, gang, actor=None):
        self.gang = gang
        self.actor = actor
        self._miniatures = {}
        self._effect_depth = 0

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
        paid=0,
        list_price=None,
        discount=0,
        trade_points=0,
        rating=None,
        reason=None,
        bought_from=None,
        note="",
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
        """
        assignment = Assignment.objects.create(
            assignable=assignable,
            gang=gang,
            miniature=miniature,
            parent=parent,
            stash=stash,
            caused_by=caused_by,
            chosen_for=chosen_for,
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
            note=note,
        )
        self.event(
            assignment,
            _kind_for(paid, caused_by),
            credits_delta=paid,
            trade_points_delta=trade_points,
            rating_delta=rating,
            note=note,
        )
        self.touched(assignment.miniature_root)
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

    def event(self, assignment, kind, **deltas):
        """Append to the log. Nothing already written is ever altered."""
        return LedgerEvent.objects.create(
            assignment=assignment, kind=kind, actor=self.actor, **deltas
        )

    def remove(self, assignment, note=""):
        """Take something away — and everything it brought with it.

        Archives rather than deletes: the ledger is append-only, so the
        record of having owned the thing survives. Its rating stops counting
        because rating sums skip archived assignments; the entry keeps
        saying what the thing was worth.
        """
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
        nobody paid for are simply removed. Trade Points are recorded as
        returned for the ledger's sake, but TP never outlives its session,
        so nothing is ever re-spendable.
        """
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

        Returns what the gang was paid.
        """
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
        self._materialise_defaults(membership, taken)
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
        from n26.core.models import Stash

        founding = self.assign(gang_type, gang=self.gang, paid=0, **kwargs)
        self.gang.founding = founding
        self.gang.save(update_fields=["founding", "modified"])
        Stash.objects.get_or_create(gang=self.gang)
        self._materialise_defaults(founding, list(taken), gang=self.gang)
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
        self._materialise_defaults(carrier, arriving, gang=gang, built_ins=False)

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

        Most of a set's members landed caused by the carrier itself; an
        ammo member landed caused by its weapon's own assignment, wherever
        that weapon came from. Where the built-ins grant the same
        assignable as the set, the set's copy is the newer one — the
        built-ins materialise first — so the newest live match is taken,
        as many as the set granted.
        """
        from n26.core.models import Reason
        from n26.library.models import WeaponProfile

        wanted = {}
        for member in default_set.members.all():
            assignable = member.assignable
            if assignable is None:
                continue
            wanted[assignable] = wanted.get(assignable, 0) + 1

        rows = []
        for assignable, count in wanted.items():
            scope = {
                Assignment.field_for(assignable): assignable,
                "archived": False,
                "ledger_entry__reason": Reason.DEFAULT,
                "gang_root": carrier.gang_root,
                "miniature_root": carrier.miniature_root,
            }
            matches = Assignment.objects.filter(**scope)
            if isinstance(assignable, WeaponProfile):
                # Granted ammo is caused by its gun, not by the carrier.
                matches = matches.exclude(caused_by=None)
            else:
                matches = matches.filter(caused_by=carrier)
            rows.extend(matches.order_by("-pk")[:count])
        return rows

    def _materialise_defaults(
        self, carrier, taken, kinds=None, gang=None, built_ins=True
    ):
        """Grant a carrier's built-ins and the sets taken with it.

        ``carrier`` is the assignment that brought the thing in — a
        model's membership, a bought mount's own assignment, a gang's
        founding. Everything created is **caused by** it and hosted
        alongside it, so removing the carrier removes all of it, and a
        card draws the grants as ordinary lines with the carrier as their
        source. Pass ``gang`` for a gang-hosted carrier, which has no
        model to hang things on.

        Nothing is ever replaced: the option not taken is simply never
        created, which is what keeps this free of v1's inheritance mess.
        A thing that may be swapped for something else is an *option*,
        not a built-in.

        A weapon-profile member is an extra ammo type: it stacks on its
        weapon's assignment — the same shape ``buy_weapon_profile`` writes
        — and that weapon may arrive from any of these sets, so the ammo
        is granted after every weapon has been.

        A slot member brings the choice open. Where the member also names
        a starting pick, the pick is written in the same breath, settling
        the slot exactly as a click would — changing it later is the
        ordinary rechoose.

        ``kinds`` narrows what materialises — a Legacy profile brings its
        lists but not a second set of free kit.
        """
        from n26.core.models import ChosenProfileOption, CounterValue, Reason
        from n26.library.models import Weapon, WeaponProfile

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
        sets = [getattr(carrier.assignable, "built_ins", None) if built_ins else None]
        sets += taken
        weapon_assignments = {}
        ammo = []
        for default_set in sets:
            if default_set is None:
                continue
            for member in default_set.members.all():
                assignable = member.assignable
                if assignable is None:
                    continue
                if kinds is not None and not isinstance(assignable, kinds):
                    continue
                if isinstance(assignable, WeaponProfile):
                    ammo.append(assignable)
                    continue
                assignment = self.assign(
                    assignable,
                    caused_by=carrier,
                    paid=0,
                    reason=Reason.DEFAULT,
                    **host,
                )
                if isinstance(assignable, Weapon):
                    self._grant_free_profiles(assignable, assignment)
                    weapon_assignments[assignable.pk] = assignment
                elif member.default_pickable_id is not None:
                    # A slot arriving already settled. The pick goes
                    # where the slot says, which need not be where the
                    # slot itself landed.
                    self._choose_for_slot(
                        assignment, assignable, member.default_pickable
                    )
                elif member.counter_id is not None:
                    # A counter opens at its member's amount — Starting XP.
                    CounterValue.objects.create(
                        assignment=assignment, value=member.amount
                    )
        for weapon_profile in ammo:
            gun = weapon_assignments.get(weapon_profile.weapon_id)
            if gun is None:
                # The weapon may already be there — a set chosen after the
                # hire grants ammo for a gun the built-ins brought — so an
                # existing live assignment on the same host takes it.
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
                # A content bug, not a player mistake: the set names ammo
                # for a weapon nothing here brings.
                raise ValueError(
                    f"{carrier.assignable} grants {weapon_profile}, but "
                    f"nothing it brings is its weapon "
                    f"({weapon_profile.weapon})."
                )
            # Caused by the weapon, like its free profiles: the card says
            # "from the grenade launcher array", not "from the profile".
            self.assign(
                weapon_profile,
                parent=gun,
                caused_by=gun,
                paid=0,
                reason=Reason.DEFAULT,
            )
        for chosen in taken:
            ChosenProfileOption.objects.create(assignment=carrier, default_set=chosen)

    def choose(self, anchor, chosen, slot=None, **kwargs):
        """Make a choice — pick a specialisation, pick a gang legacy.

        ``anchor`` is the assignment that asked: the one whose assignable
        carries a modifier offering the choice (the Specialist subtype's),
        or a **slot's** own assignment. What was chosen is a free
        assignment caused by it, so removing what asked takes the answer
        along, and it points back through ``chosen_for`` so the card reads
        the choice as settled.

        ``slot`` names which choice is being settled where the anchor
        cannot say: a slot a modifier *gave* has no assignment of its
        own, so the thing that gave it is the anchor and the slot is
        named here.

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

        if slot is None and isinstance(anchor.assignable, Slot):
            slot = anchor.assignable
        if slot is not None:
            return self._choose_for_slot(anchor, slot, chosen, **kwargs)

        matched = [
            modifier.effect
            for modifier in anchor.assignable.modifiers.all()
            if isinstance(modifier.effect, OffersChoice)
            and modifier.effect.selector().matches(select.matchable(chosen))
        ]
        if not matched:
            raise NotOnOffer(anchor, chosen)
        # What was chosen lands on the host the offer names: the bearer
        # of the question by default — a fighter's choice on the fighter, a
        # gang's (a Venator's ranked trees) on the gang — or the gang,
        # when the offer says so (the Outcast Leader picks the
        # archetype; the gang carries it, and it dies with the Leader
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
                bearer = anchor.miniature or anchor.member_or_none()
                kwargs |= {"miniature": bearer} if bearer else {"gang": anchor.gang}
        return self.assign(
            chosen,
            caused_by=anchor,
            paid=0,
            reason=Reason.GRANTED,
            **kwargs,
        )

    def _choose_for_slot(self, anchor, slot, chosen, **kwargs):
        """Settle one slot: write the pick, pointing back at what asked.

        The one check is the domain — a Gang Legacy choice is settled by
        a Gang Legacy option and by nothing else, because the row reads
        as settled by the same match and anything else would leave the
        choice open with a stray assignment beside it. Which options the
        picklist offers is not checked: a shorter list informs, and an
        owner may still hand over something off it.

        Where the pick lands is the slot's own business — the bearer, or
        the gang where the slot says so (the Leader is asked and the gang
        holds the answer). An explicit host wins over both, which is how
        a slot the gang holds is settled for one particular fighter.
        """
        from n26.library.models import Pickable, Slot

        if not isinstance(chosen, Pickable) or chosen.slot_type_id != slot.slot_type_id:
            raise NotOnOffer(
                anchor,
                chosen,
                message=(
                    f"{chosen} cannot settle {slot.choice_label} — that "
                    f"choice takes {slot.slot_type} options."
                ),
            )
        if not any(key in kwargs for key in ("miniature", "gang", "stash", "parent")):
            if slot.assigned_to == Slot.WillBeAssignedTo.GANG:
                kwargs |= {"gang": anchor.gang or anchor.gang_root}
            else:
                bearer = anchor.miniature or anchor.member_or_none()
                kwargs |= {"miniature": bearer} if bearer else {"gang": anchor.gang}
        return self.assign(
            chosen,
            caused_by=anchor,
            chosen_for=anchor,
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
        from n26.library.models import Collection

        assignment = self.assign(profile, miniature=miniature, **kwargs)
        ProfileRole.objects.create(assignment=assignment, role=ProfileRole.Role.LEGACY)
        self._materialise_defaults(assignment, [], kinds=(Collection,))
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
            host = {"stash": holder}
        elif isinstance(holder, Assignment):
            host = {"parent": holder}
        else:
            host = {"miniature": holder}

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
            **host,
            **kwargs,
        )
        if isinstance(thing, Weapon):
            self._grant_free_profiles(
                thing, bought, sold_separately=_sold_separately(line, entry, thing)
            )
        if hasattr(thing, "resolve_selection"):
            self._materialise_defaults(bought, taken)
        return bought

    def learn(self, miniature, thing, note=""):
        """Take on something a model *is* — a skill, a power.

        Free, and recorded as a reward. No credits move: what a fighter
        learns is earned rather than bought, and a purchase is not the
        way to it. What it adds to the gang's rating is the thing's own
        reference price, which is nothing for a skill the rules hand
        out and whatever content says for one that is worth something.

        Nothing causes it. A skill is not a consequence of the assignment whose
        grid placed the set it came from, so swapping a profile — or
        dropping the wargear that opened a set up — never unlearns
        anything. That is the difference between this and ``choose``,
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

    def tally(self, assignment, change, note=""):
        """Change a counter's value — the only writer it has.

        ``change`` is signed; the value floors at zero. Every change is a
        ledger event, so the history of a Kill Count reads like the
        history of anything else the gang owns.
        """
        from n26.core.models import CounterValue, LedgerEvent

        held, _ = CounterValue.objects.get_or_create(assignment=assignment)
        held.value = max(0, held.value + change)
        held.save(update_fields=["value", "modified"])
        self.event(assignment, LedgerEvent.Kind.TALLIED, note=note)
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
            stash = getattr(self.gang, "stash", None)
            if stash is not None:
                stash.repin_rating()
            self.gang.repin_rating()
            remaining = self.gang.recompute_credits()
            if remaining is not None and remaining < 0:
                raise NotEnoughCredits(self.gang, shortfall=-remaining)
            self.gang.repin_credits()


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


@contextmanager
def operation(gang, actor=None):
    """One transaction; pinned numbers rewritten when it closes."""
    op = Operation(gang, actor=actor)
    with transaction.atomic():
        yield op
        op.settle()
