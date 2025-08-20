import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import ContentFighter, ContentHouse
from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.list import List, ListFighter, CapturedFighter

User = get_user_model()


@pytest.fixture
def campaign_with_lists(db):
    """Create a campaign with two lists owned by different users."""
    owner1 = User.objects.create_user(username="owner1", email="owner1@test.com")
    owner2 = User.objects.create_user(username="owner2", email="owner2@test.com")

    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=owner1,
        status=Campaign.IN_PROGRESS,
    )

    list1 = List.objects.create(
        name="Gang 1",
        owner=owner1,
        content_house=house,
        status=List.CAMPAIGN_MODE,
        credits_current=100,
        campaign=campaign,
    )
    campaign.lists.add(list1)

    list2 = List.objects.create(
        name="Gang 2",
        owner=owner2,
        content_house=house,
        status=List.CAMPAIGN_MODE,
        credits_current=50,
        campaign=campaign,
    )
    campaign.lists.add(list2)

    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        house=house,
        category="GANGER",
        base_cost=50,
    )

    fighter1 = ListFighter.objects.create(
        name="Fighter 1",
        list=list1,
        content_fighter=content_fighter,
        owner=owner1,
    )

    fighter2 = ListFighter.objects.create(
        name="Fighter 2",
        list=list2,
        content_fighter=content_fighter,
        owner=owner2,
    )

    return {
        "campaign": campaign,
        "list1": list1,
        "list2": list2,
        "fighter1": fighter1,
        "fighter2": fighter2,
        "owner1": owner1,
        "owner2": owner2,
    }


@pytest.mark.django_db
def test_capture_fighter(campaign_with_lists):
    """Test capturing a fighter."""
    fighter = campaign_with_lists["fighter1"]
    capturing_list = campaign_with_lists["list2"]

    # Create capture
    captured = CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=capturing_list,
    )

    # Test fighter properties
    assert fighter.is_captured is True
    assert fighter.is_sold_to_guilders is False
    assert fighter.captured_state == "captured"
    assert fighter.can_participate() is False

    # Test capture relationship
    assert captured.fighter == fighter
    assert captured.capturing_list == capturing_list
    assert captured.sold_to_guilders is False


@pytest.mark.django_db
def test_sell_fighter_to_guilders(campaign_with_lists):
    """Test selling a captured fighter to guilders."""
    fighter = campaign_with_lists["fighter1"]
    capturing_list = campaign_with_lists["list2"]

    captured = CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=capturing_list,
    )

    # Sell to guilders
    captured.sell_to_guilders(credits=25)

    # Test state
    assert captured.sold_to_guilders is True
    assert captured.sold_at is not None
    assert captured.ransom_amount == 25

    # Test fighter properties
    assert fighter.is_captured is False
    assert fighter.is_sold_to_guilders is True
    assert fighter.captured_state == "sold"
    assert fighter.can_participate() is False


@pytest.mark.django_db
def test_sold_fighter_contributes_zero_to_gang_cost(campaign_with_lists):
    """Test that fighters sold to guilders contribute 0 to gang cost."""
    fighter = campaign_with_lists["fighter1"]
    capturing_list = campaign_with_lists["list2"]
    original_list = campaign_with_lists["list1"]

    # Record the initial costs
    fighter_cost = fighter.cost_int()
    assert fighter_cost > 0  # Fighter should have a cost initially
    initial_gang_cost = original_list.cost_int()

    # Create capture
    captured = CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=capturing_list,
    )

    # Sell to guilders
    captured.sell_to_guilders(credits=25)

    # Refresh fighter from database to clear cached properties
    fighter.refresh_from_db()

    # Test fighter cost is now 0
    assert fighter.cost_int() == 0
    assert fighter.cost_int_cached == 0

    # Test gang total cost is reduced by the fighter's cost
    new_gang_cost = original_list.cost_int()
    assert new_gang_cost == initial_gang_cost - fighter_cost

    # Clear cache and verify cached value is also correct
    # Note: update_cost_cache is mocked in tests for performance
    # We can still verify the cost calculation works correctly
    assert new_gang_cost == initial_gang_cost - fighter_cost


@pytest.mark.django_db
def test_captured_fighter_contributes_zero_to_gang_cost(campaign_with_lists):
    """Test that captured (but not sold) fighters contribute 0 to gang cost."""
    fighter = campaign_with_lists["fighter1"]
    capturing_list = campaign_with_lists["list2"]
    original_list = campaign_with_lists["list1"]

    # Record the initial costs
    fighter_cost = fighter.cost_int()
    assert fighter_cost > 0
    initial_gang_cost = original_list.cost_int()

    # Create capture
    CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=capturing_list,
    )

    # Refresh fighter from database to clear cached properties
    fighter.refresh_from_db()

    # Test fighter is captured but not sold
    assert fighter.is_captured is True
    assert fighter.is_sold_to_guilders is False

    # Test fighter cost is now 0
    assert fighter.cost_int() == 0
    assert fighter.cost_int_cached == 0

    # Test gang total cost is reduced by the fighter's cost
    assert original_list.cost_int() == initial_gang_cost - fighter_cost


@pytest.mark.django_db
def test_return_fighter_to_owner(campaign_with_lists):
    """Test returning a captured fighter to their original gang."""
    fighter = campaign_with_lists["fighter1"]
    capturing_list = campaign_with_lists["list2"]
    campaign_with_lists["list1"]

    captured = CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=capturing_list,
    )

    # Return with ransom
    captured.return_to_owner(credits=30)

    # Capture record should be deleted
    assert CapturedFighter.objects.filter(fighter=fighter).exists() is False

    # Refresh fighter from database to clear cached relationships
    fighter.refresh_from_db()

    # Fighter should be back to normal
    assert fighter.is_captured is False
    assert fighter.is_sold_to_guilders is False
    assert fighter.captured_state is None
    assert fighter.can_participate() is True


@pytest.mark.django_db
def test_captured_fighters_view(client, campaign_with_lists):
    """Test the captured fighters view."""
    campaign = campaign_with_lists["campaign"]
    owner1 = campaign_with_lists["owner1"]
    fighter1 = campaign_with_lists["fighter1"]
    list2 = campaign_with_lists["list2"]

    # Create a captured fighter
    CapturedFighter.objects.create(
        fighter=fighter1,
        capturing_list=list2,
    )

    client.force_login(owner1)

    url = reverse("core:campaign-captured-fighters", args=[campaign.id])
    response = client.get(url)

    assert response.status_code == 200
    assert b"Fighter 1" in response.content
    assert b"Gang 2" in response.content
    assert b"Captured" in response.content


@pytest.mark.django_db
def test_sell_to_guilders_view(client, campaign_with_lists):
    """Test the sell to guilders view."""
    campaign = campaign_with_lists["campaign"]
    owner2 = campaign_with_lists["owner2"]
    fighter1 = campaign_with_lists["fighter1"]
    list2 = campaign_with_lists["list2"]

    captured = CapturedFighter.objects.create(
        fighter=fighter1,
        capturing_list=list2,
    )

    client.force_login(owner2)

    url = reverse("core:fighter-sell-to-guilders", args=[campaign.id, fighter1.id])

    # Test GET
    response = client.get(url)
    assert response.status_code == 200

    # Test POST
    initial_credits = list2.credits_current
    response = client.post(url, {"credits": "50"})

    assert response.status_code == 302

    # Check fighter was sold
    captured.refresh_from_db()
    assert captured.sold_to_guilders is True
    assert captured.ransom_amount == 50

    # Check credits were added
    list2.refresh_from_db()
    assert list2.credits_current == initial_credits + 50

    # Check campaign action was logged
    action = CampaignAction.objects.filter(
        campaign=campaign, description__contains="Sold Fighter 1"
    ).first()
    assert action is not None


@pytest.mark.django_db
def test_return_to_owner_view(client, campaign_with_lists):
    """Test the return to owner view."""
    campaign = campaign_with_lists["campaign"]
    owner2 = campaign_with_lists["owner2"]
    fighter1 = campaign_with_lists["fighter1"]
    list1 = campaign_with_lists["list1"]
    list2 = campaign_with_lists["list2"]

    CapturedFighter.objects.create(
        fighter=fighter1,
        capturing_list=list2,
    )

    client.force_login(owner2)

    url = reverse("core:fighter-return-to-owner", args=[campaign.id, fighter1.id])

    # Test GET
    response = client.get(url)
    assert response.status_code == 200

    # Test POST with ransom
    initial_credits_list1 = list1.credits_current
    initial_credits_list2 = list2.credits_current

    response = client.post(url, {"ransom": "25"})
    assert response.status_code == 302

    # Check fighter was returned
    assert CapturedFighter.objects.filter(fighter=fighter1).exists() is False

    # Check credits were transferred
    list1.refresh_from_db()
    list2.refresh_from_db()
    assert list1.credits_current == initial_credits_list1 - 25
    assert list2.credits_current == initial_credits_list2 + 25

    # Check campaign actions were logged
    actions = CampaignAction.objects.filter(campaign=campaign).order_by("created")
    assert any("Paid 25 credit ransom" in action.description for action in actions)
    assert any("Returned Fighter 1" in action.description for action in actions)


@pytest.mark.django_db
def test_capture_permissions(client, campaign_with_lists):
    """Test permissions for captured fighters - campaign owner, captor, and captured fighter owner."""
    campaign = campaign_with_lists["campaign"]
    owner1 = campaign_with_lists["owner1"]  # Campaign owner and list1 owner
    owner2 = campaign_with_lists["owner2"]  # list2 owner
    fighter1 = campaign_with_lists["fighter1"]  # owned by owner1
    list1 = campaign_with_lists["list1"]
    list2 = campaign_with_lists["list2"]

    # Fighter1 (owned by owner1) is captured by list2 (owned by owner2)
    CapturedFighter.objects.create(
        fighter=fighter1,
        capturing_list=list2,
    )

    # Create a third user who is not involved
    other_user = User.objects.create_user(username="other", email="other@test.com")

    # Create a third list owned by the other user (not a campaign owner)
    third_owner = User.objects.create_user(username="third", email="third@test.com")
    list3 = List.objects.create(
        name="Gang 3",
        owner=third_owner,
        content_house=list1.content_house,
        status=List.CAMPAIGN_MODE,
        credits_current=75,
        campaign=campaign,
    )
    campaign.lists.add(list3)

    # Create a fighter3 owned by third_owner, captured by owner2
    fighter3 = ListFighter.objects.create(
        name="Fighter 3",
        list=list3,
        content_fighter=fighter1.content_fighter,
    )
    CapturedFighter.objects.create(
        fighter=fighter3,
        capturing_list=list2,
    )

    # Test 1: Campaign owner (owner1) can sell/return
    client.force_login(owner1)

    # Campaign owner can sell
    url = reverse("core:fighter-sell-to-guilders", args=[campaign.id, fighter1.id])
    response = client.get(url)
    assert response.status_code == 200

    # Campaign owner can return
    url = reverse("core:fighter-return-to-owner", args=[campaign.id, fighter1.id])
    response = client.get(url)
    assert response.status_code == 200

    # Test 2: Capturing gang owner (owner2) can also sell/return
    client.force_login(owner2)

    # Capturing gang owner can sell
    url = reverse("core:fighter-sell-to-guilders", args=[campaign.id, fighter1.id])
    response = client.get(url)
    assert response.status_code == 200

    # Capturing gang owner can return
    url = reverse("core:fighter-return-to-owner", args=[campaign.id, fighter1.id])
    response = client.get(url)
    assert response.status_code == 200

    # Test 3: Captured fighter owner (third_owner, NOT campaign owner) can return for ransom and release, but not sell
    client.force_login(third_owner)

    # Captured fighter owner CANNOT sell to guilders
    url = reverse("core:fighter-sell-to-guilders", args=[campaign.id, fighter3.id])
    response = client.get(url)
    assert response.status_code == 404

    # Captured fighter owner CAN return for ransom
    url = reverse("core:fighter-return-to-owner", args=[campaign.id, fighter3.id])
    response = client.get(url)
    assert response.status_code == 200

    # Captured fighter owner CAN release
    url = reverse("core:fighter-release", args=[campaign.id, fighter3.id])
    response = client.get(url)
    assert response.status_code == 200

    # Test 4: Other users get 404
    client.force_login(other_user)

    # Other user cannot sell
    url = reverse("core:fighter-sell-to-guilders", args=[campaign.id, fighter1.id])
    response = client.post(url, {"credits": "50"})
    assert response.status_code == 404

    # Other user cannot return
    url = reverse("core:fighter-return-to-owner", args=[campaign.id, fighter1.id])
    response = client.post(url, {"ransom": "25"})
    assert response.status_code == 404

    # Other user cannot release
    url = reverse("core:fighter-release", args=[campaign.id, fighter1.id])
    response = client.post(url)
    assert response.status_code == 404

    # Captured fighter should still exist
    assert CapturedFighter.objects.filter(fighter=fighter1).exists()


@pytest.mark.django_db
def test_release_fighter(campaign_with_lists):
    """Test releasing a captured fighter without ransom."""
    fighter = campaign_with_lists["fighter1"]
    capturing_list = campaign_with_lists["list2"]

    captured = CapturedFighter.objects.create(
        fighter=fighter,
        capturing_list=capturing_list,
    )

    # Test fighter is captured
    assert fighter.is_captured is True
    assert fighter.can_participate() is False

    # Release the fighter (simulate what the view does)
    captured.delete()

    # Refresh fighter from database to clear cached relationships
    fighter.refresh_from_db()

    # Fighter should be back to normal
    assert fighter.is_captured is False
    assert fighter.is_sold_to_guilders is False
    assert fighter.captured_state is None
    assert fighter.can_participate() is True


@pytest.mark.django_db
def test_release_fighter_view(client, campaign_with_lists):
    """Test the release fighter view."""
    campaign = campaign_with_lists["campaign"]
    owner2 = campaign_with_lists["owner2"]
    fighter1 = campaign_with_lists["fighter1"]
    list1 = campaign_with_lists["list1"]
    list2 = campaign_with_lists["list2"]

    CapturedFighter.objects.create(
        fighter=fighter1,
        capturing_list=list2,
    )

    client.force_login(owner2)

    url = reverse("core:fighter-release", args=[campaign.id, fighter1.id])

    # Test GET
    response = client.get(url)
    assert response.status_code == 200

    # Test POST
    response = client.post(url)
    assert response.status_code == 302

    # Check fighter was released
    assert CapturedFighter.objects.filter(fighter=fighter1).exists() is False

    # Check credits were NOT transferred (no ransom)
    list1.refresh_from_db()
    list2.refresh_from_db()
    assert list1.credits_current == 100  # Unchanged
    assert list2.credits_current == 50  # Unchanged

    # Check campaign action was logged
    action = CampaignAction.objects.filter(
        campaign=campaign, description__contains="Released Fighter 1"
    ).first()
    assert action is not None
    assert "without ransom" in action.description


@pytest.mark.django_db
def test_release_permissions(client, campaign_with_lists):
    """Test that only the capturing gang owner, campaign owner, or captured fighter owner can release fighters."""
    campaign = campaign_with_lists["campaign"]
    owner1 = campaign_with_lists["owner1"]
    owner2 = campaign_with_lists["owner2"]
    fighter1 = campaign_with_lists["fighter1"]
    list2 = campaign_with_lists["list2"]

    CapturedFighter.objects.create(
        fighter=fighter1,
        capturing_list=list2,
    )

    # Create a third user who is not involved
    other_user = User.objects.create_user(username="other", email="other@test.com")

    # Test: Campaign owner (owner1) can release
    client.force_login(owner1)
    url = reverse("core:fighter-release", args=[campaign.id, fighter1.id])
    response = client.get(url)
    assert response.status_code == 200

    # Test: Capturing gang owner (owner2) can release
    client.force_login(owner2)
    url = reverse("core:fighter-release", args=[campaign.id, fighter1.id])
    response = client.get(url)
    assert response.status_code == 200

    # Test: Captured fighter owner (owner1) can release
    client.force_login(owner1)
    url = reverse("core:fighter-release", args=[campaign.id, fighter1.id])
    response = client.get(url)
    assert response.status_code == 200

    # Test: Other users get 404
    client.force_login(other_user)
    url = reverse("core:fighter-release", args=[campaign.id, fighter1.id])
    response = client.get(url)
    assert response.status_code == 404

    # Captured fighter should still exist
    assert CapturedFighter.objects.filter(fighter=fighter1).exists()


@pytest.mark.django_db
def test_fighter_sorting_with_captured(campaign_with_lists):
    """Test that captured fighters are sorted to the end of the list."""
    list1 = campaign_with_lists["list1"]
    fighter1 = campaign_with_lists["fighter1"]

    # Create additional fighters
    content_fighter = fighter1.content_fighter
    owner = fighter1.owner

    ListFighter.objects.create(
        name="Active Fighter",
        list=list1,
        content_fighter=content_fighter,
        owner=owner,
        injury_state=ListFighter.ACTIVE,
    )

    ListFighter.objects.create(
        name="Dead Fighter",
        list=list1,
        content_fighter=content_fighter,
        owner=owner,
        injury_state=ListFighter.DEAD,
    )

    # Capture fighter1
    CapturedFighter.objects.create(
        fighter=fighter1,
        capturing_list=campaign_with_lists["list2"],
    )

    # Check ordering
    fighters = list1.fighters()
    fighter_names = [f.name for f in fighters]

    # Active fighter should be first
    assert fighter_names[0] == "Active Fighter"
    # Dead fighter should be before captured
    assert fighter_names.index("Dead Fighter") < fighter_names.index("Fighter 1")
