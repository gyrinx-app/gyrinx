import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentAdvancementAssignment,
    ContentAdvancementEquipment,
)
from gyrinx.core.models import ListFighterEquipmentAssignment
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_content_advancement_equipment_creation(make_equipment):
    """Test basic creation of ContentAdvancementEquipment."""

    advancement = ContentAdvancementEquipment.objects.create(
        name="Legendary Weapons",
        xp_cost=20,
        cost_increase=50,
        enable_chosen=True,
    )

    assert advancement.name == "Legendary Weapons"
    assert advancement.xp_cost == 20
    assert advancement.cost_increase == 50
    assert str(advancement) == "Legendary Weapons"
    assert advancement.enable_chosen is True
    assert advancement.enable_random is False


@pytest.mark.django_db
def test_content_advancement_equipment_enable_flags_validation():
    """Test that at least one enable flag must be set."""
    # Test with no flags set - should fail validation
    advancement = ContentAdvancementEquipment(
        name="Invalid Advancement",
        xp_cost=20,
        cost_increase=0,
        enable_chosen=False,
        enable_random=False,
    )

    with pytest.raises(ValidationError) as exc_info:
        advancement.full_clean()
    assert "At least one selection type (random or chosen) must be enabled" in str(
        exc_info.value
    )

    # Test with enable_chosen set - should pass
    advancement_chosen = ContentAdvancementEquipment(
        name="Chosen Only",
        xp_cost=15,
        cost_increase=0,
        enable_chosen=True,
        enable_random=False,
    )
    advancement_chosen.full_clean()  # Should not raise

    # Test with enable_random set - should pass
    advancement_random = ContentAdvancementEquipment(
        name="Random Only",
        xp_cost=15,
        cost_increase=0,
        enable_chosen=False,
        enable_random=True,
    )
    advancement_random.full_clean()  # Should not raise

    # Test with both flags set - should pass
    advancement_both = ContentAdvancementEquipment(
        name="Both Options",
        xp_cost=15,
        cost_increase=0,
        enable_chosen=True,
        enable_random=True,
    )
    advancement_both.full_clean()  # Should not raise


@pytest.mark.django_db
def test_content_advancement_equipment_house_restrictions(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test house restrictions on equipment advancement."""
    house1 = make_content_house("House 1")
    house2 = make_content_house("House 2")

    advancement = ContentAdvancementEquipment.objects.create(
        name="House Special",
        xp_cost=15,
        enable_chosen=True,
    )
    advancement.restricted_to_houses.add(house1)

    # Create fighters from different houses
    fighter_type1 = make_content_fighter(
        type="Ganger Type 1",
        category=FighterCategoryChoices.GANGER,
        house=house1,
        base_cost=50,
    )
    list1 = make_list("Gang 1", content_house=house1)
    fighter1 = make_list_fighter(list1, "Fighter 1", content_fighter=fighter_type1)

    fighter_type2 = make_content_fighter(
        type="Ganger Type 2",
        category=FighterCategoryChoices.GANGER,
        house=house2,
        base_cost=50,
    )
    list2 = make_list("Gang 2", content_house=house2)
    fighter2 = make_list_fighter(list2, "Fighter 2", content_fighter=fighter_type2)

    # Fighter from house1 should have access
    assert advancement.is_available_to_fighter(fighter1) is True

    # Fighter from house2 should not have access
    assert advancement.is_available_to_fighter(fighter2) is False


@pytest.mark.django_db
def test_content_advancement_equipment_category_restrictions(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test fighter category restrictions on equipment advancement."""
    house = make_content_house("Test House")

    # Create content fighters with different categories
    ganger_content = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )
    champion_content = make_content_fighter(
        type="Champion",
        category=FighterCategoryChoices.CHAMPION,
        house=house,
        base_cost=100,
    )

    advancement = ContentAdvancementEquipment.objects.create(
        name="Elite Equipment",
        xp_cost=25,
        restricted_to_fighter_categories=["CHAMPION", "LEADER"],
        enable_random=True,
    )

    # Create list fighters
    gang_list = make_list("Test Gang", content_house=house)
    ganger = make_list_fighter(
        gang_list, "Ganger Fighter", content_fighter=ganger_content
    )
    champion = make_list_fighter(
        gang_list, "Champion Fighter", content_fighter=champion_content
    )

    # Ganger should not have access
    assert advancement.is_available_to_fighter(ganger) is False

    # Champion should have access
    assert advancement.is_available_to_fighter(champion) is True


@pytest.mark.django_db
def test_content_advancement_equipment_multiple_equipment_choices(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test advancement with multiple equipment options."""
    house = make_content_house("Test House")

    equipment1 = make_equipment(name="Option 1", cost=30, rarity="C")
    equipment2 = make_equipment(name="Option 2", cost=40, rarity="C")
    equipment3 = make_equipment(name="Option 3", cost=50, rarity="R")

    advancement = ContentAdvancementEquipment.objects.create(
        name="Choose Your Weapon",
        xp_cost=15,
        enable_chosen=True,
    )
    # Create assignments for each equipment option
    ContentAdvancementAssignment.objects.create(
        advancement=advancement,
        equipment=equipment1,
    )
    ContentAdvancementAssignment.objects.create(
        advancement=advancement,
        equipment=equipment2,
    )
    ContentAdvancementAssignment.objects.create(
        advancement=advancement,
        equipment=equipment3,
    )

    fighter_type = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )
    gang_list = make_list("Test Gang", content_house=house)
    fighter = make_list_fighter(gang_list, "Test Fighter", content_fighter=fighter_type)

    # Fighter should have access
    assert advancement.is_available_to_fighter(fighter) is True

    # Assign one of the equipment options
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=equipment2,
    )

    # Fighter should still have access even after owning some of the options
    assert advancement.is_available_to_fighter(fighter) is True


@pytest.mark.django_db
def test_content_advancement_equipment_combined_restrictions(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test advancement with both house and category restrictions."""
    house1 = make_content_house("House 1")
    house2 = make_content_house("House 2")

    champion_content = make_content_fighter(
        type="Champion",
        category=FighterCategoryChoices.CHAMPION,
        house=house1,
        base_cost=100,
    )
    ganger_content = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house1,
        base_cost=50,
    )

    advancement = ContentAdvancementEquipment.objects.create(
        name="House Elite Special",
        xp_cost=30,
        restricted_to_fighter_categories=["CHAMPION", "LEADER"],
        enable_random=True,
    )
    advancement.restricted_to_houses.add(house1)

    # Create test cases
    list1 = make_list("Gang 1", content_house=house1)
    list2 = make_list("Gang 2", content_house=house2)

    # House1 champion - should have access
    h1_champion = make_list_fighter(
        list1, "H1 Champion", content_fighter=champion_content
    )
    assert advancement.is_available_to_fighter(h1_champion) is True

    # House1 ganger - wrong category
    h1_ganger = make_list_fighter(list1, "H1 Ganger", content_fighter=ganger_content)
    assert advancement.is_available_to_fighter(h1_ganger) is False

    # House2 champion - wrong house
    h2_champion_content = make_content_fighter(
        type="House2 Champion",
        category=FighterCategoryChoices.CHAMPION,
        house=house2,
        base_cost=100,
    )
    h2_champion = make_list_fighter(
        list2, "H2 Champion", content_fighter=h2_champion_content
    )
    assert advancement.is_available_to_fighter(h2_champion) is False
