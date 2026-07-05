"""
Tests for roll flows (#706 / #1427 / #1428): spend a counter, roll on a
table, gain the result as a mod + rating cost source.

Test matrix:

A. Content roll semantics
   A1. parse_roll_value: single, range, whitespace, reversed, malformed
   A2. roll_value_from_dice: D6 (single), 2D6 (sum), D66 (tens+units)
   A3. dice_count per dice config
   A4. row_for_roll: exact match, range match, no match, malformed row skipped

B. handle_roll_flow (handler)
   B1. success: result created with copied fields, counter deducted,
       CampaignAction linked with outcome, ListAction with rating delta
   B2. insufficient counter -> ValidationError, nothing changes
   B3. stash fighter -> ValidationError
   B4. idempotent on campaign_action_id double-submit
   B5. works without a campaign (no CampaignAction)
   B6. cost paths agree: cost_int, facts_from_db and rating_current all
       include the rating increase after the handler runs

C. handle_roll_result_deletion (handler)
   C1. archive + counter refund + rating reversal + negative ListAction
   C2. double deletion -> ValidationError
   C3. wrong fighter -> ValidationError

D. Mods integration
   D1. roll result stat mods apply to the statline (any list mode)
   D2. archived result mods do not apply
   D3. multiple results stack

E. Views
   E1. roll page: owner 200, arbitrator 200, stranger 404, wrong flow 404
   E2. roll POST auto (campaign): CampaignAction with dice, redirect to
       confirm with campaign_action_id
   E3. roll POST manual dice recorded
   E4. roll POST when unaffordable redirects to counter page
   E5. roll POST without campaign redirects with dice= param
   E6. confirm GET shows matched row; bad dice state redirects to roll
   E7. confirm POST applies the result and redirects to the list
   E8. confirm POST double-submit is idempotent
   E9. results edit page lists results; remove confirm + POST refunds
   E10. counter edit page shows flows (affordable vs not)

F. Card display
   F1. roll results row grouped by table name
   F2. counter warning: value > warning stat -> warn flag; edge cases

G. Clone
   G1. clone carries roll results and counter values; costs stay in sync
"""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from gyrinx.content.models import (
    ContentCounter,
    ContentModFighterStat,
    ContentRollFlow,
    ContentRollTable,
    ContentRollTableRow,
)
from gyrinx.content.models.roll_table import parse_roll_value
from gyrinx.core.handlers.fighter import (
    handle_roll_flow,
    handle_roll_result_deletion,
)
from gyrinx.core.models.action import ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import (
    ListFighter,
    ListFighterCounter,
    ListFighterRollResult,
)

# --- Fixtures ---


@pytest.fixture
def kill_count(content_fighter):
    counter = ContentCounter.objects.create(
        name="Kill Count",
        description="Tracks kills",
        display_order=0,
    )
    counter.restricted_to_fighters.add(content_fighter)
    return counter


@pytest.fixture
def power_boost_table():
    table = ContentRollTable.objects.create(
        name="Power Boost Table",
        dice=ContentRollTable.DICE_D6,
    )
    mod = ContentModFighterStat.objects.create(
        stat="strength",
        mode="improve",
        value="1",
    )
    minor = ContentRollTableRow.objects.create(
        table=table,
        roll_value="1-3",
        name="Minor Boost",
        rating_increase=10,
        sort_order=1,
    )
    minor.modifiers.add(mod)
    ContentRollTableRow.objects.create(
        table=table,
        roll_value="4-6",
        name="Major Boost",
        rating_increase=25,
        sort_order=2,
    )
    return table


@pytest.fixture
def suit_evolution(kill_count, power_boost_table):
    return ContentRollFlow.objects.create(
        name="Suit Evolution",
        counter=kill_count,
        cost=4,
        roll_table=power_boost_table,
    )


@pytest.fixture
def fighter(list_with_campaign, make_list_fighter):
    return make_list_fighter(list_with_campaign, "Spyrer Test")


@pytest.fixture
def fighter_with_kills(fighter, kill_count, user):
    ListFighterCounter.objects.create(
        fighter=fighter,
        counter=kill_count,
        value=5,
        owner=user,
    )
    return fighter


def minor_row(power_boost_table):
    return power_boost_table.rows.get(name="Minor Boost")


def major_row(power_boost_table):
    return power_boost_table.rows.get(name="Major Boost")


# --- A. Content roll semantics ---


def test_parse_roll_value():
    assert parse_roll_value("6") == (6, 6)
    assert parse_roll_value("2-3") == (2, 3)
    assert parse_roll_value(" 4 - 5 ") == (4, 5)
    assert parse_roll_value("6-4") == (4, 6)
    assert parse_roll_value("") is None
    assert parse_roll_value("abc") is None
    assert parse_roll_value("1-2-3") is None


@pytest.mark.django_db
def test_roll_value_from_dice():
    d6 = ContentRollTable.objects.create(name="T1", dice=ContentRollTable.DICE_D6)
    two_d6 = ContentRollTable.objects.create(name="T2", dice=ContentRollTable.DICE_2D6)
    d66 = ContentRollTable.objects.create(name="T3", dice=ContentRollTable.DICE_D66)

    assert d6.roll_value_from_dice([4]) == 4
    assert two_d6.roll_value_from_dice([4, 5]) == 9
    # D66 reads tens and units, not a sum
    assert d66.roll_value_from_dice([4, 5]) == 45

    assert d6.dice_count == 1
    assert two_d6.dice_count == 2
    assert d66.dice_count == 2


@pytest.mark.django_db
def test_row_for_roll(power_boost_table):
    assert power_boost_table.row_for_roll(1).name == "Minor Boost"
    assert power_boost_table.row_for_roll(3).name == "Minor Boost"
    assert power_boost_table.row_for_roll(6).name == "Major Boost"
    assert power_boost_table.row_for_roll(7) is None


@pytest.mark.django_db
def test_row_for_roll_skips_malformed_rows(power_boost_table):
    ContentRollTableRow.objects.create(
        table=power_boost_table,
        roll_value="not-a-number",
        name="Broken Row",
        sort_order=3,
    )
    # Still matches the valid rows and never raises
    assert power_boost_table.row_for_roll(2).name == "Minor Boost"


# --- B. handle_roll_flow ---


@pytest.mark.django_db
def test_handle_roll_flow_success(
    user, fighter_with_kills, suit_evolution, power_boost_table, settings
):
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    lst = fighter_with_kills.list
    rating_before = lst.rating_current

    result = handle_roll_flow(
        user=user,
        fighter=fighter_with_kills,
        flow=suit_evolution,
        row=major_row(power_boost_table),
        rolled_value=5,
    )

    assert result is not None
    assert result.rating_increase == 25
    assert result.counter_cost == 4

    roll_result = result.roll_result
    assert roll_result.row == major_row(power_boost_table)
    assert roll_result.flow == suit_evolution
    assert roll_result.counter == suit_evolution.counter
    assert roll_result.counter_cost == 4
    assert roll_result.rating_increase == 25

    # Counter deducted
    counter = fighter_with_kills.counters.get(counter=suit_evolution.counter)
    assert counter.value == 1

    # CampaignAction created (list has a campaign) with outcome set
    assert result.campaign_action is not None
    assert "Major Boost" in result.campaign_action.outcome

    # ListAction records the rating delta
    assert result.update_action is not None
    assert result.update_action.action_type == ListActionType.UPDATE_FIGHTER
    assert result.update_action.rating_delta == 25
    assert result.update_action.stash_delta == 0
    assert result.update_action.credits_delta == 0
    assert result.update_action.rating_before == rating_before


@pytest.mark.django_db
def test_handle_roll_flow_insufficient_counter(
    user, fighter, kill_count, suit_evolution, power_boost_table
):
    # No ListFighterCounter row at all -> value 0
    with pytest.raises(ValidationError, match="insufficient"):
        handle_roll_flow(
            user=user,
            fighter=fighter,
            flow=suit_evolution,
            row=major_row(power_boost_table),
            rolled_value=5,
        )
    assert ListFighterRollResult.objects.count() == 0


@pytest.mark.django_db
def test_handle_roll_flow_stash_fighter(
    user,
    list_with_campaign,
    stash_fighter_type,
    kill_count,
    suit_evolution,
    power_boost_table,
):
    kill_count.restricted_to_fighters.add(stash_fighter_type)
    stash = ListFighter.objects.create(
        list=list_with_campaign,
        owner=user,
        content_fighter=stash_fighter_type,
        name="Stash",
    )
    with pytest.raises(ValidationError, match="[Ss]tash"):
        handle_roll_flow(
            user=user,
            fighter=stash,
            flow=suit_evolution,
            row=major_row(power_boost_table),
            rolled_value=5,
        )


@pytest.mark.django_db
def test_handle_roll_flow_idempotent(
    user, fighter_with_kills, suit_evolution, power_boost_table
):
    lst = fighter_with_kills.list
    campaign_action = CampaignAction.objects.create(
        user=user,
        owner=user,
        campaign=lst.campaign,
        list=lst,
        description="Rolling",
        dice_count=1,
        dice_results=[5],
        dice_total=5,
    )

    first = handle_roll_flow(
        user=user,
        fighter=fighter_with_kills,
        flow=suit_evolution,
        row=major_row(power_boost_table),
        rolled_value=5,
        campaign_action_id=campaign_action.id,
    )
    assert first is not None

    second = handle_roll_flow(
        user=user,
        fighter=fighter_with_kills,
        flow=suit_evolution,
        row=major_row(power_boost_table),
        rolled_value=5,
        campaign_action_id=campaign_action.id,
    )
    assert second is None

    # Only one deduction happened
    counter = fighter_with_kills.counters.get(counter=suit_evolution.counter)
    assert counter.value == 1
    assert ListFighterRollResult.objects.count() == 1


@pytest.mark.django_db
def test_handle_roll_flow_without_campaign(
    user, make_list, make_list_fighter, kill_count, suit_evolution, power_boost_table
):
    lst = make_list("No Campaign List")
    fighter = make_list_fighter(lst, "Fighter")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=kill_count, value=4, owner=user
    )

    result = handle_roll_flow(
        user=user,
        fighter=fighter,
        flow=suit_evolution,
        row=minor_row(power_boost_table),
        rolled_value=2,
    )
    assert result is not None
    assert result.campaign_action is None
    assert fighter.counters.get(counter=kill_count).value == 0


@pytest.mark.django_db
def test_handle_roll_flow_cost_paths_agree(
    user, fighter_with_kills, suit_evolution, power_boost_table, settings
):
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    base_cost = fighter_with_kills.cost_int()
    # Seed the cached rating (in production the hire handler does this)
    fighter_with_kills.facts_from_db(update=True)

    handle_roll_flow(
        user=user,
        fighter=fighter_with_kills,
        flow=suit_evolution,
        row=major_row(power_boost_table),
        rolled_value=5,
    )

    fighter = ListFighter.objects.with_related_data().get(id=fighter_with_kills.id)

    # Pull path: live computation includes the increase
    assert fighter.cost_int() == base_cost + 25
    # Push path: propagation already updated the cache
    assert fighter.rating_current == base_cost + 25
    assert fighter.dirty is False
    # Recompute agrees with the cache (reconcile would find no drift)
    assert fighter.facts_from_db(update=False).rating == fighter.rating_current


# --- C. handle_roll_result_deletion ---


@pytest.mark.django_db
def test_handle_roll_result_deletion(
    user, fighter_with_kills, suit_evolution, power_boost_table, settings
):
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True
    # Seed the cached rating (in production the hire handler does this)
    fighter_with_kills.facts_from_db(update=True)
    result = handle_roll_flow(
        user=user,
        fighter=fighter_with_kills,
        flow=suit_evolution,
        row=major_row(power_boost_table),
        rolled_value=5,
    )
    base_cost = fighter_with_kills.cost_int()

    deletion = handle_roll_result_deletion(
        user=user,
        fighter=fighter_with_kills,
        roll_result=result.roll_result,
    )

    assert deletion.rating_decrease == 25
    assert deletion.counter_refund == 4

    result.roll_result.refresh_from_db()
    assert result.roll_result.archived is True

    # Counter refunded back to 5
    counter = fighter_with_kills.counters.get(counter=suit_evolution.counter)
    assert counter.value == 5

    # Negative ListAction
    assert deletion.update_action.rating_delta == -25

    # Cost paths reversed
    fighter = ListFighter.objects.with_related_data().get(id=fighter_with_kills.id)
    assert fighter.cost_int() == base_cost - 25
    assert fighter.rating_current == base_cost - 25

    # Campaign log records the removal
    assert deletion.campaign_action is not None
    assert "refunding 4" in deletion.campaign_action.description


@pytest.mark.django_db
def test_handle_roll_result_deletion_twice(
    user, fighter_with_kills, suit_evolution, power_boost_table
):
    result = handle_roll_flow(
        user=user,
        fighter=fighter_with_kills,
        flow=suit_evolution,
        row=major_row(power_boost_table),
        rolled_value=5,
    )
    handle_roll_result_deletion(
        user=user, fighter=fighter_with_kills, roll_result=result.roll_result
    )
    result.roll_result.refresh_from_db()
    with pytest.raises(ValidationError, match="already"):
        handle_roll_result_deletion(
            user=user, fighter=fighter_with_kills, roll_result=result.roll_result
        )


@pytest.mark.django_db
def test_handle_roll_result_deletion_wrong_fighter(
    user, fighter_with_kills, make_list_fighter, suit_evolution, power_boost_table
):
    result = handle_roll_flow(
        user=user,
        fighter=fighter_with_kills,
        flow=suit_evolution,
        row=major_row(power_boost_table),
        rolled_value=5,
    )
    other = make_list_fighter(fighter_with_kills.list, "Other Fighter")
    with pytest.raises(ValidationError, match="does not belong"):
        handle_roll_result_deletion(
            user=user, fighter=other, roll_result=result.roll_result
        )


# --- D. Mods integration ---


def _statline_value(fighter, stat_name):
    for stat in fighter.statline:
        if stat.name == stat_name:
            return stat.value
    raise AssertionError(f"stat {stat_name} not found")


@pytest.mark.django_db
def test_roll_result_mods_apply_to_statline(
    user, fighter_with_kills, suit_evolution, power_boost_table
):
    # Base S is 4 (conftest content_fighter)
    assert _statline_value(fighter_with_kills, "S") == "4"

    handle_roll_flow(
        user=user,
        fighter=fighter_with_kills,
        flow=suit_evolution,
        row=minor_row(power_boost_table),  # has +1 strength mod
        rolled_value=2,
    )

    fighter = ListFighter.objects.with_related_data().get(id=fighter_with_kills.id)
    assert _statline_value(fighter, "S") == "5"


@pytest.mark.django_db
def test_roll_result_mods_apply_outside_campaign_mode(
    user, make_list, make_list_fighter, kill_count, suit_evolution, power_boost_table
):
    # Unlike injuries, roll results are permanent improvements: their mods
    # apply in list-building mode too (advancement pattern).
    lst = make_list("List Building")
    fighter = make_list_fighter(lst, "Fighter")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=kill_count, value=4, owner=user
    )
    handle_roll_flow(
        user=user,
        fighter=fighter,
        flow=suit_evolution,
        row=minor_row(power_boost_table),
        rolled_value=2,
    )
    fighter = ListFighter.objects.with_related_data().get(id=fighter.id)
    assert _statline_value(fighter, "S") == "5"


@pytest.mark.django_db
def test_archived_roll_result_mods_do_not_apply(
    user, fighter_with_kills, suit_evolution, power_boost_table
):
    result = handle_roll_flow(
        user=user,
        fighter=fighter_with_kills,
        flow=suit_evolution,
        row=minor_row(power_boost_table),
        rolled_value=2,
    )
    handle_roll_result_deletion(
        user=user, fighter=fighter_with_kills, roll_result=result.roll_result
    )
    fighter = ListFighter.objects.with_related_data().get(id=fighter_with_kills.id)
    assert _statline_value(fighter, "S") == "4"


@pytest.mark.django_db
def test_roll_result_mods_stack(
    user, fighter_with_kills, kill_count, suit_evolution, power_boost_table
):
    # Two minor boosts (+1 S each)
    fighter_counter = fighter_with_kills.counters.get(counter=kill_count)
    fighter_counter.value = 8
    fighter_counter.save()

    for _ in range(2):
        handle_roll_flow(
            user=user,
            fighter=fighter_with_kills,
            flow=suit_evolution,
            row=minor_row(power_boost_table),
            rolled_value=2,
        )

    fighter = ListFighter.objects.with_related_data().get(id=fighter_with_kills.id)
    assert _statline_value(fighter, "S") == "6"
    assert fighter._roll_result_cost_int == 20


# --- E. Views ---


def roll_url(lst, fighter, flow):
    return reverse("core:list-fighter-roll-flow", args=(lst.id, fighter.id, flow.id))


def confirm_url(lst, fighter, flow):
    return reverse(
        "core:list-fighter-roll-flow-confirm", args=(lst.id, fighter.id, flow.id)
    )


@pytest.mark.django_db
def test_roll_view_permissions(
    client, user, make_user, fighter_with_kills, suit_evolution
):
    lst = fighter_with_kills.list

    client.force_login(user)
    response = client.get(roll_url(lst, fighter_with_kills, suit_evolution))
    assert response.status_code == 200

    stranger = make_user("stranger", "password")
    client.force_login(stranger)
    response = client.get(roll_url(lst, fighter_with_kills, suit_evolution))
    assert response.status_code == 404


@pytest.mark.django_db
def test_roll_view_arbitrator_allowed(
    client, make_user, campaign, fighter_with_kills, suit_evolution
):
    # The campaign fixture is owned by `user`; make the list owner different
    lst = fighter_with_kills.list
    other = make_user("gang-owner", "password")
    lst.owner = other
    lst.save()
    fighter_with_kills.owner = other
    fighter_with_kills.save()

    client.force_login(campaign.owner)
    response = client.get(roll_url(lst, fighter_with_kills, suit_evolution))
    assert response.status_code == 200


@pytest.mark.django_db
def test_roll_view_404_for_inapplicable_flow(
    client, user, make_list, make_list_fighter, kill_count, suit_evolution
):
    # A fighter whose content_fighter is not in the counter's restriction set
    lst = make_list("Other List")
    fighter = make_list_fighter(lst, "Fighter")
    kill_count.restricted_to_fighters.clear()

    client.force_login(user)
    response = client.get(roll_url(lst, fighter, suit_evolution))
    assert response.status_code == 404


@pytest.mark.django_db
def test_roll_post_auto_creates_campaign_action(
    client, user, fighter_with_kills, suit_evolution
):
    lst = fighter_with_kills.list
    client.force_login(user)
    response = client.post(
        roll_url(lst, fighter_with_kills, suit_evolution),
        {"roll_action": "roll_auto"},
    )
    assert response.status_code == 302

    action = CampaignAction.objects.latest("created")
    assert action.dice_count == 1
    assert len(action.dice_results) == 1
    assert f"campaign_action_id={action.id}" in response.url


@pytest.mark.django_db
def test_roll_post_manual_dice(client, user, fighter_with_kills, suit_evolution):
    lst = fighter_with_kills.list
    client.force_login(user)
    response = client.post(
        roll_url(lst, fighter_with_kills, suit_evolution),
        {"roll_action": "roll_manual", "d6_1": "3"},
    )
    assert response.status_code == 302
    action = CampaignAction.objects.latest("created")
    assert action.dice_results == [3]


@pytest.mark.django_db
def test_roll_post_unaffordable(client, user, fighter, kill_count, suit_evolution):
    # fighter has no counter value at all
    lst = fighter.list
    client.force_login(user)
    response = client.post(
        roll_url(lst, fighter, suit_evolution),
        {"roll_action": "roll_auto"},
    )
    assert response.status_code == 302
    assert response.url == reverse(
        "core:list-fighter-counter-edit", args=(lst.id, fighter.id, kill_count.id)
    )
    assert CampaignAction.objects.count() == 0


@pytest.mark.django_db
def test_roll_post_without_campaign_uses_dice_param(
    client, user, make_list, make_list_fighter, kill_count, suit_evolution
):
    lst = make_list("No Campaign")
    fighter = make_list_fighter(lst, "Fighter")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=kill_count, value=4, owner=user
    )
    client.force_login(user)
    response = client.post(
        roll_url(lst, fighter, suit_evolution),
        {"roll_action": "roll_manual", "d6_1": "2"},
    )
    assert response.status_code == 302
    assert "dice=2" in response.url
    assert CampaignAction.objects.count() == 0


@pytest.mark.django_db
def test_confirm_get_shows_row(client, user, fighter_with_kills, suit_evolution):
    lst = fighter_with_kills.list
    client.force_login(user)
    response = client.get(
        confirm_url(lst, fighter_with_kills, suit_evolution) + "?dice=5"
    )
    assert response.status_code == 200
    assert b"Major Boost" in response.content


@pytest.mark.django_db
def test_confirm_get_bad_state_redirects(
    client, user, fighter_with_kills, suit_evolution
):
    lst = fighter_with_kills.list
    client.force_login(user)
    for query in ("", "?dice=abc", "?dice=9", "?campaign_action_id=not-a-uuid"):
        response = client.get(
            confirm_url(lst, fighter_with_kills, suit_evolution) + query
        )
        assert response.status_code == 302
        assert response.url == roll_url(lst, fighter_with_kills, suit_evolution)


@pytest.mark.django_db
def test_confirm_post_applies_result(
    client, user, fighter_with_kills, kill_count, suit_evolution
):
    lst = fighter_with_kills.list
    client.force_login(user)
    response = client.post(
        confirm_url(lst, fighter_with_kills, suit_evolution) + "?dice=5",
        {},
    )
    assert response.status_code == 302
    assert response.url.startswith(reverse("core:list", args=(lst.id,)))

    roll_result = ListFighterRollResult.objects.get()
    assert roll_result.row.name == "Major Boost"
    assert fighter_with_kills.counters.get(counter=kill_count).value == 1


@pytest.mark.django_db
def test_confirm_post_double_submit_idempotent(
    client, user, fighter_with_kills, kill_count, suit_evolution
):
    lst = fighter_with_kills.list
    client.force_login(user)
    # Roll first so a campaign action carries the state
    response = client.post(
        roll_url(lst, fighter_with_kills, suit_evolution),
        {"roll_action": "roll_manual", "d6_1": "5"},
    )
    target = response.url

    client.post(target, {})
    client.post(target, {})

    assert ListFighterRollResult.objects.count() == 1
    assert fighter_with_kills.counters.get(counter=kill_count).value == 1


@pytest.mark.django_db
def test_results_edit_and_remove_views(
    client, user, fighter_with_kills, kill_count, suit_evolution, power_boost_table
):
    lst = fighter_with_kills.list
    result = handle_roll_flow(
        user=user,
        fighter=fighter_with_kills,
        flow=suit_evolution,
        row=major_row(power_boost_table),
        rolled_value=5,
    )

    client.force_login(user)
    response = client.get(
        reverse(
            "core:list-fighter-roll-results-edit", args=(lst.id, fighter_with_kills.id)
        )
    )
    assert response.status_code == 200
    assert b"Major Boost" in response.content

    remove_url = reverse(
        "core:list-fighter-roll-result-remove",
        args=(lst.id, fighter_with_kills.id, result.roll_result.id),
    )
    response = client.get(remove_url)
    assert response.status_code == 200

    response = client.post(remove_url, {})
    assert response.status_code == 302

    result.roll_result.refresh_from_db()
    assert result.roll_result.archived is True
    assert fighter_with_kills.counters.get(counter=kill_count).value == 5


@pytest.mark.django_db
def test_counter_edit_page_shows_flows(
    client, user, fighter_with_kills, kill_count, suit_evolution
):
    lst = fighter_with_kills.list
    client.force_login(user)
    url = reverse(
        "core:list-fighter-counter-edit",
        args=(lst.id, fighter_with_kills.id, kill_count.id),
    )
    response = client.get(url)
    assert response.status_code == 200
    assert b"Suit Evolution" in response.content
    assert b"Start" in response.content

    # Drop below the cost: the button disappears, the requirement shows
    counter = fighter_with_kills.counters.get(counter=kill_count)
    counter.value = 2
    counter.save()
    response = client.get(url)
    assert b"Requires 4 Kill Count" in response.content


# --- F. Card display ---


@pytest.mark.django_db
def test_card_shows_roll_results_grouped_by_table(
    client, user, fighter_with_kills, suit_evolution, power_boost_table
):
    lst = fighter_with_kills.list
    handle_roll_flow(
        user=user,
        fighter=fighter_with_kills,
        flow=suit_evolution,
        row=major_row(power_boost_table),
        rolled_value=5,
    )
    client.force_login(user)
    response = client.get(reverse("core:list", args=(lst.id,)))
    assert response.status_code == 200
    assert b"Power Boost Table" in response.content
    assert b"Major Boost" in response.content


@pytest.mark.django_db
def test_counter_warning_stat(
    user, make_list, make_list_fighter, content_fighter, kill_count
):
    glitches = ContentCounter.objects.create(
        name="Glitch Count",
        display_order=1,
        warning_stat="T",  # conftest fighter has toughness "3"
    )
    glitches.restricted_to_fighters.add(content_fighter)

    lst = make_list("Warn List")
    fighter = make_list_fighter(lst, "Fighter")

    def entry_for(f, name):
        return next(e for e in f.applicable_counters if e.counter.name == name)

    # Value 0: no warning
    assert entry_for(fighter, "Glitch Count").warn is False

    # Value above toughness: warn
    ListFighterCounter.objects.create(
        fighter=fighter, counter=glitches, value=4, owner=user
    )
    fighter = ListFighter.objects.with_related_data().get(id=fighter.id)
    assert entry_for(fighter, "Glitch Count").warn is True

    # Value equal to toughness: no warning ("higher than", not "at")
    fighter_counter = fighter.counters.get(counter=glitches)
    fighter_counter.value = 3
    fighter_counter.save()
    fighter = ListFighter.objects.with_related_data().get(id=fighter.id)
    assert entry_for(fighter, "Glitch Count").warn is False

    # Counter without warning_stat never warns
    assert entry_for(fighter, "Kill Count").warn is False


@pytest.mark.django_db
def test_counter_warning_stat_unknown_stat(
    user, make_list, make_list_fighter, content_fighter
):
    counter = ContentCounter.objects.create(
        name="Weird Count",
        warning_stat="ZZ",
    )
    counter.restricted_to_fighters.add(content_fighter)
    lst = make_list("Warn List 2")
    fighter = make_list_fighter(lst, "Fighter")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=counter, value=99, owner=user
    )
    fighter = ListFighter.objects.with_related_data().get(id=fighter.id)
    assert fighter.applicable_counters[0].warn is False


# --- G. Clone ---


@pytest.mark.django_db
def test_clone_carries_roll_results_and_counters(
    user, fighter_with_kills, kill_count, suit_evolution, power_boost_table
):
    handle_roll_flow(
        user=user,
        fighter=fighter_with_kills,
        flow=suit_evolution,
        row=major_row(power_boost_table),
        rolled_value=5,
    )

    clone = fighter_with_kills.clone(name="Clone")

    # Roll results carried, unlinked from the campaign action
    cloned_results = list(clone.roll_results.all())
    assert len(cloned_results) == 1
    assert cloned_results[0].row.name == "Major Boost"
    assert cloned_results[0].rating_increase == 25
    assert cloned_results[0].campaign_action is None

    # Counter value carried (5 - 4 spent = 1)
    assert clone.counters.get(counter=kill_count).value == 1

    # Costs agree between original and clone
    assert clone.cost_int() == fighter_with_kills.cost_int()
