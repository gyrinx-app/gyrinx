import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from n23.content.models import (
    ContentFighter,
    ContentHouse,
    ContentInjury,
    ContentInjuryDefaultOutcome,
)
from n23.core.models.campaign import Campaign, CampaignAction
from n23.core.models.list import List, ListFighter, ListFighterInjury
from n23.core.tests.test_balance_sheet import (
    assert_reconciles,
    buy_equipment,
    hire_fighter,
)
from n23.models import FighterCategoryChoices


def create_test_data(client):
    """Helper function to create test data."""
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    lst = List.objects.create(
        name="Test List",
        content_house=house,
        owner=user,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Create some injuries
    injuries = [
        ContentInjury.objects.get_or_create(
            name="Test Eye Injury View",
            defaults={
                "description": "Recovery, -1 Ballistic Skill",
                "phase": ContentInjuryDefaultOutcome.RECOVERY,
            },
        )[0],
        ContentInjury.objects.get_or_create(
            name="Test Old Battle Wound View",
            defaults={
                "description": "Roll D6 after each battle",
                "phase": ContentInjuryDefaultOutcome.ACTIVE,
            },
        )[0],
        ContentInjury.objects.get_or_create(
            name="Test Humiliated View",
            defaults={
                "description": "Convalescence, -1 Leadership, -1 Cool",
                "phase": ContentInjuryDefaultOutcome.CONVALESCENCE,
            },
        )[0],
    ]

    return user, campaign, lst, fighter, injuries


@pytest.mark.django_db
def test_add_injury_view_get():
    """Test GET request to add injury view."""
    client = Client()
    user, campaign, lst, fighter, injuries = create_test_data(client)

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 200
    assert "Add Injury" in response.content.decode()
    assert fighter.name in response.content.decode()

    # Check that all injuries are in the form
    content = response.content.decode()
    for injury in injuries:
        assert injury.name in content


@pytest.mark.django_db
def test_add_injury_view_defaults_to_fighter_state():
    """Test that add injury view sets fighter_state to current fighter state."""
    client = Client()
    user, campaign, lst, fighter, injuries = create_test_data(client)

    # Set fighter to RECOVERY state
    fighter.injury_state = ListFighter.RECOVERY
    fighter.save()

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 200

    # Check that the form has the correct initial value
    form = response.context["form"]
    assert form.fields["fighter_state"].initial == ListFighter.RECOVERY

    # Check that RECOVERY is selected in the HTML
    content = response.content.decode()
    assert 'value="recovery" selected' in content.lower()

    # Test with CONVALESCENCE state
    fighter.injury_state = ListFighter.CONVALESCENCE
    fighter.save()

    response = client.get(url)
    form = response.context["form"]
    assert form.fields["fighter_state"].initial == ListFighter.CONVALESCENCE

    content = response.content.decode()
    assert 'value="convalescence" selected' in content.lower()


@pytest.mark.django_db
def test_add_injury_view_post_success():
    """Test successful POST to add injury."""
    client = Client()
    user, campaign, lst, fighter, injuries = create_test_data(client)

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    injury = injuries[0]  # Eye Injury

    response = client.post(
        url,
        {
            "injury": injury.id,
            "fighter_state": "recovery",
            "notes": "Shot by enemy sniper",
        },
    )

    # Should redirect to injuries edit page
    assert response.status_code == 302
    assert response.url == reverse(
        "core:list-fighter-injuries-edit", args=[lst.id, fighter.id]
    )

    # Check injury was created
    assert fighter.injuries.count() == 1
    fighter_injury = fighter.injuries.first()
    assert fighter_injury.injury == injury
    assert fighter_injury.notes == "Shot by enemy sniper"

    # Check campaign action was logged
    action = CampaignAction.objects.last()
    assert action.campaign == campaign
    assert f"{fighter.name} suffered {injury.name}" in action.description
    assert "Shot by enemy sniper" in action.description
    assert "was put into Recovery" in action.outcome


@pytest.mark.django_db
def test_add_injury_view_post_without_notes():
    """Test adding injury without notes."""
    client = Client()
    user, campaign, lst, fighter, injuries = create_test_data(client)

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    injury = injuries[1]  # Old Battle Wound

    response = client.post(
        url,
        {
            "injury": injury.id,
            "fighter_state": "active",  # Permanent injuries can keep fighter active
            "notes": "",
        },
    )

    assert response.status_code == 302

    # Check injury was created without notes
    fighter_injury = fighter.injuries.first()
    assert fighter_injury.injury == injury
    assert fighter_injury.notes == ""

    # Check campaign action doesn't include notes
    action = CampaignAction.objects.last()
    assert "suffered" in action.description
    assert " - " not in action.description  # No notes separator


@pytest.mark.django_db
def test_add_injury_non_campaign_mode():
    """Test that adding injury to non-campaign fighter is rejected."""
    client = Client()
    user = User.objects.create_user(username="testuser", password="testpass")
    client.login(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    # Create normal list (not campaign mode)
    lst = List.objects.create(
        name="Normal List",
        content_house=house,
        owner=user,
        status=List.LIST_BUILDING,
    )

    fighter = ListFighter.objects.create(
        name="Normal Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    response = client.get(url)

    # Should redirect with error message
    assert response.status_code == 302
    assert response.url == reverse("core:list", args=[lst.id])


@pytest.mark.django_db
def test_remove_injury_view_get():
    """Test GET request to remove injury view."""
    client = Client()
    user, campaign, lst, fighter, injuries = create_test_data(client)

    # Add an injury first
    fighter_injury = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injuries[0],
        notes="Test injury",
        owner=user,
    )

    url = reverse(
        "core:list-fighter-injury-remove", args=[lst.id, fighter.id, fighter_injury.id]
    )
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()
    assert "Remove Injury" in content
    assert fighter.name in content
    assert injuries[0].name in content
    assert injuries[0].description in content


@pytest.mark.django_db
def test_remove_injury_view_post():
    """Test POST request to remove injury."""
    client = Client()
    user, campaign, lst, fighter, injuries = create_test_data(client)

    # Add an injury first
    fighter_injury = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injuries[0],
        owner=user,
    )

    url = reverse(
        "core:list-fighter-injury-remove", args=[lst.id, fighter.id, fighter_injury.id]
    )
    response = client.post(url)

    # Should redirect to injuries edit page
    assert response.status_code == 302
    assert response.url == reverse(
        "core:list-fighter-injuries-edit", args=[lst.id, fighter.id]
    )

    # Check injury was removed
    assert fighter.injuries.count() == 0
    assert not ListFighterInjury.objects.filter(id=fighter_injury.id).exists()

    # Check campaign action was logged
    action = CampaignAction.objects.last()
    assert action.campaign == campaign
    assert f"{fighter.name} recovered from {injuries[0].name}" in action.description
    assert action.outcome == "Fighter became available"


@pytest.mark.django_db
def test_add_injury_wrong_user():
    """Test that users can't add injuries to other users' fighters."""
    client = Client()
    user1 = User.objects.create_user(username="user1", password="pass1")
    User.objects.create_user(username="user2", password="pass2")
    client.login(username="user2", password="pass2")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user1,
        status=Campaign.IN_PROGRESS,
    )

    # Create list owned by user1
    lst = List.objects.create(
        name="User1 List",
        content_house=house,
        owner=user1,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    fighter = ListFighter.objects.create(
        name="User1 Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user1,
    )

    injury = ContentInjury.objects.create(
        name="Test Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    # Try to add injury as user2
    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    response = client.post(url, {"injury": injury.id})

    # Should get 404 (list not found for this user)
    assert response.status_code == 404


@pytest.mark.django_db
def test_remove_injury_wrong_user():
    """Test that users can't remove injuries from other users' fighters."""
    client = Client()
    user1 = User.objects.create_user(username="user1", password="pass1")
    User.objects.create_user(username="user2", password="pass2")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user1,
        status=Campaign.IN_PROGRESS,
    )

    lst = List.objects.create(
        name="User1 List",
        content_house=house,
        owner=user1,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    fighter = ListFighter.objects.create(
        name="User1 Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user1,
    )

    injury = ContentInjury.objects.create(
        name="Test Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    fighter_injury = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury,
        owner=user1,
    )

    # Login as user2
    client.login(username="user2", password="pass2")

    # Try to remove injury as user2
    url = reverse(
        "core:list-fighter-injury-remove", args=[lst.id, fighter.id, fighter_injury.id]
    )
    response = client.post(url)

    # Should get 404
    assert response.status_code == 404

    # Injury should still exist
    assert ListFighterInjury.objects.filter(id=fighter_injury.id).exists()


@pytest.mark.django_db
def test_add_injury_with_dead_state_redirects_to_kill():
    """Test that adding injury with dead state redirects to kill confirmation."""
    client = Client()
    user, campaign, lst, fighter, injuries = create_test_data(client)

    url = reverse("core:list-fighter-injury-add", args=[lst.id, fighter.id])
    injury = injuries[0]  # Eye Injury

    # Add injury with dead state
    response = client.post(
        url,
        {
            "injury": injury.id,
            "fighter_state": ListFighter.DEAD,
            "notes": "Mortal wound",
        },
    )

    # Should redirect to kill confirmation
    assert response.status_code == 302
    assert response.url == reverse("core:list-fighter-kill", args=[lst.id, fighter.id])

    # Check injury was created
    assert fighter.injuries.count() == 1
    fighter_injury = fighter.injuries.first()
    assert fighter_injury.injury == injury
    assert fighter_injury.notes == "Mortal wound"

    # Death is applied by the kill confirmation, after measuring the live rating.
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.ACTIVE

    # Check campaign action was logged
    action = CampaignAction.objects.last()
    assert action.campaign == campaign
    assert f"{fighter.name} suffered {injury.name}" in action.description
    assert "Mortal wound" in action.description
    assert action.outcome == f"Death of {fighter.name} awaits confirmation."


@pytest.mark.django_db
@pytest.mark.parametrize("initial_state", [ListFighter.ACTIVE, ListFighter.RECOVERY])
@pytest.mark.parametrize("actor_role", ["gang_owner", "campaign_owner", "shared_admin"])
def test_fatal_injury_preserves_rating_until_kill_confirmation(
    client,
    user,
    list_with_campaign,
    content_fighter,
    stash_fighter_type,
    make_list_fighter,
    make_equipment,
    make_user,
    initial_state,
    actor_role,
):
    from n23.core.models.action import ListActionType

    lst = list_with_campaign
    lst.apply_credit_delta(1000)
    lst.create_action(
        user=user,
        action_type=ListActionType.UPDATE_CREDITS,
        credits_before=0,
        credits_delta=1000,
        description="Starting credits",
    )
    fighter = hire_fighter(user, lst, content_fighter)
    stash = make_list_fighter(lst, "Stash", content_fighter=stash_fighter_type)
    buy_equipment(user, lst, fighter, make_equipment("Sword", cost=20))
    buy_equipment(user, lst, fighter, make_equipment("Autopistol", cost=5))
    ListFighter.objects.filter(pk=fighter.pk).update(injury_state=initial_state)
    fighter.refresh_from_db()
    lst.refresh_from_db()
    rating_before = lst.rating_current
    fighter_rating_before = fighter.rating_current
    credits_before = lst.credits_current
    injury = ContentInjury.objects.create(
        name="Fatal test injury", phase=ContentInjuryDefaultOutcome.DEAD
    )
    actor = user
    if actor_role != "gang_owner":
        actor = make_user(actor_role, "testpass")
        if actor_role == "campaign_owner":
            lst.campaign.owner = actor
            lst.campaign.save(update_fields=["owner"])
        else:
            lst.campaign.admins.add(actor)
    client.force_login(actor)

    response = client.post(
        reverse("core:list-fighter-injury-add", args=[lst.pk, fighter.pk]),
        {"injury": injury.pk, "fighter_state": ListFighter.DEAD},
    )
    kill_url = reverse("core:list-fighter-kill", args=[lst.pk, fighter.pk])
    assert response.status_code == 302
    assert response.url == kill_url
    fighter.refresh_from_db()
    lst.refresh_from_db()
    assert fighter.injury_state == initial_state
    assert fighter.rating_current == fighter_rating_before
    assert lst.rating_current == rating_before
    assert fighter.listfighterequipmentassignment_set.count() == 2
    assert fighter.injuries.filter(injury=injury).exists()
    injury_action = CampaignAction.objects.filter(list=lst).latest("created")
    assert injury_action.outcome == f"Death of {fighter.name} awaits confirmation."
    assert_reconciles(lst)

    # Viewing or leaving the confirmation page must preserve the live fighter.
    assert client.get(kill_url).status_code == 200
    fighter.refresh_from_db()
    assert fighter.injury_state == initial_state

    assert client.post(kill_url).status_code == 302
    fighter = ListFighter.objects.with_related_data().get(pk=fighter.pk)
    stash.refresh_from_db()
    lst.refresh_from_db()
    assert fighter.injury_state == ListFighter.DEAD
    assert fighter.cost_override == 0
    assert fighter.rating_current == fighter.cost_int() == 0
    assert lst.rating_current == rating_before - fighter_rating_before
    assert lst.credits_current == credits_before
    assert stash.rating_current == lst.stash_current == 25
    assert fighter.listfighterequipmentassignment_set.count() == 0
    assert stash.listfighterequipmentassignment_set.count() == 2
    assert lst.latest_action.rating_delta == -fighter_rating_before
    assert lst.latest_action.user == actor
    assert fighter.owner == stash.owner == user
    assert_reconciles(lst)


@pytest.mark.django_db
@pytest.mark.parametrize("method", ["get", "post"])
def test_death_confirmation_rejects_other_campaign_player(
    client, user, make_user, make_list, list_with_campaign, make_list_fighter, method
):
    lst = list_with_campaign
    fighter = make_list_fighter(lst, "Other player's fighter")
    other_player = make_user("other_player", "testpass")
    make_list(
        "Other player's gang",
        owner=other_player,
        campaign=lst.campaign,
        status=List.CAMPAIGN_MODE,
    )
    client.force_login(other_player)
    url = reverse("core:list-fighter-kill", args=[lst.pk, fighter.pk])
    assert getattr(client, method)(url).status_code == 404
    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.ACTIVE
    assert fighter.owner == user


@pytest.fixture
def campaign_owner(make_user):
    return make_user("campaign_owner", "testpass")


@pytest.fixture
def list_owner(make_user):
    return make_user("list_owner", "testpass")


@pytest.fixture
def co_content_fighter(house, make_content_fighter):
    return make_content_fighter(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )


@pytest.fixture
def co_campaign(campaign_owner):
    return Campaign.objects.create(
        name="Test Campaign",
        owner=campaign_owner,
        status=Campaign.IN_PROGRESS,
    )


@pytest.fixture
def co_list(list_owner, house, co_campaign):
    return List.objects.create(
        name="Test List",
        content_house=house,
        owner=list_owner,
        status=List.CAMPAIGN_MODE,
        campaign=co_campaign,
    )


@pytest.fixture
def co_fighter(list_owner, co_content_fighter, co_list):
    return ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=co_content_fighter,
        list=co_list,
        owner=list_owner,
    )


@pytest.fixture
def co_injuries():
    return [
        ContentInjury.objects.get_or_create(
            name="CO Test Eye Injury",
            defaults={
                "description": "Recovery, -1 Ballistic Skill",
                "phase": ContentInjuryDefaultOutcome.RECOVERY,
            },
        )[0],
    ]


@pytest.mark.django_db
def test_campaign_owner_can_view_injuries_edit(
    client, campaign_owner, co_list, co_fighter
):
    """Test that campaign owner can access the injuries edit view."""
    client.login(username="campaign_owner", password="testpass")

    url = reverse("core:list-fighter-injuries-edit", args=[co_list.id, co_fighter.id])
    response = client.get(url)

    assert response.status_code == 200


@pytest.mark.django_db
def test_campaign_owner_can_add_injury(
    client, campaign_owner, list_owner, co_list, co_fighter, co_injuries
):
    """Test that campaign owner can add an injury to a fighter."""
    client.login(username="campaign_owner", password="testpass")

    url = reverse("core:list-fighter-injury-add", args=[co_list.id, co_fighter.id])
    injury = co_injuries[0]

    response = client.post(
        url,
        {
            "injury": injury.id,
            "fighter_state": "recovery",
            "notes": "Arbitrator ruling",
        },
    )

    assert response.status_code == 302

    # Check injury was created with list owner as owner
    assert co_fighter.injuries.count() == 1
    fighter_injury = co_fighter.injuries.first()
    assert fighter_injury.injury == injury
    assert fighter_injury.owner == list_owner


@pytest.mark.django_db
def test_campaign_owner_can_remove_injury(
    client, campaign_owner, list_owner, co_list, co_fighter, co_injuries
):
    """Test that campaign owner can remove an injury from a fighter."""
    client.login(username="campaign_owner", password="testpass")

    # Add an injury first
    fighter_injury = ListFighterInjury.objects.create(
        fighter=co_fighter,
        injury=co_injuries[0],
        owner=list_owner,
    )

    url = reverse(
        "core:list-fighter-injury-remove",
        args=[co_list.id, co_fighter.id, fighter_injury.id],
    )
    response = client.post(url)

    assert response.status_code == 302
    assert co_fighter.injuries.count() == 0


@pytest.mark.django_db
def test_campaign_owner_can_edit_fighter_state(
    client, campaign_owner, co_list, co_fighter
):
    """Test that campaign owner can edit fighter state."""
    client.login(username="campaign_owner", password="testpass")

    url = reverse("core:list-fighter-state-edit", args=[co_list.id, co_fighter.id])

    # GET should work
    response = client.get(url)
    assert response.status_code == 200

    # POST should change state
    response = client.post(
        url,
        {
            "fighter_state": ListFighter.RECOVERY,
            "reason": "Arbitrator decision",
        },
    )

    assert response.status_code == 302

    co_fighter.refresh_from_db()
    assert co_fighter.injury_state == ListFighter.RECOVERY


@pytest.mark.django_db
def test_non_owner_cannot_manage_injuries(
    client, make_user, co_list, co_fighter, co_injuries
):
    """Test that unrelated users cannot manage injuries."""
    make_user("unrelated_user", "testpass")
    client.login(username="unrelated_user", password="testpass")

    # Cannot view injuries edit
    url = reverse("core:list-fighter-injuries-edit", args=[co_list.id, co_fighter.id])
    assert client.get(url).status_code == 404

    # Cannot add injury
    url = reverse("core:list-fighter-injury-add", args=[co_list.id, co_fighter.id])
    assert client.post(url, {"injury": co_injuries[0].id}).status_code == 404

    # Cannot edit state
    url = reverse("core:list-fighter-state-edit", args=[co_list.id, co_fighter.id])
    assert client.get(url).status_code == 404


@pytest.mark.django_db
def test_remove_last_injury_on_dead_fighter_clears_cost_override(
    client, user, list_with_campaign, content_fighter
):
    """Removing the last injury from a DEAD fighter routes through resurrect (#1782).

    The auto-reset to ACTIVE must clear cost_override (set to 0 on death) and
    restore the rating, rather than a bare save leaving it stuck at 0.

    Uses ``list_with_campaign`` (which has an initial LIST_CREATE action) so the
    rating propagation path is exercised, unlike the inline ``create_test_data``
    helper whose list has no ``latest_action``.
    """
    lst = list_with_campaign
    fighter = ListFighter.objects.create(
        name="Dead Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.DEAD,
        cost_override=0,
        rating_current=0,
    )
    restored_cost = fighter._base_cost_before_override()
    assert restored_cost > 0

    injury = ContentInjury.objects.create(
        name="Test Lingering Injury",
        description="Recovery",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )
    fighter_injury = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury,
        owner=user,
    )

    client.force_login(user)
    url = reverse(
        "core:list-fighter-injury-remove", args=[lst.id, fighter.id, fighter_injury.id]
    )
    response = client.post(url)
    assert response.status_code == 302

    fighter.refresh_from_db()
    assert fighter.injury_state == ListFighter.ACTIVE
    assert fighter.cost_override is None
    assert fighter.rating_current == restored_cost

    lst.refresh_from_db()
    assert lst.rating_current >= restored_cost

    # The injury-removal CampaignAction is the single log line; the resurrect
    # handler's own action is suppressed to avoid duplication.
    actions = CampaignAction.objects.filter(campaign=lst.campaign)
    assert actions.filter(outcome="Fighter became available").exists()
    assert not actions.filter(description__startswith="Resurrection:").exists()
