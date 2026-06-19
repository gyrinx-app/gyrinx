"""
List models package.

This package contains the Django models for users' lists/gangs, organized by
domain into separate modules. It was split out of a single ``list.py`` module
(see issue #1858); every public symbol that module exposed is re-exported here
for backward compatibility with imports like::

    from gyrinx.core.models.list import List, ListFighter

The import order below matters: each module's foreign keys and top-level
sibling imports must resolve against modules imported before it. ``_common``
has no model dependencies, ``list`` defines :class:`List`, ``fighter`` defines
:class:`ListFighter` (which has an FK to ``List``), and so on. Cross-sibling
references that would otherwise form an import cycle stay lazy (inside method
bodies) or use string annotations, exactly as in the original module.

``signal_handlers`` is imported LAST and purely for its side effects: the
module-level ``@receiver`` handlers register only by being imported.
"""

from ._common import (
    ALLOWED_CATEGORY_OVERRIDES,
    bulk_mark_assignments_dirty,
    bulk_mark_fighters_dirty,
    validate_category_override,
)
from .list import List, ListManager, ListQuerySet
from .fighter import (
    ListFighter,
    ListFighterManager,
    ListFighterQuerySet,
    _materialise_child_fighter_defaults,
)
from .assignment import (
    ListFighterEquipmentAssignment,
    ListFighterEquipmentAssignmentQuerySet,
)
from .virtual import (
    VirtualListFighterEquipmentAssignment,
    VirtualListFighterPsykerPowerAssignment,
)
from .psyker import ListFighterPsykerPowerAssignment
from .advancement import AdvancementStatMod, ListFighterAdvancement
from .campaign_state import (
    CapturedFighter,
    ListAttributeAssignment,
    ListFighterCounter,
    ListFighterInjury,
    ListFighterStatOverride,
    ListSkillTreeAssignment,
)

# Imported last and only for its side effects: importing the module registers
# every module-level ``@receiver`` signal handler.
from . import signal_handlers  # noqa: F401

__all__ = [
    # _common
    "ALLOWED_CATEGORY_OVERRIDES",
    "validate_category_override",
    "bulk_mark_assignments_dirty",
    "bulk_mark_fighters_dirty",
    # list
    "ListQuerySet",
    "ListManager",
    "List",
    # fighter
    "ListFighterManager",
    "ListFighterQuerySet",
    "ListFighter",
    "_materialise_child_fighter_defaults",
    # assignment
    "ListFighterEquipmentAssignmentQuerySet",
    "ListFighterEquipmentAssignment",
    # virtual
    "VirtualListFighterEquipmentAssignment",
    "VirtualListFighterPsykerPowerAssignment",
    # psyker
    "ListFighterPsykerPowerAssignment",
    # advancement
    "AdvancementStatMod",
    "ListFighterAdvancement",
    # campaign_state
    "ListFighterInjury",
    "ListFighterCounter",
    "ListAttributeAssignment",
    "ListSkillTreeAssignment",
    "CapturedFighter",
    "ListFighterStatOverride",
    # signal handlers (re-exported for backward compatibility with the old
    # ``from .list import *`` surface; they register via the import above).
    "create_linked_objects",
    "enqueue_propagate_default_child_fighter_assignment",
    "touch_list_modified_on_fighter_save",
    "create_related_objects",
    "delete_related_objects_pre_delete",
    "delete_related_objects_post_delete",
    "clear_fighter_cached_properties_for_assignment",
]

# Re-export the signal handler callables at package top level so the historical
# ``from .list import *`` surface (and any direct references) keep working.
create_linked_objects = signal_handlers.create_linked_objects
enqueue_propagate_default_child_fighter_assignment = (
    signal_handlers.enqueue_propagate_default_child_fighter_assignment
)
touch_list_modified_on_fighter_save = (
    signal_handlers.touch_list_modified_on_fighter_save
)
create_related_objects = signal_handlers.create_related_objects
delete_related_objects_pre_delete = signal_handlers.delete_related_objects_pre_delete
delete_related_objects_post_delete = signal_handlers.delete_related_objects_post_delete
clear_fighter_cached_properties_for_assignment = (
    signal_handlers.clear_fighter_cached_properties_for_assignment
)
