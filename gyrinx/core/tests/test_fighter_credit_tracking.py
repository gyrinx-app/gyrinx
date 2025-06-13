import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import ContentFighter, ContentHouse
from gyrinx.core.models import List, ListFighter
from gyrinx.core.models.campaign import Campaign, CampaignAction

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="testuser", password="testpass")


@pytest.fixture
def house(db):
    return ContentHouse.objects.create(name="Test House")


@pytest.fixture
def content_fighter(db, house):
    return ContentFighter.objects.create(
        name="Test Fighter Type",
        type="Test Fighter",
        house=house,
        category="GANGER",
        cost=50,
        movement='5"',
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7",
        cool="8",
        willpower="8",
        intelligence="8",
    )


@pytest.fixture
def campaign(db, user):
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )
    return campaign


@pytest.fixture
def campaign_list(db, user, house, campaign):
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )
    return lst


@pytest.fixture
def fighter(db, campaign_list, content_fighter):
    return ListFighter.objects.create(
        name="Test Fighter",
        list=campaign_list,
        content_fighter=content_fighter,
        owner=campaign_list.owner,
    )


@pytest.mark.django_db
def test_fighter_has_credit_fields(fighter):
    """Test that fighters have credit tracking fields."""
    assert hasattr(fighter, "credits_current")
    assert hasattr(fighter, "credits_total")
    assert fighter.credits_current == 0
    assert fighter.credits_total == 0


@pytest.mark.django_db
def test_edit_fighter_credits_view_requires_campaign_mode(client, user, house):
    """Test that credit editing requires campaign mode."""
    client.login(username="testuser", password="testpass")

    # Create a list in list building mode
    lst = List.objects.create(
        name="List Building List",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        list=lst,
        content_fighter=ContentFighter.objects.create(
            name="Test Fighter Type",
            type="Test Fighter",
            house=house,
            category="GANGER",
            cost=50,
        ),
        owner=user,
    )

    response = client.get(
        reverse("core:list-fighter-credits-edit", args=(lst.id, fighter.id))
    )

    # Should redirect with error message
    assert response.status_code == 302
    assert response.url == reverse("core:list", args=(lst.id,))


@pytest.mark.django_db
def test_add_credits_to_fighter(client, user, fighter, campaign_list):
    """Test adding credits to a fighter."""
    client.login(username="testuser", password="testpass")

    response = client.post(
        reverse("core:list-fighter-credits-edit", args=(campaign_list.id, fighter.id)),
        {
            "operation": "add",
            "amount": 100,
            "description": "Won a battle",
        },
    )

    assert response.status_code == 302

    fighter.refresh_from_db()
    assert fighter.credits_current == 100
    assert fighter.credits_total == 100

    # Check campaign action was created
    action = CampaignAction.objects.get()
    assert "Added 100¢ for Test Fighter" in action.description
    assert "Won a battle" in action.description
    assert "Current: 100¢, Total: 100¢" in action.outcome


@pytest.mark.django_db
def test_spend_credits(client, user, fighter, campaign_list):
    """Test spending credits."""
    # Give fighter some credits first
    fighter.credits_current = 150
    fighter.credits_total = 150
    fighter.save()

    client.login(username="testuser", password="testpass")

    response = client.post(
        reverse("core:list-fighter-credits-edit", args=(campaign_list.id, fighter.id)),
        {
            "operation": "spend",
            "amount": 50,
            "description": "Bought equipment",
        },
    )

    assert response.status_code == 302

    fighter.refresh_from_db()
    assert fighter.credits_current == 100  # 150 - 50
    assert fighter.credits_total == 150  # Total unchanged

    # Check campaign action
    action = CampaignAction.objects.get()
    assert "Spent 50¢ for Test Fighter" in action.description
    assert "Bought equipment" in action.description


@pytest.mark.django_db
def test_reduce_credits(client, user, fighter, campaign_list):
    """Test reducing credits (affects both current and total)."""
    # Give fighter some credits first
    fighter.credits_current = 150
    fighter.credits_total = 200
    fighter.save()

    client.login(username="testuser", password="testpass")

    response = client.post(
        reverse("core:list-fighter-credits-edit", args=(campaign_list.id, fighter.id)),
        {
            "operation": "reduce",
            "amount": 50,
            "description": "Lost a bet",
        },
    )

    assert response.status_code == 302

    fighter.refresh_from_db()
    assert fighter.credits_current == 100  # 150 - 50
    assert fighter.credits_total == 150  # 200 - 50


@pytest.mark.django_db
def test_cannot_spend_more_than_available(client, user, fighter, campaign_list):
    """Test that you cannot spend more credits than available."""
    fighter.credits_current = 50
    fighter.credits_total = 50
    fighter.save()

    client.login(username="testuser", password="testpass")

    response = client.post(
        reverse("core:list-fighter-credits-edit", args=(campaign_list.id, fighter.id)),
        {
            "operation": "spend",
            "amount": 100,
        },
    )

    # Should show form with error
    assert response.status_code == 200
    assert "Cannot spend more credits than available" in response.content.decode()

    # Fighter credits unchanged
    fighter.refresh_from_db()
    assert fighter.credits_current == 50
    assert fighter.credits_total == 50


@pytest.mark.django_db
def test_credits_display_in_fighter_card(client, user, fighter, campaign_list):
    """Test that credits are displayed in the fighter card."""
    fighter.credits_current = 75
    fighter.save()

    client.login(username="testuser", password="testpass")

    response = client.get(reverse("core:list", args=(campaign_list.id,)))
    assert response.status_code == 200

    content = response.content.decode()
    assert "Credits" in content
    assert "75¢" in content
    assert "Edit Credits" in content
