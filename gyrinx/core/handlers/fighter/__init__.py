"""Fighter operation handlers."""

from gyrinx.core.handlers.fighter.advancement import (
    FighterAdvancementResult,
    handle_fighter_advancement,
)
from gyrinx.core.handlers.fighter.hire_clone import (
    FighterCloneResult,
    FighterHireResult,
    handle_fighter_clone,
    handle_fighter_hire,
)
from gyrinx.core.handlers.fighter.removal import (
    EquipmentComponentRemovalResult,
    EquipmentRemovalResult,
    FighterArchiveResult,
    FighterDeletionResult,
    handle_equipment_component_removal,
    handle_equipment_removal,
    handle_fighter_archive_toggle,
    handle_fighter_deletion,
)

__all__ = [
    "EquipmentComponentRemovalResult",
    "EquipmentRemovalResult",
    "FighterAdvancementResult",
    "FighterArchiveResult",
    "FighterCloneResult",
    "FighterDeletionResult",
    "FighterHireResult",
    "handle_equipment_component_removal",
    "handle_equipment_removal",
    "handle_fighter_advancement",
    "handle_fighter_archive_toggle",
    "handle_fighter_clone",
    "handle_fighter_deletion",
    "handle_fighter_hire",
]
