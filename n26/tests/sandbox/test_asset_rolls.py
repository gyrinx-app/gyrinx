"""Rolling on an asset table in a campaign.

The core rulebook's two rolls (design/house-and-territory-tables.md): the
Arbitrator generates the campaign's pool of territories by rolling on the
Territory table, three per player, and the same territory may come up more
than once; each gang's starting territory is rolled for the gang directly,
on the Territory table or on a table of its own House. Both rolls read the
same fact — who holds the table. The campaign holds the tables built into
its type and its additions, and rolls its pool on those; a gang holds the
tables on its card, stored or granted, and rolls its starting territory on
those. The arbitrator opens a table to every gang by building it into the
campaign's additions, and writes tables of their own into the campaign's
pack.

What this file holds still: a pool roll adds one unheld copy of what the
roll lands on and one line in the log; a starting roll adds the copy held
by the gang, with GAINED on the gang's ledger; an entered roll is checked
against the die; a gap, a list without dice, and a table the roller does
not hold are refused in words; opening a table widens the catalogue and
closing narrows it again without taking anything back; a table the
arbitrator writes reaches every member gang and no other campaign; the
controls are the arbitrator's alone and take the asset type's own word;
and the campaign page costs the same however many gangs and tables it
has.
"""

import json
import random
import re

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import tables_held_by, tables_in_play
from n26.core.history import campaign_history
from n26.core.models import CampaignAsset, CampaignEvent, LedgerEvent
from n26.core.operations import ROLL_ENTERED, Refusal
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_campaign, render_gang
from n26.core.views.campaigns import _holding_assets
from n26.flags import BUILT_IN_PROPAGATION, CAMPAIGNS
from n26.library.authoring import (
    add_asset_table_entry,
    create_asset,
    create_asset_table,
    create_campaign_type,
    create_pack,
)
from n26.library.core_campaign import CAMPAIGN_TYPE, seed_core_campaign
from n26.library.models import AssetTable, AssetTableEntry, CampaignType
from n26.library.territory_table import TABLE, seed_territory_table
from n26.tests.sandbox.actions import (
    add_built_in,
    close_table,
    create_campaign_table,
    create_gang_type,
    create_pickable,
    create_picklist,
    create_slot,
    create_slot_type,
    ef_adds,
    found_campaign,
    found_gang,
    join_campaign,
    modifier,
    open_table,
    roll_asset,
    targets_gang_alone,
)

pytestmark = pytest.mark.django_db


def sentences(acts):
    return ["".join(span.text for span in act.spans) for act in acts]


@pytest.fixture
def arbitrator(db):
    return User.objects.create_user("arbitrator")


@pytest.fixture
def campaigns_open(db):
    return FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )


@pytest.fixture
def propagating(db):
    return FeatureFlag.objects.create(
        slug=BUILT_IN_PROPAGATION,
        name="Built-in propagation",
        availability=Availability.EVERYONE,
    )


@pytest.fixture
def core(default_pack):
    """The Territory campaign type as it ships, with the Territory Selection
    Table built in: a D66 over eighteen territories, every roll covered."""
    seed_core_campaign(apps)
    seed_territory_table(apps)
    return CampaignType.objects.get(name=CAMPAIGN_TYPE)


@pytest.fixture
def territory(core):
    return core.asset_types.get(label_singular="Territory")


@pytest.fixture
def selection_table(core):
    return AssetTable.objects.get(name=TABLE)


@pytest.fixture
def supertype(default_pack):
    """The hidden Gang supertype slot, and Goliath and Escher as its
    markers — the shape a Clan House gang type builds in."""
    slot_type = create_slot_type(
        "Gang supertype", plural_name="Gang supertypes", allows_repeats=False
    )
    houses = {name: create_pickable(name, slot_type) for name in ("Goliath", "Escher")}
    picklist = create_picklist(
        "Gang supertypes", slot_type, members=list(houses.values())
    )
    slot = create_slot(
        "Gang supertype", slot_type, picklist, assigned_to="gang", hidden=True
    )
    return slot, houses


@pytest.fixture
def journal(territory, supertype, default_pack):
    """House of Chains: six Goliath territories on a D6 table, given to
    every gang that has picked Goliath. In a system pack of its own, so
    its territories are not the campaign's to add until the table is."""
    _, houses = supertype
    pack = create_pack("House of Chains", slug="house-of-chains")
    # A table in a pack of its own is given by no campaign type — the giver
    # has to share the pack — so it is written bare and granted by the
    # House pick alone.
    table = AssetTable.objects.create(
        name="Goliath Territories", asset_type=territory, dice="d6", pack=pack
    )
    names = [
        "Amneo-vats",
        "Slag Furnace",
        "Meat Locker",
        "Iron Forge",
        "Pit Fights",
        "Chem Pit",
    ]
    for roll, name in enumerate(names, start=1):
        asset = create_asset(name, territory, pack=pack)
        add_asset_table_entry(table, asset, roll_low=roll)
    modifier(
        "Goliath: the House table",
        targets_gang_alone(),
        ef_adds(table),
        carried_by=houses["Goliath"],
    )
    return table


@pytest.fixture
def goliath(supertype):
    slot, houses = supertype
    gang_type = create_gang_type("Goliath")
    add_built_in(gang_type, slot, default_pickable=houses["Goliath"])
    return gang_type


@pytest.fixture
def escher(supertype):
    slot, houses = supertype
    gang_type = create_gang_type("Escher")
    add_built_in(gang_type, slot, default_pickable=houses["Escher"])
    return gang_type


@pytest.fixture
def campaign(core, arbitrator):
    return found_campaign("Dust Falls", core, owner=arbitrator)


@pytest.fixture
def slag_kings(campaign, goliath, owner):
    gang = found_gang("Slag Kings", goliath, owner=owner, budget=1000)
    join_campaign(gang, campaign)
    return gang


@pytest.fixture
def wild_cats(campaign, escher):
    gang = found_gang(
        "Wild Cats", escher, owner=User.objects.create_user("cats"), budget=1000
    )
    join_campaign(gang, campaign)
    return gang


def rolled_events(campaign):
    return list(campaign.events.filter(kind=CampaignEvent.Kind.ASSET_ROLLED))


# --- The pool roll -----------------------------------------------------------


class TestThePoolRoll:
    """The arbitrator rolls on a table the campaign holds; what the roll
    lands on joins the campaign, held by nobody, and the log says so in
    one line."""

    def test_a_roll_adds_one_unheld_copy_and_one_line(
        self, campaign, selection_table, arbitrator
    ):
        roll = roll_asset(campaign, selection_table, rng=random.Random(7))

        (kept,) = CampaignAsset.objects.filter(campaign=campaign)
        assert kept == roll.campaign_asset
        assert kept.holder is None
        assert kept.asset.name == selection_table.landing(roll.roll).asset.name
        assert roll.dice.label == "D66"
        (event,) = rolled_events(campaign)
        assert event.note == (
            f"Rolled {roll.roll} from the Territory Selection Table: {kept.asset.name}."
        )
        assert not campaign.events.filter(kind=CampaignEvent.Kind.ASSET_ADDED).exists()
        assert sentences(campaign_history(campaign))[-1] == (
            f"rolled {roll.roll} from the Territory Selection Table: {kept.asset.name}"
        )
        assert campaign_history(campaign)[-1].actor == "arbitrator"

    def test_an_entered_roll_lands_where_the_book_says_and_is_marked(
        self, campaign, selection_table
    ):
        roll = roll_asset(campaign, selection_table, rolled=34)

        assert roll.roll == 34
        assert roll.campaign_asset.asset.name == "Corpse Farm"
        (event,) = rolled_events(campaign)
        assert ROLL_ENTERED == "Manual roll."
        assert event.note == (
            f"Rolled 34 from the Territory Selection Table: Corpse Farm. {ROLL_ENTERED}"
        )
        assert sentences(campaign_history(campaign))[-1] == (
            "rolled 34 from the Territory Selection Table: Corpse Farm (manual roll)"
        )

    def test_a_stop_inside_a_name_does_not_cut_the_log_line(
        self, campaign, territory, goliath, owner
    ):
        """The manual-roll marker is taken off the note by name, so a gang
        or a table with a full stop in its own name keeps its whole line."""
        # The table first, so the gang holds it as it joins.
        table = create_campaign_table(campaign, territory, "No. 2 Turf", dice="d3")
        ruins = _holding_assets(campaign).get(name="Old Ruins")
        add_asset_table_entry(table, ruins, roll_low=1, roll_high=3)
        doc = found_gang("Dr. Skabb's Crew", goliath, owner=owner, budget=1000)
        join_campaign(doc, campaign)

        roll_asset(campaign, table, gang=doc, rolled=2)
        roll_asset(campaign, table, gang=doc)
        lines = sentences(campaign_history(campaign))
        assert (
            "rolled 2 from No. 2 Turf for Dr. Skabb's Crew: Old Ruins (manual roll)"
            in lines
        )
        assert any(
            line.startswith("rolled ")
            and line.endswith("from No. 2 Turf for Dr. Skabb's Crew: Old Ruins")
            for line in lines
        )

    def test_a_staged_entry_is_a_gap_for_a_reader_who_may_not_see_it(
        self, campaign, selection_table, arbitrator
    ):
        """The roll is where a territory is newly chosen, so staged content
        is held back there as at every discovery surface: the band reads as
        a gap, and a reader who may see staged content lands on it."""
        from n26.library.models import Asset

        farm = Asset.objects.get(name="Corpse Farm")
        farm.staged = True
        farm.save(update_fields=["staged"])

        with pytest.raises(Refusal, match="covers a roll of 34"):
            roll_asset(campaign, selection_table, rolled=34, actor=arbitrator)
        staff = User.objects.create_user("staff", is_staff=True)
        roll = roll_asset(campaign, selection_table, rolled=34, actor=staff)
        assert roll.campaign_asset.asset == farm

    def test_the_same_roll_twice_adds_two_copies(self, campaign, selection_table):
        roll_asset(campaign, selection_table, rolled=34)
        roll_asset(campaign, selection_table, rolled=34)

        assert (
            CampaignAsset.objects.filter(
                campaign=campaign, asset__name="Corpse Farm"
            ).count()
            == 2
        )
        assert len(rolled_events(campaign)) == 2

    def test_a_roll_the_die_cannot_make_is_refused(self, campaign, selection_table):
        with pytest.raises(Refusal, match="You cannot roll 37 on a D66."):
            roll_asset(campaign, selection_table, rolled=37)
        with pytest.raises(Refusal, match="You cannot roll 7 on a D66."):
            roll_asset(campaign, selection_table, rolled=7)
        assert not CampaignAsset.objects.filter(campaign=campaign).exists()
        assert rolled_events(campaign) == []

    def test_a_gap_in_the_table_refuses_the_roll_landing_in_it(
        self, campaign, territory
    ):
        holed = create_campaign_table(campaign, territory, "Holed", dice="d6")
        add_asset_table_entry(
            holed,
            create_asset("Sump", territory, pack=campaign.pack),
            roll_low=1,
            roll_high=3,
        )

        with pytest.raises(Refusal, match="Nothing on Holed covers a roll of 5"):
            roll_asset(campaign, holed, rolled=5)
        assert roll_asset(campaign, holed, rolled=2).campaign_asset.asset.name == "Sump"

    def test_a_list_without_dice_is_refused(self, campaign, territory):
        listed = create_campaign_table(campaign, territory, "Listed")
        with pytest.raises(
            Refusal, match="Listed cannot be rolled. It is a list with no dice."
        ):
            roll_asset(campaign, listed)

    def test_a_table_the_campaign_does_not_hold_is_refused(
        self, campaign, territory, default_pack
    ):
        other = create_campaign_type("Other")
        from n26.library.authoring import add_asset_type

        turf = add_asset_type(other, "Turf", "pooled")
        elsewhere = create_asset_table("Elsewhere", turf, dice="d6")
        add_asset_table_entry(
            elsewhere, create_asset("Yard", turf), roll_low=1, roll_high=6
        )

        with pytest.raises(Refusal, match="Elsewhere is not available to Dust Falls."):
            roll_asset(campaign, elsewhere, rolled=3)
        assert list(tables_in_play(campaign)) == [AssetTable.objects.get(name=TABLE)]


# --- The starting roll -------------------------------------------------------


class TestTheStartingRoll:
    """A gang rolls its starting territory on a table it holds. The House
    table reaches a Goliath gang through its pick; an Escher gang gets it
    only while the arbitrator has opened it to every gang."""

    def test_a_goliath_gang_rolls_on_its_house_table(
        self, campaign, journal, slag_kings, owner
    ):
        assert journal in tables_held_by(slag_kings, campaign)
        roll = roll_asset(campaign, journal, gang=slag_kings, rolled=1)

        kept = roll.campaign_asset
        kept.refresh_from_db()
        assert kept.asset.name == "Amneo-vats"
        assert kept.holder.gang == slag_kings
        (gained,) = LedgerEvent.objects.filter(
            gang=slag_kings, kind=LedgerEvent.Kind.GAINED
        )
        assert gained.campaign_asset == kept
        (event,) = rolled_events(campaign)
        assert event.note == (
            f"Rolled 1 from Goliath Territories for Slag Kings: Amneo-vats. {ROLL_ENTERED}"
        )
        slag_kings.refresh_from_db()
        assert slag_kings.rating == 0
        assert_reconciled(slag_kings)

    def test_an_escher_gang_is_refused_until_the_table_is_opened(
        self, campaign, journal, wild_cats, arbitrator, propagating, task_queue
    ):
        assert journal not in tables_held_by(wild_cats, campaign)
        with pytest.raises(
            Refusal,
            match="Wild Cats cannot roll for a territory from Goliath Territories. "
            "That table is not available to Wild Cats.",
        ):
            roll_asset(campaign, journal, gang=wild_cats, rolled=2)

        # Opening builds the table into the campaign's additions; the gangs
        # already playing are given it by the propagation pass that files.
        with task_queue.capture():
            open_table(campaign, journal)
        task_queue.deliver_all()

        assert journal in tables_held_by(wild_cats, campaign)
        roll = roll_asset(campaign, journal, gang=wild_cats, rolled=2)
        assert roll.campaign_asset.asset.name == "Slag Furnace"
        assert sentences(campaign_history(campaign))[-3:] == [
            "made the table Goliath Territories available to every gang",
            "rolled 2 from Goliath Territories for Wild Cats: Slag Furnace (manual roll)",
            "Slag Furnace went to Wild Cats",
        ]

        close_table(campaign, journal)

        assert journal not in tables_held_by(wild_cats, campaign)
        with pytest.raises(Refusal, match="Wild Cats cannot roll for"):
            roll_asset(campaign, journal, gang=wild_cats, rolled=3)
        # Nothing taken back: the territory it rolled is still held.
        roll.campaign_asset.refresh_from_db()
        assert roll.campaign_asset.holder.gang == wild_cats
        assert sentences(campaign_history(campaign))[-1] == (
            "withdrew the table Goliath Territories"
        )
        wild_cats.refresh_from_db()
        assert_reconciled(wild_cats)

    def test_the_starting_roll_is_independent_of_the_pool(
        self, campaign, selection_table, slag_kings
    ):
        roll_asset(campaign, selection_table, rolled=63)
        roll = roll_asset(campaign, selection_table, gang=slag_kings, rolled=63)

        ruins = CampaignAsset.objects.filter(campaign=campaign, asset__name="Old Ruins")
        assert ruins.count() == 2
        assert [kept.holder is not None for kept in ruins.order_by("created")] == [
            False,
            True,
        ]
        assert roll.campaign_asset.holder.gang == slag_kings

    def test_a_gang_outside_the_campaign_is_a_callers_mistake(
        self, campaign, selection_table, goliath, owner, core, arbitrator
    ):
        from n26.core.campaigns import campaign_operation
        from n26.core.models import CampaignMembership

        elsewhere = found_campaign("Elsewhere", core, owner=arbitrator)
        stranger = found_gang("Stranger", goliath, owner=owner, budget=1000)
        join_campaign(stranger, elsewhere)
        membership = CampaignMembership.objects.get(gang=stranger)
        with pytest.raises(ValueError, match="is not playing"):
            with campaign_operation(campaign, actor=arbitrator) as act:
                act.roll_asset(selection_table, membership=membership, rolled=11)


# --- Opening a table widens the catalogue ------------------------------------


class TestTheCatalogue:
    """What the Add control offers: the campaign type's assets and the
    campaign's own, plus every entry of every table the campaign holds."""

    def test_opening_a_table_makes_its_entries_addable_and_closing_narrows(
        self, campaign, journal, territory
    ):
        before = [asset.name for asset in _holding_assets(campaign)]
        assert "Old Ruins" in before
        assert "Amneo-vats" not in before

        open_table(campaign, journal)
        during = [asset.name for asset in _holding_assets(campaign)]
        assert "Old Ruins" in during
        assert "Amneo-vats" in during
        assert during.count("Amneo-vats") == 1

        close_table(campaign, journal)
        after = [asset.name for asset in _holding_assets(campaign)]
        assert after == before

    def test_an_opened_tables_entry_can_be_added_by_hand(
        self, client, campaign, journal, arbitrator, campaigns_open
    ):
        """The picker and the act read one rule: what the widened catalogue
        offers, Add territory accepts, though the asset sits in a pack the
        campaign does not otherwise see."""
        open_table(campaign, journal)
        vats = _holding_assets(campaign).get(name="Amneo-vats")
        client.force_login(arbitrator)
        response = client.post(
            reverse("n26-campaign-add-asset", args=[campaign.pk]),
            {"asset": str(vats.pk), "name": ""},
        )
        assert response.status_code == 302
        assert CampaignAsset.objects.filter(campaign=campaign, asset=vats).exists()

        # Closed again, the same asset is neither offered nor accepted.
        close_table(campaign, journal)
        response = client.post(
            reverse("n26-campaign-add-asset", args=[campaign.pk]),
            {"asset": str(vats.pk), "name": ""},
        )
        assert response.status_code == 200
        assert "not one this campaign deals in" in response.content.decode()
        assert CampaignAsset.objects.filter(campaign=campaign, asset=vats).count() == 1

    def test_opening_a_table_of_another_campaigns_type_is_refused(
        self, campaign, default_pack
    ):
        from n26.library.authoring import add_asset_type

        other = create_campaign_type("Other")
        turf = add_asset_type(other, "Turf", "pooled")
        elsewhere = create_asset_table("Elsewhere", turf, dice="d6")
        with pytest.raises(Refusal, match="does not deal in"):
            open_table(campaign, elsewhere)

    def test_the_types_own_table_is_not_the_arbitrators_to_close(
        self, campaign, selection_table
    ):
        assert open_table(campaign, selection_table) is None
        with pytest.raises(Refusal, match="It is included with Territory campaign"):
            close_table(campaign, selection_table)
        assert list(tables_in_play(campaign)) == [selection_table]

    def test_closing_keeps_the_member_a_gang_was_given_through_and_reopening_revives_it(
        self, campaign, journal, wild_cats, propagating, task_queue
    ):
        from n26.library.models import DefaultAssignment

        with task_queue.capture():
            first = open_table(campaign, journal)
        task_queue.deliver_all()
        assert journal in tables_held_by(wild_cats, campaign)

        # Wild Cats was given the table through the member, so every copy
        # names it as its provenance: closing archives rather than deletes,
        # and reopening revives that same member.
        close_table(campaign, journal)
        first.refresh_from_db()
        assert first.archived
        assert journal not in tables_in_play(campaign)
        again = open_table(campaign, journal)
        assert again.pk == first.pk
        assert DefaultAssignment.objects.filter(asset_table=journal).count() == 1
        assert journal in tables_in_play(campaign)

    def test_closing_a_member_nothing_came_from_deletes_it(self, campaign, journal):
        from n26.library.models import DefaultAssignment

        first = open_table(campaign, journal)
        close_table(campaign, journal)
        assert not DefaultAssignment.objects.filter(asset_table=journal).exists()
        assert open_table(campaign, journal).pk != first.pk


# --- A table of the campaign's own -------------------------------------------


class TestCreatingATable:
    """A table the arbitrator writes lands in the campaign's pack, built
    into the campaign's additions, and reaches every member gang and no
    other campaign."""

    def test_it_lands_in_the_campaigns_pack_built_in_and_held_by_every_gang(
        self, campaign, territory, slag_kings, wild_cats, propagating, task_queue
    ):
        with task_queue.capture():
            table = create_campaign_table(
                campaign, territory, "Dust Falls Turf", dice="d6"
            )
        task_queue.deliver_all()

        assert table.pack == campaign.pack
        assert [m.assignable for m in campaign.additions.built_in_members] == [table]
        assert table in tables_in_play(campaign)
        for gang in (slag_kings, wild_cats):
            assert table in tables_held_by(gang, campaign)
            assert gang.assignments.filter(asset_table=table, archived=False).exists()
            gang.refresh_from_db()
            assert_reconciled(gang)
        assert sentences(campaign_history(campaign))[-1] == (
            "created the table Dust Falls Turf"
        )

    def test_it_never_reaches_another_campaign(
        self, campaign, territory, core, arbitrator, goliath, owner
    ):
        table = create_campaign_table(campaign, territory, "Dust Falls Turf", dice="d6")
        elsewhere = found_campaign("Elsewhere", core, owner=arbitrator)
        stranger = found_gang("Stranger", goliath, owner=owner, budget=1000)
        join_campaign(stranger, elsewhere)

        assert table not in tables_in_play(elsewhere)
        assert table not in tables_held_by(stranger, elsewhere)
        assert core.built_in_members.filter(asset_table=table).count() == 0

    def test_a_table_from_a_former_campaign_is_not_offered_in_the_next(
        self, campaign, territory, core, arbitrator, goliath, owner
    ):
        """A gang keeps what a campaign gave it after it leaves, so the
        last arbitrator's table is still on its card — but it is that
        campaign's, and the next campaign never offers it."""
        from n26.core.operations import operation

        turf = create_campaign_table(campaign, territory, "Dust Falls Turf", dice="d6")
        ruins = _holding_assets(campaign).get(name="Old Ruins")
        add_asset_table_entry(turf, ruins, roll_low=1, roll_high=6)
        rover = found_gang("Rover", goliath, owner=owner, budget=1000)
        join_campaign(rover, campaign)
        assert turf in tables_held_by(rover, campaign)

        with operation(rover, actor=owner) as op:
            op.leave_campaign()
        elsewhere = found_campaign("Elsewhere", core, owner=arbitrator)
        join_campaign(rover, elsewhere)

        assert turf not in tables_held_by(rover, elsewhere)
        assert "Dust Falls Turf" not in str(
            render_campaign(elsewhere, viewer=arbitrator)
        )
        with pytest.raises(Refusal, match="cannot roll"):
            roll_asset(elsewhere, turf, gang=rover, rolled=1)

    def test_a_name_the_campaign_already_uses_is_refused(self, campaign, territory):
        create_campaign_table(campaign, territory, "Turf", dice="d6")
        with pytest.raises(Refusal, match="already has a table called"):
            create_campaign_table(campaign, territory, "turf")

    def test_a_possession_type_has_nothing_to_roll_for(self, campaign, core):
        settlement = core.asset_types.get(label_singular="Settlement")
        with pytest.raises(Refusal, match="nothing to roll for"):
            create_campaign_table(campaign, settlement, "Homes", dice="d6")

    def test_entries_come_from_the_catalogue_and_a_roll_lands_on_them(
        self, campaign, territory, journal
    ):
        from n26.core.campaigns import campaign_operation

        table = create_campaign_table(campaign, territory, "Turf", dice="d3")
        ruins = _holding_assets(campaign).get(name="Old Ruins")
        with campaign_operation(campaign, actor=campaign.owner) as act:
            act.add_table_entry(table, ruins, roll_low=1, roll_high=3)
        assert roll_asset(campaign, table, rolled=2).campaign_asset.asset == ruins

        # Not the campaign's own: a system table is the book's.
        with pytest.raises(ValueError, match="not one of"):
            with campaign_operation(campaign, actor=campaign.owner) as act:
                act.add_table_entry(journal, ruins, roll_low=1)


# --- The pages ---------------------------------------------------------------


class TestThePages:
    """Every control is the arbitrator's and takes the asset type's own
    word; the dialogs offer only what can be rolled on; nothing new
    reaches the gang sheet."""

    @pytest.fixture(autouse=True)
    def flag(self, campaigns_open):
        return campaigns_open

    def test_the_roll_control_appears_only_where_a_rolled_table_is_held(
        self, client, arbitrator, default_pack
    ):
        from n26.library.authoring import add_asset_type

        bare = create_campaign_type("Bare")
        racket = add_asset_type(bare, "Racket", "pooled")
        quiet = found_campaign("Quiet", bare, owner=arbitrator)
        client.force_login(arbitrator)
        page = client.get(reverse("n26-campaign", args=[quiet.pk])).content.decode()
        assert "Roll racket" not in page
        assert "Add racket" in page

        # With a rolled table of Rackets the control appears, in the type's
        # word; the three-per-player line is the Territory rule and is not
        # asserted of Rackets.
        rackets = create_asset_table("Rackets", racket, dice="d6")
        add_asset_table_entry(
            rackets, create_asset("Toll", racket), roll_low=1, roll_high=6
        )
        page = client.get(
            reverse("n26-campaign", args=[quiet.pk]) + f"?roll={racket.pk}"
        ).content.decode()
        assert "Roll racket" in page
        assert "The rolled racket will be added to the campaign as unclaimed." in page
        assert "three per player" not in page

    def test_a_malformed_gang_key_is_a_bad_link(
        self, client, campaign, territory, arbitrator
    ):
        client.force_login(arbitrator)
        response = client.post(
            reverse("n26-campaign-roll-starting", args=[campaign.pk, "not-a-key"]),
            {"type": str(territory.pk)},
        )
        assert response.status_code == 404

    def test_the_controls_take_the_types_word_and_are_the_arbitrators(
        self, client, campaign, journal, slag_kings, wild_cats, arbitrator, owner
    ):
        client.force_login(arbitrator)
        page = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
        assert "Roll territory" in page
        assert page.count("Roll starting territory") == 2
        assert "Tables" in page
        assert "Add territory" in page

        client.force_login(owner)
        page = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
        assert "Roll territory" not in page
        assert "Roll starting territory" not in page
        assert "?roll=" not in page

    def test_the_pool_dialog_counts_three_per_player(
        self, client, campaign, territory, selection_table, arbitrator
    ):
        from n26.core.campaigns import campaign_operation

        for name in ("one", "two"):
            with campaign_operation(campaign, actor=arbitrator) as act:
                player = act.invite(User.objects.create_user(name))
            with campaign_operation(campaign, actor=arbitrator) as act:
                act.answer_invitation(player.user, accepted=True)
        client.force_login(arbitrator)
        address = reverse("n26-campaign", args=[campaign.pk]) + f"?roll={territory.pk}"
        page = client.get(address).content.decode()
        assert "The rules generate three per player: 6 for this campaign." in page
        assert "Roll territory" in page
        assert f'name="table" value="{selection_table.pk}"' in page

        # Over htmx the panel alone comes back, in its host.
        partial = client.get(address, HTTP_HX_REQUEST="true")
        body = partial.content.decode()
        assert 'id="n26-roll-dialog-host"' in body
        assert "hx-swap-oob" in body
        assert "<c-n26.view" not in body and "Gangs" not in body
        assert partial["HX-Replace-Url"] == address
        # One table is a fact, not a choice: named with its die, no radio,
        # and posted hidden.
        assert 'type="radio"' not in body
        assert "Territory Selection Table · D66" in body
        assert f'type="hidden" name="table" value="{selection_table.pk}"' in body
        assert (
            "The rolled territory will be added to the campaign as unclaimed." in body
        )

    def test_the_starting_dialog_offers_only_the_tables_the_gang_holds(
        self, client, campaign, territory, journal, slag_kings, wild_cats, arbitrator
    ):
        client.force_login(arbitrator)
        page = reverse("n26-campaign", args=[campaign.pk])
        kings = client.get(
            f"{page}?starting={slag_kings.pk}&type={territory.pk}"
        ).content.decode()
        assert "Roll starting territory for Slag Kings" in kings
        assert "Goliath Territories" in kings
        assert "Territory Selection Table" in kings

        cats = client.get(
            f"{page}?starting={wild_cats.pk}&type={territory.pk}"
        ).content.decode()
        assert "Roll starting territory for Wild Cats" in cats
        assert "Goliath Territories" not in cats
        assert "Territory Selection Table · D66" in cats
        assert 'type="radio"' not in cats.split('id="n26-roll-dialog-host"')[1]
        assert "The rolled territory will be assigned to Wild Cats." in cats
        assert "The tables Wild Cats holds" not in cats

        # Two tables are radio cards, each named with its die; the range
        # sentence under the own-roll field follows the selected one.
        assert kings.count('type="radio"') == 2
        assert "A D6 roll is 1 to 6." in kings
        assert "A D66 roll is 11 to 66." in kings
        assert "The rolled territory will be assigned to Slag Kings." in kings

    def test_the_own_roll_field_is_the_forms_drawn_by_the_component(
        self, client, campaign, territory, selection_table, arbitrator
    ):
        """The field is RollAssetForm.rolled through the kit's field and
        input components — the same drawing as the campaign budget — so
        it carries the component's border and background classes rather
        than a hand-written class that would replace them and leave the
        box invisible in dark mode."""
        client.force_login(arbitrator)
        address = reverse("n26-campaign", args=[campaign.pk]) + f"?roll={territory.pk}"
        body = client.get(address, HTTP_HX_REQUEST="true").content.decode()
        (widget,) = re.findall(r"<input[^>]*name=\"rolled\"[^>]*>", body)
        assert "rounded-control" in widget and "border-ink-300" in widget
        assert "max-w-32" not in widget
        assert 'type="number"' in widget and 'id="pool-roll"' in widget
        assert "Your own roll" in body
        assert "Optional. Leave blank and the roll is made for you." in body
        assert "A D66 roll is 11 to 66." in body
        assert "Use my roll" in body
        assert "at the table" not in body

    def test_posting_the_rolls(
        self,
        client,
        campaign,
        territory,
        journal,
        selection_table,
        slag_kings,
        arbitrator,
    ):
        client.force_login(arbitrator)
        response = client.post(
            reverse("n26-campaign-roll-asset", args=[campaign.pk]),
            {
                "type": str(territory.pk),
                "table": str(selection_table.pk),
                "rolled": "63",
            },
        )
        # Without htmx the plain campaign page, no anchor: the message at
        # its top is what the reader should see, not the gangs table.
        assert response.status_code == 302
        assert response["Location"] == reverse("n26-campaign", args=[campaign.pk])
        (kept,) = CampaignAsset.objects.filter(campaign=campaign)
        assert kept.asset.name == "Old Ruins" and kept.holder is None
        page = client.get(response["Location"]).content.decode()
        assert "Rolled 63: Old Ruins added to the campaign, unclaimed." in page

        response = client.post(
            reverse("n26-campaign-roll-starting", args=[campaign.pk, slag_kings.pk]),
            {"type": str(territory.pk), "table": str(journal.pk), "rolled": "4"},
        )
        assert response.status_code == 302
        assert response["Location"] == reverse("n26-campaign", args=[campaign.pk])
        held = CampaignAsset.objects.get(campaign=campaign, holder__gang=slag_kings)
        assert held.asset.name == "Iron Forge"
        page = client.get(response["Location"]).content.decode()
        assert "Rolled 4: Iron Forge assigned to Slag Kings." in page

        # A roll the die cannot make comes back to the dialog with the reason.
        response = client.post(
            reverse("n26-campaign-roll-asset", args=[campaign.pk]),
            {
                "type": str(territory.pk),
                "table": str(selection_table.pk),
                "rolled": "7",
            },
            follow=True,
        )
        assert "You cannot roll 7 on a D66." in response.content.decode()
        assert CampaignAsset.objects.filter(campaign=campaign).count() == 2

    def test_a_band_the_die_cannot_make_is_refused_on_the_tables_page(
        self, client, campaign, territory, arbitrator
    ):
        """The band columns are small integers; a number nothing could roll
        is refused in words on the form, never left for the database."""
        turf = create_campaign_table(campaign, territory, "Turf", dice="d6")
        ruins = _holding_assets(campaign).get(name="Old Ruins")
        client.force_login(arbitrator)

        response = client.post(
            reverse("n26-campaign-table", args=[campaign.pk, turf.pk]),
            {"asset": str(ruins.pk), "roll_low": "99999", "roll_high": "99999"},
        )

        assert response.status_code == 200
        assert "You cannot roll 99999 on a D6." in response.content.decode()
        assert not AssetTableEntry.objects.filter(table=turf).exists()

    def test_a_roll_over_htmx_redraws_the_page_in_place_with_a_toast(
        self,
        client,
        campaign,
        territory,
        journal,
        selection_table,
        slag_kings,
        arbitrator,
    ):
        """The dialog posts over htmx. What comes back is the changed
        sections out of band — figures, gangs, assets, log — the dialog
        host emptied, the address put back to the plain page, and the
        message as a toast. No redirect, no reload, no scroll."""
        client.force_login(arbitrator)
        response = client.post(
            reverse("n26-campaign-roll-asset", args=[campaign.pk]),
            {
                "type": str(territory.pk),
                "table": str(selection_table.pk),
                "rolled": "63",
            },
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        assert "Location" not in response
        body = response.content.decode()
        for host in (
            "n26-campaign-figures",
            "n26-campaign-gangs",
            "n26-campaign-assets",
            "n26-campaign-log",
            "n26-campaign-log-count",
        ):
            assert re.search(rf'id="{host}"\s+hx-swap-oob="true"', body), host
        assert '<div id="n26-roll-dialog-host" hx-swap-oob="true"></div>' in body
        assert "<dialog" not in body
        # The sections carry what the roll changed.
        assert "Old Ruins" in body
        assert (
            "rolled 63 from the Territory Selection Table: Old Ruins (manual roll)"
            in body
        )
        assert "1 unclaimed" in body
        assert response["HX-Replace-Url"] == reverse("n26-campaign", args=[campaign.pk])
        toasts = json.loads(response["HX-Trigger"])["n26-toasts"]
        assert [(t["variant"], t["message"]) for t in toasts] == [
            ("success", "Rolled 63: Old Ruins added to the campaign, unclaimed.")
        ]

        response = client.post(
            reverse("n26-campaign-roll-starting", args=[campaign.pk, slag_kings.pk]),
            {"type": str(territory.pk), "table": str(journal.pk), "rolled": "4"},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        body = response.content.decode()
        assert 'id="n26-campaign-gangs" hx-swap-oob="true"' in body
        assert "Iron Forge" in body
        toasts = json.loads(response["HX-Trigger"])["n26-toasts"]
        assert [t["message"] for t in toasts] == [
            "Rolled 4: Iron Forge assigned to Slag Kings."
        ]

    def test_a_roll_for_a_type_that_has_gone_sends_the_page_over_htmx(
        self, client, campaign, arbitrator
    ):
        """Over htmx a redirect's body is swallowed by hx-swap="none", so an
        asset type the dialog named but that no longer resolves answers
        with HX-Redirect and the browser goes to the page. Without htmx it
        is the redirect it always was."""
        client.force_login(arbitrator)
        address = reverse("n26-campaign-roll-asset", args=[campaign.pk])

        response = client.post(address, {"type": "nonsense"}, HTTP_HX_REQUEST="true")
        assert response.status_code == 204
        assert response["HX-Redirect"] == reverse("n26-campaign", args=[campaign.pk])

        response = client.post(address, {"type": "nonsense"})
        assert response.status_code == 302

    def test_a_refusal_over_htmx_comes_back_in_the_dialog_without_a_toast(
        self, client, campaign, territory, journal, selection_table, arbitrator
    ):
        client.force_login(arbitrator)
        response = client.post(
            reverse("n26-campaign-roll-asset", args=[campaign.pk]),
            {
                "type": str(territory.pk),
                "table": str(selection_table.pk),
                "rolled": "7",
            },
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        assert "Location" not in response
        assert "HX-Trigger" not in response
        assert "HX-Replace-Url" not in response
        body = response.content.decode()
        host = body.split('id="n26-roll-dialog-host"')[1]
        assert host.lstrip().startswith('hx-swap-oob="true"')
        # The open panel is deleted by id before the host arrives, so htmx
        # has nothing to settle the new panel's attributes against.
        assert body.index(
            '<div id="n26-dialog" hx-swap-oob="delete"></div>'
        ) < body.index('id="n26-roll-dialog-host"')
        assert "<dialog" in body and "You cannot roll 7 on a D66." in body
        # The typed roll is still in the field for the reader to fix.
        assert 'value="7"' in body
        assert "n26-campaign-assets" not in body
        assert not CampaignAsset.objects.filter(campaign=campaign).exists()

        # A table not offered lands the same way, in the form's words.
        response = client.post(
            reverse("n26-campaign-roll-asset", args=[campaign.pk]),
            {"type": str(territory.pk), "table": str(journal.pk)},
            HTTP_HX_REQUEST="true",
        )
        assert response.status_code == 200
        assert "That table is not available here." in response.content.decode()

    def test_the_cards_show_the_first_table_chosen_and_keep_the_posted_one(
        self, client, campaign, territory, journal, slag_kings, arbitrator
    ):
        """Two tables: the first card is checked when the dialog opens, so
        a roll posts with a table; after a refusal the card the reader
        chose stays checked and the range sentence follows it."""
        client.force_login(arbitrator)
        address = reverse("n26-campaign", args=[campaign.pk])
        body = client.get(
            f"{address}?starting={slag_kings.pk}&type={territory.pk}",
            HTTP_HX_REQUEST="true",
        ).content.decode()
        radios = re.findall(r'<input type="radio"[^>]*>', body)
        assert len(radios) == 2
        assert [("checked" in radio) for radio in radios] == [True, False]
        first = re.search(r'value="([^"]+)"', radios[0]).group(1)
        assert f"x-data=\"{{ table: '{first}', rolled: '' }}\"" in body

        response = client.post(
            reverse("n26-campaign-roll-starting", args=[campaign.pk, slag_kings.pk]),
            {"type": str(territory.pk), "table": str(journal.pk), "rolled": "9"},
            HTTP_HX_REQUEST="true",
        )
        body = response.content.decode()
        assert "You cannot roll 9 on a D6." in body
        radios = re.findall(r'<input type="radio"[^>]*>', body)
        assert [("checked" in radio) for radio in radios].count(True) == 1
        assert re.search(
            rf'value="{journal.pk}"[^>]*\s+checked', radios[0]
        ) or re.search(rf'value="{journal.pk}"[^>]*\s+checked', radios[1])
        assert f"x-data=\"{{ table: '{journal.pk}', rolled: '9' }}\"" in body

        # A table that is not offered falls back to the first card, and what
        # was typed is escaped for the script that reads it back.
        response = client.post(
            reverse("n26-campaign-roll-starting", args=[campaign.pk, slag_kings.pk]),
            {"type": str(territory.pk), "table": "nonsense", "rolled": "1'+x"},
            HTTP_HX_REQUEST="true",
        )
        body = response.content.decode()
        radios = re.findall(r'<input type="radio"[^>]*>', body)
        assert [("checked" in radio) for radio in radios] == [True, False]
        assert f"x-data=\"{{ table: '{first}', rolled: '1\\u0027+x' }}\"" in body

    def test_the_gang_owner_cannot_roll_or_open_and_a_stranger_finds_nothing(
        self, client, campaign, territory, journal, selection_table, slag_kings, owner
    ):
        client.force_login(owner)
        for address in (
            reverse("n26-campaign-roll-asset", args=[campaign.pk]),
            reverse("n26-campaign-roll-starting", args=[campaign.pk, slag_kings.pk]),
            reverse("n26-campaign-tables", args=[campaign.pk]),
            reverse("n26-campaign-new-table", args=[campaign.pk]),
        ):
            assert client.post(address, {"type": str(territory.pk)}).status_code == 404
            assert client.get(address).status_code == 404
        client.force_login(User.objects.create_user("stranger"))
        assert (
            client.get(reverse("n26-campaign-tables", args=[campaign.pk])).status_code
            == 404
        )
        assert not CampaignAsset.objects.filter(campaign=campaign).exists()
        assert list(tables_in_play(campaign)) == [selection_table]

    def test_the_tables_page_ticks_a_table_open_and_closed(
        self,
        client,
        campaign,
        journal,
        selection_table,
        wild_cats,
        arbitrator,
        propagating,
        task_queue,
    ):
        client.force_login(arbitrator)
        address = reverse("n26-campaign-tables", args=[campaign.pk])
        page = client.get(address).content.decode()
        assert "Territory Selection Table" in page
        assert "Included with Territory campaign. Available to every gang." in page
        assert "D66 · 18 territories" in page
        assert "D6 · 6 territories" in page
        assert "Goliath Territories" in page
        assert "Available to every gang</legend>" in page
        assert "Tables of territories the gangs in this campaign can use." in page
        assert (
            "Gangs can roll for a starting territory from any of these. You can "
            "also roll to add unclaimed territories to the campaign."
        ) in page
        assert "Territories already rolled stay in the campaign." in page
        for banned in ("roll on", "holds", "Entries", "pool", "Given by", "opened"):
            assert banned not in page, banned

        with task_queue.capture():
            response = client.post(address, {"open": [str(journal.pk)]}, follow=True)
        task_queue.deliver_all()
        assert (
            "Made Goliath Territories available to every gang."
            in response.content.decode()
        )
        assert journal in tables_in_play(campaign)
        assert journal in tables_held_by(wild_cats, campaign)

        response = client.post(address, {}, follow=True)
        assert "Withdrew Goliath Territories." in response.content.decode()
        assert journal not in tables_in_play(campaign)

        response = client.post(address, {}, follow=True)
        assert "Nothing changed." in response.content.decode()

    def test_creating_and_filling_a_table_on_the_pages(
        self, client, campaign, territory, arbitrator
    ):
        client.force_login(arbitrator)
        response = client.post(
            reverse("n26-campaign-new-table", args=[campaign.pk]),
            {"asset_type": str(territory.pk), "name": "Dust Falls Turf", "dice": "d3"},
        )
        table = AssetTable.objects.get(name="Dust Falls Turf")
        assert table.pack == campaign.pack and table.dice == "d3"
        assert response["Location"] == reverse(
            "n26-campaign-table", args=[campaign.pk, table.pk]
        )

        page = client.get(response["Location"]).content.decode()
        assert "Created the table Dust Falls Turf. Add territories to it next." in page
        assert "Rolled with a D3" in page
        assert "0 of 3 rolls covered" in page
        assert "Old Ruins" in page
        assert "No territories yet. Add the territories a roll can land on." in page
        assert "Add a territory" in page and "Add territory" in page
        assert "Entries" not in page and "entries" not in page

        ruins = _holding_assets(campaign).get(name="Old Ruins")
        client.post(
            response["Location"],
            {"asset": str(ruins.pk), "roll_low": "1", "roll_high": "3"},
        )
        (entry,) = table.entries.all()
        assert (entry.roll_low, entry.roll_high) == (1, 3)
        page = client.get(response["Location"]).content.decode()
        assert "3 of 3 rolls covered" in page

        # A band running downwards lands on the form in words.
        page = client.post(
            response["Location"],
            {"asset": str(ruins.pk), "roll_low": "3", "roll_high": "1"},
        ).content.decode()
        assert table.entries.count() == 1
        assert "roll" in page.lower()

        client.post(
            reverse(
                "n26-campaign-table-entry-remove",
                args=[campaign.pk, table.pk, entry.pk],
            )
        )
        assert not AssetTableEntry.objects.filter(pk=entry.pk).exists()

    def test_nothing_new_on_the_gang_sheet(self, client, campaign, journal, slag_kings):
        client.force_login(slag_kings.owner)
        sheet = client.get(reverse("n26-gang", args=[slag_kings.pk])).content.decode()
        assert "Roll starting" not in sheet
        assert "Goliath Territories" not in sheet
        assert "Goliath Territories" not in str(render_gang(slag_kings).rows)

    def test_the_page_costs_the_same_however_many_gangs_and_tables(
        self, client, campaign, territory, journal, slag_kings, goliath, arbitrator
    ):
        """One gang with a rolled territory, one open table and one of the
        campaign's own to start from, so what is measured is the growth
        and not the first of each kind."""
        client.force_login(arbitrator)
        address = reverse("n26-campaign", args=[campaign.pk])
        roll_asset(campaign, journal, gang=slag_kings, rolled=6)
        open_table(campaign, journal)
        create_campaign_table(campaign, territory, "Turf", dice="d6")
        client.get(address)
        with CaptureQueriesContext(connection) as few:
            body = client.get(address).content.decode()
        assert body.count("Roll starting territory") == 1

        for index in range(3):
            more = found_gang(
                f"More {index}", goliath, owner=User.objects.create_user(f"u{index}")
            )
            join_campaign(more, campaign)
            roll_asset(campaign, journal, gang=more, rolled=index + 1)
            create_campaign_table(campaign, territory, f"Turf {index}", dice="d6")

        with CaptureQueriesContext(connection) as more_queries:
            body = client.get(address).content.decode()

        assert body.count("Roll starting territory") == 4
        # No more than before: three more gangs, three more rolls and three
        # more tables add nothing per gang or per table.
        assert len(more_queries.captured_queries) <= len(few.captured_queries)
        sheet = render_campaign(campaign)
        (table,) = sheet.assets
        assert [t.name for t in table.tables] == [
            "Goliath Territories",
            "Territory Selection Table",
            "Turf",
            "Turf 0",
            "Turf 1",
            "Turf 2",
        ]
