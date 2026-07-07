"""Fighter operation handlers."""

from gyrinx.core.handlers.fighter.advancement import (
    FighterAdvancementDeletionResult,
    FighterAdvancementResult,
    handle_fighter_advancement,
    handle_fighter_advancement_deletion,
)
from gyrinx.core.handlers.fighter.counter_spend import (
    CounterSpendRemovalResult,
    CounterSpendResult,
    handle_counter_spend,
    handle_counter_spend_removal,
)
from gyrinx.core.handlers.fighter.edit import (
    FieldChange,
    FighterEditResult,
    handle_fighter_edit,
)
from gyrinx.core.handlers.fighter.hire_clone import (
    FighterCloneParams,
    FighterCloneResult,
    FighterHireResult,
    handle_fighter_clone,
    handle_fighter_hire,
)
from gyrinx.core.handlers.fighter.kill import (
    FighterKillResult,
    handle_fighter_kill,
)
from gyrinx.core.handlers.fighter.removal import (
    FighterArchiveResult,
    FighterDeletionResult,
    handle_fighter_archive_toggle,
    handle_fighter_deletion,
)
from gyrinx.core.handlers.fighter.resurrect import (
    RESURRECT_TARGET_STATES,
    FighterResurrectResult,
    handle_fighter_resurrect,
)
from gyrinx.core.handlers.fighter.roll_flow import (
    RollFlowResult,
    RollResultDeletionResult,
    handle_roll_flow,
    handle_roll_result_deletion,
)
from gyrinx.core.handlers.fighter.vehicle import (
    VehiclePurchaseResult,
    handle_vehicle_purchase,
)

__all__ = [
    "FieldChange",
    "FighterAdvancementDeletionResult",
    "FighterAdvancementResult",
    "FighterArchiveResult",
    "FighterCloneParams",
    "FighterCloneResult",
    "CounterSpendRemovalResult",
    "CounterSpendResult",
    "RESURRECT_TARGET_STATES",
    "FighterDeletionResult",
    "FighterEditResult",
    "FighterHireResult",
    "FighterKillResult",
    "FighterResurrectResult",
    "RollFlowResult",
    "RollResultDeletionResult",
    "VehiclePurchaseResult",
    "handle_counter_spend",
    "handle_counter_spend_removal",
    "handle_fighter_advancement",
    "handle_fighter_advancement_deletion",
    "handle_fighter_archive_toggle",
    "handle_fighter_clone",
    "handle_fighter_deletion",
    "handle_fighter_edit",
    "handle_fighter_hire",
    "handle_fighter_kill",
    "handle_fighter_resurrect",
    "handle_roll_flow",
    "handle_roll_result_deletion",
    "handle_vehicle_purchase",
]
