"""Test XP tracking functionality for fighters in campaign mode."""

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from gyrinx.content.models import ContentFighter, ContentHouse
from gyrinx.core.forms.list import EditFighterXPForm
from gyrinx.core.models import CampaignAction, List, ListFighter


@pytest.fixture
def content_fighter(content_house):
    """Create a test content fighter."""
    return ContentFighter.objects.create(
        type="Test Fighter",
        house=content_house,
        category="GANGER",
        movement="4",
        weapon_skill="3+",
        ballistic_skill="3+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="3+",
        attacks="1",
        leadership="7+",
        cool="7+",
        willpower="7+",
        intelligence="7+",
        base_cost=50,
    )


@pytest.fixture
def list_with_fighter(user, content_fighter, campaign):
    """Create a test list with a fighter in campaign mode."""
    list_obj = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_fighter.house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )
    fighter = ListFighter.objects.create(
        list=list_obj,
        content_fighter=content_fighter,
        name="Test Fighter",
        owner=user,
    )
    return list_obj, fighter


@pytest.mark.django_db
def test_edit_fighter_xp_form_initialization():
    """Test EditFighterXPForm initialization."""
    form = EditFighterXPForm()
    assert "operation" in form.fields
    assert "amount" in form.fields
    assert "description" in form.fields

    # Check operation choices
    operation_choices = dict(form.fields["operation"].choices)
    assert "add" in operation_choices
    assert "spend" in operation_choices
    assert "reduce" in operation_choices
    assert operation_choices["add"] == "Add XP"
    assert operation_choices["spend"] == "Spend XP"
    assert operation_choices["reduce"] == "Reduce XP"

    # Check field properties
    assert form.fields["amount"].min_value == 1
    assert form.fields["description"].required is False


@pytest.mark.django_db
def test_edit_fighter_xp_form_valid_data():
    """Test EditFighterXPForm with valid data."""
    form = EditFighterXPForm(
        data={
            "operation": "add",
            "amount": 5,
            "description": "Battle victory",
        }
    )
    assert form.is_valid()
    assert form.cleaned_data["operation"] == "add"
    assert form.cleaned_data["amount"] == 5
    assert form.cleaned_data["description"] == "Battle victory"


@pytest.mark.django_db
def test_edit_fighter_xp_form_invalid_amount():
    """Test EditFighterXPForm with invalid amount."""
    form = EditFighterXPForm(
        data={
            "operation": "add",
            "amount": 0,
            "description": "",
        }
    )
    assert not form.is_valid()
    assert "amount" in form.errors

    form = EditFighterXPForm(
        data={
            "operation": "add",
            "amount": -5,
            "description": "",
        }
    )
    assert not form.is_valid()
    assert "amount" in form.errors


@pytest.mark.django_db
def test_edit_fighter_xp_form_missing_required_fields():
    """Test EditFighterXPForm with missing required fields."""
    form = EditFighterXPForm(data={})
    assert not form.is_valid()
    assert "operation" in form.errors
    assert "amount" in form.errors


@pytest.mark.django_db
def test_edit_fighter_xp_view_requires_auth(list_with_fighter):
    """Test that edit_fighter_xp view requires authentication."""
    list_obj, fighter = list_with_fighter
    client = Client()

    url = reverse("core:list-fighter-xp-edit", args=[list_obj.id, fighter.id])
    response = client.get(url)
    assert response.status_code == 302  # Redirect to login


@pytest.mark.django_db
def test_edit_fighter_xp_view_requires_ownership(list_with_fighter):
    """Test that edit_fighter_xp view requires ownership."""
    list_obj, fighter = list_with_fighter
    client = Client()

    # Create another user
    User.objects.create_user(username="other", password="password")
    client.login(username="other", password="password")

    url = reverse("core:list-fighter-xp-edit", args=[list_obj.id, fighter.id])
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_edit_fighter_xp_view_requires_campaign_mode():
    """Test that edit_fighter_xp view requires campaign mode."""
    # Create a list in basic mode
    owner = User.objects.create_user(username="testuser", password="password")
    house = ContentHouse.objects.create(name="House")
    content_fighter = ContentFighter.objects.create(
        type="Fighter",
        house=house,
        category="GANGER",
        movement="4",
        weapon_skill="3+",
        ballistic_skill="3+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="3+",
        attacks="1",
        leadership="7+",
        cool="7+",
        willpower="7+",
        intelligence="7+",
        base_cost=50,
    )

    list_obj = List.objects.create(
        name="Basic List",
        owner=owner,
        content_house=house,
        status=List.LIST_BUILDING,  # Not campaign mode
    )
    fighter = ListFighter.objects.create(
        list=list_obj,
        content_fighter=content_fighter,
        name="Fighter",
        owner=owner,
    )

    client = Client()
    client.login(username="testuser", password="password")

    url = reverse("core:list-fighter-xp-edit", args=[list_obj.id, fighter.id])
    response = client.get(url)
    assert response.status_code == 302
    assert response.url == reverse("core:list", args=[list_obj.id])


@pytest.mark.django_db
def test_edit_fighter_xp_view_get(list_with_fighter):
    """Test GET request to edit_fighter_xp view."""
    list_obj, fighter = list_with_fighter
    client = Client()
    client.login(username="testuser", password="password")

    url = reverse("core:list-fighter-xp-edit", args=[list_obj.id, fighter.id])
    response = client.get(url)
    assert response.status_code == 200

    # Check context
    assert "form" in response.context
    assert "fighter" in response.context
    assert response.context["fighter"] == fighter

    # Check content
    content = response.content.decode()
    assert "Edit XP" in content
    assert fighter.name in content
    assert "0 XP" in content  # Current XP displayed in badge
    assert "Current" in content
    assert "Total" in content


@pytest.mark.django_db
def test_edit_fighter_xp_add_operation(list_with_fighter):
    """Test adding XP to a fighter."""
    list_obj, fighter = list_with_fighter
    client = Client()
    client.login(username="testuser", password="password")

    url = reverse("core:list-fighter-xp-edit", args=[list_obj.id, fighter.id])
    response = client.post(
        url,
        data={
            "operation": "add",
            "amount": 10,
            "description": "Defeated enemy leader",
        },
    )

    # Check redirect
    assert response.status_code == 302
    assert response.url == reverse("core:list", args=[list_obj.id])

    # Check fighter XP updated
    fighter.refresh_from_db()
    assert fighter.xp_current == 10
    assert fighter.xp_total == 10

    # Check campaign action logged
    action = CampaignAction.objects.last()
    assert action.campaign == list_obj.campaign
    assert action.user.username == "testuser"
    assert action.list == list_obj
    assert "Added 10 XP" in action.description
    assert "Defeated enemy leader" in action.description
    assert fighter.name in action.description
    assert "Current: 10 XP, Total: 10 XP" in action.outcome


@pytest.mark.django_db
def test_edit_fighter_xp_spend_operation(list_with_fighter):
    """Test spending XP for a fighter."""
    list_obj, fighter = list_with_fighter
    # Give fighter some initial XP
    fighter.xp_current = 15
    fighter.xp_total = 15
    fighter.save()

    client = Client()
    client.login(username="testuser", password="password")

    url = reverse("core:list-fighter-xp-edit", args=[list_obj.id, fighter.id])
    response = client.post(
        url,
        data={
            "operation": "spend",
            "amount": 5,
            "description": "Bought new skill",
        },
    )

    # Check redirect
    assert response.status_code == 302
    assert response.url == reverse("core:list", args=[list_obj.id])

    # Check fighter XP updated
    fighter.refresh_from_db()
    assert fighter.xp_current == 10  # 15 - 5
    assert fighter.xp_total == 15  # Total unchanged

    # Check campaign action logged
    action = CampaignAction.objects.last()
    assert "Spent 5 XP" in action.description
    assert "Bought new skill" in action.description
    assert "Current: 10 XP, Total: 15 XP" in action.outcome


@pytest.mark.django_db
def test_edit_fighter_xp_reduce_operation(list_with_fighter):
    """Test reducing XP for a fighter."""
    list_obj, fighter = list_with_fighter
    # Give fighter some initial XP
    fighter.xp_current = 20
    fighter.xp_total = 25
    fighter.save()

    client = Client()
    client.login(username="testuser", password="password")

    url = reverse("core:list-fighter-xp-edit", args=[list_obj.id, fighter.id])
    response = client.post(
        url,
        data={
            "operation": "reduce",
            "amount": 5,
            "description": "Correction: miscounted XP",
        },
    )

    # Check redirect
    assert response.status_code == 302
    assert response.url == reverse("core:list", args=[list_obj.id])

    # Check fighter XP updated
    fighter.refresh_from_db()
    assert fighter.xp_current == 15  # 20 - 5
    assert fighter.xp_total == 20  # 25 - 5

    # Check campaign action logged
    action = CampaignAction.objects.last()
    assert "Reduced 5 XP" in action.description
    assert "Correction: miscounted XP" in action.description
    assert "Current: 15 XP, Total: 20 XP" in action.outcome


@pytest.mark.django_db
def test_edit_fighter_xp_spend_validation(list_with_fighter):
    """Test validation when spending more XP than available."""
    list_obj, fighter = list_with_fighter
    # Give fighter limited XP
    fighter.xp_current = 5
    fighter.xp_total = 10
    fighter.save()

    client = Client()
    client.login(username="testuser", password="password")

    url = reverse("core:list-fighter-xp-edit", args=[list_obj.id, fighter.id])
    response = client.post(
        url,
        data={
            "operation": "spend",
            "amount": 10,  # More than current (5)
            "description": "",
        },
    )

    # Check response (should show form with error)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Cannot spend more XP than available" in content

    # Check XP unchanged
    fighter.refresh_from_db()
    assert fighter.xp_current == 5
    assert fighter.xp_total == 10


@pytest.mark.django_db
def test_edit_fighter_xp_reduce_validation(list_with_fighter):
    """Test validation when reducing XP below zero."""
    list_obj, fighter = list_with_fighter
    # Give fighter limited XP
    fighter.xp_current = 5
    fighter.xp_total = 5
    fighter.save()

    client = Client()
    client.login(username="testuser", password="password")

    url = reverse("core:list-fighter-xp-edit", args=[list_obj.id, fighter.id])
    response = client.post(
        url,
        data={
            "operation": "reduce",
            "amount": 10,  # More than total (5)
            "description": "",
        },
    )

    # Check response (should show form with error)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Cannot reduce XP below zero" in content

    # Check XP unchanged
    fighter.refresh_from_db()
    assert fighter.xp_current == 5
    assert fighter.xp_total == 5


@pytest.mark.django_db
def test_edit_fighter_xp_without_description(list_with_fighter):
    """Test XP operations without description."""
    list_obj, fighter = list_with_fighter
    client = Client()
    client.login(username="testuser", password="password")

    url = reverse("core:list-fighter-xp-edit", args=[list_obj.id, fighter.id])
    response = client.post(
        url,
        data={
            "operation": "add",
            "amount": 3,
            "description": "",  # Empty description
        },
    )

    # Check redirect
    assert response.status_code == 302

    # Check campaign action logged without extra description
    action = CampaignAction.objects.last()
    assert "Added 3 XP" in action.description
    assert action.description.count("for") == 1  # Only "for Fighter Name"


@pytest.mark.django_db
def test_fighter_card_shows_xp_in_campaign_mode(list_with_fighter):
    """Test that fighter card shows XP in campaign mode."""
    list_obj, fighter = list_with_fighter
    fighter.xp_current = 8
    fighter.xp_total = 12
    fighter.save()

    client = Client()
    client.login(username="testuser", password="password")

    url = reverse("core:list", args=[list_obj.id])
    response = client.get(url)
    assert response.status_code == 200

    content = response.content.decode()
    # Check XP is displayed
    assert 'badge text-bg-primary">8 XP</span>' in content
    # Check edit link is present
    assert (
        f'href="{reverse("core:list-fighter-xp-edit", args=[list_obj.id, fighter.id])}"'
        in content
    )
    assert "Edit XP" in content


@pytest.mark.django_db
def test_fighter_card_hides_xp_in_basic_mode():
    """Test that fighter card doesn't show XP in basic mode."""
    owner = User.objects.create_user(username="testuser", password="password")
    house = ContentHouse.objects.create(name="House")
    content_fighter = ContentFighter.objects.create(
        type="Fighter",
        house=house,
        category="GANGER",
        movement="4",
        weapon_skill="3+",
        ballistic_skill="3+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="3+",
        attacks="1",
        leadership="7+",
        cool="7+",
        willpower="7+",
        intelligence="7+",
        base_cost=50,
    )

    list_obj = List.objects.create(
        name="Basic List",
        owner=owner,
        content_house=house,
        status=List.LIST_BUILDING,  # Basic mode
    )
    ListFighter.objects.create(
        list=list_obj,
        content_fighter=content_fighter,
        name="Fighter",
        owner=owner,
        xp_current=10,
        xp_total=10,
    )

    client = Client()
    client.login(username="testuser", password="password")

    url = reverse("core:list", args=[list_obj.id])
    response = client.get(url)
    assert response.status_code == 200

    content = response.content.decode()
    # Check XP is NOT displayed
    assert "10 XP" not in content
    assert "Edit XP" not in content


@pytest.mark.django_db
def test_multiple_xp_operations_sequence(list_with_fighter):
    """Test a sequence of XP operations."""
    list_obj, fighter = list_with_fighter
    client = Client()
    client.login(username="testuser", password="password")

    url = reverse("core:list-fighter-xp-edit", args=[list_obj.id, fighter.id])

    # Add 20 XP
    client.post(
        url,
        data={
            "operation": "add",
            "amount": 20,
            "description": "Initial XP",
        },
    )

    fighter.refresh_from_db()
    assert fighter.xp_current == 20
    assert fighter.xp_total == 20

    # Spend 8 XP
    client.post(
        url,
        data={
            "operation": "spend",
            "amount": 8,
            "description": "Skill advancement",
        },
    )

    fighter.refresh_from_db()
    assert fighter.xp_current == 12
    assert fighter.xp_total == 20

    # Add 5 more XP
    client.post(
        url,
        data={
            "operation": "add",
            "amount": 5,
            "description": "Battle reward",
        },
    )

    fighter.refresh_from_db()
    assert fighter.xp_current == 17
    assert fighter.xp_total == 25

    # Reduce 3 XP (correction)
    client.post(
        url,
        data={
            "operation": "reduce",
            "amount": 3,
            "description": "Correction",
        },
    )

    fighter.refresh_from_db()
    assert fighter.xp_current == 14
    assert fighter.xp_total == 22

    # Check all actions were logged
    actions = CampaignAction.objects.filter(campaign=list_obj.campaign).order_by(
        "created"
    )
    assert actions.count() == 4
    assert "Added 20 XP" in actions[0].description
    assert "Spent 8 XP" in actions[1].description
    assert "Added 5 XP" in actions[2].description
    assert "Reduced 3 XP" in actions[3].description


@pytest.mark.django_db
def test_archived_fighter_cannot_edit_xp(list_with_fighter):
    """Test that archived fighters cannot have XP edited."""
    list_obj, fighter = list_with_fighter
    fighter.archived_at = fighter.created  # Archive the fighter
    fighter.save()

    client = Client()
    client.login(username="testuser", password="password")

    url = reverse("core:list-fighter-xp-edit", args=[list_obj.id, fighter.id])
    response = client.get(url)
    # Should get 404 because archived fighters are excluded from queries
    assert response.status_code == 404
