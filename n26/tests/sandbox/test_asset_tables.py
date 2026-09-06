"""Asset tables: a table of one Holding asset type's assets that a gang holds.

The core rulebook's Territory Selection Table is the shape
(design/house-and-territory-tables.md): the Arbitrator rolls a D66 on a
table of Territories, and every roll the die can make lands on exactly one
of them. A table is an assignable a gang holds, because holding one is
what says the gang may roll on it — and a gang holds one the three ways
it holds anything: built into its campaign type as the table is created,
given by a modifier, or built into a campaign's additions. It draws no
line anywhere.

What this file holds still: the shared coverage check names gaps,
overlaps and bandless rows in words, and is what the picklist editor
already ran; a table on a Possession asset type and an entry of another
asset type are refused; creating a table builds it into its campaign type
and archiving, unarchiving and deleting follow a possession's lifecycle; a
gang joining a campaign of the type holds the table as a stored
assignment and a pick may grant one as a computed fact; neither the gang
sheet, the campaign page nor the print view draws it; and the seed
creates the Territory Selection Table once, whole, and built in.
"""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core import select
from n26.core.card import build_gang_card, build_modifier_index
from n26.core.effects import _Facts, compute, compute_gang
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_campaign, render_gang
from n26.flags import CAMPAIGNS
from n26.library.authoring import (
    add_asset_table_entry,
    add_asset_type,
    add_picklist_member,
    create_asset,
    create_asset_table,
    create_campaign_type,
    delete_content,
    remove_asset_table_entry,
)
from n26.library.core_campaign import CAMPAIGN_TYPE, seed_core_campaign
from n26.library.models import (
    AssetTable,
    AssetTableEntry,
    CampaignType,
    DefaultAssignment,
    Dice,
)
from n26.library.models.slots import band_coverage
from n26.library.prose import sentence_for
from n26.library.specs import specs
from n26.library.territory_table import ENTRIES, TABLE, seed_territory_table
from n26.tests.sandbox.actions import (
    add_built_in,
    choose,
    create_pickable,
    create_picklist,
    create_slot,
    create_slot_type,
    ef_adds,
    found_campaign,
    found_gang,
    join_campaign,
    modifier,
    remove,
    targets_gang_alone,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def dominion(default_pack):
    """A campaign type with a Holding asset type and a Possession one, and
    two Territories to put on a table."""
    campaign_type = create_campaign_type("Dominion")
    territory = add_asset_type(
        campaign_type, "Territory", "pooled", label_plural="Territories"
    )
    settlement = add_asset_type(campaign_type, "Settlement", "held-one-each")
    return {
        "type": campaign_type,
        "territory": territory,
        "settlement": settlement,
        "ruins": create_asset("Old Ruins", territory),
        "den": create_asset("Bullet Den", territory),
    }


@pytest.fixture
def d6_table(dominion):
    return create_asset_table("Dominion Territories", dominion["territory"], dice="d6")


@pytest.fixture
def arbitrator(db):
    return User.objects.create_user("arbitrator")


@pytest.fixture
def campaigns_open():
    return FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )


def gang_computed(gang):
    card = build_gang_card(gang)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return card, compute_gang(card, index)


def gang_facts(gang):
    """The gang as its own scopes see it: stored facts with the computed
    grants layered on, the way each round of ``compute`` reads them."""
    card = build_gang_card(gang)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return _Facts(card, compute(card, index)).model()


def names(contributions):
    return [contribution.name for contribution in contributions]


class Row:
    """A band with nothing else on it, for checking coverage without rows."""

    def __init__(self, roll_low=None, roll_high=None):
        self.roll_low, self.roll_high = roll_low, roll_high


# --- The shared coverage check ---------------------------------------------


class TestTheCoverageCheck:
    """One check for every band table: every roll the die can make lands
    on exactly one row. Gaps, overlaps and rows with no band are named,
    and a die of nothing has no rolls to cover."""

    def test_a_whole_d66_table_covers_every_roll_once(self):
        rows = [Row(low, high) for low, high, _ in ENTRIES]
        said = band_coverage(Dice.D66, rows)
        assert said.whole
        assert (said.covered, said.total) == (36, 36)
        assert said.unclaimed == [] and said.doubled == [] and said.bandless == []

    def test_a_gap_names_the_unclaimed_rolls(self):
        said = band_coverage(Dice.D6, [Row(1, 2), Row(5, 6)])
        assert not said.whole
        assert said.unclaimed == [3, 4]

    def test_an_overlap_names_the_roll_and_both_rows(self):
        first, second = Row(1, 3), Row(3, 6)
        said = band_coverage(Dice.D6, [first, second])
        assert not said.whole
        assert said.doubled == [(3, [first, second])]

    def test_a_band_outside_the_die_claims_nothing(self):
        """A D66 has no 37: a band running 37-40 covers no roll at all."""
        said = band_coverage(Dice.D66, [Row(37, 40)])
        assert said.covered == 0
        assert said.unclaimed[:2] == [11, 12]

    def test_a_row_with_no_band_is_named_as_never_rolled(self):
        bare = Row()
        said = band_coverage(Dice.D6, [Row(1, 6), bare])
        assert not said.whole
        assert said.bandless == [bare]

    def test_an_unrolled_table_has_no_rolls_to_cover(self):
        said = band_coverage("", [Row(), Row()])
        assert (said.total, said.covered) == (0, 0)
        assert len(said.bandless) == 2

    def test_the_picklist_editor_reads_the_same_check(self, default_pack):
        """The picklist table page's coverage is this function on the
        list's members — the one statement of the rule."""
        from n26.library.views import coverage

        slot_type = create_slot_type("Injury")
        table = create_picklist("Injuries", slot_type, dice="d6", roll_selects="band")
        add_picklist_member(table, create_pickable("Eye", slot_type), roll_low=1)
        add_picklist_member(table, create_pickable("Leg", slot_type), roll_low=3)

        said = coverage(table)

        assert said.unclaimed == [2, 4, 5, 6]
        assert said.covered == 2


# --- Refusals ------------------------------------------------------------


class TestWhatATableRefuses:
    def test_a_table_on_a_possession_asset_type_is_refused_in_words(self, dominion):
        with pytest.raises(ValidationError, match="Possession asset type"):
            create_asset_table("Settlements", dominion["settlement"])
        table = AssetTable(name="Settlements", asset_type=dominion["settlement"])
        with pytest.raises(ValidationError, match="nothing to roll for"):
            table.clean()
        assert not AssetTable.objects.filter(name="Settlements").exists()

    def test_an_entry_of_another_asset_type_is_refused_in_words(
        self, dominion, d6_table
    ):
        racket_type = add_asset_type(dominion["type"], "Racket", "pooled")
        racket = create_asset("Protection", racket_type)
        with pytest.raises(ValidationError, match="lists Territories"):
            add_asset_table_entry(d6_table, racket, roll_low=1)
        entry = AssetTableEntry(table=d6_table, asset=racket)
        with pytest.raises(ValidationError, match="lists Territories"):
            entry.clean()

    def test_a_band_on_an_unrolled_table_is_refused(self, dominion):
        table = create_asset_table("In order", dominion["territory"])
        with pytest.raises(ValidationError, match="names no dice"):
            add_asset_table_entry(table, dominion["ruins"], roll_low=1)
        assert table.landing(1) is None

    def test_a_band_running_downwards_is_refused(self, dominion, d6_table):
        with pytest.raises(ValidationError, match="runs upwards"):
            add_asset_table_entry(d6_table, dominion["ruins"], roll_low=4, roll_high=2)

    def test_the_picker_offers_only_the_tables_own_asset_type(self, dominion, d6_table):
        racket_type = add_asset_type(dominion["type"], "Racket", "pooled")
        create_asset("Protection", racket_type)
        assert set(d6_table.may_list) == {dominion["ruins"], dominion["den"]}

    def test_a_table_needs_a_name(self, dominion):
        with pytest.raises(ValidationError, match="needs a name"):
            create_asset_table("  ", dominion["territory"])


# --- Entries and rolling -----------------------------------------------------


class TestEntries:
    def test_entries_claim_bands_and_a_roll_lands_on_one(self, dominion, d6_table):
        ruins = add_asset_table_entry(
            d6_table, dominion["ruins"], roll_low=1, roll_high=3
        )
        den = add_asset_table_entry(d6_table, dominion["den"], roll_low=4, roll_high=6)

        assert (ruins.band, den.band) == ("1-3", "4-6")
        assert d6_table.coverage().whole
        assert d6_table.landing(2) == ruins
        assert d6_table.landing(6) == den
        assert d6_table.landing(7) is None

    def test_a_band_of_one_roll_is_the_low_roll_alone(self, dominion, d6_table):
        entry = add_asset_table_entry(d6_table, dominion["ruins"], roll_low=5)
        assert (entry.roll_low, entry.roll_high, entry.band) == (5, 5, "5")

    def test_an_entry_joins_its_tables_pack_and_positions_follow(
        self, dominion, d6_table, default_pack
    ):
        first = add_asset_table_entry(d6_table, dominion["ruins"], roll_low=1)
        second = add_asset_table_entry(d6_table, dominion["den"], roll_low=2)
        assert (first.position, second.position) == (0, 1)
        assert first.pack == default_pack

    def test_removing_an_entry_leaves_the_asset(self, dominion, d6_table):
        entry = add_asset_table_entry(d6_table, dominion["ruins"], roll_low=1)
        remove_asset_table_entry(entry)
        assert not d6_table.entries.exists()
        assert dominion["ruins"].pk


# --- Built into its campaign type ------------------------------------------


class TestATableIsBuiltIntoItsCampaignType:
    """Created, the table is built into the type that gives it, the way a
    possession is; archived or deleted, it is taken out; unarchived, the
    same membership comes back."""

    def test_creating_a_table_builds_it_in(self, dominion, d6_table, default_pack):
        (member,) = dominion["type"].built_in_members
        assert member.assignable == d6_table
        assert member.pack == default_pack
        assert dominion["type"].built_ins.name == "Dominion built-ins"

    def test_the_picker_never_offers_a_table_by_hand(self):
        offered = specs()["add_built_in"].fields["thing"].over
        assert "asset_table" not in offered
        assert "asset" not in offered
        assert AssetTable.offered_as_built_in is False
        assert AssetTable.takes_built_ins is False

    def test_deleting_a_table_takes_it_out(self, dominion, d6_table):
        add_asset_table_entry(d6_table, dominion["ruins"], roll_low=1)
        delete_content(d6_table)
        assert not AssetTable.objects.filter(pk=d6_table.pk).exists()
        assert list(dominion["type"].built_in_members) == []
        # The entries went with the table; the assets stayed.
        assert not AssetTableEntry.objects.exists()
        assert dominion["ruins"].pk

    def test_archiving_before_anything_materialised_deletes_the_member(
        self, dominion, d6_table
    ):
        d6_table.archive()
        assert list(dominion["type"].built_in_members) == []
        assert not DefaultAssignment.objects.filter(asset_table=d6_table).exists()

        d6_table.unarchive()

        assert [m.assignable for m in dominion["type"].built_in_members] == [d6_table]

    def test_archiving_after_a_gang_holds_it_archives_and_unarchiving_revives(
        self, dominion, d6_table, arbitrator, gang_type, owner
    ):
        campaign = found_campaign("Dust Falls", dominion["type"], owner=arbitrator)
        gang = found_gang("The Sump Dogs", gang_type, owner=owner)
        join_campaign(gang, campaign)
        (member,) = DefaultAssignment.objects.filter(asset_table=d6_table)

        d6_table.archive()
        member.refresh_from_db()
        assert member.archived
        assert list(dominion["type"].built_in_members) == []

        d6_table.unarchive()

        member.refresh_from_db()
        assert not member.archived
        assert DefaultAssignment.objects.filter(asset_table=d6_table).count() == 1
        # The gang still holds the one copy it was given.
        assert (
            gang.assignments.filter(asset_table=d6_table, archived=False).count() == 1
        )

    def test_a_table_in_a_campaigns_own_pack_is_given_by_its_additions(
        self, dominion, arbitrator, campaigns_open
    ):
        campaign = found_campaign("Dust Falls", dominion["type"], owner=arbitrator)
        with pytest.raises(ValueError, match="own pack"):
            create_asset_table("Ours", dominion["territory"], pack=campaign.pack)
        table = create_asset_table(
            "Ours",
            dominion["territory"],
            pack=campaign.pack,
            given_by=campaign.additions,
        )
        assert [m.assignable for m in campaign.additions.built_in_members] == [table]
        assert dominion["type"].built_in_members.filter(asset_table=table).count() == 0


# --- Held by a gang -----------------------------------------------------------


class TestAGangHoldsTheTable:
    """Joining a campaign of the type puts the table on the gang as a
    stored assignment; a pick may grant one as a computed fact; both read
    as "holds this table" on the gang's facts, and neither draws a line."""

    @pytest.fixture
    def campaign(self, dominion, d6_table, arbitrator):
        return found_campaign("Dust Falls", dominion["type"], owner=arbitrator)

    @pytest.fixture
    def gang(self, gang_type, owner):
        return found_gang("The Sump Dogs", gang_type, owner=owner, budget=1000)

    def test_joining_stores_the_table_on_the_gang(self, gang, campaign, d6_table):
        membership = join_campaign(gang, campaign)

        (held,) = gang.assignments.filter(asset_table=d6_table, archived=False)
        assert held.gang == gang
        assert held.caused_by_id == membership.type_carrier_id
        assert select.Has(d6_table).matches(build_gang_card(gang).model_matchable())
        gang.refresh_from_db()
        assert gang.rating == 0
        assert_reconciled(gang)

    def test_a_pick_may_grant_a_table_and_taking_it_back_removes_it(
        self, dominion, gang_type, owner, default_pack
    ):
        """A journal's table reaches every gang of its House through a
        modifier on the House pick: targets the gang alone, gives the
        table. Un-picking retracts it."""
        journal = create_asset_table(
            "Goliath Territories", dominion["territory"], dice="d6"
        )
        slot_type = create_slot_type("House")
        goliath = create_pickable("Goliath", slot_type)
        modifier(
            "Goliath: the House table",
            targets_gang_alone(),
            ef_adds(journal),
            carried_by=goliath,
        )
        houses = create_picklist("Houses", slot_type, members=[goliath])
        slot = create_slot("House", slot_type, houses, assigned_to="gang")
        add_built_in(gang_type, slot)
        gang = found_gang("Irontooth", gang_type, owner=owner, budget=1000)

        _, computed = gang_computed(gang)
        assert names(computed.tables) == []
        assert not select.Has(journal).matches(gang_facts(gang))
        (choice,) = computed.choices
        choose(choice.anchor.assignment, goliath)

        _, computed = gang_computed(gang)
        assert names(computed.tables) == ["Goliath Territories"]
        assert select.Has(journal).matches(gang_facts(gang))
        # A grant, not a stored assignment: nothing was written.
        assert not gang.assignments.filter(asset_table=journal).exists()
        assert "Goliath Territories" not in str(render_gang(gang).rows)

        remove(Assignment.objects.get(pickable=goliath, archived=False))

        _, computed = gang_computed(gang)
        assert names(computed.tables) == []
        assert not select.Has(journal).matches(gang_facts(gang))
        gang.refresh_from_db()
        assert gang.rating == 0
        assert_reconciled(gang)

    def test_a_table_may_be_given_to_the_gang_and_nothing_else(self, d6_table):
        from n26.library.models import AddsAssignable
        from n26.library.models.modifier import GANG, MODEL, WEAPON_PROFILE

        grant = AddsAssignable(asset_table=d6_table)
        assert grant.accepts(GANG)
        assert not grant.accepts(MODEL)
        assert not grant.accepts(WEAPON_PROFILE)
        assert "asset_table" in specs()["ef_adds"].fields["thing"].over

    def test_the_grant_reads_as_a_table_the_gang_may_roll_on(self, d6_table):
        row = modifier("Gives the table", targets_gang_alone(), ef_adds(d6_table))
        sentence = sentence_for(row, carriage=None)
        assert sentence.text == (
            "The gang gains the Dominion Territories table, and may roll on it."
        )


# --- Nothing draws it ---------------------------------------------------------


class TestNothingDrawsATable:
    """The gang sheet, the campaign block on it, the campaign page and
    the print view all leave the table out; the sheet costs the same
    with it as without."""

    @pytest.fixture
    def held(self, dominion, d6_table, arbitrator, gang_type, owner, campaigns_open):
        create_asset("Settlement", dominion["settlement"])
        campaign = found_campaign("Dust Falls", dominion["type"], owner=arbitrator)
        gang = found_gang("The Sump Dogs", gang_type, owner=owner, budget=1000)
        join_campaign(gang, campaign)
        return campaign, gang

    def test_the_gang_sheet_and_its_campaign_block_leave_it_out(self, held):
        campaign, gang = held
        sheet = render_gang(gang)
        assert "Dominion Territories" not in str(sheet.rows)
        assert "Dominion Territories" not in str(sheet.rules)
        assert "Dominion Territories" not in str(sheet.campaign)
        # The possession it was given beside is drawn as before.
        assert "Settlement" in str(sheet.campaign.lines)

    def test_the_pages_leave_it_out(self, client, held, arbitrator):
        campaign, gang = held
        client.force_login(gang.owner)
        sheet = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        paper = client.get(reverse("n26-print", args=[gang.pk])).content.decode()
        client.force_login(arbitrator)
        page = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()

        assert "Settlement" in sheet
        for body in (sheet, paper, page):
            assert "Dominion Territories" not in body
        assert "Dominion Territories" not in str(render_campaign(campaign))

    def test_the_sheet_costs_the_same_however_many_tables_are_held(
        self, dominion, arbitrator, gang_type, owner, default_pack
    ):
        """A kind an assignment names is hydrated in one narrow pass, so a
        gang holding three tables builds its sheet in the same number of
        queries as a gang holding one — the cost is per kind, never per
        table."""
        one = create_campaign_type("Dominion with one")
        turf = add_asset_type(one, "Turf", "pooled")
        create_asset_table("Turf table", turf, dice="d6")
        for name in ("First", "Second", "Third"):
            create_asset_table(name, dominion["territory"], dice="d6")
        gangs = []
        for name, campaign_type in (("Three", dominion["type"]), ("One", one)):
            campaign = found_campaign(name, campaign_type, owner=arbitrator)
            gang = found_gang(name, gang_type, owner=owner, budget=1000)
            join_campaign(gang, campaign)
            gangs.append(gang)
        three, single = gangs
        assert three.assignments.filter(asset_table__isnull=False).count() == 3
        assert single.assignments.filter(asset_table__isnull=False).count() == 1

        counts = []
        for gang in (three, single):
            with CaptureQueriesContext(connection) as captured:
                render_gang(gang)
            counts.append(len(captured.captured_queries))

        assert counts[0] == counts[1]


# --- The Territory Selection Table --------------------------------------------


class TestTheTerritorySelectionTable:
    """What every install ships with: one D66 table of the core
    rulebook's Territories, whole, built into the Territory campaign type.
    The data migration never runs under the test settings, so the same
    code seeds it here."""

    def test_it_creates_the_table_its_entries_and_the_territories(self, default_pack):
        lines, made = seed_territory_table(apps)

        (table,) = AssetTable.objects.filter(name=TABLE)
        core = CampaignType.objects.get(name=CAMPAIGN_TYPE)
        assert table.dice == Dice.D66
        assert table.asset_type.campaign_type == core
        assert table.asset_type.label_singular == "Territory"
        assert table.pack == default_pack
        entries = list(table.entries.select_related("asset").order_by("position"))
        assert [(e.roll_low, e.roll_high, e.asset.name) for e in entries] == list(
            ENTRIES
        )
        assert len(entries) == 18
        assert table.coverage(entries).whole
        assert table.landing(34).asset.name == "Corpse Farm"
        assert all(e.asset.asset_type == table.asset_type for e in entries)
        assert any("Territory Selection Table" in line for line in lines)
        assert [member.assignable for member in made] == [table]

    def test_it_is_built_into_the_territory_campaign_type(self, default_pack):
        seed_territory_table(apps)
        core = CampaignType.objects.get(name=CAMPAIGN_TYPE)
        (member,) = core.built_in_members.filter(asset_table__isnull=False)
        assert member.assignable.name == TABLE
        # The type's other built-ins are exactly what the core seed gives.
        assert [str(m.assignable) for m in core.built_in_members] == [
            "Reputation",
            "Settlement",
            "Income",
            TABLE,
        ]

    def test_running_it_again_creates_nothing(self, default_pack):
        seed_territory_table(apps)
        before = (
            AssetTable.objects.count(),
            AssetTableEntry.objects.count(),
            DefaultAssignment.objects.count(),
        )

        lines, made = seed_territory_table(apps)

        assert (lines, made) == ([], [])
        assert before == (
            AssetTable.objects.count(),
            AssetTableEntry.objects.count(),
            DefaultAssignment.objects.count(),
        )

    def test_it_reuses_a_territory_already_standing(self, default_pack):
        seed_core_campaign(apps)
        core = CampaignType.objects.get(name=CAMPAIGN_TYPE)
        territory = core.asset_types.get(label_singular="Territory")
        ruins = create_asset("Old Ruins", territory, income=30)

        seed_territory_table(apps)

        entry = AssetTableEntry.objects.get(roll_low=63)
        assert entry.asset == ruins
        assert ruins.income == 30

    def test_a_same_named_asset_of_another_type_is_skipped_and_said(self, default_pack):
        """An asset's name is unique in its pack whatever its type, so a
        Settlement called Old Ruins is found rather than collided with;
        its entry is left out and the line says so."""
        seed_core_campaign(apps)
        core = CampaignType.objects.get(name=CAMPAIGN_TYPE)
        settlement = core.asset_types.get(label_singular="Settlement")
        create_asset("Old Ruins", settlement)

        lines, _ = seed_territory_table(apps)

        table = AssetTable.objects.get(name=TABLE)
        assert table.entries.count() == 17
        assert not table.entries.filter(roll_low=63).exists()
        assert any(line.startswith("skipped Old Ruins") for line in lines)
        assert not table.coverage().whole

    def test_a_gang_joining_a_territory_campaign_holds_it(
        self, default_pack, arbitrator, gang_type, owner
    ):
        seed_territory_table(apps)
        core = CampaignType.objects.get(name=CAMPAIGN_TYPE)
        table = AssetTable.objects.get(name=TABLE)
        campaign = found_campaign("Dust Falls", core, owner=arbitrator)
        gang = found_gang("The Sump Dogs", gang_type, owner=owner, budget=1000)

        join_campaign(gang, campaign)

        assert gang.assignments.filter(asset_table=table, archived=False).count() == 1
        assert select.Has(table).matches(build_gang_card(gang).model_matchable())


# --- The authoring pages ------------------------------------------------------


class TestTheAuthoringPages:
    """A Holding asset type lists its tables on the campaign type's page
    with a form that adds one; a table's own page lists its entries with
    their bands under the coverage check, adds one, and takes one off."""

    @pytest.fixture
    def author(self, client):
        user = User.objects.create_user("author", is_staff=True)
        client.force_login(user)
        return user

    def test_the_type_page_lists_tables_under_holding_types_only(
        self, author, client, dominion, d6_table
    ):
        body = client.get(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/"
        ).content.decode()

        assert "Territory tables" in body
        assert "Dominion Territories" in body
        assert "rolled on a D6" in body
        assert f'href="/n26/authoring/asset-table/{d6_table.pk}/"' in body
        assert "Settlement tables" not in body
        assert f'name="add-asset-table-{dominion["territory"].pk}-dice"' in body
        assert f'name="add-asset-table-{dominion["settlement"].pk}-dice"' not in body

    def test_the_type_page_adds_a_table_and_builds_it_in(
        self, author, client, dominion, default_pack
    ):
        territory = dominion["territory"]
        page = f"/n26/authoring/campaign-type/{dominion['type'].pk}/"
        response = client.post(
            page,
            {
                "act": "add-asset-table",
                "part": str(territory.pk),
                f"add-asset-table-{territory.pk}-name": "Dominion Territories",
                f"add-asset-table-{territory.pk}-dice": "d66",
            },
        )

        table = AssetTable.objects.get(name="Dominion Territories")
        assert response.status_code == 302
        assert (table.asset_type, table.dice, table.pack) == (
            territory,
            "d66",
            default_pack,
        )
        campaign_type = CampaignType.objects.get(pk=dominion["type"].pk)
        assert [m.assignable for m in campaign_type.built_in_members] == [table]
        body = client.get(page, follow=True).content.decode()
        assert "Added Dominion Territories under Territory." in body
        # The member row names where it came from and offers no Remove.
        assert "delete the table to remove it" in body

    def test_a_table_under_a_possession_type_is_a_mistyped_address(
        self, author, client, dominion
    ):
        """The page draws no tables block under a Possession asset type, so
        a post naming one is not an author's mistake to be refused in
        words — it is an address nothing on the page leads to."""
        settlement = dominion["settlement"]
        response = client.post(
            f"/n26/authoring/campaign-type/{dominion['type'].pk}/",
            {
                "act": "add-asset-table",
                "part": str(settlement.pk),
                f"add-asset-table-{settlement.pk}-name": "Settlements",
            },
        )
        assert response.status_code == 404
        assert not AssetTable.objects.filter(name="Settlements").exists()

    def test_the_table_page_lists_entries_under_the_coverage_check(
        self, author, client, dominion, d6_table
    ):
        add_asset_table_entry(d6_table, dominion["ruins"], roll_low=1, roll_high=3)
        page = f"/n26/authoring/asset-table/{d6_table.pk}/"

        body = client.get(page).content.decode()

        assert "3 of 6 rolls covered — 4, 5, 6 unclaimed." in body
        assert "1-3 — Old Ruins" in body
        assert "Rolled on a D6." in body
        # The trail runs through the campaign type, as an asset's does.
        assert f'href="/n26/authoring/campaign-type/{dominion["type"].pk}/"' in body

        response = client.post(
            page,
            {"asset": str(dominion["den"].pk), "roll_low": "4", "roll_high": "6"},
        )

        assert response.status_code == 302
        body = client.get(page).content.decode()
        assert "6 of 6 rolls covered." in body
        assert "4-6 — Bullet Den" in body

    def test_the_table_page_offers_only_the_types_assets(
        self, author, client, dominion, d6_table
    ):
        racket_type = add_asset_type(dominion["type"], "Racket", "pooled")
        racket = create_asset("Protection", racket_type)

        body = client.get(f"/n26/authoring/asset-table/{d6_table.pk}/").content.decode()
        assert "Old Ruins" in body
        assert "Protection" not in body

        response = client.post(
            f"/n26/authoring/asset-table/{d6_table.pk}/",
            {"asset": str(racket.pk), "roll_low": "1"},
        )
        assert response.status_code == 200
        assert not d6_table.entries.exists()

    def test_an_entry_is_taken_off_at_its_own_address(
        self, author, client, dominion, d6_table
    ):
        entry = add_asset_table_entry(d6_table, dominion["ruins"], roll_low=1)
        address = reverse("authoring-asset-table-entry-remove", args=[entry.pk])

        body = client.get(address).content.decode()
        assert "Take Old Ruins off Dominion Territories?" in body

        response = client.post(address)

        assert response.status_code == 302
        assert not d6_table.entries.exists()
        assert dominion["ruins"].pk

    def test_deleting_a_table_returns_to_its_types_page(
        self, author, client, dominion, d6_table
    ):
        response = client.post(f"/n26/authoring/asset-table/{d6_table.pk}/delete/")
        assert response.status_code == 302
        assert response.url == f"/n26/authoring/campaign-type/{dominion['type'].pk}/"
        assert not AssetTable.objects.filter(pk=d6_table.pk).exists()
        assert list(dominion["type"].built_in_members) == []

    def test_the_menu_offers_no_asset_tables(self, author, client):
        body = client.get("/n26/authoring/").content.decode()
        assert "asset table" not in body.lower()
