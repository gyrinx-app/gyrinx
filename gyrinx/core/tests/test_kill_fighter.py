import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentFighter,
    ContentFighterEquipmentListItem,
)
from gyrinx.core.handlers.equipment.reassignment import (
    handle_equipment_reassignment,
)
from gyrinx.core.handlers.fighter.kill import handle_fighter_kill
from gyrinx.core.models.action import ListAction, ListActionType
from gyrinx.core.models.list import (
    List,
    ListFighter,
    ListFighterEquipmentAssignment,
)

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
def test_kill_freezes_transferred_equipment_value(
    user, make_list, make_content_fighter, make_list_fighter, content_house
):
    """Gear transferred to the stash on death keeps its dying-fighter price.

    Regression for #1826. A weapon priced by the dying fighter's equipment list
    must not re-price to the stash's context (which has no equipment list).
    Freezing the value via total_cost_override keeps the cached stash total in
    sync with the stash fighter's own recomputed cost_int() — no drift.
    """
    lst = make_list("Freeze Gang", status=List.CAMPAIGN_MODE)
    stash = lst.ensure_stash()

    # A fighter whose equipment list discounts the Lasgun to 5¢, while its full
    # price (what the stash, with no equipment list, would charge) is 15¢.
    cf = make_content_fighter(
        type="Ganger",
        category="GANGER",
        house=content_house,
        base_cost=50,
    )
    fighter = make_list_fighter(lst, "Bob", content_fighter=cf)

    lasgun = ContentEquipment.objects.create(name="Lasgun", cost=15)
    ContentFighterEquipmentListItem.objects.create(fighter=cf, equipment=lasgun, cost=5)

    fighter.assign(lasgun)

    # Sanity: the Lasgun costs 5¢ on Bob (equipment-list price), not 15¢.
    bob_assignment = fighter.listfighterequipmentassignment_set.get()
    assert bob_assignment.cost_int() == 5

    handle_fighter_kill(user=user, lst=lst, fighter=fighter)

    # The gear moved to the stash pinned at its frozen 5¢ — not re-priced to 15¢.
    stash_assignment = stash.listfighterequipmentassignment_set.get()
    assert stash_assignment.total_cost_override == 5
    assert stash_assignment.cost_int() == 5

    # The cached stash total agrees with a fresh recompute of the stash
    # fighter's contents: the cache did not drift.
    lst.refresh_from_db()
    stash.refresh_from_db()
    assert stash.cost_int() == 5
    assert lst.stash_current == 5


@pytest.mark.django_db
def test_frozen_stash_value_survives_reassignment_out(
    user, make_list, make_content_fighter, make_list_fighter, content_house, campaign
):
    """Frozen stash gear keeps its price when re-equipped onto another fighter.

    Confirms the #1826 decision: gear stays frozen through reassignment — it
    does not re-price to the receiving fighter's equipment list. The
    reassignment handler moves the existing assignment row, so the
    total_cost_override pinned on death rides along.
    """
    lst = make_list("Freeze Gang", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(lst)
    stash = lst.ensure_stash()

    # Bob's equipment list prices the Lasgun at 5¢.
    dying_cf = make_content_fighter(
        type="Ganger", category="GANGER", house=content_house, base_cost=50
    )
    fighter = make_list_fighter(lst, "Bob", content_fighter=dying_cf)
    lasgun = ContentEquipment.objects.create(name="Lasgun", cost=15)
    ContentFighterEquipmentListItem.objects.create(
        fighter=dying_cf, equipment=lasgun, cost=5
    )
    fighter.assign(lasgun)

    handle_fighter_kill(user=user, lst=lst, fighter=fighter)
    stash_assignment = stash.listfighterequipmentassignment_set.get()
    assert stash_assignment.cost_int() == 5  # frozen at Bob's price

    # A new fighter whose own equipment list would price the Lasgun at 12¢.
    heir_cf = make_content_fighter(
        type="Champion", category="CHAMPION", house=content_house, base_cost=80
    )
    ContentFighterEquipmentListItem.objects.create(
        fighter=heir_cf, equipment=lasgun, cost=12
    )
    heir = make_list_fighter(lst, "Heir", content_fighter=heir_cf)

    # Re-fetch participants so the handler reads current cached values.
    lst.refresh_from_db()
    stash = ListFighter.objects.get(pk=stash.pk)
    stash_assignment = ListFighterEquipmentAssignment.objects.get(
        pk=stash_assignment.pk
    )

    result = handle_equipment_reassignment(
        user=user,
        lst=lst,
        from_fighter=stash,
        to_fighter=heir,
        assignment=stash_assignment,
    )

    # Still 5¢ on the heir — not re-priced to the heir's 12¢ list price.
    assert result.equipment_cost == 5
    stash_assignment.refresh_from_db()
    assert stash_assignment.cost_int() == 5

    # Wealth bookkeeping: 5¢ left the stash, 5¢ joined the rating; no drift.
    lst.refresh_from_db()
    heir.refresh_from_db()
    assert lst.stash_current == 0
    assert heir.cost_int() == 80 + 5


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
    assert b"Transfer their equipment to the stash" in response.content
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


@pytest.fixture
def campaign_list_with_stash(make_list, make_list_fighter, stash_fighter_type):
    """A campaign-mode list with a stash fighter and a regular fighter.

    Composed from the canonical conftest factories (``make_list``,
    ``make_list_fighter``, ``stash_fighter_type``) rather than inline ORM
    creation. The regular fighter uses the default ``content_fighter`` fixture.
    """
    lst = make_list("Test List", status=List.CAMPAIGN_MODE)
    stash = make_list_fighter(lst, "Stash", content_fighter=stash_fighter_type)
    fighter = make_list_fighter(lst, "Test Fighter")
    return lst, stash, fighter


@pytest.fixture
def persistent_category():
    """A persistent equipment category (gear stays with a dead fighter)."""
    return ContentEquipmentCategory.objects.create(
        name="Impressive Leadership",
        group="Other",
        persistent=True,
    )


@pytest.mark.django_db
def test_kill_fighter_persistent_equipment_stays_with_fighter(
    client, user, campaign_list_with_stash, persistent_category
):
    """Persistent-category equipment stays on the dead fighter, not the stash."""
    lst, stash, fighter = campaign_list_with_stash

    equipment = ContentEquipment.objects.create(
        name="Impressive Leadership",
        cost=20,
        category=persistent_category,
    )
    fighter.assign(equipment)

    client.force_login(user)
    url = reverse("core:list-fighter-kill", args=[lst.id, fighter.id])
    response = client.post(url)
    assert response.status_code == 302

    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.DEAD
    assert fighter.cost_override == 0

    # The persistent assignment stays attached to the (now dead) fighter...
    assert fighter.listfighterequipmentassignment_set.count() == 1
    assert (
        fighter.listfighterequipmentassignment_set.first().content_equipment
        == equipment
    )
    # ...and is NOT transferred to the stash.
    assert not stash.listfighterequipmentassignment_set.exists()

    # A dead fighter contributes 0 regardless of equipment still attached.
    assert fighter.cost_int() == 0


@pytest.mark.django_db
def test_kill_fighter_mixed_persistent_and_normal(
    client, user, campaign_list_with_stash, persistent_category
):
    """A fighter with both kinds: persistent stays, non-persistent transfers."""
    lst, stash, fighter = campaign_list_with_stash

    persistent_equipment = ContentEquipment.objects.create(
        name="Impressive Leadership",
        cost=20,
        category=persistent_category,
    )
    normal_equipment = ContentEquipment.objects.create(name="Lasgun", cost=15)
    fighter.assign(persistent_equipment)
    fighter.assign(normal_equipment)

    client.force_login(user)
    url = reverse("core:list-fighter-kill", args=[lst.id, fighter.id])
    response = client.post(url)
    assert response.status_code == 302

    # Persistent item stays on the fighter; normal item moves to the stash.
    fighter_assignments = fighter.listfighterequipmentassignment_set.all()
    assert fighter_assignments.count() == 1
    assert fighter_assignments.first().content_equipment == persistent_equipment

    stash_assignments = stash.listfighterequipmentassignment_set.all()
    assert stash_assignments.count() == 1
    assert stash_assignments.first().content_equipment == normal_equipment


@pytest.mark.django_db
def test_kill_fighter_persistent_stash_delta_is_transferred_cost_only(
    user, campaign_list_with_stash, persistent_category, settings
):
    """stash_delta counts only transferred gear; rating drops by the full cost."""
    # The kill action is only created when this flag is on; set it explicitly
    # so the test is deterministic regardless of config defaults.
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst, stash, fighter = campaign_list_with_stash
    # make_list already seeds an initial LIST_CREATE action, so the kill action
    # can be created.

    fighter.assign(
        ContentEquipment.objects.create(
            name="Impressive Leadership",
            cost=20,
            category=persistent_category,
        )
    )
    fighter.assign(ContentEquipment.objects.create(name="Lasgun", cost=15))

    fighter_cost_before = fighter.cost_int()  # base + 20 (persistent) + 15
    lst.rating_current = fighter_cost_before
    lst.stash_current = 0
    lst.save()

    result = handle_fighter_kill(user=user, lst=lst, fighter=fighter)

    # Result reports one transferred and one kept.
    assert result.equipment_count == 1
    assert result.persistent_count == 1
    assert "transferred to stash" in result.description
    assert "stayed with the fighter" in result.description

    # Only the non-persistent Lasgun (15¢) bumps the stash.
    assert result.list_action is not None
    assert result.list_action.stash_delta == 15
    assert result.list_action.rating_delta == -fighter_cost_before

    lst.refresh_from_db()
    assert lst.rating_current == 0
    assert lst.stash_current == 15


@pytest.mark.django_db
def test_dead_fighter_card_shows_persistent_equipment(
    client, user, campaign_list_with_stash, persistent_category
):
    """The persistent item remains visible on the dead fighter's card."""
    lst, stash, fighter = campaign_list_with_stash

    fighter.assign(
        ContentEquipment.objects.create(
            name="Impressive Leadership",
            cost=20,
            category=persistent_category,
        )
    )

    client.force_login(user)
    kill_url = reverse("core:list-fighter-kill", args=[lst.id, fighter.id])
    assert client.post(kill_url).status_code == 302

    response = client.get(reverse("core:list", args=[lst.id]))
    assert response.status_code == 200
    assert "Impressive Leadership" in response.content.decode()


@pytest.mark.django_db
def test_kill_fighter_without_stash_does_not_claim_transfer(
    user, make_list, make_list_fighter
):
    """With no stash, nothing transfers and the result doesn't claim it did."""
    lst = make_list("No Stash List", status=List.CAMPAIGN_MODE)
    fighter = make_list_fighter(lst, "Test Fighter")
    fighter.assign(ContentEquipment.objects.create(name="Lasgun", cost=15))

    assert not lst.listfighter_set.filter(content_fighter__is_stash=True).exists()

    result = handle_fighter_kill(user=user, lst=lst, fighter=fighter)

    # Nothing was transferred (no stash to receive it).
    assert result.equipment_count == 0
    assert result.persistent_count == 0
    assert "transferred to stash" not in result.description
    # The non-persistent gear stays on the fighter rather than being deleted.
    assert fighter.listfighterequipmentassignment_set.count() == 1
