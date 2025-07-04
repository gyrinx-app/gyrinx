import pytest
from django.contrib import messages
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import ContentHouse
from gyrinx.core.models.campaign import Campaign, CampaignResourceType
from gyrinx.core.models.list import List


@pytest.mark.django_db
def test_campaign_can_have_lists():
    """Test that campaigns can have multiple lists."""
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)

    list1 = List.objects.create(name="List 1", owner=user, content_house=house)
    list2 = List.objects.create(name="List 2", owner=user, content_house=house)

    campaign.lists.add(list1, list2)

    assert campaign.lists.count() == 2
    assert list1 in campaign.lists.all()
    assert list2 in campaign.lists.all()


@pytest.mark.django_db
def test_campaign_add_lists_view_requires_login():
    """Test that the add lists view requires authentication."""
    client = Client()
    campaign = Campaign.objects.create(name="Test Campaign", owner=None, public=True)

    response = client.get(reverse("core:campaign-add-lists", args=[campaign.id]))
    assert response.status_code == 302  # Redirects to login


@pytest.mark.django_db
def test_campaign_add_lists_view_requires_ownership():
    """Test that only the campaign owner can add lists."""
    client = Client()
    owner = User.objects.create_user(username="owner", password="testpass")
    User.objects.create_user(username="other", password="testpass")

    campaign = Campaign.objects.create(name="Test Campaign", owner=owner, public=True)

    # Login as other user
    client.login(username="other", password="testpass")

    response = client.get(reverse("core:campaign-add-lists", args=[campaign.id]))
    assert response.status_code == 404  # Not found for non-owners


@pytest.mark.django_db
def test_campaign_add_lists_view_shows_available_lists():
    """Test that the view shows available lists."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    other_user = User.objects.create_user(username="other", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)

    # Create lists
    my_list = List.objects.create(
        name="My List", owner=user, content_house=house, public=False
    )
    public_list = List.objects.create(
        name="Public List", owner=other_user, content_house=house, public=True
    )
    private_list = List.objects.create(
        name="Private List", owner=other_user, content_house=house, public=False
    )

    client.login(username="testuser", password="testpass")

    response = client.get(reverse("core:campaign-add-lists", args=[campaign.id]))
    assert response.status_code == 200

    # Should see own list and public lists, but not private lists from others
    assert my_list.name.encode() in response.content
    assert public_list.name.encode() in response.content
    assert private_list.name.encode() not in response.content


@pytest.mark.django_db
def test_campaign_add_lists_excludes_already_added():
    """Test that lists already in the campaign are excluded."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)

    list1 = List.objects.create(name="List 1", owner=user, content_house=house)
    list2 = List.objects.create(name="List 2", owner=user, content_house=house)

    # Add list1 to campaign
    campaign.lists.add(list1)

    client.login(username="testuser", password="testpass")

    response = client.get(reverse("core:campaign-add-lists", args=[campaign.id]))
    assert response.status_code == 200

    # Should not see list1 but should see list2
    assert list1.name.encode() not in response.content
    assert list2.name.encode() in response.content


@pytest.mark.django_db
def test_campaign_add_list_post():
    """Test adding a list to a campaign via POST."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)

    list_to_add = List.objects.create(
        name="List to Add", owner=user, content_house=house
    )

    client.login(username="testuser", password="testpass")

    response = client.post(
        reverse("core:campaign-add-lists", args=[campaign.id]),
        {"list_id": str(list_to_add.id)},
    )

    # Should redirect back to the same page
    assert response.status_code == 302
    assert response.url == reverse("core:campaign-add-lists", args=[campaign.id])

    # List should be added to campaign
    assert list_to_add in campaign.lists.all()

    # Check for success message
    response = client.get(response.url)
    messages_list = list(response.context["messages"])
    assert len(messages_list) == 1
    assert messages_list[0].level == messages.SUCCESS
    assert f"{list_to_add.name} ({house.name}) has been added to the campaign." in str(
        messages_list[0]
    )


@pytest.mark.django_db
def test_campaign_add_list_search():
    """Test searching for lists to add."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    house1 = ContentHouse.objects.create(name="Goliath")
    house2 = ContentHouse.objects.create(name="Escher")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)

    # Create lists with different names and houses
    List.objects.create(name="Alpha Squad", owner=user, content_house=house1)
    List.objects.create(name="Beta Team", owner=user, content_house=house2)
    List.objects.create(name="Gamma Force", owner=user, content_house=house1)

    client.login(username="testuser", password="testpass")

    # Search by name
    response = client.get(
        reverse("core:campaign-add-lists", args=[campaign.id]) + "?q=Alpha"
    )
    assert response.status_code == 200
    assert b"Alpha Squad" in response.content
    assert b"Beta Team" not in response.content

    # Search by house
    response = client.get(
        reverse("core:campaign-add-lists", args=[campaign.id]) + "?q=Goliath"
    )
    assert response.status_code == 200
    assert b"Alpha Squad" in response.content
    assert b"Gamma Force" in response.content
    assert b"Beta Team" not in response.content


@pytest.mark.django_db
def test_campaign_add_list_owner_filter():
    """Test filtering lists by owner."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    other = User.objects.create_user(username="other", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)

    # Create lists owned by different users
    List.objects.create(name="My List", owner=user, content_house=house, public=True)
    List.objects.create(
        name="Other List", owner=other, content_house=house, public=True
    )

    client.login(username="testuser", password="testpass")

    # Filter for my lists only
    response = client.get(
        reverse("core:campaign-add-lists", args=[campaign.id]) + "?owner=mine"
    )
    assert response.status_code == 200
    assert b"My List" in response.content
    assert b"Other List" not in response.content

    # Filter for others' lists only
    response = client.get(
        reverse("core:campaign-add-lists", args=[campaign.id]) + "?owner=others"
    )
    assert response.status_code == 200
    # When filtering for "others", should only see public lists from other users
    assert b"My List" not in response.content
    assert b"Other List" in response.content


@pytest.mark.django_db
def test_campaign_detail_shows_lists():
    """Test that the campaign detail page shows added lists."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)

    list1 = List.objects.create(name="List 1", owner=user, content_house=house)
    list2 = List.objects.create(name="List 2", owner=user, content_house=house)

    campaign.lists.add(list1, list2)

    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200

    # Should show both lists
    assert b"List 1" in response.content
    assert b"List 2" in response.content
    assert b"Lists" in response.content


@pytest.mark.django_db
def test_campaign_detail_shows_add_lists_button_for_owner():
    """Test that the campaign owner sees the add lists button."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)

    client.login(username="testuser", password="testpass")

    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200
    assert b"Add Gangs" in response.content
    assert (
        reverse("core:campaign-add-lists", args=[campaign.id]).encode()
        in response.content
    )


@pytest.mark.django_db
def test_add_list_to_in_progress_campaign_shows_confirmation():
    """Test that adding a list to an in-progress campaign shows a confirmation."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)

    # Add an initial list and start the campaign
    initial_list = List.objects.create(
        name="Initial List", owner=user, content_house=house
    )
    campaign.lists.add(initial_list)
    assert campaign.start_campaign()  # This starts the campaign

    # Refresh the campaign to get updated status
    campaign.refresh_from_db()

    # Create a new list to add
    new_list = List.objects.create(name="New List", owner=user, content_house=house)

    client.login(username="testuser", password="testpass")

    # Try to add the list - should show confirmation
    response = client.post(
        reverse("core:campaign-add-lists", args=[campaign.id]),
        {"list_id": str(new_list.id)},
    )

    # Should show the confirmation page, not redirect
    assert response.status_code == 200
    assert b"Confirm Add Gang to Active Campaign" in response.content
    assert b"will immediately clone it for campaign use" in response.content
    assert new_list.name.encode() in response.content

    # List should NOT be added yet
    assert new_list not in campaign.lists.all()


@pytest.mark.django_db
def test_confirm_add_list_to_in_progress_campaign():
    """Test confirming the addition of a list to an in-progress campaign."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)

    # Add resources to the campaign
    resource_type = CampaignResourceType.objects.create(
        campaign=campaign,
        name="Credits",
        default_amount=100,
        owner=user,
    )

    # Add an initial list and start the campaign
    initial_list = List.objects.create(
        name="Initial List", owner=user, content_house=house
    )
    campaign.lists.add(initial_list)
    assert campaign.start_campaign()

    # After starting, the initial list is cloned, so get the cloned version
    campaign.refresh_from_db()
    initial_clone = campaign.lists.get(original_list=initial_list)

    # Create a new list to add
    new_list = List.objects.create(name="New List", owner=user, content_house=house)

    client.login(username="testuser", password="testpass")

    # Confirm adding the list
    response = client.post(
        reverse("core:campaign-add-lists", args=[campaign.id]),
        {
            "list_id": str(new_list.id),
            "confirm": "true",
        },
    )

    # Should redirect after successful addition
    assert response.status_code == 302

    # Refresh the campaign
    campaign.refresh_from_db()

    # The new list should be cloned and added
    assert campaign.lists.count() == 2  # Initial + new

    # Find the newly cloned list (not the initial clone)
    cloned_list = campaign.lists.exclude(id=initial_clone.id).first()
    assert cloned_list is not None
    assert cloned_list.name == new_list.name
    assert cloned_list.original_list == new_list
    assert cloned_list.status == List.CAMPAIGN_MODE
    assert cloned_list.campaign == campaign

    # Check that resources were allocated
    from gyrinx.core.models.campaign import CampaignListResource

    resource = CampaignListResource.objects.get(
        campaign=campaign, resource_type=resource_type, list=cloned_list
    )
    assert resource.amount == 100  # Default amount


@pytest.mark.django_db
def test_add_list_to_pre_campaign_no_cloning():
    """Test that adding a list to a pre-campaign doesn't clone it."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)
    list_to_add = List.objects.create(name="Test List", owner=user, content_house=house)

    client.login(username="testuser", password="testpass")

    # Add the list (no confirmation needed for pre-campaign)
    response = client.post(
        reverse("core:campaign-add-lists", args=[campaign.id]),
        {"list_id": str(list_to_add.id)},
    )

    # Should redirect immediately
    assert response.status_code == 302

    # List should be added directly (not cloned)
    assert list_to_add in campaign.lists.all()
    assert campaign.lists.count() == 1

    # Verify it's the original list, not a clone
    added_list = campaign.lists.first()
    assert added_list.id == list_to_add.id
    assert added_list.status == List.LIST_BUILDING  # Not in campaign mode


@pytest.mark.django_db
def test_cannot_add_list_to_post_campaign():
    """Test that lists cannot be added to a completed campaign."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)

    # Start and end the campaign
    initial_list = List.objects.create(
        name="Initial List", owner=user, content_house=house
    )
    campaign.lists.add(initial_list)
    assert campaign.start_campaign()
    assert campaign.end_campaign()

    # Refresh the campaign to get updated status
    campaign.refresh_from_db()

    client.login(username="testuser", password="testpass")

    # Try to access the add lists page
    response = client.get(reverse("core:campaign-add-lists", args=[campaign.id]))

    # Should redirect with error message
    assert response.status_code == 302
    assert response.url == reverse("core:campaign", args=[campaign.id])


@pytest.mark.django_db
def test_campaign_detail_shows_add_lists_for_in_progress():
    """Test that the add lists button is shown for in-progress campaigns."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)

    # Start the campaign
    initial_list = List.objects.create(
        name="Initial List", owner=user, content_house=house
    )
    campaign.lists.add(initial_list)
    assert campaign.start_campaign()

    # Refresh the campaign to get updated status
    campaign.refresh_from_db()

    client.login(username="testuser", password="testpass")

    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200

    # Should still show the Add Lists button for in-progress campaigns
    assert b"Add Gangs" in response.content
