"""The campaign as a data structure of its own.

A campaign gets the treatment a gang does (design/gang-sheet.md): a plain
structure holding everything its page draws — the gangs at the table with
their money, their campaign counters and what they hold, every copy of every
pooled asset with its holder — built by ``render_campaign`` in a fixed
number of queries however many gangs are in it. The page is a renderer
over this; what the campaign *is* is asserted here.
"""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.models import Campaign
from n26.core.render import render_campaign
from n26.flags import CAMPAIGNS
from n26.library.authoring import (
    add_asset_kind,
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
    found_campaign,
    found_gang,
    grant_asset,
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
    """A Territory worth Reputation while held, with a named rule."""
    territory = core.asset_kinds.get(label_singular="Territory")
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
    """A Territory with income and nothing else."""
    territory = core.asset_kinds.get(label_singular="Territory")
    return create_asset("Toll Crossing", territory, income=20)


@pytest.fixture
def protection(campaign):
    """A Racket the arbitrator added to this campaign alone, so a second
    pooled kind sits beside the shared type's Territory."""
    racket = add_asset_kind(campaign.additions, "Racket", "pooled")
    return create_asset("Protection", racket)


@pytest.fixture
def gangs(gang_type, campaign):
    """Three gangs at the table, named out of alphabetical order so the
    sheet's sorting is seen to do something."""
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


class TestTheGangsTable:
    """One line per gang playing, sorted by name, carrying the gang's own
    money and the campaign's counters and assets by column."""

    def test_gangs_are_sorted_by_name_with_their_money(self, campaign, gangs):
        sheet = render_campaign(campaign)
        assert [line.name for line in sheet.gangs] == [
            "Pit of Teeth",
            "The Ashen Choir",
            "The Rust Kings",
        ]
        ash = line_named(sheet, "The Ashen Choir")
        assert ash.owner == "ash"
        assert ash.gang_type == "Escher"
        assert (ash.rating, ash.credits) == (gangs[1].rating, gangs[1].credits)
        assert ash.href == ""

    def test_reputation_leads_the_counter_columns(self, campaign, gang_type):
        """Reputation first however the counters sort; the rest by name.
        A gang joining carries the type's counter and the additions' at
        their opening values."""
        meat = create_counter("Meat")
        add_built_in(campaign.additions, meat, amount=2)
        gang = found_gang("Late", gang_type, owner=User.objects.create_user("late"))
        join_campaign(gang, campaign)

        sheet = render_campaign(campaign)

        assert sheet.counter_columns == ["Reputation", "Meat"]
        assert line_named(sheet, "Late").counters == [0, 2]

    def test_a_held_territory_counts_in_the_reading(self, campaign, gangs, old_ruins):
        """The same reading the gang sheet shows: stored value plus what a
        held asset contributes."""
        copy = add_asset(campaign, old_ruins)
        grant_asset(copy, gangs[1])
        reputation = gangs[1].assignments.get(counter__name="Reputation")
        tally(reputation, 2)

        sheet = render_campaign(campaign)

        assert line_named(sheet, "The Ashen Choir").counters == [3]
        assert line_named(sheet, "The Rust Kings").counters == [0]

    def test_a_gang_without_the_counter_reads_none(self, campaign, gangs):
        """A dash, never a blank: a gang whose card lacks the counter says
        so rather than reading as a zero."""
        from n26.core.models import Assignment

        Assignment.objects.filter(
            gang_root=gangs[2], counter__name="Reputation"
        ).update(archived=True)
        sheet = render_campaign(campaign)
        assert line_named(sheet, "Pit of Teeth").counters == [None]
        assert line_named(sheet, "The Ashen Choir").counters == [0]

    def test_assets_sit_under_their_kind_column(
        self, campaign, gangs, old_ruins, toll_crossing, protection
    ):
        """Every kind the campaign deals in is a column — the shared type's
        first, then the additions' — and a gang's possessions and holdings
        land under theirs. A held-one-each Settlement is every gang's."""
        ruins = add_asset(campaign, old_ruins)
        toll = add_asset(campaign, toll_crossing, name="The Sump Toll")
        racket = add_asset(campaign, protection)
        grant_asset(ruins, gangs[1])
        grant_asset(toll, gangs[1])
        grant_asset(racket, gangs[0])

        sheet = render_campaign(campaign)

        assert [(kind.plural, kind.pooled) for kind in sheet.asset_kinds] == [
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
        """Measured on wealth, as the join warning is: a gang whose rating
        alone passes the budget is marked."""
        profile = make_profile("Ganger", price=1200)
        hire_with_option(gangs[0], profile, "Vex")
        sheet = render_campaign(campaign)
        assert line_named(sheet, "The Rust Kings").over_budget
        assert not line_named(sheet, "The Ashen Choir").over_budget
        assert sheet.gangs_over_budget == 1


class TestTheAssetsTables:
    """One table per pooled kind, each copy with its name, income, boons
    in words, and holder."""

    def test_pooled_kinds_get_a_table_and_held_one_each_kinds_do_not(
        self, campaign, gangs, old_ruins, protection
    ):
        sheet = render_campaign(campaign)
        assert [table.plural for table in sheet.assets] == ["Territories", "Rackets"]
        assert all(table.copies == [] for table in sheet.assets)

    def test_a_copy_says_what_it_is_and_who_holds_it(
        self, campaign, gangs, old_ruins, arbitrator
    ):
        named = add_asset(campaign, old_ruins, name="Old Ruins by the sump")
        plain = add_asset(campaign, old_ruins)
        grant_asset(named, gangs[1])

        sheet = render_campaign(campaign, viewer=gangs[1].owner)
        (territories,) = sheet.assets
        by_name = {copy.name: copy for copy in territories.copies}

        held = by_name["Old Ruins by the sump"]
        assert held.copy_id == str(named.pk)
        assert held.asset_name == "Old Ruins"
        assert held.income == 30
        assert held.held and held.holder == "The Ashen Choir"
        assert held.holder_gang_id == str(gangs[1].pk)
        assert held.holder_yours
        assert any("Reputation" in boon for boon in held.boons)
        assert any("Salvage" in boon for boon in held.boons)

        unclaimed = by_name["Old Ruins"]
        assert unclaimed.copy_id == str(plain.pk)
        assert unclaimed.asset_name == ""
        assert not unclaimed.held and unclaimed.holder == ""
        assert (territories.held, territories.unclaimed) == (1, 1)
        assert (sheet.copies, sheet.copies_held, sheet.copies_unclaimed) == (2, 1, 1)

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
        assert sheet.additions == []


class TestTheQueryBudget:
    """A campaign of many gangs costs what a campaign of one does. The
    gangs are read together — one assignment fetch, one hydration pass,
    one modifier index — so adding gangs adds rows to queries already
    made and never a query of its own."""

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
        grant_asset(add_asset(campaign, old_ruins), first)
        sheet, few = self.measure(campaign)
        assert len(sheet.gangs) == 1

        for index in range(3):
            more = found_gang(
                f"More {index}", gang_type, owner=User.objects.create_user(f"u{index}")
            )
            join_campaign(more, campaign)
            hire(more, profile, f"Model {index}")
            grant_asset(add_asset(campaign, toll_crossing), more)
        sheet, again = self.measure(campaign)

        assert len(sheet.gangs) == 4
        assert again == few

    def test_the_page_costs_a_fixed_number_of_queries(
        self, client, campaign, gangs, old_ruins, arbitrator
    ):
        FeatureFlag.objects.create(
            slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
        )
        grant_asset(add_asset(campaign, old_ruins), gangs[0])
        client.force_login(arbitrator)
        address = reverse("n26-campaign", args=[campaign.pk])
        # The first request of a session writes the session row; that is
        # the sign-in's, not the page's, so it is paid before measuring.
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
            grant_asset(add_asset(campaign, old_ruins), more)

        with CaptureQueriesContext(connection) as more_queries:
            body = client.get(address).content.decode()

        assert "More 2" in body
        assert len(more_queries.captured_queries) == len(few.captured_queries)
