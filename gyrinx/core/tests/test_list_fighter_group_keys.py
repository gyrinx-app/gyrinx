import pytest
from django.contrib.auth import get_user_model

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentFighterProfile,
    ContentFighter,
    ContentHouse,
)
from gyrinx.core.models.list import List, ListFighter, ListFighterEquipmentAssignment
from gyrinx.models import FighterCategoryChoices

User = get_user_model()


@pytest.mark.django_db
def test_vehicle_and_crew_have_same_group_key():
    """Test that vehicles and their crew have the same group key (the crew member's ID)."""
    # Create a user and house
    user = User.objects.create_user("testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    # Create a list
    test_list = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
    )

    # Create a regular fighter (who will be the crew)
    crew_cf = ContentFighter.objects.create(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
        house=house,
        movement='5"',
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="8+",
        cool="8+",
        willpower="9+",
        intelligence="9+",
    )
    crew_lf = ListFighter.objects.create(
        name="Crew Member",
        list=test_list,
        content_fighter=crew_cf,
    )

    # Create vehicle equipment with fighter profile
    vehicle_ce = ContentEquipment.objects.create(
        name="Vehicle Equipment",
        cost=100,
    )
    vehicle_cf = ContentFighter.objects.create(
        type="Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        base_cost=0,  # Vehicles don't have base cost
        house=house,
        movement='7"',
        weapon_skill="5+",
        ballistic_skill="4+",
        strength="5",
        toughness="5",
        wounds="3",
        initiative="5+",
        attacks="*",
        leadership="7+",
        cool="7+",
        willpower="8+",
        intelligence="8+",
    )
    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle_ce,
        content_fighter=vehicle_cf,
    )

    # Assign vehicle equipment to crew member
    assignment = ListFighterEquipmentAssignment(
        list_fighter=crew_lf,
        content_equipment=vehicle_ce,
    )
    assignment.save()

    # The save should have created a linked fighter (the vehicle)
    assert assignment.child_fighter is not None
    vehicle_lf = assignment.child_fighter

    # Get fighters with group keys
    fighters_with_groups = ListFighter.objects.with_group_keys().filter(list=test_list)

    # Find the crew member and vehicle in the results
    crew_with_group = fighters_with_groups.get(id=crew_lf.id)
    vehicle_with_group = fighters_with_groups.get(id=vehicle_lf.id)

    # Check that both have the same group key (the crew member's ID)
    assert crew_with_group.group_key == crew_lf.id
    assert vehicle_with_group.group_key == crew_lf.id
    assert crew_with_group.group_key == vehicle_with_group.group_key


@pytest.mark.django_db
def test_regular_fighters_have_unique_group_keys():
    """Test that regular fighters (non-vehicles, non-crew) have unique group keys."""
    # Create a user and house
    user = User.objects.create_user("testuser2", password="testpass")
    house = ContentHouse.objects.create(name="Test House 2")

    # Create a list
    test_list = List.objects.create(
        name="Test List 2",
        owner=user,
        content_house=house,
    )

    # Create two regular fighters
    cf1 = ContentFighter.objects.create(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
        house=house,
        movement='5"',
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="8+",
        cool="8+",
        willpower="9+",
        intelligence="9+",
    )
    lf1 = ListFighter.objects.create(
        name="Fighter 1",
        list=test_list,
        content_fighter=cf1,
    )

    cf2 = ContentFighter.objects.create(
        type="Champion",
        category=FighterCategoryChoices.CHAMPION,
        base_cost=100,
        house=house,
        movement='5"',
        weapon_skill="3+",
        ballistic_skill="3+",
        strength="3",
        toughness="3",
        wounds="2",
        initiative="3+",
        attacks="2",
        leadership="7+",
        cool="7+",
        willpower="8+",
        intelligence="8+",
    )
    lf2 = ListFighter.objects.create(
        name="Fighter 2",
        list=test_list,
        content_fighter=cf2,
    )

    # Get fighters with group keys
    fighters_with_groups = ListFighter.objects.with_group_keys().filter(list=test_list)

    # Check that each fighter has their own ID as their group key
    fighter1_with_group = fighters_with_groups.get(id=lf1.id)
    fighter2_with_group = fighters_with_groups.get(id=lf2.id)

    assert fighter1_with_group.group_key == lf1.id
    assert fighter2_with_group.group_key == lf2.id
    assert fighter1_with_group.group_key != fighter2_with_group.group_key


@pytest.mark.django_db
def test_list_view_includes_fighters_with_groups(client, django_user_model):
    """Test that the list view includes fighters_with_groups in context."""
    # Create a user and log in
    user = django_user_model.objects.create_user("testuser3", password="testpass")
    client.login(username="testuser3", password="testpass")

    # Create a house and list
    house = ContentHouse.objects.create(name="Test House 3")
    test_list = List.objects.create(
        name="Test List 3",
        owner=user,
        content_house=house,
    )

    # Create a fighter
    cf = ContentFighter.objects.create(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        base_cost=50,
        house=house,
        movement='5"',
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="8+",
        cool="8+",
        willpower="9+",
        intelligence="9+",
    )
    ListFighter.objects.create(
        name="Test Fighter",
        list=test_list,
        content_fighter=cf,
    )

    # Access the list view
    response = client.get(f"/list/{test_list.id}")

    # Check that the view returns successfully
    assert response.status_code == 200

    # Check that fighters_with_groups is in the context
    assert "fighters_with_groups" in response.context
    fighters = response.context["fighters_with_groups"]

    # Check that the fighters have group_key attribute
    for fighter in fighters:
        assert hasattr(fighter, "group_key")


@pytest.mark.django_db
def test_stash_vehicles_have_unique_group_keys():
    """Test that vehicles linked to the stash have their own ID as group key (not grouped with stash)."""
    # Create a user and house
    user = User.objects.create_user("testuser4", password="testpass")
    house = ContentHouse.objects.create(name="Test House 4")

    # Create a campaign list
    test_list = List.objects.create(
        name="Test Campaign List",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
    )

    # Create a stash fighter
    stash_cf = ContentFighter.objects.create(
        type="Stash",
        category=FighterCategoryChoices.STASH,
        is_stash=True,
        base_cost=0,
        house=house,
    )
    stash_lf = ListFighter.objects.create(
        name="Stash",
        list=test_list,
        content_fighter=stash_cf,
    )

    # Create two vehicle equipment items with fighter profiles
    vehicle1_ce = ContentEquipment.objects.create(
        name="Vehicle Equipment 1",
        cost=100,
    )
    vehicle1_cf = ContentFighter.objects.create(
        type="Vehicle 1",
        category=FighterCategoryChoices.VEHICLE,
        base_cost=0,
        house=house,
        movement='7"',
        weapon_skill="5+",
        ballistic_skill="4+",
        strength="5",
        toughness="5",
        wounds="3",
        initiative="5+",
        attacks="*",
        leadership="7+",
        cool="7+",
        willpower="8+",
        intelligence="8+",
    )
    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle1_ce,
        content_fighter=vehicle1_cf,
    )

    vehicle2_ce = ContentEquipment.objects.create(
        name="Vehicle Equipment 2",
        cost=150,
    )
    vehicle2_cf = ContentFighter.objects.create(
        type="Vehicle 2",
        category=FighterCategoryChoices.VEHICLE,
        base_cost=0,
        house=house,
        movement='8"',
        weapon_skill="5+",
        ballistic_skill="4+",
        strength="5",
        toughness="5",
        wounds="3",
        initiative="5+",
        attacks="*",
        leadership="7+",
        cool="7+",
        willpower="8+",
        intelligence="8+",
    )
    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle2_ce,
        content_fighter=vehicle2_cf,
    )

    # Assign both vehicles to the stash
    assignment1 = ListFighterEquipmentAssignment(
        list_fighter=stash_lf,
        content_equipment=vehicle1_ce,
    )
    assignment1.save()
    vehicle1_lf = assignment1.child_fighter

    assignment2 = ListFighterEquipmentAssignment(
        list_fighter=stash_lf,
        content_equipment=vehicle2_ce,
    )
    assignment2.save()
    vehicle2_lf = assignment2.child_fighter

    # Get fighters with group keys
    fighters_with_groups = ListFighter.objects.with_group_keys().filter(list=test_list)

    # Find all fighters in the results
    stash_with_group = fighters_with_groups.get(id=stash_lf.id)
    vehicle1_with_group = fighters_with_groups.get(id=vehicle1_lf.id)
    vehicle2_with_group = fighters_with_groups.get(id=vehicle2_lf.id)

    # Check that stash has its own ID as group key
    assert stash_with_group.group_key == stash_lf.id

    # Check that each vehicle has its own ID as group key (not grouped with stash)
    assert vehicle1_with_group.group_key == vehicle1_lf.id
    assert vehicle2_with_group.group_key == vehicle2_lf.id

    # Check that all three have different group keys
    assert stash_with_group.group_key != vehicle1_with_group.group_key
    assert stash_with_group.group_key != vehicle2_with_group.group_key
    assert vehicle1_with_group.group_key != vehicle2_with_group.group_key
