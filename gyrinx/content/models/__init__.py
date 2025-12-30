"""
Content models package.

This package contains all Django models for the content app, organized
by domain into separate modules.

All models are re-exported here for backward compatibility with imports like:
    from gyrinx.content.models import ContentFighter
"""

# Base classes and shared utilities
from .base import Content, RulelineDisplay, StatlineDisplay

# Simple domain models
from .skill import ContentSkill, ContentSkillCategory
from .attribute import ContentAttribute, ContentAttributeValue
from .statline import (
    ContentStat,
    ContentStatline,
    ContentStatlineStat,
    ContentStatlineType,
    ContentStatlineTypeStat,
)
from .metadata import (
    ContentBook,
    ContentPack,
    ContentPageRef,
    ContentPolicy,
    ContentRule,
    similar,
)

# Core domain models
from .house import ContentFighterHouseOverride, ContentHouse
from .equipment import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentCategoryFighterRestriction,
    ContentEquipmentEquipmentProfile,
    ContentEquipmentFighterProfile,
    ContentEquipmentManager,
    ContentEquipmentQuerySet,
    ContentEquipmentUpgrade,
    ContentEquipmentUpgradeManager,
    ContentEquipmentUpgradeQuerySet,
    ContentFighterEquipmentCategoryLimit,
)
from .weapon import (
    ContentWeaponAccessory,
    ContentWeaponAccessoryManager,
    ContentWeaponAccessoryQuerySet,
    ContentWeaponProfile,
    ContentWeaponProfileManager,
    ContentWeaponProfileQuerySet,
    ContentWeaponTrait,
    VirtualWeaponProfile,
)
from .fighter import (
    ContentFighter,
    ContentFighterCategoryTerms,
    ContentFighterManager,
    ContentFighterQuerySet,
)

# Dependent domain models
from .psyker import (
    ContentFighterPsykerDisciplineAssignment,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentPsykerDiscipline,
    ContentPsykerPower,
)
from .modifier import (
    ContentMod,
    ContentModFighterRule,
    ContentModFighterSkill,
    ContentModFighterStat,
    ContentModPsykerDisciplineAccess,
    ContentModSkillTreeAccess,
    ContentModStat,
    ContentModStatApplyMixin,
    ContentModTrait,
)
from .injury import (
    ContentInjury,
    ContentInjuryDefaultOutcome,
    ContentInjuryGroup,
)

# Assignment models
from .equipment_list import (
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListUpgrade,
    ContentFighterEquipmentListWeaponAccessory,
)
from .default_assignment import ContentFighterDefaultAssignment
from .advancement import ContentAdvancementAssignment, ContentAdvancementEquipment

# Expansion models
from .expansion import (
    ContentEquipmentListExpansion,
    ContentEquipmentListExpansionItem,
    ContentEquipmentListExpansionRule,
    ContentEquipmentListExpansionRuleByAttribute,
    ContentEquipmentListExpansionRuleByFighterCategory,
    ContentEquipmentListExpansionRuleByHouse,
    ExpansionRuleInputs,
)

# Import signal handlers to register them
# This must be done last to avoid circular imports
from . import signal_handlers  # noqa: F401

# Re-export FighterCategoryChoices for backward compatibility
# (some code imports it from content.models instead of gyrinx.models)
from gyrinx.models import FighterCategoryChoices  # noqa: F401

__all__ = [
    # Base
    "Content",
    "RulelineDisplay",
    "StatlineDisplay",
    # Skills
    "ContentSkill",
    "ContentSkillCategory",
    # Attributes
    "ContentAttribute",
    "ContentAttributeValue",
    # Statlines
    "ContentStat",
    "ContentStatline",
    "ContentStatlineStat",
    "ContentStatlineType",
    "ContentStatlineTypeStat",
    # Metadata
    "ContentBook",
    "ContentPack",
    "ContentPageRef",
    "ContentPolicy",
    "ContentRule",
    "similar",
    # Houses
    "ContentFighterHouseOverride",
    "ContentHouse",
    # Equipment
    "ContentEquipment",
    "ContentEquipmentCategory",
    "ContentEquipmentCategoryFighterRestriction",
    "ContentEquipmentEquipmentProfile",
    "ContentEquipmentFighterProfile",
    "ContentEquipmentManager",
    "ContentEquipmentQuerySet",
    "ContentEquipmentUpgrade",
    "ContentEquipmentUpgradeManager",
    "ContentEquipmentUpgradeQuerySet",
    "ContentFighterEquipmentCategoryLimit",
    # Weapons
    "ContentWeaponAccessory",
    "ContentWeaponAccessoryManager",
    "ContentWeaponAccessoryQuerySet",
    "ContentWeaponProfile",
    "ContentWeaponProfileManager",
    "ContentWeaponProfileQuerySet",
    "ContentWeaponTrait",
    "VirtualWeaponProfile",
    # Fighters
    "ContentFighter",
    "ContentFighterCategoryTerms",
    "ContentFighterManager",
    "ContentFighterQuerySet",
    # Psyker
    "ContentFighterPsykerDisciplineAssignment",
    "ContentFighterPsykerPowerDefaultAssignment",
    "ContentPsykerDiscipline",
    "ContentPsykerPower",
    # Modifiers
    "ContentMod",
    "ContentModFighterRule",
    "ContentModFighterSkill",
    "ContentModFighterStat",
    "ContentModPsykerDisciplineAccess",
    "ContentModSkillTreeAccess",
    "ContentModStat",
    "ContentModStatApplyMixin",
    "ContentModTrait",
    # Injuries
    "ContentInjury",
    "ContentInjuryDefaultOutcome",
    "ContentInjuryGroup",
    # Equipment Lists
    "ContentFighterEquipmentListItem",
    "ContentFighterEquipmentListUpgrade",
    "ContentFighterEquipmentListWeaponAccessory",
    # Default Assignments
    "ContentFighterDefaultAssignment",
    # Advancements
    "ContentAdvancementAssignment",
    "ContentAdvancementEquipment",
    # Expansions
    "ContentEquipmentListExpansion",
    "ContentEquipmentListExpansionItem",
    "ContentEquipmentListExpansionRule",
    "ContentEquipmentListExpansionRuleByAttribute",
    "ContentEquipmentListExpansionRuleByFighterCategory",
    "ContentEquipmentListExpansionRuleByHouse",
    "ExpansionRuleInputs",
    # Re-exports from gyrinx.models for backward compatibility
    "FighterCategoryChoices",
]
