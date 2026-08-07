"""Handlers for battles.

Ending a battle is the one part of the battle flow with real business logic:
it records who won (or that it was a draw), freezes what each crew fielded,
*and* advances the state machine, and those writes must not be able to come
apart. Everything else in the battle flow is simple CRUD and stays in the views.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils import timezone
from django.utils.html import format_html, format_html_join

from gyrinx.site.models import NotificationType, notify
from gyrinx.tracing import traced
from n23.core.handlers.crew import snapshot_played_crew_ratings
from n23.core.models.action import ListActionType
from n23.core.models.battle import Battle
from n23.core.models.campaign import CampaignAction

logger = logging.getLogger(__name__)

User = get_user_model()


@dataclass
class BattleEndResult:
    """Result of ending a battle."""

    battle: Battle
    is_draw: bool
    winners: list
    campaign_action: CampaignAction | None


@traced("handle_battle_end")
@transaction.atomic
def handle_battle_end(*, user, battle: Battle, winners, is_draw) -> BattleEndResult:
    """
    End a battle, recording its result.

    Sets ``winners`` (empty for a draw), marks how the battle finished, freezes
    what each locked crew fielded, moves the battle to post-battle, and writes a
    battle-linked CampaignAction. A battle that has already ended raises rather
    than recording a second result.
    """
    # Lock the battle row for the duration so two concurrent end POSTs
    # serialise: the second one sees post_battle and fails the guard cleanly.
    battle = (
        Battle.objects.select_for_update().select_related("campaign").get(pk=battle.pk)
    )
    if not battle.can_end():
        raise ValidationError("This battle has already been ended.")

    # Re-check participation under the lock: a gang may have been removed from
    # the battle between rendering the form and this POST.
    winners = [] if is_draw else list(winners)
    if not is_draw and not winners:
        # The form stops this, but the invariant belongs here: a "someone won"
        # result with nobody in it would record an empty "Winner:" outcome.
        raise ValidationError("Choose at least one winning gang, or record a draw.")
    if winners:
        participant_ids = set(battle.participants.values_list("pk", flat=True))
        for winner in winners:
            if winner.pk not in participant_ids:
                raise ValidationError(
                    f"{winner} cannot be a winner without being a participant."
                )

    battle.winners.set(winners)
    battle.result = Battle.RESULT_DRAW if is_draw else Battle.RESULT_WINNERS
    # Persist the result BEFORE transitioning: transition_to() saves with
    # update_fields=["status", "modified"], which would silently drop an
    # unsaved `result` from this instance.
    battle.save_with_user(user=user, update_fields=["result", "modified"])
    # Freeze what each crew fielded before the transition: from here on a crew
    # reports what fought rather than what the gang looks like today, and the
    # fighters must be read as they were at the end of the battle, not after
    # any post-battle spending.
    snapshot_played_crew_ratings(user=user, battle=battle)
    battle.states.transition_to(Battle.POST_BATTLE)

    if is_draw:
        outcome = "Draw"
    else:
        plural = "s" if len(winners) > 1 else ""
        outcome = f"Winner{plural}: " + ", ".join(sorted(w.name for w in winners))

    # Battle.campaign is a non-nullable FK, so there is always a campaign to log.
    # `list` stays null: a battle-level action has no single gang, matching the
    # battle-creation action. The description is a neutral headline so it can
    # never contradict the concrete result in `outcome`.
    campaign_action = CampaignAction.objects.create(
        user=user,
        owner=user,
        campaign=battle.campaign,
        battle=battle,
        description=f"Battle ended: {battle.mission}",
        outcome=outcome,
    )

    return BattleEndResult(
        battle=battle,
        is_draw=is_draw,
        winners=winners,
        campaign_action=campaign_action,
    )


def _join_gang_names(gangs):
    """A natural-language join of gang names ('A', 'A and B', 'A, B and C').

    Names are user content, so each is HTML-escaped by ``format_html*``.
    """
    if len(gangs) == 1:
        return format_html("{}", gangs[0].name)
    if len(gangs) == 2:
        return format_html("{} and {}", gangs[0].name, gangs[1].name)
    head = format_html_join(", ", "{}", ((g.name,) for g in gangs[:-1]))
    return format_html("{} and {}", head, gangs[-1].name)


def notify_battle_participants(*, user, battle, added_lists):
    """Notify each added gang's owner that their gang is taking part in a battle.

    Fans out **one notification per owner**, not per gang: a player who fields
    two gangs in the same battle gets a single notification naming both. This
    mirrors the per-owner aggregation in
    :func:`n23.core.cost.reconcile_notify.notify_lists_reconciled` and keeps
    the inbox free of near-duplicate rows.

    The acting user is never notified about their own action — an arbitrator
    adding another player's gang notifies that player, while a player adding
    their own gang notifies nobody about it (other players are still notified).

    Uses ``NotificationType.LIST``: the notification is about one of the
    recipient's own lists (their gang), links to it, and lands in that list
    owner's inbox — "something changed on your list". ``CAMPAIGN`` is framed for
    the arbitrator's perspective ("something in a campaign you arbitrate"), which
    is not who receives this. Creation goes through the safe ``notify()`` helper,
    so a notification failure can never break battle creation or editing.

    Args:
        user: the acting User (creator/editor), never notified about their own action.
        battle: the :class:`~n23.core.models.battle.Battle` (with ``campaign``).
        added_lists: the gangs newly added to the battle (List instances).

    Returns:
        The number of owners notified.
    """
    # Only other players' gangs, and only those with a real owner.
    lists = [lst for lst in added_lists if lst.owner_id and lst.owner_id != user.id]
    if not lists:
        return 0

    by_owner = defaultdict(list)
    for lst in lists:
        by_owner[lst.owner_id].append(lst)

    # One query for the recipient User objects rather than a lazy .owner per gang.
    owners = {u.id: u for u in User.objects.filter(pk__in=by_owner.keys())}

    campaign = battle.campaign
    battle_url = reverse("core:battle", args=[battle.id])

    notified = 0
    for owner_id, gangs in by_owner.items():
        owner = owners.get(owner_id)
        if owner is None:
            continue
        gangs = sorted(gangs, key=lambda g: g.name)
        multiple = len(gangs) > 1
        if multiple:
            subject = "Your gangs have been added to a battle"
            lead = format_html("Your gangs {} are", _join_gang_names(gangs))
        else:
            subject = "Your gang has been added to a battle"
            lead = format_html("Your gang {} is", gangs[0].name)
        content = format_html(
            '{} taking part in <a href="{}">{}</a>, a battle in the {} campaign.',
            lead,
            battle_url,
            battle.mission,
            campaign.name,
        )
        n = notify(
            recipient=owner,
            subject=subject,
            content=content,
            sender=user,
            notification_type=NotificationType.LIST,
            # A single-gang notification is about that gang, inside the campaign,
            # and links straight to it. A multi-gang one has no single gang to
            # point at, so the campaign itself becomes the subject.
            target=campaign if multiple else gangs[0],
            scope=None if multiple else campaign,
        )
        if n is not None:
            notified += 1

    return notified


def live_battle_crews(battle: Battle):
    """Crews of gangs still taking part in ``battle``.

    ``set_participants`` deletes the participant rows and leaves the crews
    behind, so every path that counts, charges or lists crews has to scope them
    this way. Doing it separately at each call site is how one of them ended up
    charging a gang that had been dropped, and another reporting "every gang
    picked a crew" on a battle with no gangs at all.
    """
    from n23.core.models.crew import Crew

    return Crew.objects.filter(
        battle=battle, archived=False, list__in=battle.participants.all()
    )


@dataclass
class CrewChargeResult:
    """What one crew's gang was charged when the battle started."""

    crew: object
    owed: int
    charged: int

    @property
    def shortfall(self) -> int:
        return self.owed - self.charged


@traced("charge_crew_spending")
@transaction.atomic
def charge_crew_spending(*, user, battle: Battle) -> list:
    """Take each crew's spending out of its gang's credits, once, at battle start.

    Only the Spending column moves: balancing is granted to the underdog rather
    than paid for, and free extras cost nobody anything.

    A gang that cannot cover its spending is charged what it has and floored at
    zero rather than taken negative — so the crew sheet and the ledger can
    disagree, and :meth:`Crew.credits_shortfall` is what makes that visible
    instead of leaving it to a campaign action nobody reads.

    ``spend_credits()`` is deliberately not used: it raises rather than paying
    what it can, which is the behaviour this flow rules out. Idempotent —
    ``credits_charged_at`` means a retried transition never charges twice.
    """

    crews = (
        live_battle_crews(battle)
        .select_for_update()
        .filter(credits_charged_at__isnull=True)
        .select_related("list")
        # spending_total() walks the line items for every crew; without this it
        # is a query each. The prefetch runs unlocked, which is fine — the row
        # locks that make the charge idempotent are on the crew and its gang.
        .prefetch_related("line_items")
    )

    results = []
    for crew in crews:
        owed = crew.spending_total()
        # One SELECT hydrates every crew.list, so these balances are all as they
        # stood before the loop began. That is safe only because a gang can hold
        # at most one live crew per battle (unique_crew_per_gang_per_battle) —
        # without that, two crews of the same gang would each charge against the
        # same starting balance and could overdraw it.
        available = max(0, crew.list.credits_current)
        charged = min(owed, available)

        if charged:
            # A ListAction pairs every credit movement in this codebase, and it
            # is not optional bookkeeping: cost/balance_sheet.py asserts that
            # the anchor's credits_before plus the sum of every credits_delta
            # equals credits_current, and checks each action's before-value
            # against the previous action's after-value. An unpaired
            # apply_credit_delta would leave a permanent ledger mismatch and a
            # broken chain for every gang that ever fought a battle.
            crew.list.create_action(
                user=user,
                action_type=ListActionType.UPDATE_CREDITS,
                description=f"Crew spending for {battle.name}",
                rating_delta=0,
                stash_delta=0,
                credits_delta=-charged,
                credits_before=crew.list.credits_current,
            )
            crew.list.apply_credit_delta(-charged, earned_delta=0)

        crew.credits_owed = owed
        crew.credits_charged = charged
        crew.credits_charged_at = timezone.now()
        crew.save_with_user(
            user=user,
            update_fields=["credits_owed", "credits_charged", "credits_charged_at"],
        )

        if owed:
            outcome = f"{charged}¢ charged"
            if charged < owed:
                outcome += f" of {owed}¢ — {owed - charged}¢ unpaid"
            CampaignAction.objects.create(
                user=user,
                owner=user,
                campaign=battle.campaign,
                list=crew.list,
                battle=battle,
                description=f"Crew spending charged for {crew.list.name}",
                outcome=outcome,
            )

        results.append(CrewChargeResult(crew=crew, owed=owed, charged=charged))

    return results


def battle_start_crew_rows(battle: Battle) -> list:
    """One row per live crew for the start-battle confirmation: who is ready,
    and what starting the battle will take from them."""

    rows = []
    for crew in (
        live_battle_crews(battle).select_related("list").prefetch_related("line_items")
    ):
        owed = crew.spending_total()
        will_pay = min(owed, max(0, crew.list.credits_current))
        rows.append(
            {
                "crew": crew,
                "gang": crew.list,
                "is_ready": crew.is_ready,
                "owed": owed,
                # What the gang can actually cover right now — the charge floors
                # at zero, so this is what it will really pay.
                "will_pay": will_pay,
                "unpaid": owed - will_pay,
            }
        )
    return rows


def battle_not_ready_gangs(battle: Battle) -> list:
    """Gangs holding the battle up, as ``{gang, reason}``, for the start warning.

    Covers two cases, not one: a gang whose crew is not marked ready, and a gang
    that has not picked a crew at all. Looking only at crews that exist would
    stay silent about the second, which is the more incomplete of the two.
    """

    crew_by_gang = {
        crew.list_id: crew for crew in live_battle_crews(battle).select_related("list")
    }
    blocking = []
    for gang in battle.participants.all():
        crew = crew_by_gang.get(gang.id)
        if crew is None:
            blocking.append({"gang": gang, "reason": "no crew picked"})
        elif not crew.is_ready:
            blocking.append({"gang": gang, "reason": "not marked ready"})
    return blocking


def battle_timeline(battle: Battle) -> list:
    """The battle process as ordered steps, each marked done / current / to do.

    Read-only: it reports where the battle has got to, it never advances
    anything. The first step that isn't done is the current one, so the list
    always has exactly one "you are here" — including on a battle that skipped
    a step (a crew that was never marked ready, say), where the step still reads
    as outstanding rather than silently vanishing.
    """

    participant_count = battle.participants.count()
    crews = list(live_battle_crews(battle).select_related("list"))
    state = battle.states.current
    started = state in (Battle.IN_PROGRESS, Battle.POST_BATTLE)
    ended = state == Battle.POST_BATTLE

    # Every gang has a crew. Readiness is measured against this rather than
    # against the crews that happen to exist: with one crew of two gangs, "all
    # crews are ready" is true and would light up a later step than the one the
    # battle is actually waiting on.
    crews_complete = bool(crews) and len(crews) >= participant_count

    steps = [
        {
            "label": "Gangs join the battle",
            "detail": "Add the gangs taking part, and give them roles if the scenario has any.",
            "done": participant_count > 0,
        },
        {
            "label": "Each gang picks a crew",
            "detail": "Who is eligible, who attends, what they bring from the stash, and what the gang spends.",
            "done": crews_complete,
        },
        {
            "label": "Gangs mark themselves ready",
            "detail": "A gang can only say ready once it can cover its crew's spending.",
            "done": crews_complete and all(c.is_ready for c in crews),
        },
        {
            "label": "The battle starts",
            "detail": "Spending is taken from each gang's credits, and crew membership is frozen.",
            "done": started,
        },
        {
            "label": "Play the battle",
            "detail": "Use each crew page to print fighter cards.",
            "done": ended,
        },
        {
            "label": "Record the result",
            "detail": "Who won, or that it was a draw.",
            "done": ended and battle.result_recorded,
        },
        {
            "label": "Post-battle updates",
            "detail": "XP, injuries, captures and credits, recorded by each gang.",
            "done": False,
        },
    ]

    current_marked = False
    for step in steps:
        if not step["done"] and not current_marked:
            step["current"] = True
            current_marked = True
        else:
            step["current"] = False
    return steps
