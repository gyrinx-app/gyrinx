import pytest
from django.contrib.auth.models import User

from gyrinx.content.models import ContentEquipment, ContentFighter, ContentHouse
from gyrinx.core.handlers.campaign_operations import handle_campaign_start
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List, ListFighter


@pytest.mark.django_db
def test_stash_equipment_cloned_to_campaign():
    """Test that equipment assigned to the stash is cloned when a list goes into campaign mode."""
    # Create a user and house
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    # Create a list
    list_obj = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    # Get or create a stash ContentFighter
    stash_cf, _ = ContentFighter.objects.get_or_create(
        house=house,
        is_stash=True,
        defaults={
            "type": "Stash",
            "category": "STASH",
            "base_cost": 0,
        },
    )

    # Create a stash ListFighter
    stash_fighter = ListFighter.objects.create(
        name="Gang Stash",
        content_fighter=stash_cf,
        list=list_obj,
        owner=user,
    )

    # Create equipment categories
    from gyrinx.content.models import ContentEquipmentCategory

    basic_weapons_cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Basic Weapons"
    )
    grenades_cat, _ = ContentEquipmentCategory.objects.get_or_create(name="Grenades")

    # Create some equipment
    lasgun = ContentEquipment.objects.create(
        name="Lasgun",
        cost="10",
        category=basic_weapons_cat,
    )
    frag_grenade = ContentEquipment.objects.create(
        name="Frag Grenade",
        cost="30",
        category=grenades_cat,
    )

    # Assign equipment to the stash
    stash_fighter.assign(lasgun)
    stash_fighter.assign(frag_grenade)

    # Verify stash has equipment
    assert len(stash_fighter.assignments()) == 2
    lasgun_assignment = next(
        a for a in stash_fighter.assignments() if a.content_equipment == lasgun
    )
    assert lasgun_assignment.content_equipment == lasgun
    frag_assignment = next(
        a for a in stash_fighter.assignments() if a.content_equipment == frag_grenade
    )
    assert frag_assignment.content_equipment == frag_grenade

    # Create a campaign and clone the list for it
    campaign = Campaign.objects.create(name="Test Campaign", owner=user)
    cloned_list = list_obj.clone(for_campaign=campaign)

    # Verify the clone has a stash fighter
    cloned_stash = cloned_list.listfighter_set.filter(
        content_fighter__is_stash=True
    ).first()
    assert cloned_stash is not None
    assert cloned_stash.name == "Stash"

    # Verify the cloned stash has the same equipment
    assert len(cloned_stash.assignments()) == 2

    cloned_lasgun = next(
        a for a in cloned_stash.assignments() if a.content_equipment == lasgun
    )
    assert cloned_lasgun.content_equipment == lasgun

    cloned_frag = next(
        a for a in cloned_stash.assignments() if a.content_equipment == frag_grenade
    )
    assert cloned_frag.content_equipment == frag_grenade


@pytest.mark.django_db
def test_stash_equipment_not_cloned_when_no_stash_in_original():
    """Test that when original list has no stash, campaign clone creates empty stash."""
    # Create a user and house
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    # Create a list without a stash
    list_obj = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    # Verify no stash exists
    assert not list_obj.listfighter_set.filter(content_fighter__is_stash=True).exists()

    # Create a campaign and clone the list for it
    campaign = Campaign.objects.create(name="Test Campaign", owner=user)
    cloned_list = list_obj.clone(for_campaign=campaign)

    # Verify the clone has a stash fighter
    cloned_stash = cloned_list.listfighter_set.filter(
        content_fighter__is_stash=True
    ).first()
    assert cloned_stash is not None
    assert cloned_stash.name == "Stash"

    # Verify the cloned stash has no equipment
    assert len(cloned_stash.assignments()) == 0


@pytest.mark.django_db
def test_stash_fighter_facts_in_sync_after_campaign_start(settings):
    """
    Regression test: stash fighter rating_current should match equipment cost after campaign start.

    Scenario:
    1. Create a list with equipment in the stash
    2. Add list to campaign
    3. Start the campaign
    4. Check that cloned stash fighter's facts match the cost of assignments
    """
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    # Create a user and house
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    # Create a list
    list_obj = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    # Get or create a stash ContentFighter
    stash_cf, _ = ContentFighter.objects.get_or_create(
        house=house,
        is_stash=True,
        defaults={
            "type": "Stash",
            "category": "STASH",
            "base_cost": 0,
        },
    )

    # Create a stash ListFighter
    stash_fighter = ListFighter.objects.create(
        name="Gang Stash",
        content_fighter=stash_cf,
        list=list_obj,
        owner=user,
    )

    # Create equipment category
    from gyrinx.content.models import ContentEquipmentCategory

    basic_weapons_cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Basic Weapons"
    )

    # Create equipment with known cost
    lasgun = ContentEquipment.objects.create(
        name="Lasgun",
        cost="50",
        category=basic_weapons_cat,
    )

    # Assign equipment to the stash
    assignment = stash_fighter.assign(lasgun)
    assert assignment.cost_int() == 50

    # Verify stash cost
    assert stash_fighter.cost_int() == 50

    # Create a campaign and add the list
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.PRE_CAMPAIGN,
    )
    campaign.lists.add(list_obj)

    # Start the campaign using the handler
    result = handle_campaign_start(user=user, campaign=campaign)
    assert result.campaign == campaign

    # Get the cloned list from the campaign
    cloned_list = campaign.lists.first()
    assert cloned_list is not None
    assert cloned_list.status == List.CAMPAIGN_MODE

    # Get the cloned stash fighter
    cloned_stash = cloned_list.listfighter_set.filter(
        content_fighter__is_stash=True
    ).first()
    assert cloned_stash is not None

    # Verify stash has the cloned equipment
    assert len(cloned_stash.assignments()) == 1
    cloned_assignment = cloned_stash.assignments()[0]
    assert cloned_assignment.content_equipment == lasgun
    assert cloned_assignment.cost_int() == 50

    # CRITICAL: Check that stash fighter's rating_current matches the equipment cost
    # This is the bug we're testing for - the stash fighter's cached rating
    # should be updated to reflect the cloned equipment
    assert cloned_stash.cost_int() == 50, (
        f"Stash fighter cost_int() should be 50, got {cloned_stash.cost_int()}"
    )

    facts = cloned_stash.facts()
    assert facts is not None, "Stash fighter should not be dirty after campaign start"
    assert facts.rating == 50, (
        f"Stash fighter facts.rating should be 50, got {facts.rating}"
    )

    # Also verify the cloned list is not dirty
    list_facts = cloned_list.facts()
    assert list_facts is not None, (
        "Cloned list should not be dirty after campaign start"
    )

    # The stash value should match
    assert list_facts.stash == 50, f"List stash should be 50, got {list_facts.stash}"
