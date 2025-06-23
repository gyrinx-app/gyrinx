import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import ContentEquipment, ContentFighter
from gyrinx.core.models.list import List, ListFighter

User = get_user_model()


@pytest.mark.django_db
def test_kill_fighter_url_exists(client, user, content_house):
    """Test that the kill fighter URL exists and requires login."""
    # Create a campaign mode list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
    )

    # Create a content fighter
    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    # Create a list fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Test unauthenticated access
    url = reverse("core:list-fighter-kill", args=[lst.id, fighter.id])
    response = client.get(url)
    assert response.status_code == 302  # Redirect to login

    # Test authenticated access
    client.force_login(user)
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_kill_fighter_requires_campaign_mode(client, user, content_house):
    """Test that killing fighters only works in campaign mode."""
    # Create a list building mode list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.LIST_BUILDING,
    )

    # Create a content fighter
    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )

    # Create a list fighter
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-kill", args=[lst.id, fighter.id])
    response = client.post(url)

    # Should redirect with error message
    assert response.status_code == 302
    fighter.refresh_from_db()
    assert fighter.injury_state != ListFighter.DEAD


@pytest.mark.django_db
def test_kill_fighter_cannot_kill_stash(client, user, content_house):
    """Test that stash fighters cannot be killed."""
    # Create a campaign mode list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
    )

    # Create a stash fighter
    stash_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Stash",
        category="STASH",
        base_cost=0,
        is_stash=True,
    )

    # Create a list fighter
    fighter = ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_fighter,
        list=lst,
        owner=user,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-kill", args=[lst.id, fighter.id])
    response = client.post(url)

    # Should redirect with error message
    assert response.status_code == 302
    fighter.refresh_from_db()
    assert fighter.injury_state != ListFighter.DEAD


@pytest.mark.django_db
def test_kill_fighter_transfers_equipment_to_stash(client, user, content_house):
    """Test that killing a fighter transfers all equipment to stash."""
    # Create a campaign mode list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
    )

    # Create a stash fighter
    stash_content = ContentFighter.objects.create(
        house=content_house,
        type="Stash",
        category="STASH",
        base_cost=0,
        is_stash=True,
    )
    stash = ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_content,
        list=lst,
        owner=user,
    )

    # Create a regular fighter
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
    )

    # Create some equipment
    equipment = ContentEquipment.objects.create(
        name="Lasgun",
        cost=15,
    )

    # Assign equipment to fighter
    fighter.assign(equipment)

    # Kill the fighter
    client.force_login(user)
    url = reverse("core:list-fighter-kill", args=[lst.id, fighter.id])
    response = client.post(url)

    assert response.status_code == 302

    # Check fighter is dead
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.DEAD
    assert fighter.cost_override == 0

    # Check equipment was transferred to stash
    assert not fighter.listfighterequipmentassignment_set.exists()
    assert stash.listfighterequipmentassignment_set.count() == 1

    stash_assignment = stash.listfighterequipmentassignment_set.first()
    assert stash_assignment.content_equipment == equipment
    assert stash_assignment.cost_int() == 15


@pytest.mark.django_db
def test_kill_fighter_marks_as_dead_and_sets_cost_to_zero(client, user, content_house):
    """Test that killing a fighter marks them as dead and sets cost to 0."""
    # Create a campaign mode list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
    )

    # Create a stash (required for equipment transfer)
    stash_content = ContentFighter.objects.create(
        house=content_house,
        type="Stash",
        category="STASH",
        base_cost=0,
        is_stash=True,
    )
    ListFighter.objects.create(
        name="Stash",
        content_fighter=stash_content,
        list=lst,
        owner=user,
    )

    # Create a fighter
    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Champion",
        category="CHAMPION",
        base_cost=100,
    )
    fighter = ListFighter.objects.create(
        name="Test Champion",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Kill the fighter
    client.force_login(user)
    url = reverse("core:list-fighter-kill", args=[lst.id, fighter.id])
    response = client.post(url)

    assert response.status_code == 302

    # Check fighter state
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.DEAD
    assert fighter.cost_override == 0

    # Verify the fighter's cost is indeed 0
    assert fighter.cost_int() == 0


@pytest.mark.django_db
def test_kill_fighter_confirmation_page(client, user, content_house):
    """Test the kill fighter confirmation page displays correctly."""
    # Create a campaign mode list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
    )

    # Create a fighter
    content_fighter = ContentFighter.objects.create(
        house=content_house,
        type="Ganger",
        category="GANGER",
        base_cost=50,
    )
    fighter = ListFighter.objects.create(
        name="Doomed Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    client.force_login(user)
    url = reverse("core:list-fighter-kill", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 200
    assert b"Kill Fighter: Doomed Fighter" in response.content
    assert b"Transfer all their equipment to the stash" in response.content
    assert b"Set their cost to 0 credits" in response.content
