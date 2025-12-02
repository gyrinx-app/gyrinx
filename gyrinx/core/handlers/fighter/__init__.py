"""Fighter operation handlers."""

from gyrinx.core.handlers.fighter.advancement import (
    FighterAdvancementResult,
    handle_fighter_advancement,
)
from gyrinx.core.handlers.fighter.edit import (
    FieldChange,
    FighterEditResult,
    handle_fighter_edit,
)
from gyrinx.core.handlers.fighter.hire_clone import (
    FighterCloneResult,
    FighterHireResult,
    handle_fighter_clone,
    handle_fighter_hire,
)
from gyrinx.core.handlers.fighter.removal import (
    FighterArchiveResult,
    FighterDeletionResult,
    handle_fighter_archive_toggle,
    handle_fighter_deletion,
)
from gyrinx.core.handlers.fighter.vehicle import (
    VehiclePurchaseResult,
    handle_vehicle_purchase,
)

__all__ = [
    "FieldChange",
    "FighterAdvancementResult",
    "FighterArchiveResult",
    "FighterCloneResult",
    "FighterDeletionResult",
    "FighterEditResult",
    "FighterHireResult",
    "VehiclePurchaseResult",
    "handle_fighter_advancement",
    "handle_fighter_archive_toggle",
    "handle_fighter_clone",
    "handle_fighter_deletion",
    "handle_fighter_edit",
    "handle_fighter_hire",
    "handle_vehicle_purchase",
]
