"""Atomic writes to player data and its journal.

Each operation groups related changes in one transaction. On exit, it
recomputes affected model ratings and the gang's rating and credits from
the ledger. ``n26.core.reconcile`` checks those cached totals independently.

Renames, notes and characteristic overrides also use operations so the
journal records who changed them. Device preferences, including print
configurations and display sets, use ordinary saves.

Use it as a context manager::

    with operation(gang, actor=player) as op:
        yolanda = op.hire(hunt_champion, "Yolanda", paid=130)
        op.give_weapon(yolanda, combat_shotgun, paid=60)
"""

from contextlib import contextmanager
from dataclasses import dataclass
from functools import cached_property
from uuid import uuid4

from django.db import transaction
from django.db.models import Q, Sum

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
from n26.errors import UserFacingError

#: Minimum proceeds for a sale with a non-negative rating.
MINIMUM_PROCEEDS = 5


@dataclass(frozen=True)
class _CloneResult:
    """Destination assignments and models made from a clone plan."""

    primary: Miniature | None
    assignments: dict
    miniatures: dict


def proceeds_for(rating):
    """Return sale proceeds calculated from rating.

    Non-negative ratings return half, rounded up, with a minimum of
    :data:`MINIMUM_PROCEEDS`. Negative ratings return zero, preventing repeated
    sales of negative-rating upgrades from generating credits.
    """
    if rating < 0:
        return 0
    return max(MINIMUM_PROCEEDS, -(-rating // 2))


def sale_of(assignment, keeping=()):
    """Return live assignments to sell, their total rating, and the proceeds.

    Confirmation pages and settlement share this calculation. ``keeping``
    excludes each retained child's subtree, which can be moved into the stash.
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
    """Return live children that can be kept when selling their parent.

    Weapon profiles and equipment granted by the parent cannot be detached.
    See :func:`n26.core.owned.can_unbolt`.
    """
    from n26.core.owned import can_unbolt

    return [
        child
        for child in assignment.children.all()
        if not child.archived and can_unbolt(child)
    ]


def refund_of(assignment):
    """Return live assignments in the subtree and their total paid credits.

    Confirmation pages and settlement share this calculation. Trade Points
    are calculated separately by :func:`trade_points_refund_of`; a purchase
    may have spent both currencies.
    """
    rows = [row for row in [assignment, *subtree(assignment)] if not row.archived]
    paid = sum(
        entry.paid
        for row in rows
        if (entry := getattr(row, "ledger_entry", None)) is not None
    )
    return rows, paid


def option_grants(carrier, default_set):
    """Find live assignments materialised by a selected set for this carrier.

    Provenance includes archived set members, whose surviving copies must
    still leave when the option is removed. Ammunition without provenance
    uses :func:`_ammo_rows_without_provenance`.
    """
    from n26.core.builtins import copies_of_set

    tagged = list(copies_of_set(default_set, carrier))
    rows = [copy for copy in tagged if not copy.archived]
    rows.extend(_ammo_rows_without_provenance(carrier, default_set, tagged))
    return rows


def _ammo_rows_without_provenance(carrier, default_set, tagged):
    """Find ammunition grants whose assignments have no recorded provenance.

    Granted profiles share the representation of free weapon profiles. Match
    the newest live copies caused by a weapon on the same host, up to the
    set's remaining required quantity. Other assignable kinds require provenance.

    Tagged copies, including archived copies, count towards that quantity so
    removing an earlier grant cannot cause an unrelated copy to be removed.
    Only live set members can require additional matches.
    """
    from n26.core.models import Reason

    wanted = {}
    for member in default_set.members.filter(archived=False):
        if member.weapon_profile_id is not None:
            wanted[member.weapon_profile_id] = (
                wanted.get(member.weapon_profile_id, 0) + 1
            )
    for copy in tagged:
        if copy.weapon_profile_id in wanted:
            wanted[copy.weapon_profile_id] -= 1

    needed = {profile_id: count for profile_id, count in wanted.items() if count > 0}
    if not needed:
        return []
    matches = Assignment.objects.filter(
        weapon_profile_id__in=needed,
        archived=False,
        materialised_from__isnull=True,
        ledger_entry__reason=Reason.DEFAULT,
        gang_root=carrier.gang_root,
        miniature_root=carrier.miniature_root,
        # Granted ammo is caused by its gun, not by the carrier.
        caused_by__isnull=False,
    ).order_by("-pk")
    by_profile = {profile_id: [] for profile_id in needed}
    for row in matches:
        if needed[row.weapon_profile_id] > 0:
            by_profile[row.weapon_profile_id].append(row)
            needed[row.weapon_profile_id] -= 1
    return [row for profile_id in by_profile for row in by_profile[profile_id]]


def option_refunds(carrier, default_sets):
    """Refundable assignments under each held option's grants.

    Departing options may share descendants. Keep their identities so a
    preview can count each refunded assignment once, as settlement does.
    """
    roots = {
        default_set.pk: {row.pk for row in option_grants(carrier, default_set)}
        for default_set in default_sets
    }
    frontier = set().union(*roots.values()) if roots else set()
    rows = {
        row.pk: row
        for row in Assignment.objects.filter(pk__in=frontier).select_related(
            "ledger_entry"
        )
    }
    children = {}
    # Batch each depth of the refund graph, rather than querying each grant.
    # Archived intermediates may still have live descendants to refund.
    while frontier:
        found = list(
            Assignment.objects.filter(
                Q(parent_id__in=frontier) | Q(caused_by_id__in=frontier)
            ).select_related("ledger_entry")
        )
        for row in found:
            for parent in (row.parent_id, row.caused_by_id):
                if parent is not None:
                    children.setdefault(parent, set()).add(row.pk)
        frontier = {row.pk for row in found if row.pk not in rows}
        rows.update((row.pk, row) for row in found)
    refunds = {}
    for key, granted in roots.items():
        pending = list(granted)
        seen = set()
        while pending:
            pk = pending.pop()
            if pk in seen:
                continue
            seen.add(pk)
            pending.extend(children.get(pk, ()))
        refunds[key] = tuple(
            rows[pk] for pk in seen if pk in rows and not rows[pk].archived
        )
    return refunds


def trade_points_in(assignments):
    """Sum Trade Points paid for these assignments.

    Accepts the assignments from :func:`refund_of` so a confirmation needing
    both currencies traverses the subtree once.
    """
    return sum(
        entry.trade_points
        for assignment in assignments
        if (entry := getattr(assignment, "ledger_entry", None)) is not None
    )


def trade_points_refund_of(assignment):
    """Return the Trade Points refundable from this assignment's live subtree.

    These points return to the purchase's original allowance. Gangs without
    a credit budget use this total when deciding whether to offer a refund.
    """
    return trade_points_in(refund_of(assignment)[0])


def trade_points_carried_by(miniature):
    """Sum Trade Points paid for all live assignments on this model.

    Includes the hire and equipment in one query, for refund availability checks.
    """
    from django.db.models import Sum

    return (
        Assignment.objects.filter(miniature_root=miniature, archived=False).aggregate(
            total=Sum("ledger_entry__trade_points")
        )["total"]
        or 0
    )


class Refusal(UserFacingError):
    """A player action cannot be completed; ``public_message`` explains why.

    Raising inside an operation rolls back its transaction. Views display the
    message and redirect. Content defects and caller mistakes must propagate
    as ordinary exceptions so their tracebacks remain available.
    """


class LibraryError(Exception):
    """Content requires an operation that cannot be performed.

    This exception rolls back the operation and retains its traceback.
    Views must not present it as a player validation error.
    """


class NotEnoughCredits(Refusal):
    """Settlement would leave a gang with a credit budget below zero.

    Raised at the operation boundary so assignments, payments and events all
    roll back together. Raising or clearing the budget permits the expenditure.
    """

    def __init__(self, gang, shortfall):
        self.gang = gang
        self.shortfall = shortfall
        super().__init__(
            f"Not enough credits: this spend leaves {gang.name} {shortfall}¢ "
            f"short of their {gang.starting_credits}¢ budget."
        )


class AlreadyInACampaign(Refusal):
    """Joining would give the gang two open campaign memberships.

    A single active membership determines which campaign receives gang events.
    """

    def __init__(self, gang, campaign):
        self.gang = gang
        self.campaign = campaign
        super().__init__(
            f"{gang.name} is already playing {campaign.name}. "
            "A gang plays one campaign at a time — leave that one first."
        )


class NotOnOffer(Refusal):
    """The selected assignable's kind cannot resolve the offered choice.

    Choices resolve only when the selected kind matches the offer. See
    ``n26.core.browse.offered_by`` for the choices presented by the picker.
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


#: Distinguish an unqueried campaign from a cached absence of membership.
_UNASKED = object()

#: Distinguish manually entered rolls from generated rolls in the journal.
ROLL_ENTERED = "Manual roll."

#: Also recognise this stored note as a manually entered roll.
ROLL_ENTERED_BEFORE = "Rolled at the table and entered here."

#: Identify status changes caused by Clean House in the history.
CLEAN_HOUSE = "Clean House"


def _movement_note(moved, reason):
    """Combine a counter movement and reason within the event note limit.

    Truncate the reason first so the recorded numeric movement remains intact.
    """
    from n26.core.models import LedgerEvent

    if not reason:
        return moved
    room = LedgerEvent._meta.get_field("note").max_length - len(moved) - len(": ")
    if len(reason) > room:
        reason = reason[: max(0, room - 1)] + "…"
    return f"{moved}: {reason}"


class Operation:
    """Track changed miniatures for recomputation at settlement."""

    #: Bound recursive model grants to reject cyclic content.
    MAX_STORED_EFFECT_DEPTH = 3

    def __init__(self, gang, actor=None, batch=None, post_battle_revision=None):
        self.gang = gang
        self.actor = actor
        # Share the batch across participating gangs so their events can
        # be grouped as one operation in history.
        self.batch = batch or uuid4()
        self.post_battle_revision = post_battle_revision
        self.post_battle_occurrence = None
        self._miniatures = {}
        self._effect_depth = 0
        self._campaign = _UNASKED
        #: Created assignment IDs, as strings. ``n26.core.arrivals`` uses
        #: these anchors to find choices introduced by this operation.
        self.written = set()

    def touched(self, miniature):
        if miniature is not None:
            self._miniatures[miniature.pk] = miniature

    @cached_property
    def counter_tracking_active(self):
        from n26.core.counter_tracking import is_active

        return is_active()

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
        chosen_for_status_revision=None,
        chosen_for_holding=None,
        chosen_for_holding_revision=None,
        materialised_from=None,
        materialised_for=None,
        paid=0,
        list_price=None,
        discount=0,
        trade_points=0,
        rating=None,
        reason=None,
        bought_from=None,
        activity=None,
        spent_by=None,
        note="",
        removes=False,
        kind=None,
        roll=None,
        action_record=None,
    ):
        """Create an assignment, ledger entry and opening event together.

        ``assignable`` identifies the content; the host is a model, gang, stash
        or parent assignment. ``caused_by`` links dependants for recursive removal.

        ``chosen_for`` identifies the assignment providing a choice.
        ``chosen_for_slot`` and ``chosen_for_offer`` distinguish multiple choices
        on that assignment. ``roll`` links the recorded roll validated by
        ``_choose_for_slot``.

        ``materialised_from`` and ``materialised_for`` identify a built-in's set
        member and carrier. ``reconcile_defaults`` supplies these provenance fields.

        ``activity`` identifies the allowance used. ``spent_by`` identifies the
        model whose Trade Points were spent, even if equipment later moves.
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
            chosen_for_status_revision=chosen_for_status_revision,
            chosen_for_holding=chosen_for_holding,
            chosen_for_holding_revision=chosen_for_holding_revision,
            materialised_from=materialised_from,
            materialised_for=materialised_for,
            removes=removes,
            roll=roll,
        )
        if list_price is None:
            list_price = paid + discount
        if rating is None:
            # Rating defaults to list_price, which defaults to paid + discount.
            # Moving equipment retains this rating.
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
            activity=activity,
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
            action_record=action_record,
        )
        self.touched(assignment.miniature_root)
        self.written.add(str(assignment.pk))
        # Removal assignments must not trigger acquisition effects.
        if not removes:
            self._run_stored_effects(assignment, assignable)
            self._default_asset_income(assignment, assignable)
        return assignment

    def _default_asset_income(self, assignment, assignable):
        """Record a declared Income selection when an owned asset arrives."""
        from n26.library.models import Asset

        if (
            not isinstance(assignable, Asset)
            or not getattr(assignable, "base_income_modifier_id", None)
            or self.gang is None
            or assignment.gang_root_id != self.gang.pk
        ):
            return
        from n26.core.card import build_gang_card, build_modifier_index, carriers
        from n26.core.effects import compute_gang
        from n26.core.models import DismissedOffer
        from n26.core.models.dismissed_offer import GANG_SLOT_HOST, slot_key
        from n26.library.income_choices import declared_income_choice

        declared = declared_income_choice(assignable)
        if declared is None:
            return
        if (
            Assignment.objects.filter(
                chosen_for=assignment, chosen_for_slot=declared.slot
            ).exists()
            or DismissedOffer.objects.filter(
                gang=self.gang,
                slot_key=slot_key(GANG_SLOT_HOST, assignment.pk, declared.slot.pk),
            ).exists()
        ):
            return
        card = build_gang_card(self.gang)
        computed = compute_gang(card, build_modifier_index(carriers(card)))
        choice = next(
            (
                choice
                for choice in computed.choices
                if choice.slot is not None
                and choice.slot.pk == declared.slot.pk
                and getattr(choice.anchor, "key", None) == assignment.pk
            ),
            None,
        )
        if choice is None or choice.picks:
            return
        member = (
            declared.slot.picklist.available_members(include_staged=True)
            .filter(pickable=declared.pickable, pickable__record_only=False)
            .first()
        )
        if member is not None:
            self.choose(assignment, member.pickable, slot=declared.slot)

    def _run_stored_effects(self, assignment, assignable):
        """Run the assignable's effects that write persistent state.

        Each effect implements ``perform`` and receives this operation.
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

    def gain_asset(self, holding, **deltas):
        """Record a campaign holding's arrival in the gang's history.

        The campaign operation has already set the holder under its lock.
        Assigning it to the same holder again does not record another arrival.
        """
        if self.gang is None or holding.holder.gang_id != self.gang.pk:
            raise ValueError("The holding must have arrived at this operation's gang.")
        self.event(
            holding,
            LedgerEvent.Kind.GAINED,
            note=str(holding),
            received_asset_type=holding.asset.asset_type_id,
            **deltas,
        )
        self._default_holding_picks(holding)

    def _default_holding_picks(self, holding):
        """Apply the first available option to required one-pick holding choices.

        Acquisition is the only trigger. Reading a holding, removing its
        pick or changing content never recreates a selection. Each default
        uses ordinary choosing, including its ledger and stored effects.
        """
        from n26.library.models import Slot
        from n26.library.staged import sees_staged

        include_staged = sees_staged(self.gang.owner)
        from n26.core.models import DismissedOffer
        from n26.core.models.dismissed_offer import holding_slot_key
        from n26.library.income_choices import declared_income_choice

        declared = (
            declared_income_choice(holding.asset)
            if getattr(holding.asset, "base_income_modifier_id", None)
            else None
        )

        def declared_slot(slot):
            return declared is not None and slot.pk == declared.slot.pk

        def eligible(choice):
            slot = choice.slot
            return (
                slot is not None
                and choice.min_picks == choice.max_picks == 1
                and slot.mode == Slot.Mode.STANDARD
                and not slot.hidden
                and not slot.follows_status
                and not slot.picklist.dice
                and (
                    declared_slot(slot)
                    or include_staged
                    or not (slot.staged or slot.picklist.staged)
                )
            )

        slots = [
            choice.slot for choice in self._holding_choices(holding) if eligible(choice)
        ]
        for slot in slots:
            # A previous default may remove another offered choice. Read
            # the current card before applying each subsequent selection.
            choice = next(
                (
                    current
                    for current in self._holding_choices(holding)
                    if current.slot.pk == slot.pk
                ),
                None,
            )
            if choice is None or choice.picks or not eligible(choice):
                continue
            if Assignment.objects.filter(
                gang_root=self.gang,
                chosen_for_holding=holding,
                chosen_for_holding_revision=holding.ownership_revision,
                chosen_for_slot=slot,
            ).exists():
                continue
            if DismissedOffer.objects.filter(
                gang=self.gang, slot_key=holding_slot_key(holding, slot.pk)
            ).exists():
                continue
            members = slot.picklist.available_members(
                include_staged=include_staged or declared_slot(slot)
            ).filter(pickable__record_only=False)
            if declared_slot(slot):
                members = members.filter(pickable=declared.pickable)
            member = members.first()
            if member is not None:
                self.choose(holding, member.pickable, slot=slot)

    def _holding_choices(self, holding):
        """Derive the choices offered for this holding's ownership period."""
        from n26.core.card import build_gang_card, build_modifier_index, carriers
        from n26.core.effects import compute_gang

        card = build_gang_card(self.gang)
        computed = compute_gang(card, build_modifier_index(carriers(card)))
        return [
            choice
            for choice in computed.choices
            if choice.holding is not None
            and choice.holding.pk == holding.pk
            and choice.holding.ownership_revision == holding.ownership_revision
            and choice.slot is not None
        ]

    def event(self, about, kind, **deltas):
        """Append an event linked to its gang and current campaign.

        ``about`` may be an assignment, model, campaign asset or None for a gang
        change. When no operation gang is set, derive it from the assignment or
        model membership. Post-battle events use the report's campaign; other
        events resolve the gang's current membership here.
        """
        assignment = about if isinstance(about, Assignment) else None
        gang = self.gang
        if gang is None and assignment is not None:
            gang = assignment.gang_root
        if gang is None and isinstance(about, Miniature):
            membership = getattr(about, "membership", None)
            gang = membership.gang if membership else None
        report = self.post_battle_revision.report if self.post_battle_revision else None
        if report is not None:
            deltas.setdefault("post_battle_revision", self.post_battle_revision)
            deltas.setdefault("post_battle_occurrence", self.post_battle_occurrence)
            deltas.setdefault("battle", report.battle)
        return LedgerEvent.objects.create(
            assignment=assignment,
            miniature=about if isinstance(about, Miniature) else None,
            campaign_asset=about if isinstance(about, CampaignAsset) else None,
            gang=gang,
            campaign=(
                report.battle.campaign
                if report and report.battle_id
                else self._campaign_of(gang)
            ),
            kind=kind,
            batch=self.batch,
            actor=self.actor,
            **deltas,
        )

    def _campaign_of(self, gang):
        """Resolve the gang's current campaign once per operation.

        Delay the lookup until needed so a newly created membership is visible.
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
        """Join a campaign and record its types as granted gang assignments.

        A second active campaign raises ``AlreadyInACampaign``. Rejoining the
        same campaign returns the existing membership. Campaign budgets provide
        information and do not block joining.

        The membership records both the campaign type and additions carriers.
        Their built-ins arrive through normal reconciliation. The join event
        appears in both the gang and campaign histories.
        """
        from n26.core.models import CampaignMembership

        gang = self.gang
        # Check archival under the gang lock; the form may be stale.
        if type(gang).objects.filter(pk=gang.pk, archived=True).exists():
            raise Refusal(
                f"{gang.name} has been deleted, so it cannot join a campaign."
            )
        open_now = CampaignMembership.objects.filter(
            gang=gang, left__isnull=True
        ).select_related("campaign")
        already = open_now.first()
        if already is not None:
            if already.campaign_id == campaign.pk:
                return already
            raise AlreadyInACampaign(gang, already.campaign)

        membership = CampaignMembership.objects.create(campaign=campaign, gang=gang)
        # The join and subsequent grant events must name this campaign.
        self._campaign = campaign
        self.event(None, LedgerEvent.Kind.JOINED_CAMPAIGN)
        membership.type_carrier = self._carry(campaign.campaign_type)
        membership.additions_carrier = self._carry(campaign.additions)
        membership.save(update_fields=["type_carrier", "additions_carrier", "modified"])
        return membership

    def _carry(self, campaign_type):
        """Grant a campaign type and its built-ins to this gang.

        The carrier is gang-hosted, free, and contributes no model rating.
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
        """Close the membership and remove the campaign's grants and holdings.

        Release each asset with a LOST event, then remove both campaign type
        carriers and their dependants. Preserve the membership and event history.
        Return None if no membership is open.

        Call through ``CampaignOperation.remove_gang`` so the campaign lock is
        acquired before the gang lock, matching other asset ownership writers.
        """
        from n26.core.models import CampaignMembership

        membership = (
            CampaignMembership.objects.filter(gang=self.gang, left__isnull=True)
            .select_related("campaign", "type_carrier", "additions_carrier")
            .first()
        )
        if membership is None:
            return None

        # Cache the campaign before closing membership so departure events
        # remain linked to it.
        self._campaign = membership.campaign
        for campaign_asset in membership.held.select_related("asset").order_by(
            "created"
        ):
            self.remove_holding_picks(campaign_asset)
            campaign_asset.holder = None
            campaign_asset.ownership_revision += 1
            campaign_asset.save(
                update_fields=["holder", "ownership_revision", "modified"]
            )
            self.event(campaign_asset, LedgerEvent.Kind.LOST, note=str(campaign_asset))
        for carrier in (membership.type_carrier, membership.additions_carrier):
            if carrier is not None:
                self.remove(carrier)
        membership.left = _now()
        membership.save(update_fields=["left", "modified"])
        self.event(None, LedgerEvent.Kind.LEFT_CAMPAIGN)
        self._campaign = None
        return membership

    def archive_gang(self):
        """Archive this gang without overwriting its cached totals.

        Update only the archive columns; the caller's other fields may be stale.
        """
        now = _now()
        type(self.gang).objects.filter(pk=self.gang.pk).update(
            archived=True, archived_at=now
        )
        self.gang.archived = True
        self.gang.archived_at = now
        return self.gang

    def set_base_rating(self, miniature, rating):
        """Change the hire's rating contribution, preserving its payment.

        Reload the membership under the gang lock so repeated saves compare
        against the current contribution and emit no duplicate event.
        Passing None removes the override and keeps any hire option changes.
        """
        membership = _under_the_lock(miniature.membership)
        if membership.archived or membership.gang_root_id != self.gang.pk:
            raise Refusal("You cannot change this model's base rating.")
        entry = membership.ledger_entry
        resetting = rating is None
        if resetting:
            rating = entry.rating_without_override
        # A refund negates this contribution in an integer ledger delta.
        if not isinstance(rating, int) or not -(2**31) < rating < 2**31:
            raise Refusal("Enter a whole number between -2147483647 and 2147483647.")
        before = entry.rating_contribution
        if rating == before:
            return False
        if not -(2**31) <= rating - before < 2**31:
            raise Refusal("This rating change is too large. Enter a smaller change.")
        entry.rating_contribution = rating
        entry.save(update_fields=["rating_contribution", "modified"])
        from n26.core.reconcile import sum_rating

        underlying = sum_rating(miniature_root=miniature, include_dead=True)
        counted = sum_rating(miniature_root=miniature)
        # A dead model can return to Active; its underlying total must fit then too.
        totals = (
            underlying,
            self.gang.recompute_rating() + underlying - counted,
        )
        if any(not -(2**31) <= total < 2**31 for total in totals):
            raise Refusal(
                "This would make the model or gang rating too large. Enter a smaller rating."
            )
        self.event(
            membership,
            LedgerEvent.Kind.RATING_RESET if resetting else LedgerEvent.Kind.RATING_SET,
            rating_delta=rating - before,
            note=f"Base rating {before}¢ → {rating}¢",
        )
        self.touched(miniature)
        return True

    def rename(self, miniature, name):
        """Rename a model and record its old and new names in a journal event."""
        was = miniature.name
        if was == name:
            return miniature
        miniature.name = name
        miniature.save(update_fields=["name", "modified"])
        self.event(miniature, LedgerEvent.Kind.RENAMED, note=f"{was} → {name}"[:255])
        return miniature

    def set_status(self, miniature, status, note=""):
        """Change a model's status and journal the old and new statuses.

        The note includes the cause when supplied. Mark the model for rating
        recomputation because death affects its contribution. An unchanged status
        produces no event.
        """
        status = Status(status)
        # Reload under the gang lock to avoid duplicate status events from
        # concurrent submissions.
        miniature.refresh_from_db(fields=["status", "status_revision"])
        was = Status(miniature.status)
        if was == status:
            return miniature
        miniature.status = status
        miniature.status_revision += 1
        miniature.save(update_fields=["status", "status_revision", "modified"])
        self.touched(miniature)
        self.event(
            miniature,
            LedgerEvent.Kind.STATUS_SET,
            note=_movement_note(f"{was} → {status}", note),
        )
        return miniature

    def transfer(self, to, credits, note="", about=None):
        """Pay credits to another gang and journal both sides atomically.

        The payer records a positive spend delta. The recipient's nested
        operation records the receipt and repins its totals. Settlement rolls
        back both sides if the payer would overspend. Unlimited-budget gangs
        record events without changing an available-credit balance.

        ``to=None`` records a payment outside Gyrinx. ``about`` optionally names
        the model concerned. Include ``to`` in the enclosing operation's ``also``
        gangs so both locks are acquired in a consistent order.
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

    def receive_credits(self, amount, note):
        """Record signed income, including an exact correction of an earlier receipt."""
        if not amount:
            return None
        if not note.strip():
            raise Refusal("Enter a reason for the credits.")
        return self.event(
            None, LedgerEvent.Kind.INCOME, credits_delta=-amount, note=note[:255]
        )

    def adjust_credits(self, amount, note=""):
        """Add credits (positive) or remove them (negative) by hand.

        ``settle`` refuses a removal that would leave a gang with a budget
        below zero. A gang with unlimited credits records it and counts
        nothing.
        """
        if not amount:
            raise Refusal("Enter a number of credits.")
        return self.event(
            None,
            LedgerEvent.Kind.CREDITS_ADJUSTED,
            credits_delta=-amount,
            note=note.strip()[:255],
        )

    def clean_house(self):
        """Return every model In Recovery to Active and return the changed models.

        Their events share this operation's batch and form one history entry.
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
        """Rename this operation's gang and record both names in its history."""
        gang = self.gang
        was = gang.name
        if was == name:
            return gang
        gang.name = name
        gang.save(update_fields=["name", "modified"])
        self.event(None, LedgerEvent.Kind.RENAMED, note=f"{was} → {name}"[:255])
        return gang

    def set_budget(self, credits):
        """Change the gang's credit budget and journal both values.

        ``credits=None`` means unlimited. Settlement recomputes the remaining
        balance and rejects a budget below existing spending.

        When setting a budget on an unlimited-budget gang, adjust recorded spend
        to current wealth so sold or deleted possessions do not consume the new
        budget. Changes between finite budgets retain the existing spending total.
        """
        from n26.core.reconcile import total_spent

        gang = self.gang
        was = gang.starting_credits
        if was == credits:
            return gang
        opening = 0
        if was is None and credits is not None:
            stash = getattr(gang, "stash", None)
            held = gang.recompute_rating() + (
                stash.recompute_rating() if stash is not None else 0
            )
            opening = held - total_spent(gang)
        gang.starting_credits = credits
        gang.save(update_fields=["starting_credits", "modified"])
        self.event(
            None,
            LedgerEvent.Kind.BUDGET_SET,
            note=f"{_budget_word(was)} → {_budget_word(credits)}"[:255],
            credits_delta=opening,
        )
        return gang

    def _refuse_if_open(self, kind, miniature=None):
        """Refuse a second open activity of the same kind under the gang lock.

        Purchases must refer unambiguously to the activity they count against.
        """
        already = self.gang.open_activity(kind, miniature)
        if already is not None:
            raise Refusal(
                f"Complete the open {already.get_kind_display()} activity "
                "before starting another."
            )

    def open_activity(self, kind, trade_points=None, *, miniature=None):
        """Open an activity and record its starting Trade Points in the journal.

        The activity references its opening event. Purchases record the activity
        whose allowance they use; opening it moves no money.
        """
        from n26.core.models import Activity
        from n26.core.models.activity import note_for

        gang = self.gang
        if (kind == Activity.Kind.HIRE_TIME) != (miniature is not None):
            raise ValueError("Only hire-time activities have a model target.")
        if miniature is not None and miniature.membership.gang_id != gang.pk:
            raise Refusal("That model does not belong to this gang.")
        self._refuse_if_open(kind, miniature)
        opened = self.event(
            miniature,
            LedgerEvent.Kind.ACTION_OPENED,
            note=note_for(kind, trade_points),
        )
        activity = Activity.objects.create(
            gang=gang,
            kind=kind,
            opened=opened,
            trade_points=trade_points,
            miniature=miniature,
        )
        gang.forget_open_activities()
        return activity

    def close_activity(self, activity):
        """Close this gang's activity and record its remaining Trade Points.

        Reload under the gang lock to prevent duplicate closing events. An
        already closed activity, or one belonging to another gang, returns None.
        Closing allows a new activity of the same kind to open.
        """
        from n26.core.models import Activity
        from n26.core.models.activity import note_for
        from n26.core.reconcile import trade_points_spent_for

        fresh = (
            Activity.objects.filter(pk=activity.pk, gang=self.gang, closed__isnull=True)
            .select_related("miniature")
            .first()
        )
        if fresh is None:
            return None
        left = None
        if fresh.trade_points is not None:
            left = fresh.trade_points - trade_points_spent_for(fresh)
        closed = self.event(
            fresh.miniature,
            LedgerEvent.Kind.ACTION_CLOSED,
            note=note_for(fresh.kind, left),
        )
        fresh.closed = closed
        fresh.save(update_fields=["closed", "modified"])
        self.gang.forget_open_activities()
        return fresh

    def start_hire_time_tp(self, miniature, *, reopen=False):
        """Enable one recruit's existing allowance, retaining lifetime spend."""
        from n26.core.card import build_card, build_modifier_index, carriers
        from n26.core.effects import compute
        from n26.core.founding import hire_time_states
        from n26.core.models import Activity

        miniature = Miniature.objects.select_related("membership").get(pk=miniature.pk)
        if miniature.membership.gang_id != self.gang.pk:
            raise Refusal("That model does not belong to this gang.")
        card = build_card(miniature)
        folded = compute(card, build_modifier_index(carriers(card)))
        state = hire_time_states(
            self.gang, [miniature], {str(miniature.pk): folded}
        ).get(str(miniature.pk))
        if state is None:
            raise Refusal("This model has no available hire-time Trade Points action.")
        if state.act == "finish":
            return None
        if (state.act == "reopen") != reopen:
            raise Refusal(
                "Reopen the completed action for correction to use its remaining Trade Points."
            )
        return self.open_activity(Activity.Kind.HIRE_TIME, miniature=miniature)

    def visit_trading_post(self, visitors=(), brought=None):
        """Open a Trading Post visit with these fighters and their Trade Points.

        A fighter can attend without contributing points. Each attendance event
        shares the opening event's batch. Purchases reference the visit to charge
        its allowance; closing it ends access to any remaining points.

        ``brought`` overrides the total contributed by the fighters.
        """
        from n26.core.models import Activity
        from n26.core.trading import minted

        kind = Activity.Kind.TRADING_POST_VISIT
        # A second open visit would make allowance attribution ambiguous.
        self._refuse_if_open(kind)
        going = [visitor for visitor in visitors if visitor.visiting]
        amount = minted(going) if brought is None else brought
        self.open_activity(kind, trade_points=amount)
        for visitor in going:
            self.event(
                visitor.miniature,
                LedgerEvent.Kind.VISITED_TRADING_POST,
                note=visitor.rank[:255],
            )
        return self.gang

    def leave_trading_post(self):
        """Close the current Trading Post visit and record its unused allowance.

        Purchases made without an open visit remain permitted after confirmation
        and count against no activity. A closed visit differs from an open visit
        with no remaining points. Return the gang whether or not a visit was open.
        With no open visit, write nothing. The enclosing gang lock prevents
        duplicate closing events.
        """
        from n26.core.models import Activity

        open_now = self.gang.open_activity(Activity.Kind.TRADING_POST_VISIT)
        if open_now is None:
            return self.gang
        self.close_activity(open_now)
        return self.gang

    def edit_notes(self, miniature, notes):
        """Save the model's notes and record that they changed.

        The journal omits the notes' contents.
        """
        return self._write_prose(miniature, "notes", notes, LedgerEvent.Kind.NOTED)

    def append_note(self, miniature, paragraph, note=""):
        """Append an HTML paragraph already escaped by the caller to the model's notes.

        The journal records ``note`` as the reason for the change without
        copying the paragraph.
        """
        miniature.refresh_from_db(fields=["notes"])
        miniature.notes = f"{miniature.notes}{paragraph}"
        miniature.save(update_fields=["notes", "modified"])
        self.event(miniature, LedgerEvent.Kind.NOTED, note=note)
        return miniature

    def edit_lore(self, miniature, lore):
        """Save the model's lore and journal the change without copying the prose."""
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
        """Save a gang or model's prose field and record the change.

        An unchanged value produces neither a save nor an event.
        """
        if getattr(subject, field) == value:
            return subject
        setattr(subject, field, value)
        subject.save(update_fields=[field, "modified"])
        about = subject if isinstance(subject, Miniature) else None
        self.event(about, kind)
        return subject

    def _write_picture(self, subject, upload, clear):
        """Replace or clear a gang or model's picture.

        Keep the old file in storage so previously shared image URLs still work.
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
        """Apply characteristic overrides and journal each changed value.

        ``changes`` contains ``(type_stat, value, said)`` tuples. An empty value
        clears the override; ``said`` is the history text. Overrides do not alter rating.
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

    def _close_hire_time_tp_for(self, assignment):
        """Leaving the roster ends a model's open spending opportunity."""
        from n26.core.models import Activity

        if assignment.gang_id is None or assignment.miniature_root_id is None:
            return
        model = Miniature.objects.filter(membership=assignment).first()
        if model is not None:
            active = self.gang.open_activity(Activity.Kind.HIRE_TIME, model)
            if active is not None:
                self.close_activity(active)

    def remove(self, assignment, note="", **event_fields):
        """Archive an assignment and its dependants, preserving their ledger history.

        Archived assignments stop contributing to rating. Entries retain their
        rating and expenditure. An archived root is a no-op; see
        :func:`_under_the_lock`.
        """
        assignment = _under_the_lock(assignment)
        if assignment.archived:
            return None
        descendant_event_fields = {
            key: value
            for key, value in event_fields.items()
            if key not in {"before_pick", "after_pick"}
        }
        for target in [assignment, *subtree(assignment)]:
            if target.archived:
                continue
            self._close_hire_time_tp_for(target)
            self.touched(target.miniature_root)
            target.archived = True
            target.archived_at = _now()
            target.save(update_fields=["archived", "archived_at", "modified"])
            self.event(
                target,
                LedgerEvent.Kind.REMOVED,
                note=note,
                **(
                    event_fields
                    if target.pk == assignment.pk
                    else descendant_event_fields
                ),
            )
        return assignment

    def restore(self, assignment, note="", **event_fields):
        """Restore this archived assignment without restoring its dependants.

        Callers restore each required assignment explicitly, since a dependant
        may have been removed independently. An already live assignment is a no-op.
        """
        assignment = _under_the_lock(assignment)
        if not assignment.archived:
            return None
        self.touched(assignment.miniature_root)
        assignment.archived = False
        assignment.archived_at = None
        assignment.save(update_fields=["archived", "archived_at", "modified"])
        self.event(assignment, LedgerEvent.Kind.RESTORED, note=note, **event_fields)
        return assignment

    def refund(self, assignment, note=""):
        """Archive the assignment's subtree and return its credits and Trade Points.

        Zero each refunded entry with a matching event so folding events still
        reproduces the entry. Assignments with no payment are simply removed.
        Trade Points return to the purchase's original activity; they cannot
        increase a later visit's allowance.

        An already archived root returns None; see :func:`_under_the_lock`.
        """
        assignment = _under_the_lock(assignment)
        if assignment.archived:
            return None
        rows, _ = refund_of(assignment)
        for target in rows:
            self._close_hire_time_tp_for(target)
            self.touched(target.miniature_root)
            target.archived = True
            target.archived_at = _now()
            target.save(update_fields=["archived", "archived_at", "modified"])

            entry = getattr(target, "ledger_entry", None)
            if entry is None or not (entry.paid or entry.trade_points):
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
        """Archive the sold subtree and return proceeds based on its total rating.

        Retained children are moved into the stash first. Record the entire
        payment on the root entry, reducing ``paid`` and adjusting ``discount``
        to preserve ``paid = list_price - discount``. Entries keep their rating
        contributions, which cease to count while archived.

        Return the credits received, or None for an archived root. See
        :func:`proceeds_for` and :func:`_under_the_lock`.
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
            # Record the entire subtree's proceeds on the root entry once.
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
        """Copy a model's current state into this operation's gang.

        Write fresh assignments and ledger openings without replaying stored
        acquisition effects.
        """
        from n26.core.cloning import (
            HoldingDependentClone,
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
        try:
            plan = plan_miniature_clone(source)
        except HoldingDependentClone:
            raise Refusal(
                f"{source.name} cannot be cloned while it belongs to a holding's choice."
            ) from None
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
        from n26.core.card import advancement_rated
        from n26.core.models import (
            AssignmentSet,
            ChosenProfileOption,
            PrintConfig,
            StatOverride,
        )

        assignment_map = {}
        miniature_map = {}
        memberships = {model.membership_id for model in plan.miniatures}
        rating_overrides = dict(
            LedgerEvent.objects.filter(
                assignment_id__in=memberships,
                kind__in=[LedgerEvent.Kind.RATING_SET, LedgerEvent.Kind.RATING_RESET],
            )
            .values("assignment_id")
            .annotate(total=Sum("rating_delta"))
            .values_list("assignment_id", "total")
        )
        planned = {assignment.pk for assignment in plan.assignments}
        # A clone copies no advancement records, which would count towards
        # eligibility and allow undo. Its ledger entries keep the receipt's
        # Advancements line instead.
        from_advancement = set(
            Assignment.objects.filter(advancement_rated(), pk__in=planned).values_list(
                "pk", flat=True
            )
        )
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
            self._clone_ledger(
                source,
                clone,
                neutral=source.pk in plan.neutral,
                rating_override=rating_overrides.get(source.pk, 0),
                from_advancement=source.pk in from_advancement,
            )

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
                self.open_counter(clone, counter.value)

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
                orientation=source_config.orientation,
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

        from n26.core.allowances import clone_unused_allowances

        for source in plan.miniatures:
            clone_unused_allowances(self, source, miniature_map[source.pk])

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

    def _clone_ledger(
        self, source, clone, *, neutral=False, rating_override=0, from_advancement=False
    ):
        """Give a cloned assignment a fresh opening and its rating override."""
        from n26.core.cloning import CLONED_RATING_NOTE_PREFIX

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
        if neutral:
            rating_override = 0
        baseline = values["rating_contribution"] - rating_override
        if not -(2**31) <= baseline < 2**31:
            raise Refusal(
                "You cannot clone this model. Its base rating without an override "
                "is outside the supported range."
            )
        LedgerEntry.objects.create(
            assignment=clone, cloned_from_advancement=from_advancement, **values
        )
        self.event(
            clone,
            LedgerEvent.Kind.CLONED,
            credits_delta=values["paid"],
            trade_points_delta=values["trade_points"],
            rating_delta=baseline,
        )
        # The difference between two integer contributions can need several deltas.
        while rating_override:
            delta = max(-(2**31), min(2**31 - 1, rating_override))
            self.event(
                clone,
                LedgerEvent.Kind.RATING_SET,
                rating_delta=delta,
                note=f"{CLONED_RATING_NOTE_PREFIX}{baseline}|{baseline + delta}",
            )
            baseline += delta
            rating_override -= delta

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
        from n26.core.allowances import grant_recruitment_allowances

        grant_recruitment_allowances(self, miniature)
        return miniature

    def found(self, gang_type, taken=(), **kwargs):
        """Create the gang's free founding assignment and its built-ins.

        The gang-hosted carrier supplies equipment lists and gang-wide modifiers.
        The gang's budget is stored separately from the founding's ledger entry.
        """
        from n26.core.models import Stash

        founding = self.assign(gang_type, gang=self.gang, paid=0, **kwargs)
        self.gang.founding = founding
        self.gang.save(update_fields=["founding", "modified"])
        Stash.objects.get_or_create(gang=self.gang)
        # Spend founding TP is not opened here. Most gangs never use it, so
        # the owner starts it from the Actions square when they want it.
        self._record_options(founding, taken)
        self.reconcile_defaults(founding, gang=self.gang)
        return founding

    def refound(self, gang_type):
        """Change the gang type while preserving the founding's identity and history.

        Update the existing founding assignment so its ledger entry and events
        survive. A gang without a founding uses ordinary founding.

        Refuse if the founding has any caused assignments or recorded option
        selections. This operation does not remove or refund them.
        """
        from n26.core.models import Stash

        # Validate before mutating the instance, which callers may retain
        # after catching a refusal.
        founding = self.gang.founding
        if founding is not None and (
            founding.caused.exists() or founding.chosen_options.exists()
        ):
            raise Refusal(
                f"You cannot change {self.gang}'s type. Its founding type gave "
                "it things, and those would have to be given back first."
            )
        # Keep the gang type and founding assignment consistent.
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
        """Replace an assignment's selected option sets and adjust its price.

        Resolve defaults and validate the selection as at acquisition. An unchanged
        selection is a no-op. Refund departing sets and paid descendants; create
        arriving sets as free dependants, retaining the built-ins.

        Apply the price difference to payment, list price and rating on the
        carrier's entry, preserving its discount. Settlement rolls back an
        unaffordable upgrade.
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
            for granted in option_grants(carrier, row.default_set):
                self.refund(
                    granted, note=note or f"No longer takes {row.default_set.name}"
                )
            row.delete()
        arriving = [chosen for chosen in taken if chosen.pk not in before_pks]
        # Founding grants belong to the gang; membership grants belong to
        # its model even though the membership itself is gang-hosted.
        gang = (
            carrier.gang
            if carrier.miniature_root_id is None and carrier.gang_id is not None
            else None
        )
        self._record_options(carrier, arriving)
        # Newly selected sets must recreate kit archived when a previous
        # selection of the same set was removed.
        self.reconcile_defaults(carrier, gang=gang, built_ins=False, fresh=arriving)

        delta = sum(chosen.price for chosen in taken) - sum(
            chosen.price for chosen in before
        )
        if delta:
            entry = getattr(carrier, "ledger_entry", None)
            if entry is not None:
                entry.refresh_from_db()
                if not -(2**31) < entry.rating_contribution + delta < 2**31:
                    raise Refusal(
                        "You cannot take this option. The resulting base rating is outside "
                        "the range -2147483647¢ to 2147483647¢."
                    )
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

    def _record_options(self, carrier, taken):
        """Record selected sets before reconciling their members.

        The reconciliation plan reads these records to determine required copies.
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
        """Materialise missing built-ins and selected options for a carrier.

        ``carrier`` is the acquisition assignment, such as a membership or founding.
        Its recorded selections determine the required sets. A copy with matching
        member and carrier provenance satisfies a requirement even when archived,
        preventing automatic replacement of equipment the owner removed. Satisfied
        members never call ``assign`` or repeat stored effects.

        Non-ammunition grants are caused by their carrier and hosted on its model
        or stash root. Pass ``gang`` for gang-hosted carriers without a model,
        such as a founding. Process ammunition after weapons:
        ``gun_member`` identifies an exact weapon copy, while unanchored ammunition
        uses the newest live matching weapon on the host. Missing weapons raise
        content errors during acquisition (``strict``) and become skips during repair.

        A slot member may include a starting pick. Write it through ordinary
        choosing, and preserve an already resolved slot's selection.

        ``kinds`` limits grant kinds, defaulting to the carrier's role. A Legacy
        profile therefore grants lists without duplicating equipment. ``fresh``
        names newly selected sets, for which only live copies satisfy requirements.
        This permits reselecting an option whose previous copies were archived.

        ``event_kind`` overrides the grant event kind, allowing propagation to
        identify catch-up grants. ``omit`` contains member IDs already satisfied
        by another route; record these as skips without creating copies.

        Reconcile every created copy's own built-ins recursively. Each nested
        grant names its immediate carrier, preserving provenance for later
        propagation. Cyclic content raises during strict acquisition and is
        recorded as a skip during repair.
        """
        from n26.core.builtins import (
            ReconcileOutcome,
            copies_of,
            kinds_for,
            plan_defaults,
        )
        from n26.core.models import Reason
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
            # Stashed carriers grant option equipment into the stash. Spawned models
            # still join the gang's roster.
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
                # Starting picks use the slot's configured destination.
                self._choose_for_slot(assignment, assignable, member.default_pickable)
            elif member.counter_id is not None:
                # A counter opens at its member's amount — Starting XP.
                self.open_counter(assignment, member.amount)

        for entry in ammo:
            if entry.satisfied:
                continue
            member = entry.member
            weapon_profile = member.assignable
            if member.gun_member_id is not None:
                # Anchored ammunition targets the exact live weapon copy recorded for
                # this set member and carrier.
                gun = (
                    copies_of(member.gun_member, carrier, include_archived=False)
                    .order_by("-pk")
                    .first()
                )
            else:
                # Unanchored ammunition may use any matching weapon on the host,
                # including one supplied by another set.
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
                    # Ammunition without a matching weapon is invalid content.
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
            # The weapon is the cause and host. Provenance still records
            # the set member and carrier that supplied the ammunition.
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
        # Reconcile nested built-ins after every copy, including ammunition,
        # has been created.
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
        """Create a free selection linked to the choice that provided it.

        ``anchor`` is the source assignment, or the stored root of a computed
        grant chain. ``slot`` and ``offer`` distinguish multiple choices from
        that source. The selection records ``chosen_for`` and is caused by the
        anchor, so removing the source removes its selection.

        A mismatched assignable kind raises ``NotOnOffer``. Narrowed picklists
        inform the picker without preventing an owner from selecting off-list.

        A campaign holding may anchor a gang-level slot during its current
        ownership period. Such picks reference the holding instead of an
        assignment cause. Acquire ``campaign_operation`` before ``operation``.
        """
        from n26.core import select
        from n26.library.models import Slot
        from n26.library.models.modifier import OffersChoice

        if isinstance(anchor, CampaignAsset):
            if slot is None or offer is not None:
                raise ValueError("A holding choice needs a Slot.")
            self._check_holding_choice(anchor, slot)
            return self._choose_for_slot(anchor, slot, chosen, **kwargs)

        # The object may predate removal of its carrier, including a lost
        # holding's root pick. Never create a new choice below archived state.
        try:
            anchor.refresh_from_db(
                fields=[
                    "archived",
                    "gang_root",
                    "gang",
                    "miniature",
                    "stash",
                    "parent",
                    "miniature_root",
                    "stash_root",
                ]
            )
        except Assignment.DoesNotExist:
            raise Refusal("That choice is no longer available.") from None
        if anchor.archived or anchor.gang_root_id != self.gang.pk:
            raise Refusal("That choice is no longer available.")

        from n26.core.action_records import battle_action_for_slot
        from n26.core.allowances import require_allowance_available

        battle_action = battle_action_for_slot(
            anchor, record=kwargs.get("action_record")
        )
        if battle_action is not None:
            require_allowance_available(battle_action.allowance)
            if getattr(kwargs.get("action_record"), "pk", None) != battle_action.pk:
                raise Refusal("Choose this result through its earned action flow.")

        if offer is None:
            # Infer the slot from its assignment when no offer was supplied.
            if slot is None and isinstance(anchor.assignable, Slot):
                slot = anchor.assignable
            if slot is not None:
                return self._choose_for_slot(anchor, slot, chosen, **kwargs)
        if kwargs.get("roll") is not None:
            # Rolls belong to slot tables; supplying one for an offer is a caller error.
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
        # Use the offer's destination, defaulting to its bearer. An explicit host
        # selects the recipient of a gang-carried offer scoped to individual models.
        # The cause still links the selection to its source for recursive removal.
        if not any(key in kwargs for key in ("miniature", "gang", "stash", "parent")):
            if any(
                offer.will_be_assigned_to == OffersChoice.WillBeAssignedTo.GANG
                for offer in matched
            ):
                kwargs |= {"gang": anchor.gang or anchor.gang_root}
            else:
                # Resolve the bearer, stash, then gang, matching _choose_for_slot.
                bearer = anchor.miniature or anchor.member_or_none()
                if bearer:
                    kwargs |= {"miniature": bearer}
                elif anchor.stash_id or anchor.stash_root_id:
                    kwargs |= {"stash": anchor.stash or anchor.stash_root}
                else:
                    kwargs |= {"gang": anchor.gang or anchor.gang_root}
        settled = offer or (matched[0] if len(matched) == 1 else None)
        if settled is not None:
            _clear_dismissal(anchor, settled, kwargs)
        return self.assign(
            chosen,
            caused_by=kwargs.pop("caused_by", anchor),
            # Preserve offer identity when an assignment provides multiple choices
            # of the same kind.
            chosen_for_offer=settled,
            paid=0,
            reason=Reason.GRANTED,
            **kwargs,
        )

    def _choose_for_slot(self, anchor, slot, chosen, roll=None, **kwargs):
        """Write a slot selection with its source, destination and optional roll.

        The assignment and slot together identify the choice. Require matching
        slot types, while allowing pickables outside the displayed picklist.

        Use the slot's configured host unless the caller supplies one. A choice
        in the stash keeps its pick with its item so they move together.

        ``roll`` must identify an unused roll for this gang, model and choice.
        Archived picks release their roll. Do not enforce the rolled table result:
        rules can substitute results, and the journal retains both roll and pick.

        Free picks may contribute their pickable's ``rating_contribution``.
        Gang-hosted picks add no rating. An explicit ``rating`` overrides the default.
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
        holding = isinstance(anchor, CampaignAsset)
        if holding:
            if any(key in kwargs for key in ("miniature", "parent", "stash")):
                raise ValueError("A holding's pick belongs to its gang.")
            kwargs["gang"] = self.gang
        elif not any(key in kwargs for key in ("miniature", "gang", "stash", "parent")):
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
            gang = self.gang if holding else anchor.gang or anchor.gang_root
            host = kwargs.get("miniature")
            if roll.gang_id != gang.pk or roll.miniature_id != (
                host.pk if host is not None else None
            ):
                raise Refusal(
                    "That roll was made for a different card. "
                    "Roll again for this choice."
                )
            if roll.campaign_asset_id != (anchor.pk if holding else None) or (
                holding and roll.holding_revision != anchor.ownership_revision
            ):
                raise Refusal(
                    "That roll was made for a different holding. Roll again for this choice."
                )
        if kwargs.get("rating") is None:
            from n26.core.choice_ratings import rating_for_pick

            # Rating is what the models are worth, and a gang-hosted
            # assignment carries none of its own: a pick the gang holds
            # adds nothing, whatever its pickable says.
            kwargs["rating"] = (
                0
                if kwargs.get("gang") is not None
                else rating_for_pick(slot, chosen, record=kwargs.get("action_record"))
            )
        host = kwargs.get("miniature")
        if slot.follows_status:
            if host is None:
                raise ValueError("A status choice belongs to a model.")
            host.refresh_from_db(fields=["status", "status_revision"])
            if roll is not None and roll.status_revision != host.status_revision:
                raise Refusal(
                    "That roll does not match this status change. Roll again for this choice."
                )
            kwargs.setdefault("chosen_for_status_revision", host.status_revision)
        _clear_dismissal(anchor, slot, kwargs)
        picked = self.assign(
            chosen,
            caused_by=kwargs.pop("caused_by", None if holding else anchor),
            chosen_for=None if holding else anchor,
            chosen_for_slot=slot,
            chosen_for_holding=anchor if holding else None,
            chosen_for_holding_revision=anchor.ownership_revision if holding else None,
            paid=0,
            reason=Reason.GRANTED,
            **({"kind": LedgerEvent.Kind.GRANTED} if holding else {}),
            **kwargs,
        )
        record = kwargs.get("action_record")
        if record is not None:
            context = record.recorded_ratings.get(
                str(slot.pk),
                {
                    "override": slot.pick_rating_override,
                    "picks": {},
                },
            )
            record.recorded_ratings = {
                **record.recorded_ratings,
                str(slot.pk): {
                    **context,
                    "picks": {
                        **context["picks"],
                        str(chosen.pk): picked.ledger_entry.rating_contribution,
                    },
                },
            }
            record.save(update_fields=["recorded_ratings", "modified"])
        return picked

    def _check_holding_choice(self, holding, slot):
        """Revalidate a holding while its campaign and gang are locked.

        Callers take campaign_operation before operation, matching every
        ownership writer. A submitted ownership revision never follows an
        asset into a new holding period.
        """
        current = (
            CampaignAsset.objects.select_related("holder", "campaign")
            .filter(pk=holding.pk)
            .first()
        )
        if (
            current is None
            or not current.held
            or current.holder.gang_id != self.gang.pk
            or current.campaign.archived
            or current.ownership_revision != holding.ownership_revision
        ):
            raise Refusal(
                "You cannot choose for this holding. Its ownership has changed."
            )
        if not any(
            choice.slot.pk == slot.pk for choice in self._holding_choices(current)
        ):
            raise Refusal("That choice is no longer available for this holding.")

    def remove_holding_picks(self, holding):
        """Archive one ownership period's picks through ordinary removal."""
        roots = Assignment.with_assignables(
            Assignment.objects.filter(
                gang_root=self.gang,
                chosen_for_holding=holding,
                chosen_for_holding_revision=holding.ownership_revision,
                archived=False,
            )
        ).order_by("created", "pk")
        for pick in roots:
            self.remove(pick)

    def replace_slot_pick(
        self,
        anchor,
        slot,
        chosen,
        *,
        previous_pick,
        miniature,
        action_record,
        roll=None,
        rating=None,
    ):
        """Archive one slot pick and retain exact before/after provenance."""
        anchor, miniature = _slot_context_under_the_lock(
            self.gang,
            anchor,
            slot,
            miniature,
            "That augmentation has changed. Review it again.",
        )
        if previous_pick is not None:
            previous_pick = _under_the_lock(previous_pick)
            if (
                previous_pick.archived
                or previous_pick.gang_root_id != self.gang.pk
                or previous_pick.chosen_for_id != anchor.pk
                or previous_pick.chosen_for_slot_id != slot.pk
                or previous_pick.miniature_root_id != miniature.pk
            ):
                raise Refusal("That augmentation has changed. Review it again.")
            self.remove(
                previous_pick,
                action_record=action_record,
                before_pick=previous_pick,
            )
        replacement = None
        if chosen is not None:
            replacement = self.choose(
                anchor,
                chosen,
                slot=slot,
                miniature=miniature,
                action_record=action_record,
                roll=roll,
                rating=rating,
            )
        if replacement is not None or previous_pick is not None:
            self.event(
                replacement or previous_pick,
                LedgerEvent.Kind.AMENDED,
                action_record=action_record,
                before_pick=previous_pick,
                after_pick=replacement,
            )
        return replacement

    def restore_slot_pick(
        self,
        anchor,
        slot,
        *,
        restore_pick,
        replacing,
        miniature,
        action_record,
    ):
        """Restore the exact archived pick replaced by an earlier action."""
        message = "That augmentation has changed and cannot be restored."
        anchor, miniature = _slot_context_under_the_lock(
            self.gang,
            anchor,
            slot,
            miniature,
            message,
        )
        restore_pick = _under_the_lock(restore_pick)
        replacing = _under_the_lock(replacing)
        if (
            not restore_pick.archived
            or replacing.archived
            or restore_pick.gang_root_id != self.gang.pk
            or replacing.gang_root_id != self.gang.pk
            or restore_pick.chosen_for_id != anchor.pk
            or restore_pick.chosen_for_slot_id != slot.pk
            or replacing.chosen_for_id != anchor.pk
            or replacing.chosen_for_slot_id != slot.pk
            or restore_pick.miniature_root_id != miniature.pk
            or replacing.miniature_root_id != miniature.pk
            or Assignment.objects.filter(
                chosen_for=anchor,
                chosen_for_slot=slot,
                archived=False,
            )
            .exclude(pk=replacing.pk)
            .exists()
        ):
            raise Refusal(message)
        self.remove(
            replacing,
            action_record=action_record,
            before_pick=replacing,
        )
        restore_pick.unarchive()
        self.touched(miniature)
        self.event(
            restore_pick,
            LedgerEvent.Kind.AMENDED,
            action_record=action_record,
            before_pick=replacing,
            after_pick=restore_pick,
        )
        return restore_pick

    def add_legacy_profile(self, miniature, profile, **kwargs):
        """Associate a Legacy profile with a model and grant its equipment lists.

        The association grants no weapons, subtypes or other default equipment.
        """
        assignment = self.assign(profile, miniature=miniature, **kwargs)
        ProfileRole.objects.create(assignment=assignment, role=ProfileRole.Role.LEGACY)
        # The Legacy role narrows what reconciling grants to the lists
        # alone (``n26.core.builtins.kinds_for``), so it is written first.
        self.reconcile_defaults(assignment)
        return assignment

    def give_weapon(self, miniature, weapon, paid=0, free_profiles=True, **kwargs):
        """Assign a weapon to a model, copying its free profiles onto it
        and materialising what it has built in."""
        assignment = self.assign(weapon, miniature=miniature, paid=paid, **kwargs)
        if free_profiles:
            self._grant_free_profiles(weapon, assignment)
        if weapon.built_ins_id is not None:
            self.reconcile_defaults(assignment)
        return assignment

    def _grant_free_profiles(self, weapon, assignment, sold_separately=frozenset()):
        """Grant a weapon's free profiles on every acquisition path.

        Exclude ``sold_separately`` profile IDs, which the purchase's listing
        prices independently. Including them would grant paid ammunition for free
        and duplicate it when subsequently bought.
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
        activity=None,
        option=None,
        **kwargs,
    ):
        """Buy an assignable using listing defaults or explicit purchase terms.

        ``line`` supplies the item, effective credits, Trade Points and source
        entry; callers may override those values. Without a line, ``thing`` and
        an explicit price support off-list purchases.

        ``option`` selects option sets. Materialise these and built-ins as
        purchase dependants. Compose the price from the item's base or listing
        override, built-ins and selected sets.

        ``activity`` identifies the allowance charged, or None for an untracked
        purchase. Record the buyer so model-specific spending remains attributed
        when equipment moves.

        ``holder`` may be a model, stash or parent assignment. A weapon keeps
        its free profiles in the stash; paid ammunition attaches to its weapon.
        """
        from n26.core.models import Activity, Assignment, Stash
        from n26.library.models import Weapon
        from n26.library.models.collection import price_of

        if isinstance(holder, Stash):
            # Stash purchases do not spend a model's allowance.
            host, buyer = {"stash": holder}, None
        elif isinstance(holder, Assignment):
            # Charge paid ammunition to the model carrying its weapon.
            host, buyer = {"parent": holder}, holder.miniature_root
        else:
            host, buyer = {"miniature": holder}, holder

        if activity is not None and activity.kind in (
            Activity.Kind.FOUNDING,
            Activity.Kind.HIRE_TIME,
        ):
            from n26.core.founding import personal_activity_for

            active = (
                personal_activity_for(self.gang, buyer) if buyer is not None else None
            )
            if active is None or active.pk != activity.pk:
                raise Refusal(
                    "This spending action has changed. Reload the page before buying."
                )

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
                # Entry overrides replace only the item's base price.
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
            activity=activity,
            # Attribute a buyer only when an activity allowance was used.
            spent_by=buyer if activity is not None else None,
            **host,
            **kwargs,
        )
        if isinstance(thing, Weapon):
            self._grant_free_profiles(
                thing, bought, sold_separately=_sold_separately(line, entry, thing)
            )
        if hasattr(thing, "resolve_selection"):
            self._record_options(bought, taken)
        # Skip reconciliation queries when there are no built-ins or
        # selected option sets.
        if getattr(thing, "built_ins_id", None) is not None or taken:
            self.reconcile_defaults(bought)
        return bought

    def select(self, miniature, thing, note=""):
        """Grant an earned skill or power and record its reference rating.

        No credits move. The assignment has no cause, so removing a profile or
        other source of access to its collection does not remove the selection.
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

    def roll(
        self,
        slot,
        *,
        miniature=None,
        campaign_asset=None,
        rolled=None,
        rng=None,
        note="",
        dice=None,
        action_record=None,
    ):
        """Record a choice's table roll before a result is selected.

        The event identifies the gang, model and slot so a subsequent selection
        can validate its origin. ``rolled`` supplies a manual result and must be
        valid for the die. ``rng`` allows deterministic tests.

        A slot without a roll table raises a caller error.
        """
        from n26.library.models import Dice

        if campaign_asset is not None:
            if miniature is not None:
                raise ValueError("A holding roll belongs to the gang.")
            self._check_holding_choice(campaign_asset, slot)
        picklist = slot.picklist
        if not picklist.dice:
            raise ValueError(f"{slot.choice_label} is not rolled for.")
        configured_dice = Dice(picklist.dice)
        if dice is not None and Dice(dice) != configured_dice:
            raise Refusal(
                f"{slot.choice_label} uses a {configured_dice.label}, not a "
                f"{Dice(dice).label}."
            )
        dice = configured_dice
        if rolled is None:
            rolled = Dice.roll(dice, rng)
        elif rolled not in Dice.rolls(dice):
            raise Refusal(f"You cannot roll {rolled} on a {dice.label}.")
        else:
            note = note or ROLL_ENTERED
        status_revision = None
        if slot.follows_status:
            if miniature is None:
                raise ValueError("A status choice belongs to a model.")
            miniature.refresh_from_db(fields=["status_revision"])
            status_revision = miniature.status_revision
        return self.event(
            campaign_asset if campaign_asset is not None else miniature,
            LedgerEvent.Kind.ROLLED,
            holding_revision=campaign_asset.ownership_revision
            if campaign_asset
            else None,
            status_revision=status_revision,
            roll=rolled,
            dice=dice.value,
            slot=slot,
            note=note,
            action_record=action_record,
        )

    def track_progression_counter(self, fighter, counter_id):
        from n26.core.allowances import track_progression_counter

        return track_progression_counter(self, fighter, counter_id)

    def tally(self, assignment, change, note="", **event_fields):
        """Change a counter, respecting its minimum, and journal the actual movement.

        ``change`` is signed. ``note`` supplies the reason for the adjustment.
        """
        from n26.core.models import CounterValue, LedgerEvent

        try:
            held = CounterValue.objects.get(assignment=assignment)
        except CounterValue.DoesNotExist:
            held = self.open_counter(assignment, 0)
        before = held.value
        held.value = max(assignment.counter.minimum, held.value + change)
        held.save(update_fields=["value", "modified"])
        # Record the actual movement after applying the counter's minimum.
        moved = f"{held.value - before:+d} → {held.value}"
        amounts = (
            {
                "counter_before": before,
                "counter_delta": held.value - before,
                "counter_after": held.value,
            }
            if self.counter_tracking_active
            else {}
        )
        self.event(
            assignment,
            LedgerEvent.Kind.TALLIED,
            note=_movement_note(moved, note),
            **amounts,
            **event_fields,
        )
        from n26.core.allowances import grant_rank_allowances

        grant_rank_allowances(self, assignment, before, held.value)
        return held.value

    def record_action_roll(
        self,
        record,
        configured,
        request_key,
        *,
        rolled=None,
        rng=None,
        decline_promotion=False,
        previous_roll=None,
    ):
        from n26.core.advancements import record_action_roll

        return record_action_roll(
            self,
            record,
            configured,
            request_key,
            rolled=rolled,
            rng=rng,
            decline_promotion=decline_promotion,
            previous_roll=previous_roll,
        )

    def record_skill_roll(
        self,
        record,
        configured,
        request_key,
        *,
        pickable_id,
        skill_set_id,
        rolled=None,
        rng=None,
    ):
        from n26.core.advancements import record_skill_roll

        return record_skill_roll(
            self,
            record,
            configured,
            request_key,
            pickable_id=pickable_id,
            skill_set_id=skill_set_id,
            rolled=rolled,
            rng=rng,
        )

    def start_action(self, fighter, action, request_key, allowance=None):
        """Start or resume one idempotent fighter action use."""
        from n26.core.action_records import start_action

        return start_action(self, fighter, action, request_key, allowance=allowance)

    def review_action(self, record, *, outcome, terms=None):
        """Capture the exact terms and balances offered for confirmation."""
        from n26.core.action_records import review_action

        return review_action(self, record, outcome=outcome, terms=terms)

    def save_action_choices(self, record, *, outcome, terms):
        """Persist incomplete typed choices so a draft resumes at the same step."""
        from n26.core.action_records import save_action_choices

        return save_action_choices(self, record, outcome=outcome, terms=terms)

    def complete_action(self, record, *, revision, review, outcome):
        """Verify and atomically pay for and apply a reviewed action use."""
        from n26.core.action_records import complete_action

        return complete_action(
            self, record, revision=revision, review=review, outcome=outcome
        )

    def cancel_action(self, record):
        """Cancel an unpaid action draft."""
        from n26.core.action_records import cancel_action

        return cancel_action(self, record)

    def apply_allowance_by_hand(self, fighter, action, request_key, allowance=None):
        """Settle an unused earned use the player applied outside Gyrinx."""
        from n26.core.action_records import start_action

        return start_action(
            self, fighter, action, request_key, allowance=allowance, by_hand=True
        )

    def apply_action_by_hand(self, record):
        """Settle a started earned-use flow the player applied outside Gyrinx."""
        from n26.core.action_records import apply_action_by_hand

        return apply_action_by_hand(self, record)

    def reopen_action(self, record):
        """Undo applied by hand, so the earned use is waiting again."""
        from n26.core.action_records import reopen_action

        return reopen_action(self, record)

    def undo_action(self, record, *, expected):
        """Undo an earned advancement and resume its original flow."""
        from n26.core.action_records import undo_action

        return undo_action(self, record, expected=expected)

    def review_action_correction(self, record, *, terms):
        """Capture exact completed-result state before a safe correction."""
        from n26.core.action_records import review_action_correction

        return review_action_correction(self, record, terms=terms)

    def correct_action(self, record, *, revision, review, terms):
        """Correct a completed typed result without replaying its payment."""
        from n26.core.action_records import correct_action

        return correct_action(
            self, record, revision=revision, review=review, terms=terms
        )

    def open_counter(self, assignment, value):
        """Store an opening balance, journalling it once tracking is active."""
        from n26.core.models import CounterValue, LedgerEvent

        if (
            self.counter_tracking_active
            and LedgerEvent.objects.filter(
                assignment=assignment, counter_before__isnull=False
            ).exists()
        ):
            raise Refusal(
                "You cannot edit this counter. "
                "Its value is missing, but its history already exists."
            )
        value = max(assignment.counter.minimum, value)
        held = CounterValue.objects.create(assignment=assignment, value=value)
        if self.counter_tracking_active:
            self.event(
                assignment,
                LedgerEvent.Kind.COUNTER_OPENED,
                counter_before=0,
                counter_delta=value,
                counter_after=value,
            )
        return held

    def reassign(self, assignment, to):
        """Redistribute equipment without transferring earned augmentations.

        Lifecycle operations use ``move`` directly so death, ransom and
        promotion can still leave equipment in the stash.
        """
        from n26.core.models import Assignment, Miniature
        from n26.core.tier_choices import augmentation_bound_items

        destination_fighter_id = (
            to.pk
            if isinstance(to, Miniature)
            else (to.miniature_root_id if isinstance(to, Assignment) else None)
        )
        if (
            assignment.miniature_root_id is None
            or assignment.miniature_root_id != destination_fighter_id
        ) and augmentation_bound_items([assignment, *subtree(assignment)]):
            raise Refusal(
                f"You cannot reassign {assignment.assignable}. "
                "It has earned augmentations that cannot be transferred."
            )

        return self.move(assignment, to)

    def move(self, assignment, to, note="", *, action_record=None):
        """Move an assignment and its subtree without repricing them.

        ``to`` may be a model, stash or parent assignment, such as a weapon
        receiving an accessory. Recompute denormalised roots and record a MOVED
        event. Weapon profiles cannot be detached from their weapon.
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
        # Sibling grants use the carrier's root host, including a weapon's
        # bearer when the carrier is an accessory.
        was_on = (assignment.miniature_root_id, assignment.stash_root_id)
        assignment.gang = None
        assignment.miniature = assignment.stash = assignment.parent = None
        if isinstance(to, Stash):
            assignment.stash = to
        elif isinstance(to, Miniature):
            assignment.miniature = to
        elif isinstance(to, Assignment):
            # Parent cycles prevent denormalised roots from being derived.
            if to.pk == assignment.pk or any(
                row.pk == to.pk for row in subtree(assignment)
            ):
                raise ValueError("Cannot attach something to itself.")
            assignment.parent = to
        else:
            raise ValueError(f"Cannot move something onto {to!r}.")
        assignment.save()
        # Move sibling grants only when they shared the carrier's old
        # host. Gang-held picks stay on the gang; attached parts derive
        # their new roots from the carrier.
        if isinstance(to, Assignment):
            host = (to.miniature_root, to.stash_root)
        else:
            host = (assignment.miniature, assignment.stash)
        for row in subtree(assignment):
            if (
                row.parent_id is None
                and row.gang_id is None
                and (row.miniature_id, row.stash_id) == was_on
            ):
                row.miniature, row.stash = host
            row.save()  # roots re-derive from the parent chain
        self.touched(assignment.miniature_root)
        self.event(
            assignment, LedgerEvent.Kind.MOVED, note=note, action_record=action_record
        )
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
        """Recompute touched ratings and the gang's available credits.

        Refuse rating overflow or overspend so the transaction rolls back all
        assignments, payments and events.
        """

        def repin_rating(thing):
            rating = thing.recompute_rating()
            if not -(2**31) <= rating < 2**31:
                raise Refusal(
                    "You cannot make this change. The resulting rating is outside "
                    "the range -2147483648¢ to 2147483647¢."
                )
            thing.rating = rating
            thing.save(update_fields=["rating", "modified"])

        for miniature in self._miniatures.values():
            repin_rating(miniature)
        if self.gang is not None:
            # The gang instance may outlive this operation; invalidate its cached
            # activities after an opening or closing.
            self.gang.forget_open_activities()
            stash = getattr(self.gang, "stash", None)
            if stash is not None:
                repin_rating(stash)
            repin_rating(self.gang)
            remaining = self.gang.recompute_credits()
            if remaining is not None and remaining < 0:
                raise NotEnoughCredits(self.gang, shortfall=-remaining)
            self.gang.repin_credits()


def _budget_word(credits):
    """A budget as the history says it: a figure, or no ceiling at all."""
    return "unlimited" if credits is None else f"{credits}¢"


def _reason_for(paid, caused_by):
    """Classify an acquisition by its cause and payment.

    A caused assignment is granted even when its paid amount is zero.
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
    """Reload an assignment and ledger entry after acquiring the gang lock.

    The caller may have loaded the assignment before another operation
    archived or refunded it. Removal methods check the fresh archive state
    to prevent duplicate refunds or sales. Descendants are queried afresh.
    """
    from n26.core.models import Assignment

    return Assignment.objects.select_related("ledger_entry").get(pk=assignment.pk)


def _slot_context_under_the_lock(gang, anchor, slot, miniature, message):
    """Reload and prove a slot edit belongs to the operation's gang."""
    anchor = _under_the_lock(anchor)
    miniature = Miniature.objects.select_related("membership").get(pk=miniature.pk)
    membership = miniature.membership if miniature.membership_id else None
    if (
        anchor.archived
        or anchor.gang_root_id != gang.pk
        or anchor.slot_id != slot.pk
        or anchor.miniature_root_id != miniature.pk
        or membership is None
        or membership.archived
        or membership.gang_id != gang.pk
    ):
        raise Refusal(message)
    return anchor, miniature


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
    """Return this weapon's profile IDs priced separately by the listing.

    A collection entry uses its collection's profile entries; a swept line
    uses its parts. Without a listing, return no exclusions from the free profiles.
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


def _clear_dismissal(anchor, identity, kwargs):
    """Clear the resolved choice's dismissal on its displayed host.

    Use the explicit recipient, carrier's model or root, then the gang host.
    Holding choices use their holding and slot identity instead.
    """
    from n26.core.models import DismissedOffer
    from n26.core.models.dismissed_offer import GANG_SLOT_HOST

    if isinstance(anchor, CampaignAsset):
        from n26.core.models.dismissed_offer import holding_slot_key

        DismissedOffer.objects.filter(
            gang=kwargs["gang"], slot_key=holding_slot_key(anchor, identity.pk)
        ).delete()
        return

    bearer = (
        kwargs.get("miniature")
        or anchor.miniature
        or anchor.member_or_none()
        or anchor.miniature_root
    )
    DismissedOffer.clear(
        anchor.gang or anchor.gang_root,
        host=str(bearer.pk) if bearer is not None else GANG_SLOT_HOST,
        anchor=anchor,
        identity=identity,
        status_revision=kwargs.get("chosen_for_status_revision"),
    )


def _hold(*gangs):
    """Lock all participating gangs in primary-key order until transaction end.

    All player-data writers acquire these locks before modifying assignments
    or totals. Consistent ordering prevents opposite-direction transfers from
    deadlocking on the same gangs.
    """
    from n26.core.models import Gang

    pks = sorted({gang.pk for gang in gangs if gang is not None and gang.pk})
    list(Gang.objects.select_for_update().filter(pk__in=pks).order_by("pk"))


def clone_gang(source, *, name, owner, actor=None):
    """Create an independent snapshot of one live gang.

    The source is locked while its plan is read.  A clone carries current
    possessions and current cash, not the source's past acts, campaign, or an
    open Visit Trading Post activity.
    """
    from n26.core.cloning import clone_event_note, plan_gang_clone
    from n26.core.models import Gang, Stash
    from n26.write_pause import write_guard

    with transaction.atomic(), write_guard():
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
        return clone


@contextmanager
def operation(gang, actor=None, batch=None, also=(), post_battle_revision=None):
    """Run player-data writes atomically and recompute cached totals on exit.

    ``also`` includes every other gang to be modified, such as a transfer
    recipient, so their locks are acquired together in primary-key order.
    """
    op = Operation(
        gang, actor=actor, batch=batch, post_battle_revision=post_battle_revision
    )
    from n26.write_pause import write_guard

    with transaction.atomic(), write_guard():
        if gang is not None and gang.pk is not None:
            _hold(gang, *also)
            # Refresh values loaded before locking so concurrent submissions
            # use the preceding operation's committed state.
            gang.refresh_from_db(fields=["starting_credits"])
            gang.forget_open_activities()
        yield op
        op.settle()
