import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import ContentHouse
from gyrinx.core.models.campaign import Campaign
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
    assert (
        response.url
        == reverse("core:campaign-add-lists", args=[campaign.id]) + "#added"
    )

    # List should be added to campaign
    assert list_to_add in campaign.lists.all()


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
    assert b"Lists in Campaign" in response.content


@pytest.mark.django_db
def test_campaign_detail_shows_add_lists_button_for_owner():
    """Test that the campaign owner sees the add lists button."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")

    campaign = Campaign.objects.create(name="Test Campaign", owner=user, public=True)

    client.login(username="testuser", password="testpass")

    response = client.get(reverse("core:campaign", args=[campaign.id]))
    assert response.status_code == 200
    assert b"Add Lists" in response.content
    assert (
        reverse("core:campaign-add-lists", args=[campaign.id]).encode()
        in response.content
    )
