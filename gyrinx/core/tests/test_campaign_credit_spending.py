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
    client, user, campaign_list_with_credits, content_fighter: ContentFighter
):
    """Test hiring a fighter in campaign mode spends credits."""
    client.login(username="testuser", password="password")

    response = client.post(
        reverse("core:list-fighter-new", args=(campaign_list_with_credits.id,)),
        {
            "name": "New Ganger 1",
            "content_fighter": content_fighter.id,
        },
    )

    assert response.status_code == 302

    campaign_list_with_credits.refresh_from_db()
    assert (
        campaign_list_with_credits.credits_current == 1000 - content_fighter.base_cost
    )

    fighter = ListFighter.objects.get(name="New Ganger 1")
    assert fighter.list == campaign_list_with_credits


@pytest.mark.django_db
def test_hire_fighter_in_campaign_mode_insufficient_credits(
    client, user, campaign_list_low_credits, content_fighter
):
    """Test hiring a fighter fails when insufficient credits."""
    client.login(username="testuser", password="password")

    response = client.post(
        reverse("core:list-fighter-new", args=(campaign_list_low_credits.id,)),
        {
            "name": "Expensive Ganger",
            "content_fighter": content_fighter.id,
        },
    )

    assert response.status_code == 200
    content = response.content.decode()
    assert "Insufficient credits" in content

    campaign_list_low_credits.refresh_from_db()
    assert campaign_list_low_credits.credits_current == 50

    assert not ListFighter.objects.filter(name="Expensive Ganger").exists()


@pytest.mark.django_db
def test_hire_fighter_in_list_building_mode_no_credit_check(
    client, user, list_building_list_with_credits, content_fighter
):
    """Test hiring a fighter in list building mode doesn't spend credits."""
    client.login(username="testuser", password="password")

    response = client.post(
        reverse("core:list-fighter-new", args=(list_building_list_with_credits.id,)),
        {
            "name": "New Ganger",
            "content_fighter": content_fighter.id,
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


@pytest.mark.django_db
def test_hire_fighter_creates_campaign_action(
    client, user, campaign_list_with_credits, content_fighter: ContentFighter
):
    """Test that hiring a fighter in campaign mode creates a campaign action."""
    from gyrinx.core.models.campaign import CampaignAction

    client.login(username="testuser", password="password")

    # Verify no campaign actions exist initially
    assert CampaignAction.objects.filter(list=campaign_list_with_credits).count() == 0

    response = client.post(
        reverse("core:list-fighter-new", args=(campaign_list_with_credits.id,)),
        {
            "name": "New Ganger 1",
            "content_fighter": content_fighter.id,
        },
    )

    assert response.status_code == 302

    # Verify campaign action was created
    actions = CampaignAction.objects.filter(list=campaign_list_with_credits)
    assert actions.count() == 1

    action = actions.first()
    assert action.user == user
    assert action.campaign == campaign_list_with_credits.campaign
    assert "Hired New Ganger 1" in action.description
    assert f"{content_fighter.base_cost}¢" in action.description
    assert "Credits remaining:" in action.outcome


@pytest.mark.django_db
def test_add_vehicle_creates_campaign_action(
    client, user, campaign_list_with_credits, house, make_equipment
):
    """Test that adding a vehicle in campaign mode creates a campaign action."""
    from gyrinx.core.models.campaign import CampaignAction
    from gyrinx.models import FighterCategoryChoices

    client.login(username="testuser", password="password")

    # Create a vehicle equipment and crew fighter
    from gyrinx.content.models import ContentEquipmentFighterProfile

    vehicle_equipment = make_equipment(
        name="Test Bike",
        category="Vehicles",
        base_cost=80,
        is_vehicle=True,
    )

    crew_fighter = ContentFighter.objects.create(
        type="Vehicle Crew",
        category=FighterCategoryChoices.CREW,
        house=house,
        base_cost=20,
    )

    # Create profile that links the vehicle to the crew fighter
    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle_equipment,
        fighter=crew_fighter,
    )

    # Verify no campaign actions exist initially
    assert CampaignAction.objects.filter(list=campaign_list_with_credits).count() == 0

    # Simulate the vehicle flow - step 1: select vehicle
    session = client.session
    session["vehicle_flow_params"] = {
        "vehicle_equipment_id": str(vehicle_equipment.id),
        "action": "select_crew",
        "crew_name": "Test Crew Member",
        "crew_fighter_id": str(crew_fighter.id),
    }
    session.save()

    # Step 3: confirm vehicle purchase
    response = client.post(
        reverse("core:list-vehicle-confirm", args=(campaign_list_with_credits.id,)),
        {},  # Confirmation form has no fields
    )

    assert response.status_code == 302

    # Verify credits were spent
    campaign_list_with_credits.refresh_from_db()
    expected_cost = vehicle_equipment.base_cost + crew_fighter.base_cost
    assert campaign_list_with_credits.credits_current == 1000 - expected_cost

    # Verify campaign action was created
    actions = CampaignAction.objects.filter(list=campaign_list_with_credits)
    assert actions.count() == 1

    action = actions.first()
    assert action.user == user
    assert action.campaign == campaign_list_with_credits.campaign
    assert "Purchased Test Bike" in action.description
    assert "Test Crew Member" in action.description
    assert f"{expected_cost}¢" in action.description
    assert "Credits remaining:" in action.outcome
