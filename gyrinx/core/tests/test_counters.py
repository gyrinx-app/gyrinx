"""Tests for counter models and views."""

import pytest
from django.core.exceptions import ValidationError
from django.urls import reverse

from gyrinx.content.models import (
    ContentCounter,
    ContentRollFlow,
    ContentRollTable,
    ContentRollTableRow,
)
from gyrinx.core.handlers.fighter import handle_counter_spend
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import (
    List,
    ListFighterCounter,
    ListFighterCounterSpend,
)


@pytest.fixture
def content_counter(content_fighter):
    """A ContentCounter restricted to the test content_fighter."""
    counter = ContentCounter.objects.create(
        name="Kill Count",
        description="Tracks kills",
        display_order=0,
    )
    counter.restricted_to_fighters.add(content_fighter)
    return counter


@pytest.fixture
def content_counter_glitches(content_fighter):
    """A second ContentCounter for glitches."""
    counter = ContentCounter.objects.create(
        name="Glitch Count",
        description="Tracks glitches",
        display_order=1,
    )
    counter.restricted_to_fighters.add(content_fighter)
    return counter


@pytest.fixture
def content_roll_table():
    """A ContentRollTable for testing."""
    return ContentRollTable.objects.create(
        name="Power Boost Table",
        description="Roll for power boost",
        dice=ContentRollTable.DICE_D6,
    )


# --- Content model tests ---


@pytest.mark.django_db
def test_content_counter_creation(content_counter, content_fighter):
    assert content_counter.name == "Kill Count"
    assert content_fighter in content_counter.restricted_to_fighters.all()
    assert str(content_counter) == "Kill Count"


@pytest.mark.django_db
def test_content_counter_ordering(content_counter, content_counter_glitches):
    counters = list(ContentCounter.objects.all())
    assert counters[0].name == "Kill Count"
    assert counters[1].name == "Glitch Count"


@pytest.mark.django_db
def test_content_roll_table_creation(content_roll_table):
    assert content_roll_table.name == "Power Boost Table"
    assert content_roll_table.dice == ContentRollTable.DICE_D6
    assert str(content_roll_table) == "Power Boost Table"


@pytest.mark.django_db
def test_content_roll_table_row_creation(content_roll_table):
    row = ContentRollTableRow.objects.create(
        table=content_roll_table,
        roll_value="1-2",
        name="Improved Reflexes",
        description="Better reflexes",
        rating_increase=10,
        sort_order=0,
    )
    assert row.table == content_roll_table
    assert str(row) == "Power Boost Table: 1-2 - Improved Reflexes"
    assert row.rating_increase == 10


@pytest.mark.django_db
def test_content_roll_table_row_unique_sort_order(content_roll_table):
    ContentRollTableRow.objects.create(
        table=content_roll_table,
        roll_value="1",
        name="Row A",
        sort_order=0,
    )
    with pytest.raises(Exception):
        ContentRollTableRow.objects.create(
            table=content_roll_table,
            roll_value="2",
            name="Row B",
            sort_order=0,
        )


@pytest.mark.django_db
def test_content_roll_flow_creation(content_counter, content_roll_table):
    flow = ContentRollFlow.objects.create(
        name="Suit Evolution",
        description="Spend kills for power",
        counter=content_counter,
        cost=4,
        roll_table=content_roll_table,
    )
    assert flow.counter == content_counter
    assert flow.cost == 4
    assert flow.roll_table == content_roll_table
    assert str(flow) == "Suit Evolution"


# --- ListFighterCounter model tests ---


@pytest.mark.django_db
def test_list_fighter_counter_creation(
    user, make_list, make_list_fighter, content_counter
):
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    counter_record = ListFighterCounter.objects.create(
        fighter=fighter,
        counter=content_counter,
        value=3,
        owner=user,
    )
    assert counter_record.value == 3
    assert counter_record.fighter == fighter
    assert counter_record.counter == content_counter
    assert str(counter_record) == "Fighter 1 - Kill Count: 3"


@pytest.mark.django_db
def test_list_fighter_counter_unique_constraint(
    user, make_list, make_list_fighter, content_counter
):
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    ListFighterCounter.objects.create(
        fighter=fighter,
        counter=content_counter,
        value=1,
        owner=user,
    )
    with pytest.raises(Exception):
        ListFighterCounter.objects.create(
            fighter=fighter,
            counter=content_counter,
            value=2,
            owner=user,
        )


@pytest.mark.django_db
def test_list_fighter_counter_default_value(
    user, make_list, make_list_fighter, content_counter
):
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    counter_record = ListFighterCounter.objects.create(
        fighter=fighter,
        counter=content_counter,
        owner=user,
    )
    assert counter_record.value == 0


# --- applicable_counters property tests ---


@pytest.mark.django_db
def test_applicable_counters_empty(make_list, make_list_fighter):
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    assert fighter.applicable_counters == []


@pytest.mark.django_db
def test_applicable_counters_with_counter(
    make_list, make_list_fighter, content_counter
):
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    counters = fighter.applicable_counters
    assert len(counters) == 1
    assert counters[0][0] == content_counter
    assert counters[0][1] == 0  # default value


@pytest.mark.django_db
def test_applicable_counters_with_value(
    user, make_list, make_list_fighter, content_counter
):
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    ListFighterCounter.objects.create(
        fighter=fighter,
        counter=content_counter,
        value=5,
        owner=user,
    )
    # Re-fetch to get prefetched data
    from gyrinx.core.models.list import ListFighter

    fighter = ListFighter.objects.with_related_data().get(id=fighter.id)
    counters = fighter.applicable_counters
    assert len(counters) == 1
    assert counters[0][1] == 5


@pytest.mark.django_db
def test_applicable_counters_ordering(
    make_list, make_list_fighter, content_counter, content_counter_glitches
):
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    counters = fighter.applicable_counters
    assert len(counters) == 2
    assert counters[0][0].name == "Kill Count"
    assert counters[1][0].name == "Glitch Count"


# --- View tests ---


@pytest.mark.django_db
def test_counter_edit_view_get(
    client, user, make_list, make_list_fighter, content_counter
):
    """GET should show the counter edit form."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    client.force_login(user)
    url = reverse(
        "core:list-fighter-counter-edit", args=[lst.id, fighter.id, content_counter.id]
    )
    response = client.get(url)
    assert response.status_code == 200
    assert b"Kill Count" in response.content


@pytest.mark.django_db
def test_counter_edit_view_post_creates_counter(
    client, user, make_list, make_list_fighter, content_counter
):
    """POST should create a ListFighterCounter on first edit."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    client.force_login(user)
    url = reverse(
        "core:list-fighter-counter-edit", args=[lst.id, fighter.id, content_counter.id]
    )
    response = client.post(url, {"value": "3"})
    assert response.status_code == 302

    counter_record = ListFighterCounter.objects.get(
        fighter=fighter, counter=content_counter
    )
    assert counter_record.value == 3


@pytest.mark.django_db
def test_counter_edit_view_post_updates_counter(
    client, user, make_list, make_list_fighter, content_counter
):
    """POST should update an existing ListFighterCounter."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=content_counter, value=2, owner=user
    )
    client.force_login(user)
    url = reverse(
        "core:list-fighter-counter-edit", args=[lst.id, fighter.id, content_counter.id]
    )
    response = client.post(url, {"value": "7"})
    assert response.status_code == 302

    counter_record = ListFighterCounter.objects.get(
        fighter=fighter, counter=content_counter
    )
    assert counter_record.value == 7


@pytest.mark.django_db
def test_counter_edit_view_no_change_skips_save(
    client, user, make_list, make_list_fighter, content_counter
):
    """POST with no value change should not create a counter record."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    client.force_login(user)
    url = reverse(
        "core:list-fighter-counter-edit", args=[lst.id, fighter.id, content_counter.id]
    )
    response = client.post(url, {"value": "0"})
    assert response.status_code == 302

    assert not ListFighterCounter.objects.filter(
        fighter=fighter, counter=content_counter
    ).exists()


@pytest.mark.django_db
def test_counter_edit_view_permission_denied(
    client, make_user, make_list, make_list_fighter, content_counter
):
    """Non-owner should not be able to edit counters."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    other_user = make_user("otheruser", "password")
    client.force_login(other_user)
    url = reverse(
        "core:list-fighter-counter-edit", args=[lst.id, fighter.id, content_counter.id]
    )
    response = client.get(url)
    assert response.status_code == 404


@pytest.mark.django_db
def test_counter_edit_view_arbitrator_can_edit(
    client, make_user, user, make_list, make_list_fighter, content_counter, campaign
):
    """Campaign arbitrator (campaign owner) should be able to edit counters."""
    lst = make_list("Test List", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(lst)
    fighter = make_list_fighter(lst, "Fighter 1")

    # Campaign is owned by user, so log in as user (who is the arbitrator)
    # and test that they can edit a list they own
    client.force_login(user)
    url = reverse(
        "core:list-fighter-counter-edit", args=[lst.id, fighter.id, content_counter.id]
    )
    response = client.get(url)
    assert response.status_code == 200


@pytest.mark.django_db
def test_counter_edit_view_404_for_inapplicable_counter(
    client, user, make_list, make_list_fighter
):
    """Accessing a counter that doesn't apply to the fighter should 404."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    # Create a counter not restricted to this fighter
    unrelated_counter = ContentCounter.objects.create(
        name="Unrelated",
        display_order=0,
    )
    client.force_login(user)
    url = reverse(
        "core:list-fighter-counter-edit",
        args=[lst.id, fighter.id, unrelated_counter.id],
    )
    response = client.get(url)
    assert response.status_code == 404


# --- Fighter card display tests ---


@pytest.mark.django_db
def test_fighter_card_shows_counters(
    client, user, make_list, make_list_fighter, content_counter
):
    """Fighter card should display applicable counters."""
    lst = make_list("Test List")
    make_list_fighter(lst, "Fighter 1")
    client.force_login(user)
    url = reverse("core:list", args=[lst.id])
    response = client.get(url)
    assert response.status_code == 200
    assert b"Kill Count" in response.content


@pytest.mark.django_db
def test_fighter_card_shows_multiple_counters(
    client,
    user,
    make_list,
    make_list_fighter,
    content_counter,
    content_counter_glitches,
):
    """Fighter card should display all applicable counters with values."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=content_counter, value=3, owner=user
    )
    ListFighterCounter.objects.create(
        fighter=fighter, counter=content_counter_glitches, value=7, owner=user
    )
    client.force_login(user)
    url = reverse("core:list", args=[lst.id])
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Kill Count" in content
    assert "Glitch Count" in content
    assert ">3<" in content
    assert ">7<" in content


@pytest.mark.django_db
def test_fighter_card_shows_counter_value(
    client, user, make_list, make_list_fighter, content_counter
):
    """Fighter card should show counter value when a record exists."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=content_counter, value=5, owner=user
    )
    client.force_login(user)
    url = reverse("core:list", args=[lst.id])
    response = client.get(url)
    assert response.status_code == 200
    # Should show value of 5
    content = response.content.decode()
    assert "Kill Count" in content
    assert ">5<" in content


@pytest.mark.django_db
def test_fighter_card_shows_edit_link_on_every_counter(
    client,
    user,
    make_list,
    make_list_fighter,
    content_counter,
    content_counter_glitches,
):
    """Each counter row should have its own Edit link."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    client.force_login(user)
    url = reverse("core:list", args=[lst.id])
    response = client.get(url)
    content = response.content.decode()
    # Both counters should have Edit links pointing to their own edit page
    kill_edit_url = reverse(
        "core:list-fighter-counter-edit",
        args=[lst.id, fighter.id, content_counter.id],
    )
    glitch_edit_url = reverse(
        "core:list-fighter-counter-edit",
        args=[lst.id, fighter.id, content_counter_glitches.id],
    )
    assert kill_edit_url in content
    assert glitch_edit_url in content


# --- Free-form counter spend tests (#1961) ---


def _counter_url(lst, fighter, counter):
    return reverse(
        "core:list-fighter-counter-edit", args=[lst.id, fighter.id, counter.id]
    )


@pytest.mark.django_db
def test_counter_spend_records_spend(
    client, user, make_list, make_list_fighter, content_counter
):
    """A free-form spend decrements the counter and records the rationale."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=content_counter, value=5, owner=user
    )
    client.force_login(user)
    response = client.post(
        _counter_url(lst, fighter, content_counter),
        {
            "intent": "spend",
            "amount": "3",
            "reason": "Bribed a guilder",
            "outcome": "Safe passage through the tunnels",
        },
    )
    assert response.status_code == 302

    counter_record = ListFighterCounter.objects.get(
        fighter=fighter, counter=content_counter
    )
    assert counter_record.value == 2

    spend = ListFighterCounterSpend.objects.get(fighter=fighter)
    assert spend.amount == 3
    assert spend.reason == "Bribed a guilder"
    assert spend.outcome == "Safe passage through the tunnels"
    assert spend.counter == content_counter
    # No campaign → no campaign action mirrored
    assert spend.campaign_action is None


@pytest.mark.django_db
def test_counter_spend_creates_campaign_action(
    client, user, make_list, make_list_fighter, content_counter, campaign
):
    """In campaign mode the spend is mirrored to a CampaignAction."""
    lst = make_list("Test List", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(lst)
    fighter = make_list_fighter(lst, "Fighter 1")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=content_counter, value=5, owner=user
    )
    client.force_login(user)
    response = client.post(
        _counter_url(lst, fighter, content_counter),
        {
            "intent": "spend",
            "amount": "2",
            "reason": "Bribed a guilder",
            "outcome": "Safe passage",
        },
    )
    assert response.status_code == 302

    spend = ListFighterCounterSpend.objects.get(fighter=fighter)
    assert spend.campaign_action is not None
    action = spend.campaign_action
    assert action.campaign == campaign
    assert action.list == lst
    # description carries the "why", outcome carries the intended outcome
    assert "spent 2 Kill Count" in action.description
    assert "Bribed a guilder" in action.description
    assert action.outcome == "Safe passage"


@pytest.mark.django_db
def test_counter_spend_rejects_overspend(
    client, user, make_list, make_list_fighter, content_counter
):
    """Spending more than the current value is rejected, leaving no record."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=content_counter, value=2, owner=user
    )
    client.force_login(user)
    response = client.post(
        _counter_url(lst, fighter, content_counter),
        {"intent": "spend", "amount": "5", "reason": "Too much"},
    )
    assert response.status_code == 200  # re-render with errors, no redirect

    counter_record = ListFighterCounter.objects.get(
        fighter=fighter, counter=content_counter
    )
    assert counter_record.value == 2
    assert not ListFighterCounterSpend.objects.filter(fighter=fighter).exists()


@pytest.mark.django_db
def test_counter_spend_rejects_zero_amount(
    client, user, make_list, make_list_fighter, content_counter
):
    """Amount must be at least 1."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=content_counter, value=5, owner=user
    )
    client.force_login(user)
    response = client.post(
        _counter_url(lst, fighter, content_counter),
        {"intent": "spend", "amount": "0", "reason": "Nothing"},
    )
    assert response.status_code == 200
    assert not ListFighterCounterSpend.objects.filter(fighter=fighter).exists()


@pytest.mark.django_db
def test_counter_spend_requires_reason(
    client, user, make_list, make_list_fighter, content_counter
):
    """A rationale is required — otherwise it's just a silent decrement."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=content_counter, value=5, owner=user
    )
    client.force_login(user)
    response = client.post(
        _counter_url(lst, fighter, content_counter),
        {"intent": "spend", "amount": "3", "reason": ""},
    )
    assert response.status_code == 200
    assert not ListFighterCounterSpend.objects.filter(fighter=fighter).exists()
    counter_record = ListFighterCounter.objects.get(
        fighter=fighter, counter=content_counter
    )
    assert counter_record.value == 5


@pytest.mark.django_db
def test_counter_spend_remove_refunds(
    client, user, make_list, make_list_fighter, content_counter
):
    """Removing a spend refunds the counter and archives the record."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=content_counter, value=5, owner=user
    )
    result = handle_counter_spend(
        user=user,
        fighter=fighter,
        counter=content_counter,
        amount=3,
        reason="Bribe",
    )
    assert (
        ListFighterCounter.objects.get(fighter=fighter, counter=content_counter).value
        == 2
    )

    client.force_login(user)
    response = client.post(
        _counter_url(lst, fighter, content_counter),
        {"remove_spend_id": str(result.spend.id)},
    )
    assert response.status_code == 302

    # Counter refunded back to 5
    assert (
        ListFighterCounter.objects.get(fighter=fighter, counter=content_counter).value
        == 5
    )
    # Spend archived (no longer active)
    result.spend.refresh_from_db()
    assert result.spend.archived
    assert not ListFighterCounterSpend.objects.filter(
        fighter=fighter, archived=False
    ).exists()


@pytest.mark.django_db
def test_counter_spend_remove_creates_refund_campaign_action(
    client, user, make_list, make_list_fighter, content_counter, campaign
):
    """Removing a spend in campaign mode records a reversing CampaignAction."""
    lst = make_list("Test List", status=List.CAMPAIGN_MODE, campaign=campaign)
    campaign.lists.add(lst)
    fighter = make_list_fighter(lst, "Fighter 1")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=content_counter, value=5, owner=user
    )
    result = handle_counter_spend(
        user=user,
        fighter=fighter,
        counter=content_counter,
        amount=3,
        reason="Bribe",
    )
    actions_before = CampaignAction.objects.filter(campaign=campaign).count()

    client.force_login(user)
    client.post(
        _counter_url(lst, fighter, content_counter),
        {"remove_spend_id": str(result.spend.id)},
    )

    actions_after = CampaignAction.objects.filter(campaign=campaign).count()
    assert actions_after == actions_before + 1
    latest = (
        CampaignAction.objects.filter(campaign=campaign).order_by("-created").first()
    )
    assert "refunded 3 Kill Count" in latest.description


@pytest.mark.django_db
def test_counter_spend_form_hidden_when_value_zero(
    client, user, make_list, make_list_fighter, content_counter
):
    """The spend form is not offered when there is nothing to spend."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    client.force_login(user)
    response = client.get(_counter_url(lst, fighter, content_counter))
    assert response.status_code == 200
    # The spend form carries a hidden intent=spend marker
    assert b'value="spend"' not in response.content


@pytest.mark.django_db
def test_counter_spend_permission_denied(
    client, make_user, user, make_list, make_list_fighter, content_counter
):
    """A non-owner cannot spend another user's counter."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=content_counter, value=5, owner=user
    )
    other_user = make_user("otheruser", "password")
    client.force_login(other_user)
    response = client.post(
        _counter_url(lst, fighter, content_counter),
        {"intent": "spend", "amount": "3", "reason": "Nope"},
    )
    assert response.status_code == 404
    assert not ListFighterCounterSpend.objects.filter(fighter=fighter).exists()


@pytest.mark.django_db
def test_counter_spend_handler_rejects_insufficient(
    user, make_list, make_list_fighter, content_counter
):
    """The handler raises when the amount exceeds the current value."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Fighter 1")
    ListFighterCounter.objects.create(
        fighter=fighter, counter=content_counter, value=2, owner=user
    )
    with pytest.raises(ValidationError):
        handle_counter_spend(
            user=user,
            fighter=fighter,
            counter=content_counter,
            amount=5,
            reason="Too much",
        )


@pytest.mark.django_db
def test_counter_spend_handler_rejects_stash(
    user, make_list, make_list_fighter, stash_fighter_type
):
    """Stash fighters cannot spend counters."""
    counter = ContentCounter.objects.create(name="Loot", display_order=0)
    counter.restricted_to_fighters.add(stash_fighter_type)
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Stash", content_fighter=stash_fighter_type)
    ListFighterCounter.objects.create(
        fighter=fighter, counter=counter, value=5, owner=user
    )
    with pytest.raises(ValidationError):
        handle_counter_spend(
            user=user,
            fighter=fighter,
            counter=counter,
            amount=1,
            reason="Nope",
        )
