"""
Content models package.

This package contains all Django models for the content app, organized
by domain into separate modules.

All models are re-exported here for backward compatibility with imports like:
    from n23.content.models import ContentFighter
"""

# Base classes and shared utilities
# Re-export FighterCategoryChoices for backward compatibility
# (some code imports it from content.models instead of n23.models)
from n23.models import FighterCategoryChoices  # noqa: F401

from .advancement import ContentAdvancementAssignment, ContentAdvancementEquipment
from .attribute import ContentAttribute, ContentAttributeValue

# Availability preset models
from .availability_preset import ContentAvailabilityPreset
from .base import (
    Content,
    ContentManager,
    ContentQuerySet,
    RulelineDisplay,
    StatlineDisplay,
)
from .battle import (
    ContentBattleRole,
    ContentBattleRoleOption,
)
from .counter import ContentCounter
from .default_assignment import ContentFighterDefaultAssignment
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

# Assignment models
from .equipment_list import (
    ContentFighterEquipmentListItem,
    ContentFighterEquipmentListUpgrade,
    ContentFighterEquipmentListWeaponAccessory,
)

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
from .fighter import (
    ContentFighter,
    ContentFighterCategoryTerms,
    ContentFighterManager,
    ContentFighterQuerySet,
)
from .gang_skills import ContentHouseSkillRankAccess

# Core domain models
from .house import ContentFighterHouseOverride, ContentHouse
from .injury import (
    ContentEquipmentInjuryLink,
    ContentInjury,
    ContentInjuryDefaultOutcome,
    ContentInjuryGroup,
)
from .metadata import (
    ContentBook,
    ContentPageRef,
    ContentPolicy,
    ContentRule,
    similar,
)
from .modifier import (
    ContentMod,
    ContentModApplication,
    ContentModFighterRule,
    ContentModFighterSkill,
    ContentModFighterStat,
    ContentModPsykerDisciplineAccess,
    ContentModSkillTreeAccess,
    ContentModStat,
    ContentModStatApplyMixin,
    ContentModTrait,
)
from .promotion import ContentPromotionPath

# Dependent domain models
from .psyker import (
    ContentFighterPsykerDisciplineAssignment,
    ContentFighterPsykerPowerDefaultAssignment,
    ContentPsykerDiscipline,
    ContentPsykerPower,
)
from .roll_table import (
    ContentRollFlow,
    ContentRollTable,
    ContentRollTableRow,
)

# Simple domain models
from .skill import ContentSkill, ContentSkillCategory
from .statline import (
    ContentStat,
    ContentStatline,
    ContentStatlineStat,
    ContentStatlineType,
    ContentStatlineTypeStat,
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

# Import signal handlers to register them. Must stay last to avoid a circular
# import — `isort: skip` keeps the sorter from hoisting it back up.
from . import signal_handlers  # noqa: F401  # isort: skip

__all__ = [
    # Base
    "Content",
    "ContentManager",
    "ContentQuerySet",
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
    "ContentPageRef",
    "ContentPolicy",
    "ContentRule",
    "similar",
    # Houses
    "ContentFighterHouseOverride",
    "ContentHouse",
    "ContentHouseSkillRankAccess",
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
    "ContentModApplication",
    "ContentModFighterRule",
    "ContentModFighterSkill",
    "ContentModFighterStat",
    "ContentModPsykerDisciplineAccess",
    "ContentModSkillTreeAccess",
    "ContentModStat",
    "ContentModStatApplyMixin",
    "ContentModTrait",
    # Injuries
    "ContentEquipmentInjuryLink",
    "ContentInjury",
    "ContentInjuryDefaultOutcome",
    "ContentInjuryGroup",
    # Battle roles
    "ContentBattleRole",
    "ContentBattleRoleOption",
    # Equipment Lists
    "ContentFighterEquipmentListItem",
    "ContentFighterEquipmentListUpgrade",
    "ContentFighterEquipmentListWeaponAccessory",
    # Default Assignments
    "ContentFighterDefaultAssignment",
    # Advancements
    "ContentAdvancementAssignment",
    "ContentAdvancementEquipment",
    # Promotions
    "ContentPromotionPath",
    # Expansions
    "ContentEquipmentListExpansion",
    "ContentEquipmentListExpansionItem",
    "ContentEquipmentListExpansionRule",
    "ContentEquipmentListExpansionRuleByAttribute",
    "ContentEquipmentListExpansionRuleByFighterCategory",
    "ContentEquipmentListExpansionRuleByHouse",
    "ExpansionRuleInputs",
    # Counters
    "ContentCounter",
    # Roll Tables
    "ContentRollFlow",
    "ContentRollTable",
    "ContentRollTableRow",
    # Availability Presets
    "ContentAvailabilityPreset",
    # Re-exports from gyrinx.models for backward compatibility
    "FighterCategoryChoices",
]
