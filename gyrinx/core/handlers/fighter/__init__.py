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

__all__ = [
    "FighterAdvancementResult",
    "FighterCloneResult",
    "FighterHireResult",
    "handle_fighter_advancement",
    "handle_fighter_clone",
    "handle_fighter_hire",
]
