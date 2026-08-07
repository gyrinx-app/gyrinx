"""Equipment operation handlers."""

from n23.core.handlers.equipment.cost_override import (
    EquipmentCostOverrideResult,
    handle_equipment_cost_override,
)
from n23.core.handlers.equipment.deltas import component_delta
from n23.core.handlers.equipment.purchase import (
    AccessoryPurchaseResult,
    EquipmentPurchaseResult,
    EquipmentUpgradeResult,
    WeaponProfilePurchaseResult,
    handle_accessory_purchase,
    handle_equipment_purchase,
    handle_equipment_upgrade,
    handle_weapon_profile_purchase,
)
from n23.core.handlers.equipment.reassignment import (
    EquipmentReassignmentResult,
    handle_equipment_reassignment,
)
from n23.core.handlers.equipment.removal import (
    EquipmentComponentRemovalResult,
    EquipmentRemovalResult,
    handle_equipment_component_removal,
    handle_equipment_removal,
)
from n23.core.handlers.equipment.sale import (
    EquipmentSaleResult,
    SaleItemDetail,
    handle_equipment_sale,
)

__all__ = [
    "component_delta",
    "AccessoryPurchaseResult",
    "EquipmentComponentRemovalResult",
    "EquipmentCostOverrideResult",
    "EquipmentPurchaseResult",
    "EquipmentReassignmentResult",
    "EquipmentRemovalResult",
    "EquipmentSaleResult",
    "EquipmentUpgradeResult",
    "SaleItemDetail",
    "WeaponProfilePurchaseResult",
    "handle_accessory_purchase",
    "handle_equipment_component_removal",
    "handle_equipment_cost_override",
    "handle_equipment_purchase",
    "handle_equipment_reassignment",
    "handle_equipment_removal",
    "handle_equipment_sale",
    "handle_equipment_upgrade",
    "handle_weapon_profile_purchase",
]
