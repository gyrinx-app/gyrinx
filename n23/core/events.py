"""This edition's event vocabulary.

The platform stores events; the words are the edition's. A list, a fighter, a
campaign and a battle mean something here and nothing next door, so they are
declared here and claimed for this edition — the stored noun is then enough to
say which product a row came from, and no call site has to remember to add it.

Accounts and site banners are not in this set: they are the platform's, and
live in ``gyrinx.analytics.nouns.PlatformNoun``, because signing in happens on
the way to either edition.

Imported by ``n23.core.apps``' ``ready()`` so the claim is staked before any
request is served. Nouns must be registered before an event carrying one is
written, or the row is filed as ``unknown``.
"""

from django.db import models

from gyrinx.analytics.nouns import Edition, register_nouns

__all__ = ["EventNoun"]


class EventNoun(models.TextChoices):
    """Nouns representing objects that can be acted upon in this edition."""

    LIST = "list", "List"
    LIST_FIGHTER = "list_fighter", "List Fighter"
    CAMPAIGN = "campaign", "Campaign"
    CAMPAIGN_INVITATION = "campaign_invitation", "Campaign Invitation"
    BATTLE = "battle", "Battle"
    EQUIPMENT_ASSIGNMENT = "equipment_assignment", "Equipment Assignment"
    SKILL_ASSIGNMENT = "skill_assignment", "Skill Assignment"
    UPLOAD = "upload", "Upload"
    FIGHTER_ADVANCEMENT = "fighter_advancement", "Fighter Advancement"
    CAMPAIGN_ACTION = "campaign_action", "Campaign Action"
    CAMPAIGN_RESOURCE = "campaign_resource", "Campaign Resource"
    CAMPAIGN_ASSET = "campaign_asset", "Campaign Asset"
    PRINT_CONFIG = "print_config", "Print Config"
    CONTENT_PACK = "content_pack", "Content Pack"


register_nouns(Edition.N23, EventNoun)
