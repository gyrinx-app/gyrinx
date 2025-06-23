import pytest

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
    ContentFighter,
    ContentFighterEquipmentListUpgrade,
    ContentHouse,
)
from gyrinx.core.models import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
    VirtualListFighterEquipmentAssignment,
)
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_content_fighter_equipment_list_upgrade_creation():
    """Test basic creation of ContentFighterEquipmentListUpgrade."""
    # Create equipment category
    wargear_category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Wargear",
        defaults={"group": "Gear"},
    )

    # Create equipment with upgrade
    equipment = ContentEquipment.objects.create(
        name="Servo-arm",
        category=wargear_category,
        cost=35,
        upgrade_mode=ContentEquipment.UpgradeMode.SINGLE,
        upgrade_stack_name="Upgrades",
    )

    upgrade = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Suspensor",
        cost=60,
        position=1,
    )

    # Create fighter
    fighter = ContentFighter.objects.create(
        type="Archaeotek",
        category=FighterCategoryChoices.LEADER,
    )

    # Create upgrade override
    override = ContentFighterEquipmentListUpgrade.objects.create(
        fighter=fighter,
        upgrade=upgrade,
        cost=30,  # Half price for Archaeotek
    )

    assert override.cost_int() == 30
    assert override.cost_display() == "30¢"
    assert str(override) == "Archaeotek Upgrades – Suspensor (30)"


@pytest.mark.django_db
def test_upgrade_with_cost_for_fighter_queryset():
    """Test the with_cost_for_fighter queryset method."""
    # Create equipment category
    wargear_category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Wargear",
        defaults={"group": "Gear"},
    )

    # Create equipment with upgrades
    equipment = ContentEquipment.objects.create(
        name="Servo-arm",
        category=wargear_category,
        cost=35,
        upgrade_mode=ContentEquipment.UpgradeMode.SINGLE,
        upgrade_stack_name="Upgrades",
    )

    upgrade1 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Suspensor",
        cost=60,
        position=1,
    )

    upgrade2 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Extra Grip",
        cost=20,
        position=2,
    )

    # Create fighters
    archaeotek = ContentFighter.objects.create(
        type="Archaeotek",
        category=FighterCategoryChoices.LEADER,
    )

    champion = ContentFighter.objects.create(
        type="Champion",
        category=FighterCategoryChoices.CHAMPION,
    )

    # Create override for Archaeotek only
    ContentFighterEquipmentListUpgrade.objects.create(
        fighter=archaeotek,
        upgrade=upgrade1,
        cost=30,  # Half price
    )

    # Test queryset with Archaeotek
    upgrades_for_archaeotek = ContentEquipmentUpgrade.objects.filter(
        equipment=equipment
    ).with_cost_for_fighter(archaeotek)

    assert upgrades_for_archaeotek.get(pk=upgrade1.pk).cost_for_fighter == 30
    assert (
        upgrades_for_archaeotek.get(pk=upgrade2.pk).cost_for_fighter == 20
    )  # No override

    # Test queryset with Champion (no overrides)
    upgrades_for_champion = ContentEquipmentUpgrade.objects.filter(
        equipment=equipment
    ).with_cost_for_fighter(champion)

    assert upgrades_for_champion.get(pk=upgrade1.pk).cost_for_fighter == 60  # Base cost
    assert upgrades_for_champion.get(pk=upgrade2.pk).cost_for_fighter == 20  # Base cost


@pytest.mark.django_db
def test_list_fighter_equipment_assignment_upgrade_override():
    """Test upgrade cost overrides in ListFighterEquipmentAssignment."""
    # Create house and equipment
    house = ContentHouse.objects.create(name="Test House")

    # Create equipment category
    wargear_category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Wargear",
        defaults={"group": "Gear"},
    )

    equipment = ContentEquipment.objects.create(
        name="Servo-arm",
        category=wargear_category,
        cost=35,
        upgrade_mode=ContentEquipment.UpgradeMode.SINGLE,
        upgrade_stack_name="Upgrades",
    )

    upgrade = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Suspensor",
        cost=60,
        position=1,
    )

    # Create content fighter with override
    content_fighter = ContentFighter.objects.create(
        type="Archaeotek",
        category=FighterCategoryChoices.LEADER,
        house=house,
    )

    ContentFighterEquipmentListUpgrade.objects.create(
        fighter=content_fighter,
        upgrade=upgrade,
        cost=30,
    )

    # Create list and list fighter
    list_obj = List.objects.create(
        name="Test Gang",
        content_house=house,
    )

    list_fighter = ListFighter.objects.create(
        list=list_obj,
        content_fighter=content_fighter,
    )

    # Create equipment assignment with upgrade
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )
    assignment.upgrades_field.add(upgrade)

    # Test upgrade cost override
    assert assignment._upgrade_cost_with_override(upgrade) == 30
    assert assignment.upgrade_cost_int() == 30

    # Test with different fighter (no override)
    other_content_fighter = ContentFighter.objects.create(
        type="Champion",
        category=FighterCategoryChoices.CHAMPION,
        house=house,
    )

    other_list_fighter = ListFighter.objects.create(
        list=list_obj,
        content_fighter=other_content_fighter,
    )

    other_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=other_list_fighter,
        content_equipment=equipment,
    )
    other_assignment.upgrades_field.add(upgrade)

    assert other_assignment._upgrade_cost_with_override(upgrade) == 60  # Base cost
    assert other_assignment.upgrade_cost_int() == 60


@pytest.mark.django_db
def test_virtual_equipment_assignment_upgrade_override():
    """Test upgrade cost overrides in VirtualListFighterEquipmentAssignment."""
    # Create house and equipment
    house = ContentHouse.objects.create(name="Test House")

    # Create equipment category
    wargear_category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Wargear",
        defaults={"group": "Gear"},
    )

    equipment = ContentEquipment.objects.create(
        name="Servo-arm",
        category=wargear_category,
        cost=35,
        upgrade_mode=ContentEquipment.UpgradeMode.MULTI,
        upgrade_stack_name="Upgrades",
    )

    upgrade1 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Suspensor",
        cost=60,
        position=1,
    )

    upgrade2 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Extra Grip",
        cost=20,
        position=2,
    )

    # Create content fighter with override
    content_fighter = ContentFighter.objects.create(
        type="Archaeotek",
        category=FighterCategoryChoices.LEADER,
        house=house,
    )

    ContentFighterEquipmentListUpgrade.objects.create(
        fighter=content_fighter,
        upgrade=upgrade1,
        cost=30,
    )

    # Create list and list fighter
    list_obj = List.objects.create(
        name="Test Gang",
        content_house=house,
    )

    list_fighter = ListFighter.objects.create(
        list=list_obj,
        content_fighter=content_fighter,
    )

    # Create virtual assignment
    virtual = VirtualListFighterEquipmentAssignment(
        fighter=list_fighter,
        equipment=equipment,
    )

    # Test upgrades() method returns queryset with overrides
    upgrades = virtual.upgrades()
    assert len(upgrades) == 2

    # Find upgrades by ID since QuerySet ordering might differ
    upgrade1_result = next(u for u in upgrades if u.id == upgrade1.id)
    upgrade2_result = next(u for u in upgrades if u.id == upgrade2.id)

    assert upgrade1_result.cost_for_fighter == 30  # Override
    assert upgrade2_result.cost_for_fighter == 20  # No override

    # Test upgrades_display() uses overridden costs
    # Note: This test uses MULTI mode, so costs are NOT cumulative
    display = virtual.upgrades_display()
    upgrade1_display = next(d for d in display if d["upgrade"].id == upgrade1.id)
    upgrade2_display = next(d for d in display if d["upgrade"].id == upgrade2.id)

    assert upgrade1_display["cost_int"] == 30
    assert upgrade1_display["cost_display"] == "+30¢"
    assert upgrade2_display["cost_int"] == 20
    assert upgrade2_display["cost_display"] == "+20¢"


@pytest.mark.django_db
def test_copy_to_house_includes_upgrade_overrides():
    """Test that copy_to_house includes equipment upgrade overrides."""
    # Create houses
    original_house = ContentHouse.objects.create(name="Original House")
    new_house = ContentHouse.objects.create(name="New House")

    # Create equipment category
    wargear_category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Wargear",
        defaults={"group": "Gear"},
    )

    # Create equipment with upgrade
    equipment = ContentEquipment.objects.create(
        name="Servo-arm",
        category=wargear_category,
        cost=35,
        upgrade_mode=ContentEquipment.UpgradeMode.SINGLE,
        upgrade_stack_name="Upgrades",
    )

    upgrade = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Suspensor",
        cost=60,
        position=1,
    )

    # Create original fighter with upgrade override
    original_fighter = ContentFighter.objects.create(
        type="Archaeotek",
        category=FighterCategoryChoices.LEADER,
        house=original_house,
    )
    original_fighter_id = original_fighter.pk

    original_override = ContentFighterEquipmentListUpgrade.objects.create(
        fighter=original_fighter,
        upgrade=upgrade,
        cost=30,
    )
    original_override_id = original_override.pk

    # Copy fighter to new house (modifies original_fighter in-place)
    new_fighter = original_fighter.copy_to_house(new_house)

    # Verify upgrade override was copied
    assert ContentFighterEquipmentListUpgrade.objects.filter(
        fighter=new_fighter,
        upgrade=upgrade,
        cost=30,
    ).exists()

    # Verify it's a new instance, not the same one
    new_override = ContentFighterEquipmentListUpgrade.objects.get(fighter=new_fighter)
    assert new_override.pk != original_override_id
    assert new_override.fighter == new_fighter
    assert new_fighter.pk != original_fighter_id
    assert new_override.upgrade == upgrade
    assert new_override.cost == 30


@pytest.mark.django_db
def test_cumulative_upgrade_costs_with_fighter_overrides():
    """Test that fighter-specific cost overrides work correctly with cumulative costs."""
    # Create equipment category
    wargear_category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Wargear",
        defaults={"group": "Gear"},
    )

    # Create equipment with SINGLE upgrade mode (cumulative costs)
    equipment = ContentEquipment.objects.create(
        name="Servo-arm",
        category=wargear_category,
        cost=35,
        upgrade_mode=ContentEquipment.UpgradeMode.SINGLE,
        upgrade_stack_name="Upgrades",
    )

    # Create three upgrades with individual costs
    upgrade1 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Suspensor",
        cost=20,  # Cumulative cost: 20
        position=1,
    )

    upgrade2 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Extra Grip",
        cost=30,  # Cumulative cost: 20 + 30 = 50
        position=2,
    )

    upgrade3 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Power Feed",
        cost=40,  # Cumulative cost: 20 + 30 + 40 = 90
        position=3,
    )

    # Verify base cumulative costs
    assert upgrade1.cost_int() == 20
    assert upgrade2.cost_int() == 50
    assert upgrade3.cost_int() == 90

    # Create fighter with overrides for some upgrades
    fighter = ContentFighter.objects.create(
        type="Archaeotek",
        category=FighterCategoryChoices.LEADER,
    )

    # Override costs for upgrades 1 and 3
    # For Archaeotek: upgrade1 costs 10 instead of 20
    ContentFighterEquipmentListUpgrade.objects.create(
        fighter=fighter,
        upgrade=upgrade1,
        cost=10,  # Overridden individual cost
    )

    # For Archaeotek: upgrade3 costs 20 instead of 40
    ContentFighterEquipmentListUpgrade.objects.create(
        fighter=fighter,
        upgrade=upgrade3,
        cost=20,  # Overridden individual cost
    )

    # Get upgrades with fighter-specific costs
    upgrades = (
        ContentEquipmentUpgrade.objects.filter(equipment=equipment)
        .with_cost_for_fighter(fighter)
        .order_by("position")
    )

    # The issue is: cost_for_fighter should give cumulative costs, not just individual costs
    # Expected cumulative costs for Archaeotek:
    # - upgrade1: 10 (overridden)
    # - upgrade2: 10 + 30 = 40 (upgrade1 overridden + upgrade2 base)
    # - upgrade3: 10 + 30 + 20 = 60 (upgrade1 overridden + upgrade2 base + upgrade3 overridden)

    # But currently, cost_for_fighter only gives individual costs:
    assert upgrades[0].cost_for_fighter == 10  # This is correct (individual)
    assert upgrades[1].cost_for_fighter == 30  # This is individual, not cumulative
    assert upgrades[2].cost_for_fighter == 20  # This is individual, not cumulative

    # Test actual cumulative costs in ListFighterEquipmentAssignment
    house = ContentHouse.objects.create(name="Test House")
    fighter.house = house
    fighter.save()

    list_obj = List.objects.create(
        name="Test Gang",
        content_house=house,
    )

    list_fighter = ListFighter.objects.create(
        list=list_obj,
        content_fighter=fighter,
    )

    # Create equipment assignment with all upgrades
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )
    assignment.upgrades_field.add(upgrade3)  # Adding the highest upgrade

    # The cost should be cumulative: 10 (override) + 30 (base) + 20 (override) = 60
    # Currently it might just return 20 (the individual override)
    assert assignment._upgrade_cost_with_override(upgrade3) == 60


@pytest.mark.django_db
def test_virtual_equipment_assignment_cumulative_upgrade_costs():
    """Test cumulative upgrade costs with fighter-specific overrides in VirtualListFighterEquipmentAssignment."""
    # Create house and equipment
    house = ContentHouse.objects.create(name="Test House")

    # Create equipment category
    wargear_category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Wargear",
        defaults={"group": "Gear"},
    )

    # Create equipment with SINGLE upgrade mode (cumulative costs)
    equipment = ContentEquipment.objects.create(
        name="Power Armor",
        category=wargear_category,
        cost=50,
        upgrade_mode=ContentEquipment.UpgradeMode.SINGLE,
        upgrade_stack_name="Enhancements",
    )

    # Create upgrades
    upgrade1 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Reinforced Plating",
        cost=20,
        position=1,
    )

    upgrade2 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Servo Motors",
        cost=30,
        position=2,
    )

    # Create content fighter with override
    content_fighter = ContentFighter.objects.create(
        type="Tech Specialist",
        category=FighterCategoryChoices.SPECIALIST,
        house=house,
    )

    # Override upgrade1 cost for Tech Specialist
    ContentFighterEquipmentListUpgrade.objects.create(
        fighter=content_fighter,
        upgrade=upgrade1,
        cost=10,  # Half price
    )

    # Create list and list fighter
    list_obj = List.objects.create(
        name="Test Gang",
        content_house=house,
    )

    list_fighter = ListFighter.objects.create(
        list=list_obj,
        content_fighter=content_fighter,
    )

    # Create virtual assignment
    virtual = VirtualListFighterEquipmentAssignment(
        fighter=list_fighter,
        equipment=equipment,
    )

    # Test upgrades_display() with cumulative costs
    display = virtual.upgrades_display()

    # Find upgrades by ID
    upgrade1_display = next(d for d in display if d["upgrade"].id == upgrade1.id)
    upgrade2_display = next(d for d in display if d["upgrade"].id == upgrade2.id)

    # For SINGLE mode with overrides:
    # upgrade1: 10 (overridden)
    # upgrade2: 10 (override) + 30 (base) = 40 (cumulative)
    assert upgrade1_display["cost_int"] == 10
    assert upgrade1_display["cost_display"] == "+10¢"
    assert upgrade2_display["cost_int"] == 40
    assert upgrade2_display["cost_display"] == "+40¢"


@pytest.mark.django_db
def test_virtual_equipment_assignment_active_methods_with_overrides():
    """Test that active_upgrade, active_upgrades, and active_upgrades_display respect fighter-specific overrides."""
    # Create house and equipment
    house = ContentHouse.objects.create(name="Test House")

    # Create equipment category
    wargear_category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Wargear",
        defaults={"group": "Gear"},
    )

    # Create equipment with SINGLE upgrade mode
    equipment = ContentEquipment.objects.create(
        name="Advanced Targeter",
        category=wargear_category,
        cost=40,
        upgrade_mode=ContentEquipment.UpgradeMode.SINGLE,
        upgrade_stack_name="Targeting Enhancements",
    )

    # Create upgrades
    upgrade1 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Infrared Scope",
        cost=25,
        position=1,
    )

    upgrade2 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Motion Tracker",
        cost=35,
        position=2,
    )

    # Create content fighter with overrides
    content_fighter = ContentFighter.objects.create(
        type="Sniper",
        category=FighterCategoryChoices.SPECIALIST,
        house=house,
    )

    # Override costs for Sniper
    ContentFighterEquipmentListUpgrade.objects.create(
        fighter=content_fighter,
        upgrade=upgrade1,
        cost=15,  # Reduced cost for Sniper
    )

    ContentFighterEquipmentListUpgrade.objects.create(
        fighter=content_fighter,
        upgrade=upgrade2,
        cost=20,  # Reduced cost for Sniper
    )

    # Create list and list fighter
    list_obj = List.objects.create(
        name="Test Gang",
        content_house=house,
    )

    list_fighter = ListFighter.objects.create(
        list=list_obj,
        content_fighter=content_fighter,
    )

    # Create equipment assignment with first upgrade
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )
    assignment.upgrades_field.add(upgrade1)

    # Create virtual assignment from the real assignment
    virtual = VirtualListFighterEquipmentAssignment.from_assignment(assignment)

    # Test active_upgrade returns upgrade with fighter-specific cost
    active_upgrade = virtual.active_upgrade()
    assert active_upgrade is not None
    assert active_upgrade.id == upgrade1.id
    assert hasattr(active_upgrade, "cost_for_fighter")
    assert active_upgrade.cost_for_fighter == 15  # Overridden cost

    # Test active_upgrade_cached
    assert virtual.active_upgrade_cached == active_upgrade

    # Test active_upgrades returns all upgrades with fighter-specific costs
    active_upgrades = virtual.active_upgrades()
    assert len(active_upgrades) == 1
    assert active_upgrades[0].cost_for_fighter == 15

    # Test active_upgrades_cached
    assert list(virtual.active_upgrades_cached) == list(active_upgrades)

    # Test active_upgrades_display uses cumulative costs with overrides
    display = virtual.active_upgrades_display
    assert len(display) == 1
    assert display[0]["upgrade"].id == upgrade1.id
    assert display[0]["cost_int"] == 15  # Overridden cost (cumulative)
    assert display[0]["cost_display"] == "+15¢"

    # Now add the second upgrade and test cumulative costs
    assignment.upgrades_field.add(upgrade2)

    # Create new virtual assignment to refresh cached values
    virtual2 = VirtualListFighterEquipmentAssignment.from_assignment(assignment)

    # Test active_upgrades with multiple upgrades
    active_upgrades2 = virtual2.active_upgrades()
    assert len(active_upgrades2) == 2

    # Find upgrades by ID
    upgrade1_active = next(u for u in active_upgrades2 if u.id == upgrade1.id)
    upgrade2_active = next(u for u in active_upgrades2 if u.id == upgrade2.id)

    assert upgrade1_active.cost_for_fighter == 15  # Override
    assert upgrade2_active.cost_for_fighter == 20  # Override

    # Test active_upgrades_display with cumulative costs
    display2 = virtual2.active_upgrades_display
    assert len(display2) == 2

    # Find displays by upgrade ID
    upgrade1_display = next(d for d in display2 if d["upgrade"].id == upgrade1.id)
    upgrade2_display = next(d for d in display2 if d["upgrade"].id == upgrade2.id)

    # For SINGLE mode:
    # upgrade1: 15 (overridden)
    # upgrade2: 15 + 20 = 35 (cumulative with overrides)
    assert upgrade1_display["cost_int"] == 15
    assert upgrade2_display["cost_int"] == 35


@pytest.mark.django_db
def test_virtual_equipment_assignment_active_methods_multi_mode():
    """Test active methods with MULTI mode equipment (non-cumulative costs)."""
    # Create house and equipment
    house = ContentHouse.objects.create(name="Test House")

    # Create equipment category
    wargear_category, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Wargear",
        defaults={"group": "Gear"},
    )

    # Create equipment with MULTI upgrade mode
    equipment = ContentEquipment.objects.create(
        name="Weapon Mods",
        category=wargear_category,
        cost=0,
        upgrade_mode=ContentEquipment.UpgradeMode.MULTI,
        upgrade_stack_name="Modifications",
    )

    # Create upgrades
    upgrade1 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Extended Magazine",
        cost=20,
        position=1,
    )

    upgrade2 = ContentEquipmentUpgrade.objects.create(
        equipment=equipment,
        name="Laser Sight",
        cost=30,
        position=2,
    )

    # Create content fighter with override for one upgrade
    content_fighter = ContentFighter.objects.create(
        type="Gunslinger",
        category=FighterCategoryChoices.CHAMPION,
        house=house,
    )

    # Override only upgrade2 cost
    ContentFighterEquipmentListUpgrade.objects.create(
        fighter=content_fighter,
        upgrade=upgrade2,
        cost=15,  # Half price for Gunslinger
    )

    # Create list and list fighter
    list_obj = List.objects.create(
        name="Test Gang",
        content_house=house,
    )

    list_fighter = ListFighter.objects.create(
        list=list_obj,
        content_fighter=content_fighter,
    )

    # Create equipment assignment with both upgrades
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )
    assignment.upgrades_field.add(upgrade1, upgrade2)

    # Create virtual assignment
    virtual = VirtualListFighterEquipmentAssignment.from_assignment(assignment)

    # Test active_upgrade returns None for MULTI mode
    assert virtual.active_upgrade() is None
    assert virtual.active_upgrade_cached is None

    # Test active_upgrades returns all with overrides
    active_upgrades = virtual.active_upgrades()
    assert len(active_upgrades) == 2

    # Find upgrades by ID
    upgrade1_active = next(u for u in active_upgrades if u.id == upgrade1.id)
    upgrade2_active = next(u for u in active_upgrades if u.id == upgrade2.id)

    assert upgrade1_active.cost_for_fighter == 20  # No override
    assert upgrade2_active.cost_for_fighter == 15  # Override

    # Test active_upgrades_display with non-cumulative costs
    display = virtual.active_upgrades_display
    assert len(display) == 2

    # Find displays by upgrade ID
    upgrade1_display = next(d for d in display if d["upgrade"].id == upgrade1.id)
    upgrade2_display = next(d for d in display if d["upgrade"].id == upgrade2.id)

    # For MULTI mode, costs are individual (not cumulative)
    assert upgrade1_display["cost_int"] == 20
    assert upgrade2_display["cost_int"] == 15  # Overridden cost
