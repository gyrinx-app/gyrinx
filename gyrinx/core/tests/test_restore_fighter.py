import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import ContentFighter
from gyrinx.core.models.list import List, ListFighter

User = get_user_model()


@pytest.mark.django_db
def test_restore_fighter_url_requires_login(client, user, content_house):
    """Test that the restore fighter URL requires login."""
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
    )

    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        archived=True,
    )

    url = reverse("core:list-fighter-restore", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 302
    assert "/login/" in response.url


@pytest.mark.django_db
def test_restore_fighter_url_exists_for_logged_in_user(client, user, content_house):
    """Test that the restore fighter URL exists for logged in user."""
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
    )

    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        archived=True,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-restore", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 200


@pytest.mark.django_db
def test_restore_fighter_only_works_for_archived_fighters(client, user, content_house):
    """Test that restore only works for archived fighters."""
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
    )

    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    # Create a non-archived fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        archived=False,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-restore", args=[lst.id, fighter.id])
    response = client.get(url)

    # Should return 404 for non-archived fighter
    assert response.status_code == 404


@pytest.mark.django_db
def test_restore_fighter_requires_ownership(client, user, content_house):
    """Test that only the owner can restore their fighter."""
    other_user = User.objects.create_user(username="otheruser", password="testpass")

    lst = List.objects.create(
        name="Test List",
        owner=other_user,
        content_house=content_house,
    )

    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=other_user,
        archived=True,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-restore", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 404


@pytest.mark.django_db
def test_restore_fighter_confirmation_page(client, user, content_house):
    """Test that the restore fighter confirmation page displays correctly."""
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
    )

    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    fighter = ListFighter.objects.create(
        name="Archived Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        archived=True,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-restore", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Restore Fighter" in content
    assert "Archived Fighter" in content
    assert "Are you sure you want to restore" in content
    assert "Return them to the active gang roster" in content
    assert "Cancel" in content


@pytest.mark.django_db
def test_restore_fighter_post_restores_fighter(client, user, content_house):
    """Test that POST restores the fighter."""
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
    )

    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    fighter = ListFighter.objects.create(
        name="Archived Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        archived=True,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-restore", args=[lst.id, fighter.id])
    response = client.post(url)

    assert response.status_code == 302
    assert response.url == f"{reverse('core:list', args=[lst.id])}#{fighter.id}"

    fighter.refresh_from_db()
    assert fighter.archived is False


@pytest.mark.django_db
def test_restore_fighter_shows_cost_info(client, user, content_house):
    """Test that the confirmation page shows cost information."""
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
    )

    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=75,
    )

    fighter = ListFighter.objects.create(
        name="Archived Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        archived=True,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-restore", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    # Check that the cost is mentioned (75 credits)
    assert "75" in content


@pytest.mark.django_db
def test_restore_fighter_shows_campaign_mode_info(client, user, content_house):
    """Test that campaign mode lists show additional info."""
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
    )

    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    fighter = ListFighter.objects.create(
        name="Archived Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        archived=True,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-restore", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    # Check for the campaign mode note
    assert "gang rating" in content.lower()


@pytest.mark.django_db
def test_archived_fighters_page_links_to_restore(client, user, content_house):
    """Test that the archived fighters page links to the restore confirmation."""
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
    )

    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    fighter = ListFighter.objects.create(
        name="Archived Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        archived=True,
    )

    client.force_login(user)
    url = reverse("core:list-archived-fighters", args=[lst.id])
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Check that the restore link is present
    restore_url = reverse("core:list-fighter-restore", args=[lst.id, fighter.id])
    assert restore_url in content
    assert "Restore" in content
