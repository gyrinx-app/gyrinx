"""Handlers for battles.

Ending a battle is the one part of the battle flow with real business logic:
it records who won (or that it was a draw) *and* advances the state machine,
and those two writes must not be able to come apart. Everything else in the
battle flow is simple CRUD and stays in the views.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from gyrinx.core.models.battle import Battle
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.tracing import traced

logger = logging.getLogger(__name__)


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

    Sets ``winners`` (empty for a draw), marks how the battle finished, moves
    the battle to post-battle, and writes a battle-linked CampaignAction. A
    battle that has already ended raises rather than recording a second result.
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
