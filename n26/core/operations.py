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


class NotEnoughCredits(Exception):
    """A spend would take the gang below zero credits.

    Raised at the operation boundary, so the whole operation rolls back —
    nothing is half-bought. This is the one place we reject rather than
    inform: the founding budget "may not be exceeded", and the
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
        paid=0,
        list_price=None,
        discount=0,
        trade_points=0,
        rating=None,
        reason=None,
        bought_from=None,
        note="",
    ):
        """Attach something, with its ledger entry and opening event."""
        assignment = Assignment.objects.create(
            assignable=assignable,
            gang=gang,
            miniature=miniature,
            parent=parent,
            stash=stash,
            caused_by=caused_by,
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
        *and* gives the credits back. Selling at half price is a third
        thing, waiting on the stash.

        Each refunded line's entry is settled to zero with a matching
        event, so folding the events still reproduces the entry and the
        gang's recomputed credits rise by exactly what was returned. Lines
        that cost nothing are simply removed. Trade Points are recorded as
        returned for the ledger's sake, but TP never outlives its session,
        so nothing is ever re-spendable.
        """
        for target in [assignment, *subtree(assignment)]:
            if target.archived:
                continue
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

    # --- composites ------------------------------------------------------

    def hire(self, profile, model_name, paid=None, owner=None, option=None, **kwargs):
        """Hire a model: a gang-hosted assignment of a profile, bringing a model.

        ``option`` names what was chosen — one set, or a list of sets when
        the profile offers several groups. Omitted, each one-of group's
        default applies and the any-of groups add nothing. The built-ins
        and every chosen set materialise as free assignments caused by the
        membership, and the sets' prices fold into the membership's line —
        the items themselves cost nothing, the package carries the money.
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

    def _materialise_defaults(self, carrier, taken, kinds=None, gang=None):
        """Grant a carrier's built-ins and the sets taken with it.

        ``carrier`` is the assignment that brought the thing in — a
        model's membership, a bought mount's own assignment, a gang's
        founding. Everything created is **caused by** it and hosted
        alongside it, so removing the carrier removes all of it, and a
        card draws the grants as ordinary rows with the carrier as their
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
        sets = [getattr(carrier.assignable, "built_ins", None), *taken]
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
                elif member.counter_id is not None:
                    # A counter opens at its member's amount — Starting XP.
                    CounterValue.objects.create(
                        assignment=assignment, value=member.amount
                    )
        for weapon_profile in ammo:
            gun = weapon_assignments.get(weapon_profile.weapon_id)
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

    def choose(self, anchor, chosen, **kwargs):
        """Answer a choice a modifier offered — pick a specialisation.

        ``anchor`` is the assignment whose assignable carries the offer (the
        Specialist subtype's); the answer is a free assignment caused by it,
        so removing the carrier takes the answer along, and the computed
        slot reads as resolved because this row exists.
        """
        from n26.core import select
        from n26.library.models.modifier import OffersChoice

        matched = [
            modifier.effect
            for modifier in anchor.assignable.modifiers.all()
            if isinstance(modifier.effect, OffersChoice)
            and modifier.effect.selector().matches(select.matchable(chosen))
        ]
        if not matched:
            raise ValueError(
                f"{anchor.assignable} does not offer a choice of "
                f"{type(chosen)._meta.verbose_name}."
            )
        # The answer lands on the host the offer names: the bearer of
        # the question by default — a fighter's choice on the fighter, a
        # gang's (a Venator's ranked trees) on the gang — or the gang,
        # when the offer says so (the Outcast Leader picks the
        # archetype; the gang carries it, and it dies with the Leader
        # through the caused_by cascade). An explicit host wins over all
        # of it — a *gang-carried* offer scoped to fighters ("Leaders
        # and Champions each select a skill") puts a slot on every
        # matching card, and the caller says whose is being answered:
        # ``choose(founding, skill, miniature=leader)``.
        if not any(key in kwargs for key in ("miniature", "gang", "stash", "parent")):
            if any(
                offer.answer_host == OffersChoice.AnswerHost.GANG for offer in matched
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

    def _grant_free_profiles(self, weapon, assignment):
        """A weapon's free profiles ride along with it, however it arrived.

        Bought or granted as default equipment, a weapon is the same weapon:
        without this its card line would have no statline and no traits.
        """
        for profile in weapon.profiles.filter(price=0):
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
        remembers, and any of it may be overridden at the till.

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
                # with still costs what it costs.
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
            self._grant_free_profiles(thing, bought)
        if hasattr(thing, "resolve_selection"):
            self._materialise_defaults(bought, taken)
        return bought

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
        """Re-home a root assignment — model to stash, stash to model.

        The rulebook's equipment redistribution: stash gear "can be moved
        to any number of Model Cards". The subtree rides along (roots are
        rewritten down the chain), the pinned rating rides untouched — a
        move never re-prices — and a MOVED event records who did it.
        """
        from n26.core.models import LedgerEvent, Miniature, Stash

        if assignment.parent_id is not None:
            raise ValueError(
                f"{assignment.assignable} is attached to "
                f"{assignment.parent.assignable} — move that instead."
            )
        self.touched(assignment.miniature_root)
        assignment.gang = None
        assignment.miniature = assignment.stash = None
        if isinstance(to, Stash):
            assignment.stash = to
        elif isinstance(to, Miniature):
            assignment.miniature = to
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
        no half-written rows behind.
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


@contextmanager
def operation(gang, actor=None):
    """One transaction; pinned numbers rewritten when it closes."""
    op = Operation(gang, actor=actor)
    with transaction.atomic():
        yield op
        op.settle()
