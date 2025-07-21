import pytest
from django.contrib.auth.models import User

from gyrinx.content.models import ContentEquipment, ContentFighter, ContentHouse
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
