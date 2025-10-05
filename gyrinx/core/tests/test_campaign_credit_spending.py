import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from gyrinx.content.models import ContentFighter
from gyrinx.core.models import List, ListFighter

User = get_user_model()


@pytest.fixture
def campaign_list_with_credits(db, user, house, campaign):
    lst = List.objects.create(
        name="Test Gang",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
        credits_current=1000,
        credits_earned=1000,
    )
    return lst


@pytest.fixture
def campaign_list_low_credits(db, user, house, campaign):
    lst = List.objects.create(
        name="Poor Gang",
        owner=user,
        content_house=house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
        credits_current=50,
        credits_earned=50,
    )
    return lst


@pytest.fixture
def list_building_list_with_credits(db, user, house):
    lst = List.objects.create(
        name="List Building Gang",
        owner=user,
        content_house=house,
        status=List.LIST_BUILDING,
        credits_current=1000,
        credits_earned=1000,
    )
    return lst


@pytest.fixture
def fighter_type(db, house):
    return ContentFighter.objects.create(
        house=house,
        type="Ganger",
        base_cost=50,
    )


@pytest.mark.django_db
def test_spend_credits_method_success(campaign_list_with_credits):
    """Test that spend_credits method works correctly."""
    initial_credits = campaign_list_with_credits.credits_current

    result = campaign_list_with_credits.spend_credits(100, "Test purchase")

    assert result is True
    campaign_list_with_credits.refresh_from_db()
    assert campaign_list_with_credits.credits_current == initial_credits - 100


@pytest.mark.django_db
def test_spend_credits_method_insufficient_funds(campaign_list_with_credits):
    """Test that spend_credits raises ValidationError when insufficient funds."""
    with pytest.raises(ValidationError) as exc_info:
        campaign_list_with_credits.spend_credits(2000, "Expensive purchase")

    assert "Insufficient credits" in str(exc_info.value)
    assert "2000¢" in str(exc_info.value)
    assert "1000¢" in str(exc_info.value)

    campaign_list_with_credits.refresh_from_db()
    assert campaign_list_with_credits.credits_current == 1000


@pytest.mark.django_db
def test_spend_credits_method_negative_amount(campaign_list_with_credits):
    """Test that spend_credits rejects negative amounts."""
    with pytest.raises(ValidationError) as exc_info:
        campaign_list_with_credits.spend_credits(-100, "Invalid")

    assert "Cannot spend negative credits" in str(exc_info.value)


@pytest.mark.django_db
def test_hire_fighter_in_campaign_mode_with_credits(
    client, user, campaign_list_with_credits, fighter_type
):
    """Test hiring a fighter in campaign mode spends credits."""
    client.login(username="testuser", password="password")

    response = client.post(
        reverse("core:new-list-fighter", args=(campaign_list_with_credits.id,)),
        {
            "name": "New Ganger",
            "content_fighter": fighter_type.id,
        },
    )

    assert response.status_code == 302

    campaign_list_with_credits.refresh_from_db()
    assert campaign_list_with_credits.credits_current == 950

    fighter = ListFighter.objects.get(name="New Ganger")
    assert fighter.list == campaign_list_with_credits


@pytest.mark.django_db
def test_hire_fighter_in_campaign_mode_insufficient_credits(
    client, user, campaign_list_low_credits, fighter_type
):
    """Test hiring a fighter fails when insufficient credits."""
    client.login(username="testuser", password="password")

    response = client.post(
        reverse("core:new-list-fighter", args=(campaign_list_low_credits.id,)),
        {
            "name": "Expensive Ganger",
            "content_fighter": fighter_type.id,
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Insufficient credits" in content or "error_message" in content

    campaign_list_low_credits.refresh_from_db()
    assert campaign_list_low_credits.credits_current == 50

    assert not ListFighter.objects.filter(name="Expensive Ganger").exists()


@pytest.mark.django_db
def test_hire_fighter_in_list_building_mode_no_credit_check(
    client, user, list_building_list_with_credits, fighter_type
):
    """Test hiring a fighter in list building mode doesn't spend credits."""
    client.login(username="testuser", password="password")

    response = client.post(
        reverse("core:new-list-fighter", args=(list_building_list_with_credits.id,)),
        {
            "name": "New Ganger",
            "content_fighter": fighter_type.id,
        },
    )

    assert response.status_code == 302

    list_building_list_with_credits.refresh_from_db()
    assert list_building_list_with_credits.credits_current == 1000

    fighter = ListFighter.objects.get(name="New Ganger")
    assert fighter.list == list_building_list_with_credits


@pytest.mark.django_db
def test_spend_credits_exactly_zero_credits_remaining(campaign_list_with_credits):
    """Test spending exactly the amount of credits available."""
    campaign_list_with_credits.credits_current = 100
    campaign_list_with_credits.save()

    result = campaign_list_with_credits.spend_credits(100, "Exact match")

    assert result is True
    campaign_list_with_credits.refresh_from_db()
    assert campaign_list_with_credits.credits_current == 0


@pytest.mark.django_db
def test_spend_credits_one_credit_short(campaign_list_with_credits):
    """Test that spending one more credit than available fails."""
    campaign_list_with_credits.credits_current = 99
    campaign_list_with_credits.save()

    with pytest.raises(ValidationError) as exc_info:
        campaign_list_with_credits.spend_credits(100, "One too many")

    assert "Insufficient credits" in str(exc_info.value)
    campaign_list_with_credits.refresh_from_db()
    assert campaign_list_with_credits.credits_current == 99
