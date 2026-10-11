"""Selectable asset Income and Boons agree across their player displays."""

from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.card import build_gang_card, build_modifier_index, carriers
from n26.core.effects import compute_gang
from n26.core.income import asset_assignment_income_sources, holding_income_sources
from n26.core.models import Assignment, DismissedOffer, LedgerEvent
from n26.core.models.dismissed_offer import GANG_SLOT_HOST, slot_key
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.core.render import asset_boon_lines, render_campaign, render_gang
from n26.core.views.campaign_assets import _asset_context
from n26.library.authoring import (
    add_asset_type,
    add_built_in,
    attach_modifiers_to,
    create_asset,
    create_campaign_type,
    create_counter,
    create_pickable,
    create_picklist,
    create_slot,
    create_slot_type,
    detach_modifier,
    ef_adds,
    ef_contributes_to_counter,
    modifier,
    revise,
    set_base_income_modifier,
    targets_gang_alone,
)
from n26.library.income import income_modifiers, income_of
from n26.library.models import AssetType
from n26.library.territory_boons import seed_all as seed_standing
from n26.tests.fixtures import library_setup
from n26.tests.sandbox.actions import (
    add_asset,
    assign,
    assign_asset,
    found_campaign,
    found_gang,
    join_campaign,
    remove,
    transfer_asset,
)
from n26.tests.sandbox.test_holding_choices import choose_for

pytestmark = pytest.mark.django_db


def selectable(asset, *, staged=False):
    base = income_modifiers(asset)[0]
    kind = create_slot_type(f"{asset.name} boon", staged=staged)
    income = create_pickable("Income", kind, qualifier=asset.name, staged=staged)
    alternate = create_pickable(
        "Recruitment discount",
        kind,
        qualifier=asset.name,
        summary="Resolve one recruitment discount manually after the cycle.",
        staged=staged,
    )
    attach_modifiers_to(income, [base])
    detach_modifier(asset, base)
    picklist = create_picklist(
        f"{asset.name} boons", kind, [income, alternate], staged=staged
    )
    slot = create_slot(
        "Boon", kind, picklist, assigned_to="gang", qualifier=asset.name, staged=staged
    )
    modifier(
        f"{asset.name} offers its boon",
        targets_gang_alone(),
        ef_adds(slot),
        attach_to=asset,
        staged=staged,
    )
    revise(base, staged=staged)
    set_base_income_modifier(asset, base)
    return {
        "asset": asset,
        "base": base,
        "income": income,
        "alternate": alternate,
        "slot": slot,
    }


@pytest.fixture
@library_setup
def content(default_pack):
    income = create_counter("Income")
    reputation = create_counter("Reputation")
    campaign_type = create_campaign_type("Selectable territory display")
    add_built_in(campaign_type, income)
    add_built_in(campaign_type, reputation)
    inherent = add_asset_type(
        campaign_type, "Settlement", AssetType.Ownership.POSSESSION
    )
    pooled = add_asset_type(campaign_type, "Territory", AssetType.Ownership.HOLDING)
    settlement = selectable(create_asset("Settlement", inherent, income=15))
    territory = selectable(create_asset("Workshop", pooled, income=15))
    modifier(
        "Workshop standing income",
        targets_gang_alone(),
        ef_contributes_to_counter(income, 10),
        attach_to=territory["asset"],
    )
    return {
        "campaign_type": campaign_type,
        "income": income,
        "reputation": reputation,
        "settlement": settlement,
        "territory": territory,
    }


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
    gang = found_gang("Territory keepers", gang_type, owner=owner)
    join_campaign(gang, campaign)
    return gang


def computed(gang):
    card = build_gang_card(gang)
    return compute_gang(card, build_modifier_index(carriers(card)))


def income_line(gang):
    return next(line for line in render_gang(gang).campaign.counters if line.is_income)


def source_parts(source):
    return [(part.label, part.amount, part.replaced) for part in source.parts]


def replace_owned(gang, anchor, content, pick):
    with operation(gang, actor=gang.owner) as op:
        old = Assignment.objects.filter(
            chosen_for=anchor, chosen_for_slot=content["slot"], archived=False
        ).first()
        if old is not None:
            op.remove(old)
        return op.choose(anchor, pick, slot=content["slot"])


def detail_context(campaign, holding, owner):
    request = RequestFactory().get(
        reverse("n26-campaign-asset", args=[campaign.pk, holding.pk])
    )
    request.user = owner
    return _asset_context(request, campaign.pk, holding.pk)


class TestInherentSettlement:
    """Settlement uses its own recorded selection rather than catalogue Income."""

    def test_joining_records_the_declared_income_pick_before_returning(
        self, gang, content
    ):
        assignment = gang.assignments.get(
            asset=content["settlement"]["asset"], archived=False
        )
        selected = Assignment.objects.get(
            chosen_for=assignment,
            chosen_for_slot=content["settlement"]["slot"],
            archived=False,
        )
        assert selected.pickable == content["settlement"]["income"]
        assert selected.gang_root_id == gang.pk
        assert LedgerEvent.objects.filter(assignment=selected).exists()
        assert income_line(gang).value == 15
        assert_reconciled(gang)

    def test_alternative_updates_the_settlement_line_and_both_named_counter_sources(
        self, gang, campaign, content
    ):
        settlement = content["settlement"]
        assignment = gang.assignments.get(asset=settlement["asset"], archived=False)
        for pick, expected in [
            (settlement["alternate"], 0),
            (settlement["income"], 15),
        ]:
            replace_owned(gang, assignment, settlement, pick)
            sheet = render_gang(gang)
            line = next(
                line for line in sheet.campaign.lines if line.name == "Settlement"
            )
            assert line.income == expected
            gang_income = next(
                line for line in sheet.campaign.counters if line.is_income
            )
            campaign_income = next(
                counter
                for counter in render_campaign(campaign).gangs[0].counters
                if counter and counter.is_income
            )
            assert gang_income.value == campaign_income.value == expected
            assert gang_income.income_explanation == campaign_income.income_explanation
            boon = next(
                boon for boon in sheet.campaign.boons if boon.name == "Settlement"
            )
            assert [choice.chosen for choice in boon.choices] == [pick.name]
            assert income_of(settlement["asset"]) == 15
            assert_reconciled(gang)

    def test_two_owned_occurrences_keep_separate_effective_income_sources(
        self, gang, content
    ):
        settlement = content["settlement"]
        first = gang.assignments.get(asset=settlement["asset"], archived=False)
        second = assign(settlement["asset"], gang=gang)
        replace_owned(gang, second, settlement, settlement["alternate"])
        done = computed(gang)
        sources = asset_assignment_income_sources(done)
        assert (sources[first.pk].value, sources[second.pk].value) == (15, 0)
        assert sources[first.pk].name == sources[second.pk].name == "Settlement"
        assert income_line(gang).value == 15
        assert_reconciled(gang)

    def test_reading_removing_or_dismissing_a_selection_never_recreates_it(
        self, gang, content
    ):
        settlement = content["settlement"]
        anchor = gang.assignments.get(asset=settlement["asset"], archived=False)
        selected = Assignment.objects.get(
            chosen_for=anchor, chosen_for_slot=settlement["slot"], archived=False
        )
        remove(selected)
        DismissedOffer.objects.create(
            gang=gang,
            slot_key=slot_key(GANG_SLOT_HOST, anchor.pk, settlement["slot"].pk),
        )
        before = (Assignment.objects.count(), LedgerEvent.objects.count())
        assert income_line(gang).value == 0
        with operation(gang, actor=gang.owner) as op:
            op._default_asset_income(anchor, settlement["asset"])
        assert (Assignment.objects.count(), LedgerEvent.objects.count()) == before
        assert not Assignment.objects.filter(chosen_for=anchor, archived=False).exists()
        assert_reconciled(gang)


class TestSelectableHoldingDisplay:
    """A selectable baseline and independent standing Income reconcile everywhere."""

    @pytest.mark.parametrize("override", [42, 0])
    def test_override_applies_only_while_income_is_selected_on_all_surfaces(
        self, gang, campaign, content, owner, override
    ):
        territory = content["territory"]
        from n26.core.campaigns import campaign_operation

        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.add_assets(
                [territory["asset"]],
                name="Overridden workshop",
                income=override,
                request_key=uuid4(),
            )
        holding = assign_asset(
            campaign.campaign_assets.get(name="Overridden workshop"), gang
        )
        for pick, expected in [
            (territory["income"], override + 10),
            (territory["alternate"], 10),
        ]:
            choose_for(holding, pick, territory["slot"])
            gang_sheet = render_gang(gang)
            gang_line = next(
                line
                for line in gang_sheet.campaign.holdings
                if line.campaign_asset_id == str(holding.pk)
            )
            campaign_sheet = render_campaign(campaign)
            entry = next(
                entry
                for table in campaign_sheet.assets
                for entry in table.entries
                if entry.campaign_asset_id == str(holding.pk)
            )
            context = detail_context(campaign, holding, owner)
            assert (
                gang_line.income
                == entry.income
                == context["details"].income
                == expected
            )
            assert entry.income_explanation == context["details"].income_explanation
            source = entry.income_source
            if pick == territory["income"]:
                assert source_parts(source) == [
                    ("Base income", 15, True),
                    ("Income override", override, False),
                    ("Boon", 10, False),
                ]
            else:
                assert source_parts(source) == [("Boon", 10, False)]
            assert income_line(gang).value == expected + 15
            assert income_of(territory["asset"]) == 15
            assert_reconciled(gang)

    def test_boons_rows_use_body_sized_controls_and_effective_extra_amounts(
        self, client, gang, campaign, content, owner
    ):
        holding = assign_asset(
            add_asset(
                campaign, content["territory"]["asset"], name="Long named workshop"
            ),
            gang,
        )
        client.force_login(owner)
        page = client.get(reverse("n26-gang", args=[gang.pk]))
        assert page.status_code == 200
        body = BeautifulSoup(page.content, "html.parser")
        section = body.find(id="n26-campaign-boons-heading").find_parent("section")
        assert (
            "Settlement" in section.get_text()
            and "Long named workshop" in section.get_text()
        )
        assert "Income" in section.get_text() and "+10¢" in section.get_text()
        controls = section.select('a[href*="/choose/"]')
        assert len(controls) == 2
        assert all("text-base" in link.get("class", []) for link in controls)
        context = detail_context(campaign, holding, owner)
        assert [
            (effect.name, effect.value) for effect in context["boons"][0].effects
        ] == [("Income", 10)]
        detail = render_to_string("n26/includes/campaign_asset_detail.html", context)
        assert "Boons" in BeautifulSoup(detail, "html.parser").get_text()

    def test_lost_holdings_leave_no_active_boon_but_keep_recorded_history(
        self, gang, campaign, content, gang_type, owner
    ):
        holding = assign_asset(add_asset(campaign, content["territory"]["asset"]), gang)
        selected = choose_for(
            holding, content["territory"]["alternate"], content["territory"]["slot"]
        )
        other = found_gang("Other keepers", gang_type, owner=owner)
        join_campaign(other, campaign)
        transferred = transfer_asset(holding, other)
        assert [boon.name for boon in render_gang(gang).campaign.boons] == [
            "Settlement"
        ]
        assert selected.ledger_events.exists()
        details = detail_context(campaign, transferred, owner)
        assert details["boons"][0].choices[0].chosen == "Income"
        assert details["details"].income == 25
        assert_reconciled(gang)
        assert_reconciled(other)

    def test_loaded_sources_and_boon_facts_issue_no_sql(self, gang, campaign, content):
        assign_asset(add_asset(campaign, content["territory"]["asset"]), gang)
        done = computed(gang)
        with CaptureQueriesContext(connection) as queries:
            assert len(holding_income_sources(done)) == 1
            assert len(asset_assignment_income_sources(done)) == 1
            assert len(asset_boon_lines(done)) == 2
        assert len(queries) == 0


class TestStagedIncomeDefaults:
    """Staging hides new offers but does not switch off existing asset Income."""

    def test_declared_staged_income_defaults_for_both_ownership_kinds(
        self, content, campaign, gang, owner
    ):
        for data in (content["settlement"], content["territory"]):
            for row in (
                data["asset"],
                data["base"],
                data["income"],
                data["alternate"],
                data["slot"],
                data["slot"].picklist,
            ):
                revise(row, staged=True)
            for member in data["slot"].picklist.members.all():
                revise(member, staged=True)
        owned = assign(content["settlement"]["asset"], gang=gang)
        assert Assignment.objects.filter(
            chosen_for=owned, pickable=content["settlement"]["income"], archived=False
        ).exists()
        from n26.core.campaigns import campaign_operation

        with campaign_operation(campaign, actor=campaign.owner) as act:
            holding = act.add_asset(content["territory"]["asset"])
        assign_asset(holding, gang)
        assert Assignment.objects.filter(
            chosen_for_holding=holding,
            pickable=content["territory"]["income"],
            archived=False,
        ).exists()
        assert_reconciled(gang)


class TestStandingBoons:
    """The four seeded numeric benefits appear on their actual holding."""

    @pytest.fixture
    @library_setup
    def standing(self, default_pack):
        income = create_counter("Income")
        reputation = create_counter("Reputation")
        campaign_type = create_campaign_type("Territory campaign")
        add_built_in(campaign_type, income)
        add_built_in(campaign_type, reputation)
        inherent = add_asset_type(
            campaign_type, "Settlement", AssetType.Ownership.POSSESSION
        )
        pooled = add_asset_type(campaign_type, "Territory", AssetType.Ownership.HOLDING)
        create_asset("Settlement", inherent, income=15)
        assets = {
            name: create_asset(name, pooled, income=15)
            for name in ("Generatorium", "Gambling Den", "Amneo-vats", "Shivver Den")
        }
        house_kind = create_slot_type("Gang supertype")
        goliath = create_pickable("Goliath", house_kind, qualifier="Gang supertype")
        escher = create_pickable("Escher", house_kind, qualifier="Gang supertype")
        houses = create_picklist("Current Houses", house_kind, [goliath, escher])
        house_slot = create_slot(
            "Current House", house_kind, houses, assigned_to="gang"
        )
        seed_standing()
        return {
            "campaign_type": campaign_type,
            "assets": assets,
            "house_slot": house_slot,
            "goliath": goliath,
            "escher": escher,
        }

    def test_house_changes_update_each_effect_without_catalogue_name_dispatch(
        self, standing, gang_type, owner
    ):
        campaign = found_campaign(
            "Standing territory benefits", standing["campaign_type"], owner=owner
        )
        gang = found_gang("House keepers", gang_type, owner=owner)
        join_campaign(gang, campaign)
        house = assign(standing["house_slot"], gang=gang)
        selected = None
        for asset in standing["assets"].values():
            assign_asset(add_asset(campaign, asset), gang)
        for pick, expected in [
            (
                standing["goliath"],
                {
                    "Generatorium": [("Reputation", 1)],
                    "Gambling Den": [("Reputation", 1)],
                    "Amneo-vats": [("Income", 10)],
                },
            ),
            (
                standing["escher"],
                {
                    "Generatorium": [("Reputation", 1)],
                    "Gambling Den": [("Reputation", 1)],
                    "Shivver Den": [("Reputation", 1)],
                },
            ),
        ]:
            with operation(gang, actor=owner) as op:
                if selected is not None:
                    op.remove(selected)
                selected = op.choose(house, pick, slot=standing["house_slot"])
            rows = render_gang(gang).campaign.boons
            assert {
                row.name: [(effect.name, effect.value) for effect in row.effects]
                for row in rows
            } == expected
            for holding in campaign.campaign_assets.all():
                context = detail_context(campaign, holding, owner)
                assert [
                    (effect.name, effect.value)
                    for row in context["boons"]
                    for effect in row.effects
                ] == expected.get(str(holding), [])
            assert_reconciled(gang)

    def test_selected_manual_pick_stays_under_its_asset_when_its_offer_is_hidden(
        self, campaign, gang, content
    ):
        asset = create_asset(
            "Recorded workshop", content["territory"]["asset"].asset_type, income=7
        )
        kind = create_slot_type("Workshop provision")
        pick = create_pickable("Manual equipment reward", kind)
        picklist = create_picklist("Workshop provisions", kind, [pick])
        slot = create_slot("Provision", kind, picklist, assigned_to="gang")
        modifier(
            "Recorded workshop offers provision",
            targets_gang_alone(),
            ef_adds(slot),
            attach_to=asset,
        )
        holding = assign_asset(add_asset(campaign, asset), gang)
        selected = Assignment.objects.get(
            chosen_for_holding=holding, chosen_for_slot=slot, archived=False
        )
        revise(slot, hidden=True)
        row = next(
            row
            for row in render_gang(gang).campaign.boons
            if row.name == "Recorded workshop"
        )
        assert [choice.chosen for choice in row.choices] == ["Manual equipment reward"]
        assert row.choices[0].href == row.choices[0].key == ""
        assert selected.ledger_events.exists()
        assert_reconciled(gang)
