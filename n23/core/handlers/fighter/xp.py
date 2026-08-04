"""Handler for granting XP to a fighter (post-battle participation, etc.).

Encapsulates the XP-add rules and audit trail used by the bulk post-battle
editor. The single-fighter XP view still adds XP inline and could adopt this
handler later to share the same rules.
"""

import logging
from dataclasses import dataclass
from typing import Optional

from django.core.exceptions import ValidationError
from django.db import transaction

from n23.core.models.campaign import CampaignAction
from n23.core.models.list import ListFighter
from gyrinx.tracing import traced

logger = logging.getLogger(__name__)


@dataclass
class FighterAddXPResult:
    """Result of granting XP to a fighter."""

    fighter: ListFighter
    amount: int
    campaign_action: Optional[CampaignAction]


@traced("handle_fighter_add_xp")
@transaction.atomic
def handle_fighter_add_xp(
    *,
    user,
    fighter: ListFighter,
    amount: int,
    description: str = "",
    battle=None,
) -> FighterAddXPResult:
    """
    Grant XP to a fighter, bumping both current (spendable) and total (lifetime)
    XP, and writing a CampaignAction in campaign mode.

    Args:
        user: The user granting the XP.
        fighter: The fighter receiving XP.
        amount: XP to add (must be a positive whole number).
        description: Optional note appended to the campaign log entry.
        battle: Optional Battle to attach the CampaignAction to.

    Returns:
        FighterAddXPResult.

    Raises:
        ValidationError: If amount is not positive.
    """
    if amount is None or amount < 1:
        raise ValidationError("XP to add must be a positive whole number.")

    lst = fighter.list

    fighter.xp_current += amount
    fighter.xp_total += amount
    fighter.save_with_user(user=user)

    action_desc = f"Added {amount} XP for {fighter.name}"
    if description:
        action_desc = f"{action_desc} - {description}"

    campaign_action = None
    if lst.campaign:
        campaign_action = CampaignAction.objects.create(
            user=user,
            owner=user,
            campaign=lst.campaign,
            list=lst,
            battle=battle,
            description=action_desc,
            outcome=f"Current: {fighter.xp_current} XP, Total: {fighter.xp_total} XP",
        )

    return FighterAddXPResult(
        fighter=fighter, amount=amount, campaign_action=campaign_action
    )
