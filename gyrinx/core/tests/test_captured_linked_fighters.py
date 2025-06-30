import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentFighterProfile,
    ContentFighter,
    ContentHouse,
)
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import (
    CapturedFighter,
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)


@pytest.mark.django_db
def test_linked_fighter_can_be_captured():
    """Test that linked fighters can be captured and the equipment is properly unlinked."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    # Create content fighters
    main_fighter_type = ContentFighter.objects.create(
        type="Test Fighter",
        category="LEADER",
        house=house,
        base_cost=100,
    )

    linked_fighter_type = ContentFighter.objects.create(
        type="Exotic Beast",
        category="SPECIALIST",
        house=house,
        base_cost=50,
    )

    # Create equipment that creates a linked fighter
    equipment_category = ContentEquipmentCategory.objects.create(
        name="Exotic Beasts",
        group="Gear",
    )

    beast_equipment = ContentEquipment.objects.create(
        name="Cyber-mastiff",
        category=equipment_category,
        cost=100,
    )

    # Create fighter profile link
    ContentEquipmentFighterProfile.objects.create(
        equipment=beast_equipment,
        content_fighter=linked_fighter_type,
    )

    # Create campaign and lists
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    list1 = List.objects.create(
        name="Gang 1",
        content_house=house,
        owner=user,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    list2 = List.objects.create(
        name="Gang 2",
        content_house=house,
        owner=user,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    # Create main fighter
    main_fighter = ListFighter.objects.create(
        name="Leader",
        content_fighter=main_fighter_type,
        list=list1,
        owner=user,
    )

    # Assign equipment (this should create a linked fighter)
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=main_fighter,
        content_equipment=beast_equipment,
    )

    # Refresh the assignment to get the linked fighter
    assignment.refresh_from_db()

    # The assignment should have created a linked fighter
    assert assignment.linked_fighter is not None
    linked_fighter = assignment.linked_fighter
    assert linked_fighter.name == "Exotic Beast"
    assert linked_fighter.list == list1
    assert linked_fighter.owner == user, (
        f"Expected owner {user}, got {linked_fighter.owner}"
    )

    # Test that linked fighter can be captured
    client = Client()
    client.login(username="testuser", password="testpass")

    # Check that the linked fighter exists and belongs to the right list
    assert ListFighter.objects.filter(id=linked_fighter.id, list=list1).exists()

    # First GET the page to ensure it loads correctly
    get_response = client.get(
        reverse("core:list-fighter-mark-captured", args=[list1.id, linked_fighter.id])
    )
    assert get_response.status_code == 200

    # Mark the linked fighter as captured
    response = client.post(
        reverse("core:list-fighter-mark-captured", args=[list1.id, linked_fighter.id]),
        {"capturing_list": list2.id},
    )

    # Check response
    assert response.status_code == 302
    assert response.url == reverse("core:list", args=[list1.id])

    # Verify the fighter is captured
    linked_fighter.refresh_from_db()

    # Check if the capture record exists
    capture_record = CapturedFighter.objects.filter(fighter=linked_fighter).first()
    assert capture_record is not None, "No capture record found"
    assert capture_record.capturing_list == list2
    assert not capture_record.sold_to_guilders

    # Check the property works
    assert hasattr(linked_fighter, "capture_info")
    assert linked_fighter.capture_info.capturing_list == list2
    assert not linked_fighter.capture_info.sold_to_guilders

    # Verify the equipment assignment was deleted
    assert not ListFighterEquipmentAssignment.objects.filter(id=assignment.id).exists()

    # Verify the main fighter no longer has the beast equipment
    assert main_fighter.equipment.count() == 0


@pytest.mark.django_db
def test_captured_linked_fighter_shows_correct_status():
    """Test that captured linked fighters show the correct status in templates."""
    # Create test data
    user = User.objects.create_user(username="testuser2", password="testpass")
    house = ContentHouse.objects.create(name="Test House 2")

    fighter_type = ContentFighter.objects.create(
        type="Beast",
        category="SPECIALIST",
        house=house,
        base_cost=50,
    )

    campaign = Campaign.objects.create(
        name="Test Campaign 2",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    list1 = List.objects.create(
        name="Gang A",
        content_house=house,
        owner=user,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    list2 = List.objects.create(
        name="Gang B",
        content_house=house,
        owner=user,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    # Create a linked fighter
    linked_fighter = ListFighter.objects.create(
        name="Pet Beast",
        content_fighter=fighter_type,
        list=list1,
        owner=user,
    )

    # Create capture record
    CapturedFighter.objects.create(
        fighter=linked_fighter,
        capturing_list=list2,
        owner=user,
    )

    # Test fighter properties
    assert linked_fighter.is_captured
    assert not linked_fighter.is_sold_to_guilders
    assert linked_fighter.captured_state == "captured"
    assert not linked_fighter.can_participate()

    # Test that the fighter shows as captured in the list view
    client = Client()
    client.login(username="testuser2", password="testpass")

    response = client.get(reverse("core:list", args=[list1.id]))
    assert response.status_code == 200
    assert "Captured" in response.content.decode()
    assert f"Captured by {list2.name}" in response.content.decode()


@pytest.mark.django_db
def test_sold_linked_fighter_contributes_zero_to_gang_cost():
    """Test that linked fighters sold to guilders contribute 0 to gang cost."""
    # Create test data
    user = User.objects.create_user(username="testuser3", password="testpass")
    house = ContentHouse.objects.create(name="Test House 3")

    fighter_type = ContentFighter.objects.create(
        type="Linked Beast",
        category="SPECIALIST",
        house=house,
        base_cost=75,
    )

    campaign = Campaign.objects.create(
        name="Test Campaign 3",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    list1 = List.objects.create(
        name="Gang X",
        content_house=house,
        owner=user,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    list2 = List.objects.create(
        name="Gang Y",
        content_house=house,
        owner=user,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    # Create a linked fighter
    linked_fighter = ListFighter.objects.create(
        name="Pet Cyber-Mastiff",
        content_fighter=fighter_type,
        list=list1,
        owner=user,
    )

    # Record initial costs
    fighter_cost = linked_fighter.cost_int()
    assert fighter_cost > 0
    initial_gang_cost = list1.cost_int()

    # Capture the linked fighter
    capture = CapturedFighter.objects.create(
        fighter=linked_fighter,
        capturing_list=list2,
        owner=user,
    )

    # Sell to guilders
    capture.sell_to_guilders(credits=30)

    # Test fighter cost is now 0
    assert linked_fighter.cost_int() == 0
    assert linked_fighter.cost_int_cached == 0
    assert linked_fighter._base_cost_int == 0

    # Test gang total cost is reduced by the fighter's cost
    new_gang_cost = list1.cost_int()
    assert new_gang_cost == initial_gang_cost - fighter_cost
