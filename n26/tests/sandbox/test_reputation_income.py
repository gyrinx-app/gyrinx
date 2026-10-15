"""Campaign reputation has an opening value, a minimum and a visible income contribution."""

import pytest
from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from n26.core.card import build_gang_card, build_modifier_index, carriers
from n26.core.effects import compute_gang
from n26.core.models import CounterValue, LedgerEvent
from n26.core.operations import operation
from n26.core.render import render_campaign, render_gang
from n26.core.reputation_repair import apply_one, find
from n26.library.authoring import (
    add_built_in,
    create_campaign_type,
    create_counter,
    create_hidden,
    ef_contributes_to_counter,
    modifier,
    targets_gang_alone,
)
from n26.library.core_campaign import seed_core_campaign, seed_reputation_rules
from n26.library.models import CampaignType, Counter
from n26.tests.sandbox.actions import (
    assign,
    found_campaign,
    found_gang,
    join_campaign,
    tally,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def campaign(default_pack, user):
    seed_core_campaign(apps)
    return found_campaign(
        "Dust Falls", CampaignType.objects.get(name="Territory campaign"), owner=user
    )


@pytest.fixture
def gang(gang_type, campaign, user):
    gang = found_gang("Ash Cats", gang_type, owner=user)
    join_campaign(gang, campaign)
    return gang


def counters(gang):
    card = build_gang_card(gang)
    index = build_modifier_index(carriers(card))
    with CaptureQueriesContext(connection) as queries:
        computed = compute_gang(card, index)
    assert len(queries) == 0
    return {line.name: line.value for line in computed.counters}


def reputation(gang):
    return gang.assignments.get(archived=False, counter__name="Reputation")


def test_join_opens_at_one_and_duplicate_join_preserves_progress(gang, campaign):
    assert counters(gang)["Reputation"] == 1
    assert reputation(gang).counter_value.value == 1
    tally(reputation(gang), 4)
    join_campaign(gang, campaign)
    assert counters(gang)["Reputation"] == 5


def test_adjustment_stops_at_authored_minimum(gang):
    tally(reputation(gang), -99)
    assert counters(gang)["Reputation"] == 1
    assert reputation(gang).counter_value.value == 1


def test_income_follows_current_reputation_without_awarding_credits(gang):
    before = gang.credits
    assert counters(gang)["Income"] == 10
    tally(reputation(gang), 2)
    assert counters(gang)["Income"] == 30
    gang.refresh_from_db()
    assert gang.credits == before


def test_standing_reputation_boons_raise_income_and_removal_reverses_it(gang):
    rep = Counter.objects.get(name="Reputation")
    boon = create_hidden(
        "Known locally",
        effects=[(targets_gang_alone(), ef_contributes_to_counter(rep, 2))],
    )
    held = assign(boon, gang=gang)
    assert counters(gang)["Reputation"] == 3
    assert counters(gang)["Income"] == 30
    with operation(gang, actor=gang.owner) as op:
        op.remove(held)
    assert counters(gang)["Income"] == 10


def test_campaign_and_gang_sheet_share_income_and_explanation(gang, campaign):
    tally(reputation(gang), 2)
    sheet = render_gang(gang)
    income = next(line for line in sheet.campaign.counters if line.is_income)
    campaign_gang = next(
        line for line in render_campaign(campaign).gangs if line.gang_id == str(gang.pk)
    )
    campaign_income = next(
        line for line in campaign_gang.counters if line and line.is_income
    )
    assert income.value == campaign_income.value == 30
    assert income.income_explanation == campaign_income.income_explanation
    assert any(
        part["label"] == "Reputation"
        and part["amount"] == 30
        and part["detail"] == "3 × 10¢"
        for source in income.income_explanation["sources"]
        for part in source["parts"]
    )


def test_unrelated_campaigns_keep_their_own_opening_and_income(
    gang_type, user, default_pack
):
    points = create_counter("Prestige", minimum=2)
    campaign_type = create_campaign_type("Custom campaign")
    add_built_in(campaign_type, points, amount=7)
    campaign = found_campaign("Elsewhere", campaign_type, owner=user)
    gang = found_gang("Rivals", gang_type, owner=user)
    join_campaign(gang, campaign)
    assert counters(gang) == {"Prestige": 7}


def test_scaled_contributions_resolve_dependencies_independent_of_order(gang):
    rep = Counter.objects.get(name="Reputation")
    middle = create_counter("Renown")
    result = create_counter("Rewards")
    modifier(
        "First reward",
        targets_gang_alone(),
        ef_contributes_to_counter(result, 3, per_counter=middle),
        attach_to=gang.campaign_memberships.get().campaign.campaign_type,
    )
    modifier(
        "Last renown",
        targets_gang_alone(),
        ef_contributes_to_counter(middle, 2, per_counter=rep),
        attach_to=gang.campaign_memberships.get().campaign.campaign_type,
    )
    assert counters(gang)["Rewards"] == 6
    tally(reputation(gang), 1)
    assert counters(gang)["Rewards"] == 12


def test_contribution_cycles_are_rejected(default_pack):
    first = create_counter("First")
    second = create_counter("Second")
    ef_contributes_to_counter(first, 2, per_counter=second)
    with pytest.raises(ValidationError, match="cannot form a cycle"):
        ef_contributes_to_counter(second, 2, per_counter=first)
    with pytest.raises(ValidationError, match="cannot form a cycle"):
        ef_contributes_to_counter(first, 2, per_counter=first)


def test_seed_is_idempotent_and_preserves_higher_opening(campaign):
    member = campaign.campaign_type.built_ins.members.get(counter__name="Reputation")
    member.amount = 4
    member.save()
    assert seed_reputation_rules(apps) == []
    assert seed_core_campaign(apps) == []
    member.refresh_from_db()
    assert member.amount == 4


def test_existing_zero_balance_repair_is_audited_and_idempotent(gang):
    held = reputation(gang)
    # A balance written before the minimum existed.
    CounterValue.objects.filter(assignment=held).update(value=0)
    assert find().gangs == ((gang.pk, gang.name),)
    before = gang.credits
    apply_one(gang.pk)
    held.refresh_from_db()
    assert held.counter_value.value == 1
    count = LedgerEvent.objects.filter(
        assignment=held, kind=LedgerEvent.Kind.TALLIED
    ).count()
    assert count == 1
    apply_one(gang.pk)
    assert (
        LedgerEvent.objects.filter(
            assignment=held, kind=LedgerEvent.Kind.TALLIED
        ).count()
        == count
    )
    assert find().nothing_here
    gang.refresh_from_db()
    assert gang.credits == before


def test_repair_preserves_higher_reputation_and_skips_left_memberships(gang):
    tally(reputation(gang), 8)
    apply_one(gang.pk)
    assert reputation(gang).counter_value.value == 9
    with operation(gang, actor=gang.owner) as op:
        op.leave_campaign()
    assert find().nothing_here


def test_absent_source_counter_contributes_zero_despite_its_minimum(gang):
    absent = create_counter("Absent counter", minimum=3)
    target = create_counter("Unfunded contribution")
    assign(
        create_hidden(
            "Extra income",
            effects=[
                (
                    targets_gang_alone(),
                    ef_contributes_to_counter(target, 2, per_counter=absent),
                )
            ],
        ),
        gang=gang,
    )
    assert counters(gang)["Unfunded contribution"] == 0


def test_founding_uses_authored_counter_minimum(gang_type, default_pack, user):
    counter = create_counter("Renown", minimum=3)
    add_built_in(gang_type, counter, amount=0)
    gang = found_gang("New gang", gang_type, owner=user)
    assignment = gang.assignments.get(counter=counter)
    assert assignment.counter_value.value == 3
    tally(assignment, -99)
    assert assignment.counter_value.value == 3


def test_editing_a_contribution_cannot_introduce_a_cycle(default_pack):
    from n26.library.authoring import revise

    first = create_counter("First")
    second = create_counter("Second")
    ef_contributes_to_counter(first, 2, per_counter=second)
    effect = ef_contributes_to_counter(second, 2)
    with pytest.raises(ValidationError, match="cannot form a cycle"):
        revise(effect, per_counter=first)
    effect.refresh_from_db()
    assert effect.per_counter is None


def test_seed_updates_known_help_and_preserves_authored_help(campaign):
    from n26.library.core_campaign import LIBRARY_AUTHOR_HELP

    kind = campaign.campaign_type
    kind.library_author_help = LIBRARY_AUTHOR_HELP.replace(
        "Reputation at 1", "Reputation at 0"
    )
    kind.save(update_fields=["library_author_help"])
    seed_reputation_rules(apps)
    kind.refresh_from_db()
    assert kind.library_author_help == LIBRARY_AUTHOR_HELP
    kind.library_author_help = "Our campaign instructions."
    kind.save(update_fields=["library_author_help"])
    assert seed_reputation_rules(apps) == []
    kind.refresh_from_db()
    assert kind.library_author_help == "Our campaign instructions."
