import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.core.models import List
from gyrinx.core.models.campaign import CampaignAction

User = get_user_model()


@pytest.fixture
def campaign_list(db, user, house, campaign):
    lst = List.objects.create(
        name="Test Gang",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )
    return lst


@pytest.fixture
def list_building_list(db, user, house):
    lst = List.objects.create(
        name="List Building Gang",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
    )
    return lst


@pytest.mark.django_db
def test_list_has_credit_fields(campaign_list):
    """Test that List model has credit tracking fields."""
    assert hasattr(campaign_list, "credits_current")
    assert hasattr(campaign_list, "credits_earned")
    assert campaign_list.credits_current == 0
    assert campaign_list.credits_earned == 0


@pytest.mark.django_db
def test_edit_list_credits_view_requires_campaign_mode(
    client, user, list_building_list
):
    """Test that credit editing requires campaign mode."""
    client.login(username="testuser", password="password")

    response = client.get(
        reverse("core:list-credits-edit", args=(list_building_list.id,))
    )

    # Should redirect with error message
    assert response.status_code == 302
    assert response.url == reverse("core:list", args=(list_building_list.id,))


@pytest.mark.django_db
def test_add_credits_to_list(client, user, campaign_list):
    """Test adding credits to a list."""
    client.login(username="testuser", password="password")

    response = client.post(
        reverse("core:list-credits-edit", args=(campaign_list.id,)),
        {
            "operation": "add",
            "amount": 500,
            "description": "Gang won territory",
        },
    )

    assert response.status_code == 302

    campaign_list.refresh_from_db()
    assert campaign_list.credits_current == 500
    assert campaign_list.credits_earned == 500

    # Check campaign action was created
    action = CampaignAction.objects.get()
    assert "Added 500¢" in action.description
    assert "Gang won territory" in action.description
    assert "+500¢ (to 500¢)" in action.outcome


@pytest.mark.django_db
def test_spend_credits(client, user, campaign_list):
    """Test spending credits."""
    # Give list some credits first
    campaign_list.credits_current = 1000
    campaign_list.credits_earned = 1000
    campaign_list.save()

    client.login(username="testuser", password="password")

    response = client.post(
        reverse("core:list-credits-edit", args=(campaign_list.id,)),
        {
            "operation": "spend",
            "amount": 300,
            "description": "Hired new fighter",
        },
    )

    assert response.status_code == 302

    campaign_list.refresh_from_db()
    assert campaign_list.credits_current == 700  # 1000 - 300
    assert campaign_list.credits_earned == 1000  # Total unchanged

    # Check campaign action
    action = CampaignAction.objects.get()
    assert "Spent 300¢" in action.description
    assert "Hired new fighter" in action.description


@pytest.mark.django_db
def test_reduce_credits(client, user, campaign_list):
    """Test reducing credits (affects both current and total)."""
    # Give list some credits first
    campaign_list.credits_current = 800
    campaign_list.credits_earned = 1200
    campaign_list.save()

    client.login(username="testuser", password="password")

    response = client.post(
        reverse("core:list-credits-edit", args=(campaign_list.id,)),
        {
            "operation": "reduce",
            "amount": 200,
            "description": "Lost territory",
        },
    )

    assert response.status_code == 302

    campaign_list.refresh_from_db()
    assert campaign_list.credits_current == 600  # 800 - 200
    assert campaign_list.credits_earned == 1000  # 1200 - 200


@pytest.mark.django_db
def test_cannot_spend_more_than_available(client, user, campaign_list):
    """Test that you cannot spend more credits than available."""
    campaign_list.credits_current = 100
    campaign_list.credits_earned = 100
    campaign_list.save()

    client.login(username="testuser", password="password")

    response = client.post(
        reverse("core:list-credits-edit", args=(campaign_list.id,)),
        {
            "operation": "spend",
            "amount": 500,
        },
    )

    # Should show form with error
    assert response.status_code == 200
    assert "Cannot spend more credits than available" in response.content.decode()

    # List credits unchanged
    campaign_list.refresh_from_db()
    assert campaign_list.credits_current == 100
    assert campaign_list.credits_earned == 100
