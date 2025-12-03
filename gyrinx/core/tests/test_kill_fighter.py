import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import ContentEquipment, ContentFighter
from gyrinx.core.models.action import ListAction, ListActionType
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
    # Template uses fully_qualified_name which may include additional info
    assert b"Kill Fighter:" in response.content
    assert b"Doomed Fighter" in response.content
    assert b"Transfer all their equipment to the stash" in response.content
    assert b"Set their rating to 0" in response.content


@pytest.mark.django_db
def test_kill_fighter_creates_campaign_action(client, user, content_house):
    """Test that killing a fighter creates a campaign action."""
    from gyrinx.core.models.campaign import Campaign, CampaignAction

    # Create a campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    # Create a campaign mode list associated with the campaign
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    # Create a stash fighter
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

    # Create a fighter to kill
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

    # Create some equipment
    equipment = ContentEquipment.objects.create(
        name="Test Gun",
        cost=25,
    )

    # Assign equipment to fighter
    fighter.assign(equipment)

    client.force_login(user)
    url = reverse("core:list-fighter-kill", args=[lst.id, fighter.id])

    # Check no campaign actions exist yet
    assert CampaignAction.objects.count() == 0

    # Kill the fighter
    response = client.post(url)
    assert response.status_code == 302

    # Check fighter is marked as dead
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.DEAD
    assert fighter.cost_override == 0

    # Check campaign action was created
    assert CampaignAction.objects.count() == 1
    action = CampaignAction.objects.first()
    assert action.campaign == campaign
    assert action.list == lst
    assert action.user == user
    assert "Death: Doomed Fighter was killed" in action.description
    assert "permanently dead" in action.outcome
    assert "equipment transferred to stash" in action.outcome


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_kill_fighter_creates_list_action_with_stash_delta(
    client, user, content_house, settings, feature_flag_enabled
):
    """Test that killing a fighter creates a ListAction with correct stash_delta."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    # Create a campaign mode list
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=content_house,
        status=List.CAMPAIGN_MODE,
    )

    # Create initial LIST_CREATE action so other actions can be created
    # (required by create_action which checks for latest_action)
    ListAction.objects.create(
        list=lst,
        action_type=ListActionType.CREATE,
        owner=user,
        applied=True,
    )

    # Create a stash fighter
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

    # Create equipment
    equipment1 = ContentEquipment.objects.create(name="Lasgun", cost=15)
    equipment2 = ContentEquipment.objects.create(name="Sword", cost=10)

    # Assign equipment to fighter
    fighter.assign(equipment1)
    fighter.assign(equipment2)

    # Set up initial rating/stash to match what fighters would contribute
    # (needed because we created fighters directly, not via handlers)
    fighter_cost = fighter.cost_int()  # 50 + 15 + 10 = 75
    equipment_cost = 15 + 10  # 25
    lst.rating_current = fighter_cost
    lst.stash_current = 0
    lst.save()

    # Capture initial state after setup
    initial_rating = lst.rating_current
    initial_stash = lst.stash_current

    # Kill the fighter
    client.force_login(user)
    url = reverse("core:list-fighter-kill", args=[lst.id, fighter.id])
    response = client.post(url)
    assert response.status_code == 302

    # Fighter should always be marked as dead regardless of feature flag
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.DEAD
    assert fighter.cost_override == 0

    # Equipment should always be transferred to stash
    stash = lst.listfighter_set.filter(content_fighter__is_stash=True).first()
    assert stash.listfighterequipmentassignment_set.count() == 2

    # Check ListAction behavior based on feature flag
    list_action = (
        ListAction.objects.filter(
            list=lst,
            action_type=ListActionType.UPDATE_FIGHTER,
        )
        .order_by("-created")
        .first()
    )

    if feature_flag_enabled:
        assert list_action is not None, "ListAction should be created when flag enabled"

        # Verify the deltas track equipment moving to stash
        assert list_action.rating_delta == -fighter_cost  # Full cost leaves rating
        assert list_action.stash_delta == equipment_cost  # Equipment value enters stash
        assert list_action.credits_delta == 0

        # Verify stored values were updated correctly by the action
        lst.refresh_from_db()
        assert lst.rating_current == initial_rating - fighter_cost
        assert lst.stash_current == initial_stash + equipment_cost

        # Verify wealth is preserved (only lost fighter base cost, not equipment)
        fighter_base_cost = 50
        assert (
            lst.rating_current + lst.stash_current
            == initial_rating + initial_stash - fighter_base_cost
        )
    else:
        assert list_action is None, (
            "ListAction should not be created when flag disabled"
        )
