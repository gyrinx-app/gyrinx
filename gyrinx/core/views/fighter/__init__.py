"""Fighter-related views package."""

from gyrinx.core.views.fighter.advancements import (
    AdvancementBaseParams,
    AdvancementFlowParams,
    apply_skill_advancement,
    can_fighter_roll_dice_for_advancement,
    delete_list_fighter_advancement,
    filter_equipment_assignments_for_duplicates,
    list_fighter_advancement_confirm,
    list_fighter_advancement_dice_choice,
    list_fighter_advancement_other,
    list_fighter_advancement_select,
    list_fighter_advancement_start,
    list_fighter_advancement_type,
    list_fighter_advancements,
)
from gyrinx.core.views.fighter.crud import (
    ListArchivedFightersView,
    archive_list_fighter,
    clone_list_fighter,
    delete_list_fighter,
    edit_list_fighter,
    embed_list_fighter,
    kill_list_fighter,
    new_list_fighter,
    restore_list_fighter,
    resurrect_list_fighter,
)
from gyrinx.core.views.fighter.equipment import (
    convert_list_fighter_default_assign,
    delete_list_fighter_assign,
    delete_list_fighter_gear_upgrade,
    delete_list_fighter_weapon_accessory,
    delete_list_fighter_weapon_profile,
    disable_list_fighter_default_assign,
    edit_list_fighter_assign_cost,
    edit_list_fighter_equipment,
    edit_list_fighter_weapon_accessories,
    edit_list_fighter_weapon_upgrade,
    edit_single_weapon,
    reassign_list_fighter_equipment,
    sell_list_fighter_equipment,
)
from gyrinx.core.views.fighter.narrative import (
    edit_list_fighter_info,
    edit_list_fighter_narrative,
)
from gyrinx.core.views.fighter.powers import edit_list_fighter_powers
from gyrinx.core.views.fighter.rules import (
    add_list_fighter_rule,
    edit_list_fighter_rules,
    remove_list_fighter_rule,
    toggle_list_fighter_rule,
)
from gyrinx.core.views.fighter.skills import (
    add_list_fighter_skill,
    edit_list_fighter_skills,
    remove_list_fighter_skill,
    toggle_list_fighter_skill,
)
from gyrinx.core.views.fighter.state import (
    list_fighter_add_injury,
    list_fighter_injuries_edit,
    list_fighter_remove_injury,
    list_fighter_state_edit,
    mark_fighter_captured,
)
from gyrinx.core.views.fighter.stats import list_fighter_stats_edit
from gyrinx.core.views.fighter.xp import edit_list_fighter_xp

__all__ = [
    # crud.py
    "new_list_fighter",
    "edit_list_fighter",
    "clone_list_fighter",
    "archive_list_fighter",
    "restore_list_fighter",
    "kill_list_fighter",
    "resurrect_list_fighter",
    "delete_list_fighter",
    "embed_list_fighter",
    "ListArchivedFightersView",
    # skills.py
    "edit_list_fighter_skills",
    "add_list_fighter_skill",
    "remove_list_fighter_skill",
    "toggle_list_fighter_skill",
    # powers.py
    "edit_list_fighter_powers",
    # narrative.py
    "edit_list_fighter_narrative",
    "edit_list_fighter_info",
    # stats.py
    "list_fighter_stats_edit",
    # equipment.py
    "edit_list_fighter_equipment",
    "edit_list_fighter_assign_cost",
    "delete_list_fighter_assign",
    "delete_list_fighter_gear_upgrade",
    "edit_list_fighter_weapon_accessories",
    "edit_single_weapon",
    "delete_list_fighter_weapon_profile",
    "delete_list_fighter_weapon_accessory",
    "edit_list_fighter_weapon_upgrade",
    "disable_list_fighter_default_assign",
    "convert_list_fighter_default_assign",
    "reassign_list_fighter_equipment",
    "sell_list_fighter_equipment",
    # state.py
    "list_fighter_injuries_edit",
    "list_fighter_state_edit",
    "mark_fighter_captured",
    "list_fighter_add_injury",
    "list_fighter_remove_injury",
    # xp.py
    "edit_list_fighter_xp",
    # advancements.py
    "AdvancementBaseParams",
    "AdvancementFlowParams",
    "can_fighter_roll_dice_for_advancement",
    "filter_equipment_assignments_for_duplicates",
    "apply_skill_advancement",
    "list_fighter_advancements",
    "delete_list_fighter_advancement",
    "list_fighter_advancement_start",
    "list_fighter_advancement_dice_choice",
    "list_fighter_advancement_type",
    "list_fighter_advancement_confirm",
    "list_fighter_advancement_select",
    "list_fighter_advancement_other",
    # rules.py
    "edit_list_fighter_rules",
    "toggle_list_fighter_rule",
    "add_list_fighter_rule",
    "remove_list_fighter_rule",
]
