"""Tests for psyker discipline access modifiers on equipment."""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterPsykerDisciplineAssignment,
    ContentHouse,
    ContentModPsykerDisciplineAccess,
    ContentRule,
)
from gyrinx.content.models.psyker import ContentPsykerDiscipline, ContentPsykerPower
from gyrinx.core.models import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
    ListFighterPsykerPowerAssignment,
)


@pytest.mark.django_db
def test_equipment_can_add_psyker_discipline():
    """Test that equipment can add a psyker discipline to a fighter."""
    # Create basic setup
    user = get_user_model().objects.create_user("test@example.com", "password")
    house = ContentHouse.objects.create(name="Test House")
    category = ContentEquipmentCategory.objects.create(
        name="Test Category", group="wargear"
    )

    # Create psyker disciplines
    biomancy = ContentPsykerDiscipline.objects.create(name="Biomancy", generic=False)
    telepathy = ContentPsykerDiscipline.objects.create(name="Telepathy", generic=False)

    # Create psyker powers
    power_biomancy = ContentPsykerPower.objects.create(
        name="Arachnosis", discipline=biomancy
    )
    power_telepathy = ContentPsykerPower.objects.create(
        name="Mind Control", discipline=telepathy
    )

    # Create content fighter with Biomancy discipline only
    psyker_rule, _ = ContentRule.objects.get_or_create(name="Psyker")
    content_fighter = ContentFighter.objects.create(
        type="Test Psyker",
        house=house,
        category="CHAMPION",
    )
    content_fighter.rules.add(psyker_rule)

    # Assign Biomancy discipline
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=content_fighter,
        discipline=biomancy,
    )

    # Create equipment with a modifier to add Telepathy discipline
    equipment = ContentEquipment.objects.create(
        name="Psychic Amplifier",
        category=category,
    )

    # Create the psyker discipline modifier
    modifier = ContentModPsykerDisciplineAccess.objects.create(
        discipline=telepathy,
        mode="add",
    )
    equipment.modifiers.add(modifier)

    # Create list and fighter
    list_obj = List.objects.create(
        name="Test List",
        content_house=house,
        owner=user,
    )
    list_fighter = ListFighter.objects.create(
        list=list_obj,
        content_fighter=content_fighter,
        name="Test Psyker Fighter",
    )

    # Verify fighter initially only has access to Biomancy
    available_disciplines = list_fighter.get_available_psyker_disciplines()
    assert biomancy in available_disciplines
    assert telepathy not in available_disciplines

    # Assign equipment to fighter
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )

    # Verify fighter now has access to both disciplines
    available_disciplines = list_fighter.get_available_psyker_disciplines()
    assert biomancy in available_disciplines
    assert telepathy in available_disciplines

    # Verify fighter can now take powers from Telepathy discipline
    psyker_power_assignment = ListFighterPsykerPowerAssignment(
        list_fighter=list_fighter,
        psyker_power=power_telepathy,
    )
    psyker_power_assignment.full_clean()  # Should not raise ValidationError
    psyker_power_assignment.save()

    # Verify fighter still can take powers from Biomancy discipline
    psyker_power_assignment2 = ListFighterPsykerPowerAssignment(
        list_fighter=list_fighter,
        psyker_power=power_biomancy,
    )
    psyker_power_assignment2.full_clean()  # Should not raise ValidationError
    psyker_power_assignment2.save()


@pytest.mark.django_db
def test_equipment_can_remove_psyker_discipline():
    """Test that equipment can remove a psyker discipline from a fighter."""
    # Create basic setup
    user = get_user_model().objects.create_user("test2@example.com", "password")
    house = ContentHouse.objects.create(name="Test House 2")
    category = ContentEquipmentCategory.objects.create(
        name="Test Category 2", group="wargear"
    )

    # Create psyker disciplines
    biomancy = ContentPsykerDiscipline.objects.create(name="Biomancy2", generic=False)
    telepathy = ContentPsykerDiscipline.objects.create(name="Telepathy2", generic=False)

    # Create psyker powers
    power_biomancy = ContentPsykerPower.objects.create(
        name="Arachnosis2", discipline=biomancy
    )
    power_telepathy = ContentPsykerPower.objects.create(
        name="Mind Control2", discipline=telepathy
    )

    # Create content fighter with both disciplines
    psyker_rule, _ = ContentRule.objects.get_or_create(name="Psyker")
    content_fighter = ContentFighter.objects.create(
        type="Test Psyker 2",
        house=house,
        category="CHAMPION",
    )
    content_fighter.rules.add(psyker_rule)

    # Assign both disciplines
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=content_fighter,
        discipline=biomancy,
    )
    ContentFighterPsykerDisciplineAssignment.objects.create(
        fighter=content_fighter,
        discipline=telepathy,
    )

    # Create equipment with a modifier to remove Telepathy discipline
    equipment = ContentEquipment.objects.create(
        name="Psychic Suppressor",
        category=category,
    )

    # Create the psyker discipline modifier
    modifier = ContentModPsykerDisciplineAccess.objects.create(
        discipline=telepathy,
        mode="remove",
    )
    equipment.modifiers.add(modifier)

    # Create list and fighter
    list_obj = List.objects.create(
        name="Test List 2",
        content_house=house,
        owner=user,
    )
    list_fighter = ListFighter.objects.create(
        list=list_obj,
        content_fighter=content_fighter,
        name="Test Psyker Fighter 2",
    )

    # Verify fighter initially has access to both disciplines
    available_disciplines = list_fighter.get_available_psyker_disciplines()
    assert biomancy in available_disciplines
    assert telepathy in available_disciplines

    # Assign equipment to fighter
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )

    # Verify fighter now only has access to Biomancy
    available_disciplines = list_fighter.get_available_psyker_disciplines()
    assert biomancy in available_disciplines
    assert telepathy not in available_disciplines

    # Verify fighter cannot take powers from Telepathy discipline
    psyker_power_assignment = ListFighterPsykerPowerAssignment(
        list_fighter=list_fighter,
        psyker_power=power_telepathy,
    )
    with pytest.raises(ValidationError) as exc_info:
        psyker_power_assignment.full_clean()
    assert "non-generic discipline" in str(exc_info.value)

    # Verify fighter can still take powers from Biomancy discipline
    psyker_power_assignment2 = ListFighterPsykerPowerAssignment(
        list_fighter=list_fighter,
        psyker_power=power_biomancy,
    )
    psyker_power_assignment2.full_clean()  # Should not raise ValidationError
    psyker_power_assignment2.save()


@pytest.mark.django_db
def test_equipment_psyker_discipline_modifier_non_psyker():
    """Test that psyker discipline modifiers don't affect non-psyker fighters."""
    # Create basic setup
    user = get_user_model().objects.create_user("test3@example.com", "password")
    house = ContentHouse.objects.create(name="Test House 3")
    category = ContentEquipmentCategory.objects.create(
        name="Test Category 3", group="wargear"
    )

    # Create psyker discipline
    biomancy = ContentPsykerDiscipline.objects.create(name="Biomancy3", generic=False)
    power_biomancy = ContentPsykerPower.objects.create(
        name="Arachnosis3", discipline=biomancy
    )

    # Create non-psyker content fighter
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter 3",
        house=house,
        category="GANGER",
    )
    # No psyker rule assigned

    # Create equipment with a modifier to add Biomancy discipline
    equipment = ContentEquipment.objects.create(
        name="Psychic Amplifier 3",
        category=category,
    )

    # Create the psyker discipline modifier
    modifier = ContentModPsykerDisciplineAccess.objects.create(
        discipline=biomancy,
        mode="add",
    )
    equipment.modifiers.add(modifier)

    # Create list and fighter
    list_obj = List.objects.create(
        name="Test List 3",
        content_house=house,
        owner=user,
    )
    list_fighter = ListFighter.objects.create(
        list=list_obj,
        content_fighter=content_fighter,
        name="Test Fighter 3",
    )

    # Assign equipment to fighter
    ListFighterEquipmentAssignment.objects.create(
        list_fighter=list_fighter,
        content_equipment=equipment,
    )

    # Verify fighter has access to the discipline through equipment
    available_disciplines = list_fighter.get_available_psyker_disciplines()
    assert biomancy in available_disciplines

    # But fighter still cannot take psyker powers because they're not a psyker
    psyker_power_assignment = ListFighterPsykerPowerAssignment(
        list_fighter=list_fighter,
        psyker_power=power_biomancy,
    )
    with pytest.raises(ValidationError) as exc_info:
        psyker_power_assignment.full_clean()
    assert "not a psyker" in str(exc_info.value)


@pytest.mark.django_db
def test_generic_disciplines_always_available():
    """Test that generic disciplines are always available regardless of modifiers."""
    # Create basic setup
    user = get_user_model().objects.create_user("test4@example.com", "password")
    house = ContentHouse.objects.create(name="Test House 4")
    ContentEquipmentCategory.objects.create(name="Test Category 4", group="wargear")

    # Create generic and non-generic disciplines
    generic_discipline = ContentPsykerDiscipline.objects.create(
        name="Generic Discipline", generic=True
    )
    non_generic_discipline = ContentPsykerDiscipline.objects.create(
        name="Non-Generic Discipline", generic=False
    )

    # Create psyker powers
    generic_power = ContentPsykerPower.objects.create(
        name="Generic Power", discipline=generic_discipline
    )
    non_generic_power = ContentPsykerPower.objects.create(
        name="Non-Generic Power", discipline=non_generic_discipline
    )

    # Create psyker content fighter with no specific disciplines
    psyker_rule, _ = ContentRule.objects.get_or_create(name="Psyker")
    content_fighter = ContentFighter.objects.create(
        type="Test Psyker 4",
        house=house,
        category="CHAMPION",
    )
    content_fighter.rules.add(psyker_rule)

    # Create list and fighter
    list_obj = List.objects.create(
        name="Test List 4",
        content_house=house,
        owner=user,
    )
    list_fighter = ListFighter.objects.create(
        list=list_obj,
        content_fighter=content_fighter,
        name="Test Psyker Fighter 4",
    )

    # Verify fighter can take powers from generic discipline
    psyker_power_assignment = ListFighterPsykerPowerAssignment(
        list_fighter=list_fighter,
        psyker_power=generic_power,
    )
    psyker_power_assignment.full_clean()  # Should not raise ValidationError
    psyker_power_assignment.save()

    # Verify fighter cannot take powers from non-generic discipline
    psyker_power_assignment2 = ListFighterPsykerPowerAssignment(
        list_fighter=list_fighter,
        psyker_power=non_generic_power,
    )
    with pytest.raises(ValidationError) as exc_info:
        psyker_power_assignment2.full_clean()
    assert "non-generic discipline" in str(exc_info.value)
