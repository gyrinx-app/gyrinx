"""Selectable base Income belongs to one asset occurrence and its answer.

The catalogue amount stays on an ordinary modifier. A holding's override
substitutes its amount only while that modifier runs through its recorded
Income option; other standing contributions keep their ordinary arithmetic.
"""

from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from n26.core import select
from n26.core.campaigns import campaign_operation
from n26.core.card import build_gang_card, build_modifier_index, carriers
from n26.core.effects import (
    asset_origins,
    compute_gang,
    counter_contributions_by_asset_assignment,
    counter_contributions_by_holding,
)
from n26.core.income import asset_assignment_income_sources, holding_income_sources
from n26.core.models import Assignment, CampaignAsset
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_gang
from n26.library.authoring import (
    add_asset_type,
    add_built_in,
    attach_modifiers_to,
    create_asset,
    create_campaign_type,
    create_counter,
    create_hidden,
    create_pickable,
    create_picklist,
    create_rule,
    create_slot,
    create_slot_type,
    detach_modifier,
    ef_adds,
    ef_contributes_to_counter,
    ef_removes,
    has_gang_pickable,
    modifier,
    set_base_income_modifier,
    set_income,
    targets_gang,
    targets_gang_alone,
)
from n26.library.income import income_modifiers, income_of
from n26.library.models import AssetType
from n26.tests.fixtures import library_setup
from n26.tests.sandbox.actions import (
    assign,
    assign_asset,
    choose,
    found_campaign,
    found_gang,
    join_campaign,
    remove,
    transfer_asset,
    unassign_asset,
)
from n26.tests.sandbox.test_holding_choices import choose_for

pytestmark = pytest.mark.django_db


def declare_choice(asset, income, reputation):
    """Move the original catalogue modifier onto an ordinary Income option."""
    (base,) = income_modifiers(asset)
    kind = create_slot_type(f"{asset.name} boon")
    income_pick = create_pickable(f"{asset.name} income", kind)
    alternative = create_pickable(
        f"{asset.name} reputation",
        kind,
        effects=[(targets_gang_alone(), ef_contributes_to_counter(reputation, 2))],
    )
    picks = create_picklist(
        f"{asset.name} choices", kind, members=[income_pick, alternative]
    )
    slot = create_slot(f"{asset.name} benefit", kind, picks, assigned_to="gang")
    modifier(
        f"{asset.name} offers a choice",
        targets_gang_alone(),
        ef_adds(slot),
        attach_to=asset,
    )
    detach_modifier(asset, base)
    attach_modifiers_to(income_pick, [base])
    set_base_income_modifier(asset, base)
    return {
        "asset": asset,
        "base": base,
        "income_pick": income_pick,
        "alternative": alternative,
        "slot": slot,
        "income": income,
    }


@pytest.fixture
@library_setup
def content(default_pack, gang_type):
    income = create_counter("Income")
    reputation = create_counter("Reputation")
    campaign_type = create_campaign_type("Selectable income campaign")
    add_built_in(campaign_type, income)
    add_built_in(campaign_type, reputation)
    territory = add_asset_type(campaign_type, "Territory", "pooled")
    benefit = declare_choice(
        create_asset("Workshop", territory, income=15), income, reputation
    )
    house_kind = create_slot_type("House")
    house = create_pickable("Chosen House", house_kind)
    house_list = create_picklist("Houses", house_kind, members=[house])
    house_slot = create_slot("House choice", house_kind, house_list, assigned_to="gang")
    add_built_in(gang_type, house_slot)
    benefit.update(
        campaign_type=campaign_type,
        territory=territory,
        reputation=reputation,
        house=house,
        house_slot=house_slot,
    )
    return benefit


@pytest.fixture
def campaign(content):
    return found_campaign(
        "Dust Falls",
        content["campaign_type"],
        owner=User.objects.create_user("arbitrator"),
        budget=1000,
    )


@pytest.fixture
def gang(gang_type, owner, campaign):
    gang = found_gang("Workshop keepers", gang_type, owner=owner)
    join_campaign(gang, campaign)
    return gang


@pytest.fixture
def rival(gang_type, campaign):
    gang = found_gang(
        "Other keepers", gang_type, owner=User.objects.create_user("rival")
    )
    join_campaign(gang, campaign)
    return gang


def loaded(gang):
    card = build_gang_card(gang)
    return card, build_modifier_index(carriers(card))


def computed(gang):
    card, index = loaded(gang)
    return compute_gang(card, index)


def total(done, counter):
    return sum(
        reading.value for reading in done.counters if reading.thing.pk == counter.pk
    )


def holding(campaign, gang, asset, override=None):
    name = f"Copy {uuid4()}"
    with campaign_operation(campaign, actor=campaign.owner) as act:
        act.add_assets([asset], name=name, income=override, request_key=uuid4())
    return assign_asset(CampaignAsset.objects.get(campaign=campaign, name=name), gang)


def chosen(holding):
    return Assignment.objects.get(
        chosen_for_holding=holding,
        chosen_for_holding_revision=holding.ownership_revision,
        archived=False,
    )


class TestChoosingTheBaseIncome:
    """A saved override is eligible only for this copy's selected base effect."""

    def test_removing_the_declared_slot_hides_its_question_but_preserves_recorded_income(
        self,
        campaign,
        gang,
        content,
    ):
        held = holding(campaign, gang, content["asset"])
        recorded_pick = chosen(held)
        before = computed(gang)
        assert total(before, content["income"]) == 15
        assert (
            len(
                [
                    choice
                    for choice in before.choices
                    if choice.slot.pk == content["slot"].pk
                ]
            )
            == 1
        )
        removal = modifier(
            "Cancels the declared benefit",
            targets_gang_alone(),
            ef_removes(content["slot"]),
        )
        # Invalid library content deliberately bypasses the authoring guard
        # to pin what a removal actually takes away from a recorded answer.
        content["asset"].modifiers.add(removal)
        done = computed(gang)
        assert total(done, content["income"]) == 15
        assert (
            len(
                [
                    choice
                    for choice in done.choices
                    if choice.slot.pk == content["slot"].pk
                ]
            )
            == 0
        )
        pick_node = next(
            node for node in done.card.all_nodes() if node.key == recorded_pick.pk
        )
        assert not pick_node.suppressed
        recorded_pick.refresh_from_db()
        assert not recorded_pick.archived
        assert recorded_pick.pickable_id == content["income_pick"].pk
        assert_reconciled(gang)

    @pytest.mark.parametrize(
        "amount,override,answer,expected",
        [
            (15, None, "income", 15),
            (15, 42, "income", 42),
            (15, 42, "alternative", 0),
            (15, 42, "unanswered", 0),
            (15, 0, "income", 0),
            (0, 42, "income", 42),
        ],
    )
    def test_income_alternative_and_unanswered_choices_have_distinct_override_eligibility(
        self, campaign, gang, content, amount, override, answer, expected
    ):
        set_income(content["asset"], amount)
        held = holding(campaign, gang, content["asset"], override)
        if answer == "alternative":
            choose_for(held, content["alternative"], content["slot"])
        elif answer == "unanswered":
            remove(chosen(held))
        done = computed(gang)
        assert total(done, content["income"]) == expected
        grouped = counter_contributions_by_holding(done)
        records = grouped.get((held.pk, held.ownership_revision), [])
        bases = [
            record for record in records if record.modifier.pk == content["base"].pk
        ]
        assert [record.amount for record in bases] == (
            [expected] if answer == "income" else []
        )
        assert [getattr(record.applied_override, "pk", None) for record in bases] == (
            [held.income_override_id] if answer == "income" else []
        )
        content["base"].contributes_to_counter.refresh_from_db()
        assert content["base"].contributes_to_counter.amount == amount
        assert income_of(content["asset"]) == amount
        assert_reconciled(gang)

    def test_identical_copies_substitute_separately_without_mutating_a_shared_index(
        self, campaign, gang, content
    ):
        first = holding(campaign, gang, content["asset"], 42)
        second = holding(campaign, gang, content["asset"], 0)
        card, index = loaded(gang)
        done = compute_gang(card, index)
        grouped = counter_contributions_by_holding(done)
        assert [
            sum(record.amount for record in grouped[(copy.pk, copy.ownership_revision)])
            for copy in [first, second]
        ] == [42, 0]
        assert total(done, content["income"]) == 42
        assert total(compute_gang(card, index), content["income"]) == 42
        (base, _) = next(
            (row, spec)
            for row, spec in index.for_thing(content["income_pick"])
            if row.pk == content["base"].pk
        )
        assert base.contributes_to_counter.amount == 15
        choose_for(first, content["alternative"], content["slot"])
        assert total(computed(gang), content["income"]) == 0
        assert_reconciled(gang)

    def test_additive_and_house_income_keep_running_independently_of_the_base(
        self, campaign, gang, content
    ):
        modifier(
            "Selected extra income",
            targets_gang_alone(),
            ef_contributes_to_counter(content["income"], 5),
            attach_to=content["income_pick"],
        )
        modifier(
            "House income",
            targets_gang(has_gang_pickable(content["house"])),
            ef_contributes_to_counter(content["income"], 10),
            attach_to=content["asset"],
        )
        house_slot = Assignment.objects.get(
            gang_root=gang, slot=content["house_slot"], archived=False
        )
        house_pick = choose(house_slot, content["house"])
        held = holding(campaign, gang, content["asset"], 42)
        assert total(computed(gang), content["income"]) == 57
        choose_for(held, content["alternative"], content["slot"])
        assert total(computed(gang), content["income"]) == 10
        remove(house_pick)
        assert total(computed(gang), content["income"]) == 0
        assert_reconciled(gang)

    def test_later_counter_conditions_see_the_substituted_amount(
        self, campaign, gang, content
    ):
        held = holding(campaign, gang, content["asset"], 42)
        reward = create_rule("Well funded")
        threshold = modifier(
            "Income at least forty",
            targets_gang_alone(),
            ef_adds(reward),
            attach_to=content["asset"],
        )
        card, index = loaded(gang)
        # Gang authoring currently exposes House conditions. Its existing
        # pure counter selector proves the engine's later-round contract.
        entries = index.for_thing(card.holdings[0])
        scopes = [row for row, _ in entries if row.pk == threshold.pk]
        scopes[0].targets_gang._compiled_selector = select.CounterAtLeast(
            content["income"], 40
        )
        index.add(card.holdings[0], [row for row, _ in entries])
        done = compute_gang(card, index)
        assert [record.thing.pk for record in done.rules] == [reward.pk]
        choose_for(held, content["alternative"], content["slot"])
        card, index = loaded(gang)
        entries = index.for_thing(card.holdings[0])
        next(
            row for row, _ in entries if row.pk == threshold.pk
        ).targets_gang._compiled_selector = select.CounterAtLeast(content["income"], 40)
        index.add(card.holdings[0], [row for row, _ in entries])
        assert compute_gang(card, index).rules == []

    def test_a_computed_income_pick_does_not_use_the_recorded_alternatives_override(
        self, campaign, gang, content
    ):
        nested_list = create_picklist(
            "Alternative hidden picks",
            content["income_pick"].slot_type,
            members=[content["alternative"]],
        )
        nested_slot = create_slot(
            "Alternative hidden choice",
            content["income_pick"].slot_type,
            nested_list,
            assigned_to="gang",
            hidden=True,
        )
        grant = modifier(
            "Alternative also grants ordinary income",
            targets_gang_alone(),
            ef_adds(nested_slot),
            attach_to=content["alternative"],
        )
        # The authoring guard refuses this shared computed source. A
        # malformed existing row still cannot borrow a recorded override.
        effect = grant.adds_assignable
        effect.with_pick = content["income_pick"]
        effect.save(update_fields=["with_pick"])
        held = holding(campaign, gang, content["asset"], 42)
        choose_for(held, content["alternative"], content["slot"])
        done = computed(gang)
        assert total(done, content["income"]) == 15
        records = counter_contributions_by_holding(done)[
            (held.pk, held.ownership_revision)
        ]
        assert [
            record.amount
            for record in records
            if record.modifier.pk == content["base"].pk
        ] == [15]
        assert all(record.applied_override is None for record in records)

    def test_a_nested_off_list_income_pick_cannot_use_the_holdings_base_override(
        self, campaign, gang, content
    ):
        nested_list = create_picklist(
            "Alternative nested picks",
            content["income_pick"].slot_type,
            members=[content["alternative"]],
        )
        nested_slot = create_slot(
            "Alternative nested choice",
            content["income_pick"].slot_type,
            nested_list,
            assigned_to="gang",
        )
        modifier(
            "Alternative asks another choice",
            targets_gang_alone(),
            ef_adds(nested_slot),
            attach_to=content["alternative"],
        )
        held = holding(campaign, gang, content["asset"], 42)
        answer = choose_for(held, content["alternative"], content["slot"])
        nested = choose(answer, content["income_pick"], slot=nested_slot)
        done = computed(gang)
        assert total(done, content["income"]) == 15
        assert asset_origins(done.card)[nested.pk].pk == held.pk
        assert all(
            record.applied_override is None for record in done.counter_contributions
        )
        source = holding_income_sources(done)[(held.pk, held.ownership_revision)]
        assert [(part.label, part.amount, part.replaced) for part in source.parts] == [
            ("Base income", 15, False)
        ]

    def test_a_loaded_answer_for_a_different_slot_cannot_borrow_the_base_override(
        self, campaign, gang, content
    ):
        held = holding(campaign, gang, content["asset"], 42)
        card, index = loaded(gang)
        answer = next(
            node for node in card.all_nodes() if node.chosen_for_holding_key == held.pk
        )
        answer.chosen_for_slot_id = content["house_slot"].pk
        done = compute_gang(card, index)
        assert total(done, content["income"]) == 15
        assert all(
            record.applied_override is None for record in done.counter_contributions
        )


class TestIncomeOwnershipAndAncestry:
    """Nested effects keep the selected answer's occurrence identity."""

    def test_nested_grants_are_attributed_and_retract_with_their_selected_answer(
        self, campaign, gang, content
    ):
        carrier = create_hidden(
            "Extra yield",
            effects=[
                (targets_gang_alone(), ef_contributes_to_counter(content["income"], 5))
            ],
        )
        modifier(
            "Income grants extra yield",
            targets_gang_alone(),
            ef_adds(carrier),
            attach_to=content["income_pick"],
        )
        held = holding(campaign, gang, content["asset"], 42)
        done = computed(gang)
        records = counter_contributions_by_holding(done)[
            (held.pk, held.ownership_revision)
        ]
        assert sorted(record.amount for record in records) == [5, 42]
        modifier(
            "Cancel extra yield",
            targets_gang_alone(),
            ef_removes(carrier),
            attach_to=content["asset"],
        )
        assert total(computed(gang), content["income"]) == 42
        choose_for(held, content["alternative"], content["slot"])
        assert total(computed(gang), content["income"]) == 0

    def test_possession_copies_and_nested_choices_group_by_their_asset_assignments(
        self, campaign, gang, content
    ):
        possession_type = add_asset_type(
            content["campaign_type"], "Possession", AssetType.Ownership.POSSESSION
        )
        settlement = declare_choice(
            create_asset(
                "Settlement", possession_type, income=15, given_to_every_gang=False
            ),
            content["income"],
            content["reputation"],
        )
        first = assign(settlement["asset"], gang=gang)
        second = assign(settlement["asset"], gang=gang)
        nested_kind = create_slot_type("Settlement extra")
        extra = create_pickable(
            "Extra five",
            nested_kind,
            effects=[
                (targets_gang_alone(), ef_contributes_to_counter(content["income"], 5))
            ],
        )
        extra_list = create_picklist(
            "Settlement extra options", nested_kind, members=[extra]
        )
        extra_slot = create_slot(
            "Settlement extra choice", nested_kind, extra_list, assigned_to="gang"
        )
        modifier(
            "Settlement income asks extra",
            targets_gang_alone(),
            ef_adds(extra_slot),
            attach_to=settlement["income_pick"],
        )
        first_income = Assignment.objects.get(
            chosen_for=first, chosen_for_slot=settlement["slot"], archived=False
        )
        second_income = Assignment.objects.get(
            chosen_for=second, chosen_for_slot=settlement["slot"], archived=False
        )
        extra_answer = choose(first_income, extra, slot=extra_slot)
        remove(second_income)
        choose(second, settlement["alternative"], slot=settlement["slot"])
        done = computed(gang)
        grouped = counter_contributions_by_asset_assignment(done)
        assert sorted(record.amount for record in grouped[first.pk]) == [5, 15]
        assert [record.amount for record in grouped[second.pk]] == [2]
        origins = asset_origins(done.card)
        assert origins[extra_answer.pk].key == first.pk
        assert origins[second.pk].key == second.pk
        assert total(done, content["income"]) == 20
        assert_reconciled(gang)

    def test_a_granted_possessions_display_keeps_its_actual_income_and_nested_boons(
        self, gang, content
    ):
        possession_type = add_asset_type(
            content["campaign_type"], "Settlement", AssetType.Ownership.POSSESSION
        )
        camp = create_asset(
            "Replacement camp", possession_type, income=25, given_to_every_gang=False
        )
        extra = create_hidden(
            "Camp extra yield",
            effects=[
                (targets_gang_alone(), ef_contributes_to_counter(content["income"], 5))
            ],
        )
        modifier(
            "Camp gives extra yield",
            targets_gang_alone(),
            ef_adds(extra),
            attach_to=camp,
        )
        givers = []
        for name in ["Original camp supplier", "Backup camp supplier"]:
            giver = create_rule(name)
            modifier(
                f"{name} gives the camp",
                targets_gang_alone(),
                ef_adds(camp),
                attach_to=giver,
            )
            givers.append(assign(giver, gang=gang))

        card, index = loaded(gang)
        with CaptureQueriesContext(connection) as queries:
            done = compute_gang(card, index)
            camp_nodes = [node for node in card.all_nodes() if node.assignable == camp]
            grouped = counter_contributions_by_asset_assignment(done)
            sources = asset_assignment_income_sources(done)
            origins = asset_origins(card)
        assert len(queries) == 0
        assert all(node.computed for node in camp_nodes)
        assert len(grouped) == 1
        (camp_key,) = grouped
        assert sorted(record.amount for record in grouped[camp_key]) == [5, 25]
        assert origins[camp_key].key == camp_key
        assert sources[camp_key].value == 30
        assert all(record.applied_override is None for record in grouped[camp_key])
        assert total(done, content["income"]) == 30
        sheet = render_gang(gang)
        (line,) = sheet.campaign.lines
        assert (line.name, line.income, line.provenance.computed) == (
            camp.name,
            30,
            True,
        )
        reading = next(row for row in sheet.campaign.counters if row.name == "Income")
        assert [(source.name, source.value) for source in reading.income_sources] == [
            (camp.name, 30)
        ]

        cancellation = create_rule("Cancel camp extra yield")
        modifier(
            "Remove camp extra yield",
            targets_gang_alone(),
            ef_removes(extra),
            attach_to=cancellation,
        )
        assign(cancellation, gang=gang)
        remove(givers[0])
        done = computed(gang)
        (records,) = counter_contributions_by_asset_assignment(done).values()
        assert [record.amount for record in records] == [25]
        (line,) = render_gang(gang).campaign.lines
        assert line.income == 25
        assert line.provenance.source == "Backup camp supplier"
        assert total(done, content["income"]) == 25

        remove(givers[1])
        done = computed(gang)
        assert counter_contributions_by_asset_assignment(done) == {}
        assert render_gang(gang).campaign.lines == []
        assert total(done, content["income"]) == 0
        assert_reconciled(gang)

    def test_a_previous_ownership_revision_cannot_unlock_an_override(
        self, campaign, gang, rival, content
    ):
        held = holding(campaign, gang, content["asset"], 42)
        old_pick = chosen(held)
        old_revision = held.ownership_revision
        transfer_asset(held, rival)
        held.refresh_from_db()
        assert held.ownership_revision > old_revision
        assert total(computed(gang), content["income"]) == 0
        choose_for(held, content["alternative"], content["slot"], gang=rival)
        old_pick.refresh_from_db()
        assert old_pick.archived
        assert total(computed(rival), content["income"]) == 0
        unassign_asset(held)
        assert counter_contributions_by_holding(computed(rival)) == {}
        assert_reconciled(gang)
        assert_reconciled(rival)

    def test_loading_many_copies_keeps_compute_and_ownership_readers_query_free(
        self, campaign, gang, content
    ):
        for value in [42, 0, None]:
            holding(campaign, gang, content["asset"], value)
        card, index = loaded(gang)
        with CaptureQueriesContext(connection) as queries:
            done = compute_gang(card, index)
            origins = asset_origins(card)
            grouped = counter_contributions_by_holding(done)
            assert counter_contributions_by_asset_assignment(done) == {}
            assert all(
                owner is not None
                for key, owner in origins.items()
                if any(
                    node.key == key and node.chosen_for_holding_key
                    for node in card.all_nodes()
                )
            )
            assert [income_of(copy.asset) for copy in card.holdings] == [15, 15, 15]
        assert len(queries) == 0
        assert sorted(
            sum(record.amount for record in records) for records in grouped.values()
        ) == [0, 15, 42]
        assert total(done, content["income"]) == 57

    def test_loading_more_distinct_declared_assets_does_not_add_queries(
        self, campaign, gang, content
    ):
        holding(campaign, gang, content["asset"], 42)
        loaded(gang)
        with CaptureQueriesContext(connection) as few:
            card, index = loaded(gang)
            assert total(compute_gang(card, index), content["income"]) == 42
        for number in range(7):
            extra = declare_choice(
                create_asset(
                    f"Extra workshop {number}", content["territory"], income=15
                ),
                content["income"],
                content["reputation"],
            )
            holding(campaign, gang, extra["asset"])
        loaded(gang)
        with CaptureQueriesContext(connection) as many:
            card, index = loaded(gang)
            done = compute_gang(card, index)
            assert total(done, content["income"]) == 147
            assert [income_of(copy.asset) for copy in card.holdings] == [15] * 8
        assert len(many) <= len(few), (len(few), len(many))


class TestDirectIncomeCompatibility:
    """An undeclared baseline retains ordinary override-plus-boon behaviour."""

    @pytest.mark.parametrize("override", [42, 0])
    def test_direct_base_income_overrides_keep_additive_effects(
        self, campaign, gang, content, override
    ):
        direct = create_asset("Direct income", content["territory"], income=15)
        conditional = modifier(
            "Direct extra five",
            targets_gang(has_gang_pickable(content["house"])),
            ef_contributes_to_counter(content["income"], 5),
            attach_to=direct,
        )
        house_slot = Assignment.objects.get(
            gang_root=gang, slot=content["house_slot"], archived=False
        )
        choose(house_slot, content["house"])
        held = holding(campaign, gang, direct, override)
        done = computed(gang)
        records = counter_contributions_by_holding(done)[
            (held.pk, held.ownership_revision)
        ]
        assert total(done, content["income"]) == override + 5
        assert {record.modifier.pk for record in records} == {
            held.income_override_id,
            conditional.pk,
        }
        assert income_of(direct) == 15
        assert_reconciled(gang)
