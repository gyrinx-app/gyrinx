import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.core.models.campaign import Campaign, CampaignAction
from gyrinx.core.models.list import List

User = get_user_model()


@pytest.mark.django_db
def test_archive_list_url_exists(client, user, content_house):
    """Test that the archive URL exists and requires login."""
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
    )

    # Test unauthenticated access
    url = reverse("core:list-archive", args=[lst.id])
    response = client.get(url)
    assert response.status_code == 302  # Redirect to login

    # Test authenticated access
    client.force_login(user)
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_archive_list_requires_ownership(client, user, other_user, content_house):
    """Test that only the owner can archive their list."""
    lst = List.objects.create(
        name="Test List",
        owner=other_user,
        content_house=content_house,
    )

    client.force_login(user)
    url = reverse("core:list-archive", args=[lst.id])
    response = client.get(url)
    assert response.status_code == 404  # Not found for non-owner


@pytest.mark.django_db
def test_archive_list_get_request(client, user, content_house):
    """Test the archive list confirmation page."""
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
    )

    client.force_login(user)
    url = reverse("core:list-archive", args=[lst.id])
    response = client.get(url)

    assert response.status_code == 200
    assert (
        "Are you sure you want to archive this gang/list?" in response.content.decode()
    )
    assert "Archive" in response.content.decode()


@pytest.mark.django_db
def test_archive_list_post_request(client, user, content_house):
    """Test archiving a list."""
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
    )

    assert lst.archived is False
    assert lst.archived_at is None

    client.force_login(user)
    url = reverse("core:list-archive", args=[lst.id])
    response = client.post(url, {"archive": "1"})

    assert response.status_code == 302  # Redirect
    assert response.url == reverse("core:list", args=[lst.id])

    lst.refresh_from_db()
    assert lst.archived is True
    assert lst.archived_at is not None


@pytest.mark.django_db
def test_unarchive_list_post_request(client, user, content_house):
    """Test unarchiving a list."""
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
    )
    lst.archive()

    assert lst.archived is True
    assert lst.archived_at is not None

    client.force_login(user)
    url = reverse("core:list-archive", args=[lst.id])
    response = client.post(url)  # No archive=1 parameter means unarchive

    assert response.status_code == 302  # Redirect
    assert response.url == reverse("core:list", args=[lst.id])

    lst.refresh_from_db()
    assert lst.archived is False
    assert lst.archived_at is None


@pytest.mark.django_db
def test_archive_list_with_active_campaign(client, user, content_house):
    """Test archiving a list that's in an active campaign."""
    # Create a list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
    )

    # Create an active campaign and add the list
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )
    campaign.lists.add(lst)

    client.force_login(user)
    url = reverse("core:list-archive", args=[lst.id])

    # Check the warning is shown
    response = client.get(url)
    assert response.status_code == 200
    assert "Active Campaign" in response.content.decode()
    assert campaign.name in response.content.decode()

    # Archive the list
    response = client.post(url, {"archive": "1"})
    assert response.status_code == 302

    lst.refresh_from_db()
    assert lst.archived is True

    # Check that a campaign action was created
    action = CampaignAction.objects.filter(campaign=campaign).first()
    assert action is not None
    assert f"Gang '{lst.name}' has been archived by its owner" in action.description
    assert action.user == user
    assert action.list == lst


@pytest.mark.django_db
def test_archived_list_display(client, user, content_house):
    """Test that archived lists show the archived banner."""
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
    )
    lst.archive()

    client.force_login(user)
    url = reverse("core:list", args=[lst.id])
    response = client.get(url)

    assert response.status_code == 200
    assert "This gang has been archived by its owner" in response.content.decode()
    assert "Unarchive" in response.content.decode()

    # Check that edit buttons are not shown
    assert (
        'href="' + reverse("core:list-fighter-new", args=[lst.id])
        not in response.content.decode()
    )
    assert (
        'href="' + reverse("core:list-edit", args=[lst.id])
        not in response.content.decode()
    )


@pytest.mark.django_db
def test_archived_lists_hidden_from_lists_page(client, user, content_house):
    """Test that archived lists are not shown on the lists page."""
    # Create active and archived lists
    active_list = List.objects.create(
        name="Active List",
        owner=user,
        content_house=content_house,
        public=True,
    )

    archived_list = List.objects.create(
        name="Archived List",
        owner=user,
        content_house=content_house,
        public=True,
    )
    archived_list.archive()

    # Check public lists page
    url = reverse("core:lists")
    response = client.get(url)

    assert response.status_code == 200
    assert active_list.name in response.content.decode()
    assert archived_list.name not in response.content.decode()


@pytest.mark.django_db
def test_archived_lists_hidden_from_home_page(client, user, content_house):
    """Test that archived lists are not shown on the home page."""
    # Create active and archived lists
    active_list = List.objects.create(
        name="Active List",
        owner=user,
        content_house=content_house,
    )

    archived_list = List.objects.create(
        name="Archived List",
        owner=user,
        content_house=content_house,
    )
    archived_list.archive()

    client.force_login(user)
    url = reverse("core:index")
    response = client.get(url)

    assert response.status_code == 200
    assert active_list.name in response.content.decode()
    assert archived_list.name not in response.content.decode()


@pytest.mark.django_db
def test_archived_lists_hidden_from_user_profile(client, user, content_house):
    """Test that archived lists are not shown on user profile pages."""
    # Create active and archived lists
    active_list = List.objects.create(
        name="Active List",
        owner=user,
        content_house=content_house,
        public=True,
    )

    archived_list = List.objects.create(
        name="Archived List",
        owner=user,
        content_house=content_house,
        public=True,
    )
    archived_list.archive()

    url = reverse("core:user", args=[user.username])
    response = client.get(url)

    assert response.status_code == 200
    assert active_list.name in response.content.decode()
    assert archived_list.name not in response.content.decode()


@pytest.mark.django_db
def test_archived_lists_hidden_from_campaign_add_lists(client, user, content_house):
    """Test that archived lists cannot be added to campaigns."""
    # Create active and archived lists
    active_list = List.objects.create(
        name="Active List",
        owner=user,
        content_house=content_house,
    )

    archived_list = List.objects.create(
        name="Archived List",
        owner=user,
        content_house=content_house,
    )
    archived_list.archive()

    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.PRE_CAMPAIGN,
    )

    client.force_login(user)
    url = reverse("core:campaign-add-lists", args=[campaign.id])
    response = client.get(url)

    assert response.status_code == 200
    assert active_list.name in response.content.decode()
    assert archived_list.name not in response.content.decode()


@pytest.mark.django_db
def test_archive_button_in_dropdown_menu(client, user, content_house):
    """Test that the archive/unarchive button appears in the dropdown menu."""
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
    )

    client.force_login(user)
    url = reverse("core:list", args=[lst.id])
    response = client.get(url)

    assert response.status_code == 200
    assert (
        'href="' + reverse("core:list-archive", args=[lst.id])
        in response.content.decode()
    )
    assert "Archive" in response.content.decode()

    # Archive the list and check again
    lst.archive()
    response = client.get(url)

    assert response.status_code == 200
    assert (
        'href="' + reverse("core:list-archive", args=[lst.id])
        in response.content.decode()
    )
    assert "Unarchive" in response.content.decode()


# Fixtures
@pytest.fixture
def other_user(db):
    return User.objects.create_user(username="otheruser", password="testpass")
