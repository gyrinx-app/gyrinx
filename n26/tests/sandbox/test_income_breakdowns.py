"""Income explanations name the standing effects behind the displayed reading.

Catalogue Income replaced by a holding's override remains visible as context,
while only surviving contributions and the gang's recorded adjustment add up.
"""

import json
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.db import connection
from django.template.loader import render_to_string
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.campaigns import campaign_operation
from n26.core.income import holding_income_sources, income_sources
from n26.core.models import Assignment, CampaignAsset
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_campaign, render_gang
from n26.core.views.campaign_assets import _asset_context
from n26.library.authoring import (
    add_asset_type,
    add_built_in,
    attach_modifiers_to,
    create_asset,
    create_campaign_type,
    create_counter,
    create_hidden,
    create_pack,
    create_pickable,
    create_picklist,
    create_slot,
    create_slot_type,
    ef_adds,
    ef_contributes_to_counter,
    ef_removes,
    modifier,
    targets_gang_alone,
)
from n26.library.income import income_modifiers
from n26.library.models import AssetType
from n26.tests.fixtures import island_props as component_props
from n26.tests.fixtures import library_setup
from n26.tests.sandbox.actions import (
    add_asset,
    assign,
    assign_asset,
    remove,
    tally,
    transfer_asset,
    unassign_asset,
)
from n26.tests.sandbox.test_holding_choices import campaign as campaign
from n26.tests.sandbox.test_holding_choices import (
    choose_for,
    computed,
    question,
)
from n26.tests.sandbox.test_holding_choices import gang as gang
from n26.tests.sandbox.test_holding_choices import holding as holding
from n26.tests.sandbox.test_holding_choices import rival as rival

pytestmark = pytest.mark.django_db


@pytest.fixture
@library_setup
def content(default_pack):
    income = create_counter("Income")
    reputation = create_counter("Reputation")
    campaign_type = create_campaign_type("Income explanations")
    add_built_in(campaign_type, income)
    add_built_in(campaign_type, reputation)
    settlement_type = add_asset_type(
        campaign_type, "Settlement", AssetType.Ownership.POSSESSION
    )
    create_asset("Settlement", settlement_type, income=15)
    territory = add_asset_type(campaign_type, "Territory", "pooled")
    asset = create_asset("Workshop", territory, income=15)
    kind = create_slot_type("Territory benefit")
    income_pick = create_pickable(
        "Extra income",
        kind,
        effects=[(targets_gang_alone(), ef_contributes_to_counter(income, 5))],
    )
    reputation_pick = create_pickable(
        "Local reputation",
        kind,
        effects=[(targets_gang_alone(), ef_contributes_to_counter(reputation, 2))],
    )
    table = create_picklist(
        "Workshop benefits", kind, members=[income_pick, reputation_pick]
    )
    slot = create_slot("Workshop benefit", kind, table, assigned_to="gang")
    modifier(
        "Workshop offers a benefit",
        targets_gang_alone(),
        ef_adds(slot),
        attach_to=asset,
    )
    return {
        "campaign_type": campaign_type,
        "asset": asset,
        "kind": kind,
        "slot": slot,
        "income": income,
        "reputation": reputation,
        "income_pick": income_pick,
        "reputation_pick": reputation_pick,
    }


def reading(gang):
    return next(line for line in render_gang(gang).campaign.counters if line.is_income)


def campaign_reading(sheet, gang):
    line = next(line for line in sheet.gangs if line.gang_id == str(gang.pk))
    return next(counter for counter in line.counters if counter and counter.is_income)


def entry_for(sheet, holding):
    return next(
        entry
        for table in sheet.assets
        for entry in table.entries
        if entry.campaign_asset_id == str(holding.pk)
    )


def details_context(campaign, holding):
    request = RequestFactory().get(
        reverse("n26-campaign-asset", args=[campaign.pk, holding.pk])
    )
    request.user = campaign.owner
    return _asset_context(request, campaign.pk, holding.pk)


def island_props(html):
    soup = BeautifulSoup(html, "html.parser")
    return [
        json.loads(soup.find(id=host["data-react-props"]).string)
        for host in soup.find_all(attrs={"data-react-name": "income-tooltip"})
    ]


def parts(source):
    return [
        (part.label, part.amount, part.detail, part.replaced) for part in source.parts
    ]


def overridden_holding(campaign, gang, content, amount):
    with campaign_operation(campaign, actor=campaign.owner) as act:
        act.add_assets(
            [content["asset"]],
            name="Overridden Workshop",
            income=amount,
            request_key=uuid4(),
        )
    holding = CampaignAsset.objects.get(campaign=campaign, name="Overridden Workshop")
    return assign_asset(holding, gang)


class TestExplainingTheGangReading:
    """Campaign and gang figures explain the same contributions and adjustment."""

    def test_settlement_territory_and_other_income_share_the_same_counter_explanation(
        self, holding, gang, campaign, content
    ):
        assign(
            create_hidden(
                "Independent gang income",
                effects=[
                    (
                        targets_gang_alone(),
                        ef_contributes_to_counter(content["income"], 11),
                    )
                ],
            ),
            gang=gang,
        )
        counter = Assignment.objects.get(gang_root=gang, counter=content["income"])
        tally(counter, 7)
        gang_line = reading(gang)
        sheet = render_campaign(campaign)
        props = gang_line.income_explanation
        assert props == campaign_reading(sheet, gang).income_explanation
        assert (props["value"], props["contributed"], props["adjustment"]) == (
            53,
            46,
            7,
        )
        assert {source["name"]: source["value"] for source in props["sources"]} == {
            "Settlement": 15,
            "Workshop": 20,
            "Independent gang income": 11,
        }
        workshop = next(
            source for source in gang_line.income_sources if source.name == "Workshop"
        )
        assert parts(workshop) == [
            ("Base income", 15, "", False),
            ("Boon", 5, "Extra income", False),
        ]
        assert (
            sum(source["value"] for source in props["sources"]) + props["adjustment"]
            == props["value"]
        )
        html = render_to_string("n26/includes/campaign_gangs.html", {"sheet": sheet})
        from n26.tests.fixtures import island_props as table_props

        counters = table_props(html, "campaign-gangs")["gangs"][0]["counters"]
        assert [
            counter["income"] for counter in counters if counter and counter["income"]
        ] == [props]
        assert_reconciled(gang)

    def test_two_named_holdings_keep_their_own_choices_and_contributions(
        self, gang, campaign, content
    ):
        east = assign_asset(
            add_asset(campaign, content["asset"], name="East Workshop"), gang
        )
        west = assign_asset(
            add_asset(campaign, content["asset"], name="West Workshop"), gang
        )
        choose_for(west, content["reputation_pick"], content["slot"])
        sources = holding_income_sources(computed(gang))
        assert {
            address: (source.name, source.value) for address, source in sources.items()
        } == {
            (east.pk, east.ownership_revision): ("East Workshop", 20),
            (west.pk, west.ownership_revision): ("West Workshop", 15),
        }
        assert parts(sources[(west.pk, west.ownership_revision)]) == [
            ("Base income", 15, "", False)
        ]
        assert {
            source.name: source.value for source in reading(gang).income_sources
        } == {
            "Settlement": 15,
            "East Workshop": 20,
            "West Workshop": 15,
        }

    def test_another_packs_income_and_a_duplicate_assignment_do_not_repeat_sources(
        self, holding, gang, content
    ):
        other = create_counter("Income", pack=create_pack("Other counters"))
        modifier(
            "Workshop adds other-pack Income",
            targets_gang_alone(),
            ef_contributes_to_counter(other, 77),
            attach_to=content["asset"],
        )
        assign(content["income"], gang=gang)
        done = computed(gang)
        own = [item for item in done.counters if item.thing.pk == content["income"].pk]
        foreign = next(item for item in done.counters if item.thing.pk == other.pk)
        assert [item.value for item in own] == [35, 0]
        assert own[1].contributions == ()
        assert {
            source.name: source.value
            for source in income_sources(
                done, own[0].contributions, counter=own[0].thing
            )
        } == {
            "Settlement": 15,
            "Workshop": 20,
        }
        foreign_sources = income_sources(
            done, done.counter_contributions, counter=foreign.thing
        )
        assert [
            (source.name, source.value, parts(source)) for source in foreign_sources
        ] == [("Workshop", 77, [("Base income", 77, "", False)])]
        assert reading(gang).income_explanation["contributed"] == 35


class TestExplainingOneHolding:
    """A holding's override replaces its base while keeping its selected boons."""

    @pytest.mark.parametrize("override", [42, 0])
    def test_the_override_and_boon_add_up_without_adding_the_replaced_catalogue_base(
        self, campaign, gang, content, override
    ):
        holding = overridden_holding(campaign, gang, content, override)
        source = holding_income_sources(computed(gang))[
            (holding.pk, holding.ownership_revision)
        ]
        assert source.value == override + 5
        assert parts(source) == [
            ("Base income", 15, "", True),
            ("Income override", override, "", False),
            ("Boon", 5, "Extra income", False),
        ]
        assert (
            sum(part.amount for part in source.parts if not part.replaced)
            == source.value
        )
        sheet = render_campaign(campaign)
        entry = entry_for(sheet, holding)
        context = details_context(campaign, holding)
        props = context["details"].income_explanation
        assert props == entry.income_explanation
        assert (props["value"], props["currency"], props["showAdjustment"]) == (
            override + 5,
            True,
            False,
        )
        assert island_props(
            render_to_string("n26/includes/campaign_asset_detail.html", context)
        ) == [props]
        inventory = component_props(
            render_to_string(
                "n26/includes/campaign_assets_section.html", {"sheet": sheet}
            ),
            "campaign-assets",
        )
        assert [entry["income"] for entry in inventory["entries"]] == [props]
        assert reading(gang).value == 15 + override + 5
        assert_reconciled(gang)

    @pytest.mark.parametrize("override", [42, 0])
    def test_an_unclaimed_override_shows_no_active_boons_and_keeps_a_zero_tooltip(
        self, campaign, gang, content, override
    ):
        holding = overridden_holding(campaign, gang, content, override)
        unassign_asset(holding)
        context = details_context(campaign, holding)
        details = context["details"]
        assert details.holder == "" and details.income == override
        assert parts(details.income_source) == [
            ("Base income", 15, "", True),
            ("Income override", override, "", False),
        ]
        entry = entry_for(render_campaign(campaign), holding)
        assert not entry.held and entry.income_explanation == details.income_explanation
        html = render_to_string("n26/includes/campaign_asset_detail.html", context)
        assert island_props(html) == [details.income_explanation]
        assert f"{override}¢" in BeautifulSoup(html, "html.parser").get_text()
        assert {source.name for source in reading(gang).income_sources} == {
            "Settlement"
        }

    def test_switching_choices_and_ownership_never_lists_a_previous_owners_boon(
        self, holding, gang, rival, campaign, content
    ):
        address = (holding.pk, holding.ownership_revision)
        choose_for(holding, content["reputation_pick"], content["slot"])
        assert parts(holding_income_sources(computed(gang))[address]) == [
            ("Base income", 15, "", False)
        ]
        current = transfer_asset(holding, rival)
        assert holding_income_sources(computed(gang)) == {}
        assert {source.name for source in reading(gang).income_sources} == {
            "Settlement"
        }
        rival_sources = holding_income_sources(computed(rival))
        assert address not in rival_sources
        assert parts(rival_sources[(current.pk, current.ownership_revision)]) == [
            ("Base income", 15, "", False),
            ("Boon", 5, "Extra income", False),
        ]
        unassign_asset(current)
        assert holding_income_sources(computed(rival)) == {}
        assert parts(details_context(campaign, current)["details"].income_source) == [
            ("Base income", 15, "", False)
        ]
        current = assign_asset(current, gang)
        assert (current.pk, current.ownership_revision) != address
        assert holding_income_sources(computed(rival)) == {}
        assert reading(gang).value == 35


class TestExplainingSettledEffects:
    """Only actual direct Asset income is base, and cancelled effects disappear."""

    def test_distinct_assets_sharing_base_income_keep_their_loaded_breakdowns_query_free(
        self, holding, gang, campaign, content
    ):
        with CaptureQueriesContext(connection) as few:
            details_context(campaign, holding)
        (baseline,) = income_modifiers(content["asset"])
        other = create_asset("Other Workshop", content["asset"].asset_type)
        attach_modifiers_to(other, [baseline])
        second = assign_asset(add_asset(campaign, other), gang)
        done = computed(gang)
        counter = next(
            item for item in done.counters if item.thing.pk == content["income"].pk
        )
        with CaptureQueriesContext(connection) as pure:
            sources = holding_income_sources(done)
            named = income_sources(done, counter.contributions, counter=counter.thing)
        assert len(pure) == 0
        assert {source.name: source.value for source in named} == {
            "Settlement": 15,
            "Workshop": 20,
            "Other Workshop": 15,
        }
        with CaptureQueriesContext(connection) as many:
            details = details_context(campaign, second)["details"]
        assert details.income_source == sources[(second.pk, second.ownership_revision)]
        assert parts(details.income_source) == [("Base income", 15, "", False)]
        assert len(many) <= len(few)

    def test_a_shared_modifier_is_base_only_on_the_asset_and_a_boon_on_nested_carriers(
        self, holding, gang, content
    ):
        (baseline,) = income_modifiers(content["asset"])
        attach_modifiers_to(content["income_pick"], [baseline])
        carrier = create_hidden("Workshop contract")
        attach_modifiers_to(carrier, [baseline])
        modifier(
            "Workshop grants its contract",
            targets_gang_alone(),
            ef_adds(carrier),
            attach_to=content["asset"],
        )
        kind = create_slot_type("Workshop trade")
        pick = create_pickable("Nested trade income", kind)
        attach_modifiers_to(pick, [baseline])
        table = create_picklist("Workshop trades", kind, members=[pick])
        slot = create_slot("Workshop trade", kind, table, assigned_to="gang")
        modifier(
            "Extra income offers a trade",
            targets_gang_alone(),
            ef_adds(slot),
            attach_to=content["income_pick"],
        )
        root = question(gang, holding, content["slot"]).picks[0].assignment
        with operation(gang, actor=gang.owner) as op:
            op.choose(root, pick, slot=slot)
        source = holding_income_sources(computed(gang))[
            (holding.pk, holding.ownership_revision)
        ]
        assert source.value == 65
        assert parts(source) == [
            ("Base income", 15, "", False),
            ("Boon", 5, "Extra income", False),
            ("Boon", 15, "Extra income", False),
            ("Boon", 15, "Nested trade income", False),
            ("Boon", 15, "Workshop contract", False),
        ]
        assert reading(gang).value == 80

    def test_a_retracted_grants_income_is_absent_even_when_its_pick_still_stands(
        self, holding, gang, content
    ):
        carrier = create_hidden(
            "Workshop trade payment",
            effects=[
                (targets_gang_alone(), ef_contributes_to_counter(content["income"], 7))
            ],
        )
        modifier(
            "Extra income brings a payment",
            targets_gang_alone(),
            ef_adds(carrier),
            attach_to=content["income_pick"],
        )
        blocker = assign(
            create_hidden(
                "Workshop trade is closed",
                effects=[(targets_gang_alone(), ef_removes(carrier))],
            ),
            gang=gang,
        )
        source = holding_income_sources(computed(gang))[
            (holding.pk, holding.ownership_revision)
        ]
        assert source.value == 20
        assert parts(source) == [
            ("Base income", 15, "", False),
            ("Boon", 5, "Extra income", False),
        ]
        remove(blocker)
        source = holding_income_sources(computed(gang))[
            (holding.pk, holding.ownership_revision)
        ]
        assert source.value == 27
        assert ("Boon", 7, "Workshop trade payment", False) in parts(source)

    def test_loaded_breakdowns_issue_no_sql_and_more_holdings_do_not_add_reads(
        self, holding, gang, campaign, content
    ):
        done = computed(gang)
        counter = next(
            item for item in done.counters if item.thing.pk == content["income"].pk
        )
        with CaptureQueriesContext(connection) as pure:
            assert len(holding_income_sources(done)) == 1
            assert (
                sum(
                    source.value
                    for source in income_sources(
                        done, counter.contributions, counter=counter.thing
                    )
                )
                == counter.value
            )
        assert len(pure) == 0
        render_campaign(campaign)
        with CaptureQueriesContext(connection) as few:
            render_campaign(campaign)
        for number in range(8):
            assign_asset(
                add_asset(campaign, content["asset"], name=f"Workshop {number}"), gang
            )
        render_campaign(campaign)
        with CaptureQueriesContext(connection) as many:
            sheet = render_campaign(campaign)
        props = campaign_reading(sheet, gang).income_explanation
        assert len(props["sources"]) == 10
        assert props["value"] == 195
        assert len(many) <= len(few)
