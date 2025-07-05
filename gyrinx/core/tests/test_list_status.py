import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import ContentFighter, ContentHouse
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List, ListFighter

User = get_user_model()


@pytest.mark.django_db
def test_list_default_status():
    """Test that new lists default to list building status."""
    user = User.objects.create_user(username="testuser", password="password")
    house = ContentHouse.objects.create(name="Test House")

    list_obj = List.objects.create_with_user(
        user=user,
        name="Test List",
        owner=user,
        content_house=house,
    )

    assert list_obj.status == List.LIST_BUILDING
    assert list_obj.is_list_building
    assert not list_obj.is_campaign_mode
    assert list_obj.original_list is None
    assert list_obj.campaign is None


@pytest.mark.django_db
def test_campaign_start_clones_lists():
    """Test that starting a campaign clones all associated lists."""
    user = User.objects.create_user(username="testuser", password="password")
    house = ContentHouse.objects.create(name="Test House")

    # Create a campaign
    campaign = Campaign.objects.create_with_user(
        user=user,
        name="Test Campaign",
        owner=user,
    )

    # Create a list with a fighter
    original_list = List.objects.create_with_user(
        user=user,
        name="Test List",
        owner=user,
        content_house=house,
    )

    # Add a fighter to the list
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category="leader",
        house=house,
    )
    ListFighter.objects.create(
        name="Fighter 1",
        owner=user,
        list=original_list,
        content_fighter=content_fighter,
    )

    # Add list to campaign
    campaign.lists.add(original_list)

    # Start the campaign
    assert campaign.start_campaign()

    # Check that the original list is no longer in the campaign
    assert original_list not in campaign.lists.all()

    # Check that a clone was created
    assert campaign.lists.count() == 1
    cloned_list: List = campaign.lists.first()

    # Verify clone properties
    assert cloned_list.name == original_list.name
    assert cloned_list.owner == original_list.owner
    assert cloned_list.status == List.CAMPAIGN_MODE
    assert cloned_list.is_campaign_mode
    assert cloned_list.original_list == original_list
    assert cloned_list.campaign == campaign
    assert not cloned_list.public  # Campaign lists are private

    # Verify fighters were cloned, including stash
    list_fighters = cloned_list.fighters()
    assert list_fighters.count() == 2
    stash_fighter: ListFighter = list_fighters.first()
    assert stash_fighter.name == "Stash"
    assert stash_fighter.is_stash

    cloned_fighter = (
        cloned_list.fighters().exclude(content_fighter__is_stash=True).first()
    )
    assert cloned_fighter.name == "Fighter 1"
    assert cloned_fighter.content_fighter == content_fighter


@pytest.mark.django_db
def test_list_visibility_in_views(client):
    """Test that campaign mode lists are not visible in normal list views."""
    user = User.objects.create_user(username="testuser", password="password")
    house = ContentHouse.objects.create(name="Test House")

    # Create a normal list
    normal_list = List.objects.create_with_user(
        user=user,
        name="Normal List",
        owner=user,
        content_house=house,
        public=True,
    )

    # Create a campaign mode list
    campaign_list = List.objects.create_with_user(
        user=user,
        name="Campaign List",
        owner=user,
        content_house=house,
        public=True,
        status=List.CAMPAIGN_MODE,
    )

    # Check public lists view
    response = client.get(reverse("core:lists"))
    assert response.status_code == 200
    assert normal_list in response.context["lists"]
    assert campaign_list in response.context["lists"]

    # Check user profile
    response = client.get(reverse("core:user", args=[user.username]))
    assert response.status_code == 200
    assert normal_list in response.context["public_lists"]
    assert campaign_list not in response.context["public_lists"]

    # Check index page for logged in user
    client.login(username="testuser", password="password")
    response = client.get(reverse("core:index"))
    assert response.status_code == 200
    assert normal_list in response.context["lists"]
    assert campaign_list not in response.context["lists"]


@pytest.mark.django_db
def test_campaign_add_lists_filtering(client):
    """Test that only list building mode lists can be added to campaigns."""
    owner = User.objects.create_user(username="owner", password="password")
    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create_with_user(
        user=owner,
        name="Test Campaign",
        owner=owner,
    )

    # Create various lists
    building_list = List.objects.create_with_user(
        user=owner,
        name="Building List",
        owner=owner,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    campaign_list = List.objects.create_with_user(
        user=owner,
        name="Campaign List",
        owner=owner,
        content_house=house,
        status=List.CAMPAIGN_MODE,
    )

    client.login(username="owner", password="password")
    response = client.get(reverse("core:campaign-add-lists", args=[campaign.id]))
    assert response.status_code == 200

    # Only building list should be available
    assert building_list in response.context["lists"]
    assert campaign_list not in response.context["lists"]


@pytest.mark.django_db
def test_active_campaign_clones_display(client):
    """Test that active campaign clones are shown on the original list."""
    user = User.objects.create_user(username="testuser", password="password")
    house = ContentHouse.objects.create(name="Test House")
    client.login(username="testuser", password="password")

    # Create original list
    original_list = List.objects.create_with_user(
        user=user,
        name="Original List",
        owner=user,
        content_house=house,
    )

    # Create campaign and add list
    campaign = Campaign.objects.create_with_user(
        user=user,
        name="Test Campaign",
        owner=user,
    )
    campaign.lists.add(original_list)

    # Start campaign to create clone
    campaign.start_campaign()

    # View the original list
    response = client.get(reverse("core:list", args=[original_list.id]))
    assert response.status_code == 200
    # Check that the list shows the "Active in Campaigns" link
    assert b"Active in Campaigns" in response.content
    assert (
        reverse("core:list-campaign-clones", args=[original_list.id]).encode()
        in response.content
    )


@pytest.mark.django_db
def test_list_campaign_clones_view(client):
    """Test the list campaign clones view."""
    user = User.objects.create_user(username="testuser", password="password")
    house = ContentHouse.objects.create(name="Test House")
    client.login(username="testuser", password="password")

    # Create original list
    original_list = List.objects.create_with_user(
        user=user,
        name="Original List",
        owner=user,
        content_house=house,
    )

    # Create two campaigns and add list to each
    campaign1 = Campaign.objects.create_with_user(
        user=user,
        name="Campaign 1",
        owner=user,
    )
    campaign2 = Campaign.objects.create_with_user(
        user=user,
        name="Campaign 2",
        owner=user,
    )

    campaign1.lists.add(original_list)
    campaign2.lists.add(original_list)

    # Start both campaigns to create clones
    campaign1.start_campaign()
    campaign2.start_campaign()

    # View the campaign clones page
    response = client.get(reverse("core:list-campaign-clones", args=[original_list.id]))
    assert response.status_code == 200

    # Check that both campaign clones are shown
    assert b"Campaign 1" in response.content
    assert b"Campaign 2" in response.content
    assert b"Original List" in response.content

    # Check that the table is shown (not the "no campaign versions" message)
    assert b"This list has no campaign versions" not in response.content

    # Check for status badges
    assert b"In Progress" in response.content


@pytest.mark.django_db
def test_campaign_list_shows_original():
    """Test that campaign lists show link to original list."""
    user = User.objects.create_user(username="testuser", password="password")
    house = ContentHouse.objects.create(name="Test House")

    original_list = List.objects.create_with_user(
        user=user,
        name="Original List",
        owner=user,
        content_house=house,
    )

    campaign = Campaign.objects.create_with_user(
        user=user,
        name="Test Campaign",
        owner=user,
    )

    # Clone list for campaign
    campaign_list = original_list.clone(for_campaign=campaign)

    # Verify the clone references the original
    assert campaign_list.original_list == original_list
    assert campaign_list.campaign == campaign
    assert campaign_list.status == List.CAMPAIGN_MODE
    assert not campaign_list.public


@pytest.mark.django_db
def test_regular_clone_preserves_public_flag():
    """Test that regular cloning preserves the public/private flag."""
    user = User.objects.create_user(username="testuser", password="password")
    house = ContentHouse.objects.create(name="Test House")

    # Create a public list
    public_list = List.objects.create_with_user(
        user=user,
        name="Public List",
        owner=user,
        content_house=house,
        public=True,
    )

    # Clone it normally (not for campaign)
    regular_clone = public_list.clone()
    assert regular_clone.public is True
    assert regular_clone.name == "Public List (Clone)"

    # Create a private list
    private_list = List.objects.create_with_user(
        user=user,
        name="Private List",
        owner=user,
        content_house=house,
        public=False,
    )

    # Clone it normally
    private_clone = private_list.clone()
    assert private_clone.public is False
    assert private_clone.name == "Private List (Clone)"


@pytest.mark.django_db
def test_can_add_lists_to_in_progress_campaign(client):
    """Test that lists can be added to a campaign after it starts with confirmation."""
    owner = User.objects.create_user(username="owner", password="password")
    house = ContentHouse.objects.create(name="Test House")
    client.login(username="owner", password="password")

    # Create campaign and list
    campaign = Campaign.objects.create_with_user(
        user=owner,
        name="Test Campaign",
        owner=owner,
    )

    list1 = List.objects.create_with_user(
        user=owner,
        name="List 1",
        owner=owner,
        content_house=house,
    )

    # Add list to campaign before starting
    campaign.lists.add(list1)

    # Start the campaign
    campaign.start_campaign()
    assert campaign.is_in_progress

    # Create another list to try to add
    list2 = List.objects.create_with_user(
        user=owner,
        name="List 2",
        owner=owner,
        content_house=house,
    )

    # Try to access add lists page - should be accessible
    response = client.get(reverse("core:campaign-add-lists", args=[campaign.id]))
    assert response.status_code == 200

    # Try to POST a new list without confirmation - should show confirmation
    response = client.post(
        reverse("core:campaign-add-lists", args=[campaign.id]), {"list_id": list2.id}
    )
    assert response.status_code == 200  # Stays on page to show confirmation

    # Post with confirmation - should work
    response = client.post(
        reverse("core:campaign-add-lists", args=[campaign.id]),
        {"list_id": list2.id, "confirm": "true"},
    )
    assert response.status_code == 302  # Redirects after success

    # Verify list was cloned and added
    campaign.refresh_from_db()
    assert campaign.lists.count() == 2  # Original cloned list1 + new cloned list2

    # Check campaign view shows "Add Lists" button
    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200
    assert b"Add Gangs" in response.content


@pytest.mark.django_db
def test_prevent_duplicate_list_in_campaign(client):
    """Test that a list can't be added to a campaign if it's already there."""
    user = User.objects.create_user(username="testuser", password="password")
    house = ContentHouse.objects.create(name="Test House")
    client.login(username="testuser", password="password")

    # Create list and campaign
    original_list = List.objects.create_with_user(
        user=user,
        name="Test List",
        owner=user,
        content_house=house,
    )

    campaign = Campaign.objects.create_with_user(
        user=user,
        name="Test Campaign",
        owner=user,
    )

    # Add list to campaign (but don't start it yet)
    campaign.lists.add(original_list)

    # Access add lists page - should work since campaign hasn't started
    response = client.get(reverse("core:campaign-add-lists", args=[campaign.id]))
    assert response.status_code == 200

    # Original list should not be available since it's already added
    assert original_list not in response.context["lists"]
