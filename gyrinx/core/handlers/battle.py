"""Handlers for battles.

Ending a battle is the one part of the battle flow with real business logic:
it records who won (or that it was a draw), freezes what each crew fielded,
*and* advances the state machine, and those writes must not be able to come
apart. Everything else in the battle flow is simple CRUD and stays in the views.
"""

import logging
from collections import defaultdict
from dataclasses import dataclass
from typing import Optional

from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.db import transaction
from django.urls import reverse
from django.utils.html import format_html, format_html_join

from gyrinx.core.handlers.crew import snapshot_played_crew_ratings
from gyrinx.core.models.battle import Battle
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.notification import NotificationType, notify
from gyrinx.tracing import traced

logger = logging.getLogger(__name__)

User = get_user_model()


@dataclass
class BattleEndResult:
    """Result of ending a battle."""

    battle: Battle
    is_draw: bool
    winners: list
    campaign_action: Optional[CampaignAction]


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
    :func:`gyrinx.core.cost.reconcile_notify.notify_lists_reconciled` and keeps
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
        battle: the :class:`~gyrinx.core.models.battle.Battle` (with ``campaign``).
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
            # A single-gang notification links straight to that gang; a
            # multi-gang one has no single list to point at, so it falls back to
            # the campaign (via related_campaign) for its inbox link.
            related_list=None if multiple else gangs[0],
            related_campaign=campaign,
        )
        if n is not None:
            notified += 1

    return notified
