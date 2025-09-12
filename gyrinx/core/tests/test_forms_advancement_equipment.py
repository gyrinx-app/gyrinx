import pytest

from gyrinx.content.models import ContentAdvancementEquipment
from gyrinx.core.forms.advancement import AdvancementTypeForm
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_advancement_type_form_includes_equipment_choices(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test that equipment advancements appear in AdvancementTypeForm choices."""
    house = make_content_house("Test House")

    equipment1 = make_equipment("Plasma Gun", cost=100, rarity="R")
    equipment2 = make_equipment("Power Sword", cost=50, rarity="C")

    # Create equipment advancement with both options enabled
    advancement_both = ContentAdvancementEquipment.objects.create(
        name="Elite Weapons",
        xp_cost=20,
        enable_chosen=True,
        enable_random=True,
    )
    advancement_both.equipment.set([equipment1, equipment2])

    # Create equipment advancement with only chosen enabled
    advancement_chosen = ContentAdvancementEquipment.objects.create(
        name="Chosen Weapon",
        xp_cost=15,
        enable_chosen=True,
        enable_random=False,
    )
    advancement_chosen.equipment.add(equipment1)

    # Create equipment advancement with only random enabled
    advancement_random = ContentAdvancementEquipment.objects.create(
        name="Random Weapon",
        xp_cost=10,
        enable_chosen=False,
        enable_random=True,
    )
    advancement_random.equipment.add(equipment2)

    # Create fighter
    fighter_type = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )
    gang_list = make_list("Test Gang", content_house=house)
    fighter = make_list_fighter(gang_list, "Test Fighter", content_fighter=fighter_type)

    # Create form
    form = AdvancementTypeForm(fighter=fighter)

    # Get the choices
    choices = dict(form.fields["advancement_choice"].choices)

    # Check that all expected equipment choices are present
    assert f"equipment_chosen_{advancement_both.id}" in choices
    assert f"equipment_random_{advancement_both.id}" in choices
    assert f"equipment_chosen_{advancement_chosen.id}" in choices
    assert f"equipment_random_{advancement_random.id}" in choices

    # Check the labels
    assert choices[f"equipment_chosen_{advancement_both.id}"] == "Chosen Elite Weapons"
    assert choices[f"equipment_random_{advancement_both.id}"] == "Random Elite Weapons"
    assert (
        choices[f"equipment_chosen_{advancement_chosen.id}"] == "Chosen Chosen Weapon"
    )
    assert (
        choices[f"equipment_random_{advancement_random.id}"] == "Random Random Weapon"
    )

    # Verify that disabled options don't appear
    assert f"equipment_random_{advancement_chosen.id}" not in choices
    assert f"equipment_chosen_{advancement_random.id}" not in choices


@pytest.mark.django_db
def test_advancement_type_form_respects_house_restrictions(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test that equipment advancements respect house restrictions."""
    house1 = make_content_house("House 1")
    house2 = make_content_house("House 2")

    equipment = make_equipment("House Special", cost=100, rarity="R")

    # Create house-restricted advancement
    advancement = ContentAdvancementEquipment.objects.create(
        name="House 1 Special",
        xp_cost=25,
        enable_chosen=True,
    )
    advancement.equipment.add(equipment)
    advancement.restricted_to_houses.add(house1)

    # Create fighter from house1
    fighter_type1 = make_content_fighter(
        type="House1 Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house1,
        base_cost=50,
    )
    list1 = make_list("Gang 1", content_house=house1)
    fighter1 = make_list_fighter(list1, "Fighter 1", content_fighter=fighter_type1)

    # Create fighter from house2
    fighter_type2 = make_content_fighter(
        type="House2 Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house2,
        base_cost=50,
    )
    list2 = make_list("Gang 2", content_house=house2)
    fighter2 = make_list_fighter(list2, "Fighter 2", content_fighter=fighter_type2)

    # Create forms
    form1 = AdvancementTypeForm(fighter=fighter1)
    form2 = AdvancementTypeForm(fighter=fighter2)

    # Get the choices
    choices1 = dict(form1.fields["advancement_choice"].choices)
    choices2 = dict(form2.fields["advancement_choice"].choices)

    # House1 fighter should see the advancement
    assert f"equipment_chosen_{advancement.id}" in choices1

    # House2 fighter should not see the advancement
    assert f"equipment_chosen_{advancement.id}" not in choices2


@pytest.mark.django_db
def test_advancement_type_form_respects_category_restrictions(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test that equipment advancements respect fighter category restrictions."""
    house = make_content_house("Test House")

    equipment = make_equipment("Champion Gear", cost=100, rarity="R")

    # Create category-restricted advancement
    advancement = ContentAdvancementEquipment.objects.create(
        name="Elite Equipment",
        xp_cost=30,
        restricted_to_fighter_categories=["CHAMPION", "LEADER"],
        enable_random=True,
    )
    advancement.equipment.add(equipment)

    # Create ganger
    ganger_type = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )
    gang_list = make_list("Test Gang", content_house=house)
    ganger = make_list_fighter(gang_list, "Ganger", content_fighter=ganger_type)

    # Create champion
    champion_type = make_content_fighter(
        type="Champion",
        category=FighterCategoryChoices.CHAMPION,
        house=house,
        base_cost=100,
    )
    champion = make_list_fighter(gang_list, "Champion", content_fighter=champion_type)

    # Create forms
    ganger_form = AdvancementTypeForm(fighter=ganger)
    champion_form = AdvancementTypeForm(fighter=champion)

    # Get the choices
    ganger_choices = dict(ganger_form.fields["advancement_choice"].choices)
    champion_choices = dict(champion_form.fields["advancement_choice"].choices)

    # Ganger should not see the advancement
    assert f"equipment_random_{advancement.id}" not in ganger_choices

    # Champion should see the advancement
    assert f"equipment_random_{advancement.id}" in champion_choices


@pytest.mark.django_db
def test_all_equipment_choices_classmethod():
    """Test the all_equipment_choices classmethod returns correct mapping."""
    # Create some equipment advancements
    adv1 = ContentAdvancementEquipment.objects.create(
        name="Weapons Pack",
        xp_cost=20,
        enable_chosen=True,
        enable_random=True,
    )

    adv2 = ContentAdvancementEquipment.objects.create(
        name="Armor Upgrade",
        xp_cost=15,
        enable_chosen=True,
        enable_random=False,
    )

    # Get all equipment choices
    choices = AdvancementTypeForm.all_equipment_choices()

    # Check expected choices exist
    assert f"equipment_chosen_{adv1.id}" in choices
    assert f"equipment_random_{adv1.id}" in choices
    assert f"equipment_chosen_{adv2.id}" in choices

    # Check labels
    assert choices[f"equipment_chosen_{adv1.id}"] == "Chosen Weapons Pack"
    assert choices[f"equipment_random_{adv1.id}"] == "Random Weapons Pack"
    assert choices[f"equipment_chosen_{adv2.id}"] == "Chosen Armor Upgrade"

    # Check that disabled option doesn't exist
    assert f"equipment_random_{adv2.id}" not in choices


@pytest.mark.django_db
def test_all_advancement_choices_includes_equipment():
    """Test that all_advancement_choices includes equipment choices."""
    # Create an equipment advancement
    adv = ContentAdvancementEquipment.objects.create(
        name="Test Equipment",
        xp_cost=10,
        enable_chosen=True,
    )

    # Get all advancement choices
    choices = AdvancementTypeForm.all_advancement_choices()

    # Check that equipment choice is included
    assert f"equipment_chosen_{adv.id}" in choices
    assert choices[f"equipment_chosen_{adv.id}"] == "Chosen Test Equipment"

    # Also check that skill choices are still there
    assert "skill_primary_random" in choices
    assert "skill_primary_chosen" in choices
