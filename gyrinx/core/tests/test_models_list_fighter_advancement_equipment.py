import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentSkill,
    ContentSkillCategory,
)
from gyrinx.core.models import (
    ListFighterAdvancement,
    ListFighterEquipmentAssignment,
)
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_list_fighter_advancement_equipment_creation(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test creating an equipment advancement."""
    house = make_content_house("Test House")

    equipment = make_equipment(
        name="Advanced Weapon",
        cost=75,
        rarity="R",
    )

    fighter_type = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )

    gang_list = make_list("Test Gang", content_house=house)
    fighter = make_list_fighter(
        gang_list, "Test Fighter", content_fighter=fighter_type, xp_current=50
    )

    advancement = ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
        equipment=equipment,
        xp_cost=20,
        cost_increase=30,
        owner=user,
    )

    assert advancement.advancement_type == ListFighterAdvancement.ADVANCEMENT_EQUIPMENT
    assert advancement.equipment == equipment
    assert advancement.xp_cost == 20
    assert advancement.cost_increase == 30
    assert str(advancement) == f"{fighter.name} - {equipment.name}"


@pytest.mark.django_db
def test_list_fighter_advancement_equipment_apply(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test applying an equipment advancement."""
    house = make_content_house("Test House")

    equipment = make_equipment(
        name="Power Armor",
        cost=100,
        rarity="R",
    )

    fighter_type = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )

    gang_list = make_list("Test Gang", content_house=house)
    fighter = make_list_fighter(
        gang_list,
        "Test Fighter",
        content_fighter=fighter_type,
        xp_current=50,
    )

    # Verify fighter doesn't have the equipment yet
    assert not ListFighterEquipmentAssignment.objects.filter(
        list_fighter=fighter,
        content_equipment=equipment,
    ).exists()

    advancement = ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
        equipment=equipment,
        xp_cost=25,
        cost_increase=40,
        owner=user,
    )

    # Apply the advancement
    advancement.apply_advancement()

    # Check that equipment was assigned
    assignment = ListFighterEquipmentAssignment.objects.get(
        list_fighter=fighter,
        content_equipment=equipment,
    )
    assert assignment.content_equipment == equipment

    # Check XP was deducted
    fighter.refresh_from_db()
    assert fighter.xp_current == 25  # 50 - 25

    # Note: Fighter cost increase is handled in the view, not in apply_advancement


@pytest.mark.django_db
def test_list_fighter_advancement_equipment_validation(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test validation for equipment advancements."""
    house = make_content_house("Test House")

    equipment = make_equipment(name="Test Gun", cost=50, rarity="C")
    skill_category = ContentSkillCategory.objects.create(name="Test Category")
    skill = ContentSkill.objects.create(name="Test Skill", category=skill_category)

    fighter_type = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )

    gang_list = make_list("Test Gang", content_house=house)
    fighter = make_list_fighter(gang_list, "Test Fighter", content_fighter=fighter_type)

    # Valid equipment advancement
    advancement = ListFighterAdvancement(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
        equipment=equipment,
        xp_cost=15,
        owner=user,
    )
    advancement.full_clean()  # Should not raise

    # Equipment advancement without equipment
    advancement = ListFighterAdvancement(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
        xp_cost=15,
        owner=user,
    )
    with pytest.raises(ValidationError) as exc_info:
        advancement.full_clean()
    assert "Equipment advancement requires equipment assignment to be selected" in str(
        exc_info.value
    )

    # Equipment advancement with skill (invalid)
    advancement = ListFighterAdvancement(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
        equipment=equipment,
        skill=skill,
        xp_cost=15,
        owner=user,
    )
    with pytest.raises(ValidationError) as exc_info:
        advancement.full_clean()
    assert "Equipment advancement should not have stat or skill selected" in str(
        exc_info.value
    )

    # Equipment advancement with stat (invalid)
    advancement = ListFighterAdvancement(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
        equipment=equipment,
        stat_increased="weapon_skill",
        xp_cost=15,
        owner=user,
    )
    with pytest.raises(ValidationError) as exc_info:
        advancement.full_clean()
    assert "Equipment advancement should not have stat or skill selected" in str(
        exc_info.value
    )


@pytest.mark.django_db
def test_list_fighter_advancement_equipment_multiple_assignments(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test that the same equipment can be gained multiple times through advancement."""
    house = make_content_house("Test House")

    equipment = make_equipment(
        name="Stub Gun",
        cost=5,
        rarity="C",
    )

    fighter_type = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )

    gang_list = make_list("Test Gang", content_house=house)
    fighter = make_list_fighter(
        gang_list, "Test Fighter", content_fighter=fighter_type, xp_current=100
    )

    # First advancement
    advancement1 = ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
        equipment=equipment,
        xp_cost=10,
        owner=user,
    )
    advancement1.apply_advancement()

    # Second advancement for the same equipment
    advancement2 = ListFighterAdvancement.objects.create(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
        equipment=equipment,
        xp_cost=10,
        owner=user,
    )
    advancement2.apply_advancement()

    # Should have two assignments of the same equipment
    assignments = ListFighterEquipmentAssignment.objects.filter(
        list_fighter=fighter,
        content_equipment=equipment,
        archived=False,
    )
    assert assignments.count() == 2


@pytest.mark.django_db
def test_list_fighter_advancement_type_choices():
    """Test that ADVANCEMENT_EQUIPMENT is in the type choices."""
    choices_dict = dict(ListFighterAdvancement.ADVANCEMENT_TYPE_CHOICES)

    assert ListFighterAdvancement.ADVANCEMENT_STAT in choices_dict
    assert ListFighterAdvancement.ADVANCEMENT_SKILL in choices_dict
    assert ListFighterAdvancement.ADVANCEMENT_EQUIPMENT in choices_dict
    assert ListFighterAdvancement.ADVANCEMENT_OTHER in choices_dict

    assert choices_dict[ListFighterAdvancement.ADVANCEMENT_EQUIPMENT] == "New Equipment"


@pytest.mark.django_db
def test_list_fighter_advancement_other_types_dont_have_equipment(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test that other advancement types can't have equipment."""
    house = make_content_house("Test House")

    equipment = make_equipment(name="Test Equipment", cost=20, rarity="C")

    fighter_type = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )

    gang_list = make_list("Test Gang", content_house=house)
    fighter = make_list_fighter(gang_list, "Test Fighter", content_fighter=fighter_type)

    # Stat advancement with equipment (invalid)
    advancement = ListFighterAdvancement(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="weapon_skill",
        equipment=equipment,
        xp_cost=10,
        owner=user,
    )
    with pytest.raises(ValidationError) as exc_info:
        advancement.full_clean()
    assert "Stat advancement should not have skill or equipment selected" in str(
        exc_info.value
    )

    # Skill advancement with equipment (invalid)
    skill_category = ContentSkillCategory.objects.create(name="Test Category 2")
    skill = ContentSkill.objects.create(name="Test Skill", category=skill_category)
    advancement = ListFighterAdvancement(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        skill=skill,
        equipment=equipment,
        xp_cost=10,
        owner=user,
    )
    with pytest.raises(ValidationError) as exc_info:
        advancement.full_clean()
    assert "Skill advancement should not have stat or equipment selected" in str(
        exc_info.value
    )

    # Other advancement with equipment (invalid)
    advancement = ListFighterAdvancement(
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_OTHER,
        description="Some other advancement",
        equipment=equipment,
        xp_cost=10,
        owner=user,
    )
    with pytest.raises(ValidationError) as exc_info:
        advancement.full_clean()
    assert (
        "Other advancement should not have a stat, skill, or equipment selected"
        in str(exc_info.value)
    )
