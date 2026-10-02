"""Handler for applying a lasting injury to a fighter and its default outcome.

The single-fighter add-injury view relies on client-side JS to pick the
resulting fighter state and bounces DEAD outcomes to a separate kill
confirmation. A bulk/headless caller can't do either, so this handler applies
the injury's default outcome (``ContentInjury.phase``) server-side and routes
DEAD through the real kill handler.
"""

import logging
from dataclasses import dataclass

from django.db import transaction

from gyrinx.tracing import traced
from n23.content.models import ContentInjury
from n23.content.models.injury import ContentInjuryDefaultOutcome
from n23.core.handlers.fighter.kill import handle_fighter_kill
from n23.core.models.campaign import CampaignAction
from n23.core.models.list import ListFighter, ListFighterInjury

logger = logging.getLogger(__name__)


@dataclass
class FighterAddInjuryResult:
    """Result of applying a lasting injury."""

    fighter: ListFighter
    injury: ListFighterInjury
    outcome_state: str
    killed: bool
    campaign_action: CampaignAction | None


@traced("handle_fighter_add_injury")
@transaction.atomic
def handle_fighter_add_injury(
    *,
    user,
    fighter: ListFighter,
    injury: ContentInjury,
    notes: str = "",
    battle=None,
) -> FighterAddInjuryResult:
    """
    Record a lasting injury on a fighter and apply its default outcome
    (``ContentInjury.phase``):

    - ``NO_CHANGE`` keeps the fighter's current state.
    - ``DEAD`` routes through :func:`handle_fighter_kill` so equipment moves to
      the stash, cost is zeroed and the list rating is propagated (a bare
      ``injury_state = DEAD`` would skip all of that).
    - Any other outcome sets ``injury_state`` directly.

    Writes a CampaignAction in campaign mode. Event logging (which needs the
    HTTP request) is the caller's responsibility, matching the project's
    view/handler layering.

    Args:
        user: The user applying the injury.
        fighter: The injured fighter.
        injury: The ContentInjury to apply.
        notes: Optional notes recorded on the injury and campaign log.
        battle: Optional Battle to attach the CampaignAction(s) to — including
            the death action when the outcome is DEAD.

    Returns:
        FighterAddInjuryResult.
    """
    lst = fighter.list

    # Injuries are a campaign-mode concept (ListFighterInjury.clean() enforces
    # this, but save_with_user()/create_with_user() don't run full_clean).
    # Guard here so the handler upholds its own invariant, mirroring
    # handle_fighter_kill's precondition check.
    if not lst.is_campaign_mode:
        raise ValueError("Injuries can only be applied in campaign mode")

    injury_record = ListFighterInjury.objects.create_with_user(
        user=user,
        fighter=fighter,
        injury=injury,
        notes=notes or "",
        owner=lst.owner,
    )

    killed = False
    outcome = injury.phase
    if outcome == ContentInjuryDefaultOutcome.DEAD:
        # Full kill logic: equipment -> stash, cost 0, rating propagation. Pass
        # the battle so the death CampaignAction also lands on its timeline.
        handle_fighter_kill(user=user, lst=lst, fighter=fighter, battle=battle)
        killed = True
        final_state = ListFighter.DEAD
    elif outcome and outcome != ContentInjuryDefaultOutcome.NO_CHANGE:
        fighter.injury_state = outcome
        fighter.save_with_user(user=user)
        final_state = outcome
    else:
        # NO_CHANGE (or unset): leave the fighter's state as-is.
        final_state = fighter.injury_state

    campaign_action = None
    if lst.campaign:
        description = (
            f"{fighter.term_injury_singular}: {fighter.name} suffered {injury.name}"
        )
        if notes:
            description = f"{description} - {notes}"
        state_display = dict(ListFighter.INJURY_STATE_CHOICES).get(
            final_state, final_state
        )
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            battle=battle,
            description=description,
            outcome=f"{fighter.name} was put into {state_display}",
        )

    return FighterAddInjuryResult(
        fighter=fighter,
        injury=injury_record,
        outcome_state=final_state,
        killed=killed,
        campaign_action=campaign_action,
    )
