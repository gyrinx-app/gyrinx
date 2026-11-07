"""Verify render_campaign display data: gang finances, campaign counters and assets, asset
ownership and budget guidance. Fetch related rows in batches so query counts remain
fixed as gangs are added; see n26/design/gang-sheet.md.
"""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from n26.core.models import Campaign
from n26.core.render import render_campaign
from n26.flags import STAGED_CONTENT
from n26.library.authoring import (
    add_asset_type,
    add_built_in,
    create_asset,
    create_counter,
    create_rule,
    ef_adds,
    ef_contributes_to_counter,
    modifier,
    targets_gang,
)
from n26.library.core_campaign import seed_core_campaign
from n26.library.models import CampaignType, Counter
from n26.tests.sandbox.actions import (
    add_asset,
    add_campaign_counter,
    add_campaign_label,
    assign_asset,
    found_campaign,
    found_gang,
    hire,
    hire_with_option,
    join_campaign,
    tally,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def arbitrator():
    return User.objects.create_user("arbitrator")


@pytest.fixture
def core(default_pack):
    seed_core_campaign(apps)
    return CampaignType.objects.get(name="Territory campaign")


@pytest.fixture
def campaign(arbitrator, core):
    return found_campaign("Dust Falls", core, owner=arbitrator, budget=1000)


@pytest.fixture
def old_ruins(core):
    """Territory contributing Reputation and a named rule while held."""
    territory = core.asset_types.get(label_singular="Territory")
    asset = create_asset("Old Ruins", territory, income=30)
    reputation = Counter.objects.get(name="Reputation")
    modifier(
        "Old Ruins: Reputation",
        targets_gang(),
        ef_contributes_to_counter(reputation, 1),
        attach_to=asset,
    )
    modifier(
        "Old Ruins: Salvage",
        targets_gang(),
        ef_adds(create_rule("Salvage")),
        attach_to=asset,
    )
    return asset


@pytest.fixture
def toll_crossing(core):

    territory = core.asset_types.get(label_singular="Territory")
    return create_asset("Toll Crossing", territory, income=20)


@pytest.fixture
def protection(campaign):
    """Campaign-authored Racket alongside the shared Territory asset type."""
    racket = add_asset_type(campaign.additions, "Racket", "pooled")
    return create_asset("Protection", racket)


@pytest.fixture
def gangs(gang_type, campaign):
    """Create gangs out of alphabetical order so sorting is exercised."""
    made = []
    for name, owner in (
        ("The Rust Kings", "rust"),
        ("The Ashen Choir", "ash"),
        ("Pit of Teeth", "pit"),
    ):
        gang = found_gang(name, gang_type, owner=User.objects.create_user(owner))
        join_campaign(gang, campaign)
        made.append(gang)
    return made


def line_named(sheet, name):
    return next(line for line in sheet.gangs if line.name == name)


def readings(line):
    """Return counter values from one gang row, using None when the counter is absent."""
    return [counter.value if counter is not None else None for counter in line.counters]


class TestTheGangsTable:
    """Sort active gang rows by name and include finance, counter and asset columns."""

    def test_gangs_are_sorted_by_name_with_their_money(self, campaign, gangs):
        sheet = render_campaign(campaign)
        assert [line.name for line in sheet.gangs] == [
            "Pit of Teeth",
            "The Ashen Choir",
            "The Rust Kings",
        ]
        ash = line_named(sheet, "The Ashen Choir")
        assert ash.owner.username == "ash"
        assert ash.gang_type == "Escher"
        assert (ash.rating, ash.credits) == (gangs[1].rating, gangs[1].credits)
        assert ash.href == ""

    def test_reputation_leads_the_counter_columns(self, campaign, gang_type):
        """Prioritise Reputation before the remaining counter columns, with opening values
        from shared and campaign-authored built-ins.
        """
        meat = create_counter("Meat")
        add_built_in(campaign.additions, meat, amount=2)
        gang = found_gang("Late", gang_type, owner=User.objects.create_user("late"))
        join_campaign(gang, campaign)

        sheet = render_campaign(campaign)

        assert sheet.counter_columns == ["Reputation", "Income", "Meat"]
        assert readings(line_named(sheet, "Late")) == [1, 10, 2]

    def test_a_held_territory_counts_in_the_reading(self, campaign, gangs, old_ruins):
        """Combine the stored counter value with held-asset contributions."""
        entry = add_asset(campaign, old_ruins)
        assign_asset(entry, gangs[1])
        reputation = gangs[1].assignments.get(counter__name="Reputation")
        tally(reputation, 2)

        sheet = render_campaign(campaign)

        assert readings(line_named(sheet, "The Ashen Choir")) == [4, 70]
        assert readings(line_named(sheet, "The Rust Kings")) == [1, 10]

    def test_a_gang_without_the_counter_reads_none(self, campaign, gangs):
        """Distinguish an absent counter from a zero reading."""
        from n26.core.models import Assignment

        Assignment.objects.filter(
            gang_root=gangs[2], counter__name="Reputation"
        ).update(archived=True)
        sheet = render_campaign(campaign)
        assert readings(line_named(sheet, "Pit of Teeth")) == [None, 0]
        assert readings(line_named(sheet, "The Ashen Choir")) == [1, 10]

    def test_assets_sit_under_their_asset_type_column(
        self, campaign, gangs, old_ruins, toll_crossing, protection
    ):
        """Order shared asset types before campaign-authored types, and place each gang's
        assets under the matching column.
        """
        ruins = add_asset(campaign, old_ruins)
        toll = add_asset(campaign, toll_crossing, name="The Sump Toll")
        racket = add_asset(campaign, protection)
        assign_asset(ruins, gangs[1])
        assign_asset(toll, gangs[1])
        assign_asset(racket, gangs[0])

        sheet = render_campaign(campaign)

        assert [(t.plural, t.holding) for t in sheet.asset_types] == [
            ("Settlements", False),
            ("Territories", True),
            ("Rackets", True),
        ]
        ash = line_named(sheet, "The Ashen Choir")
        assert ash.assets == [["Settlement"], ["Old Ruins", "The Sump Toll"], []]
        rust = line_named(sheet, "The Rust Kings")
        assert rust.assets == [["Settlement"], [], ["Protection"]]
        pit = line_named(sheet, "Pit of Teeth")
        assert pit.assets == [["Settlement"], [], []]

    def test_over_budget_is_marked_on_the_line(self, campaign, gangs, make_profile):
        """Use wealth for budget guidance, consistently with joining warnings."""
        profile = make_profile("Ganger", price=1200)
        hire_with_option(gangs[0], profile, "Vex")
        sheet = render_campaign(campaign)
        assert line_named(sheet, "The Rust Kings").over_budget
        assert not line_named(sheet, "The Ashen Choir").over_budget
        assert sheet.gangs_over_budget == 1

    @pytest.mark.parametrize("status", ["in_progress", "post_campaign"])
    def test_only_pre_campaign_shows_the_over_budget_warning(
        self, campaign, gangs, make_profile, arbitrator, status
    ):
        from datetime import date

        from n26.core.campaigns import campaign_operation

        hire_with_option(gangs[0], make_profile("Ganger", price=1200), "Vex")
        assert line_named(render_campaign(campaign), "The Rust Kings").over_budget
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.record_battle(date.today(), gangs[:2], scenario="Opening battle")
        assert line_named(render_campaign(campaign), "The Rust Kings").over_budget
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.set_status(status)
        assert not any(line.over_budget for line in render_campaign(campaign).gangs)
        with campaign_operation(campaign, actor=arbitrator) as act:
            act.set_status("pre_campaign")
        assert line_named(render_campaign(campaign), "The Rust Kings").over_budget


class TestTheAssetsTables:
    """List transferable asset types with each holding's income and owner."""

    def test_holdings_get_a_table_and_possessions_do_not(
        self, campaign, gangs, old_ruins, protection
    ):
        sheet = render_campaign(campaign)
        assert [table.plural for table in sheet.assets] == ["Territories", "Rackets"]
        assert all(table.entries == [] for table in sheet.assets)

    def test_an_asset_says_what_it_is_and_who_holds_it(
        self, campaign, gangs, old_ruins, arbitrator
    ):
        named = add_asset(campaign, old_ruins, name="Old Ruins by the sump")
        plain = add_asset(campaign, old_ruins)
        assign_asset(named, gangs[1])

        sheet = render_campaign(campaign, viewer=gangs[1].owner)
        (territories,) = sheet.assets
        by_name = {entry.name: entry for entry in territories.entries}

        held = by_name["Old Ruins by the sump"]
        assert held.campaign_asset_id == str(named.pk)
        assert held.asset_name == "Old Ruins"
        assert held.income == 30
        assert held.held and held.holder == "The Ashen Choir"
        assert held.holder_gang_id == str(gangs[1].pk)
        assert held.holder_yours

        unclaimed = by_name["Old Ruins"]
        assert unclaimed.campaign_asset_id == str(plain.pk)
        assert unclaimed.asset_name == ""
        assert not unclaimed.held and unclaimed.holder == ""
        assert (territories.held, territories.unclaimed) == (1, 1)
        assert (sheet.asset_count, sheet.assets_held, sheet.assets_unclaimed) == (
            2,
            1,
            1,
        )

    def test_the_headline_names_the_type_and_the_arbitrator(
        self, campaign, gangs, arbitrator
    ):
        sheet = render_campaign(campaign)
        assert sheet.name == "Dust Falls"
        assert sheet.campaign_type == "Territory campaign"
        assert sheet.arbitrator == "arbitrator"
        assert sheet.budget == 1000
        assert sheet.gang_count == 3
        assert sheet.battles_fought == 0


class TestTheQueryBudget:
    """Batch gang assignments, hydration and modifiers so more gangs add rows without
    adding queries.
    """

    def measure(self, campaign):
        found = Campaign.objects.select_related(
            "owner", "campaign_type", "additions__built_ins"
        ).get(pk=campaign.pk)
        with CaptureQueriesContext(connection) as captured:
            sheet = render_campaign(found)
        return sheet, len(captured.captured_queries)

    def test_the_sheet_costs_a_fixed_number_of_queries(
        self, campaign, gang_type, old_ruins, toll_crossing, make_profile
    ):
        profile = make_profile("Ganger", price=50)
        first = found_gang("First", gang_type, owner=User.objects.create_user("one"))
        join_campaign(first, campaign)
        hire(first, profile, "Vex")
        assign_asset(add_asset(campaign, old_ruins), first)
        sheet, few = self.measure(campaign)
        assert len(sheet.gangs) == 1

        for index in range(3):
            more = found_gang(
                f"More {index}", gang_type, owner=User.objects.create_user(f"u{index}")
            )
            join_campaign(more, campaign)
            hire(more, profile, f"Model {index}")
            assign_asset(add_asset(campaign, toll_crossing), more)
        sheet, again = self.measure(campaign)

        assert len(sheet.gangs) == 4
        assert again == few

    def test_the_page_costs_a_fixed_number_of_queries(
        self, client, campaign, gang_type, old_ruins, arbitrator
    ):
        # Add counter and label content before the smaller measurement so both rosters
        # hydrate the same relation kinds.
        add_campaign_counter(campaign, "Meat", opening=3)
        add_campaign_label(campaign, "Alignment", ["Law Abiding", "Outlaw"])
        gangs = []
        for name in ("The Rust Kings", "The Ashen Choir", "Pit of Teeth"):
            gang = found_gang(name, gang_type, owner=User.objects.create_user(name))
            join_campaign(gang, campaign)
            gangs.append(gang)
        assign_asset(add_asset(campaign, old_ruins), gangs[0])
        client.force_login(arbitrator)
        address = reverse("n26-campaign", args=[campaign.pk])
        # Warm the signed-in session before measuring page queries.
        client.get(address)

        with CaptureQueriesContext(connection) as few:
            assert client.get(address).status_code == 200

        for index in range(3):
            more = found_gang(
                f"More {index}",
                gangs[0].gang_type,
                owner=User.objects.create_user(f"u{index}"),
            )
            join_campaign(more, campaign)
            assign_asset(add_asset(campaign, old_ruins), more)

        with CaptureQueriesContext(connection) as more_queries:
            body = client.get(address).content.decode()

        assert "More 2" in body
        from n26.tests.fixtures import island_props

        rows = island_props(body, "campaign-gangs")["gangs"]
        assert (
            sum(
                bool(counter and counter["name"] == "Meat" and counter["adjustHref"])
                for row in rows
                for counter in row["counters"]
            )
            == 6
        )
        assert len(more_queries.captured_queries) == len(few.captured_queries)
        # Share the asset reader when populating action URLs so staged-content access is
        # checked once.
        assert (
            sum(
                "site_featureflag" in query["sql"] and STAGED_CONTENT in query["sql"]
                for query in more_queries.captured_queries
            )
            == 1
        )
