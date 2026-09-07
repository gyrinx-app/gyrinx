"""The journal content seed: the Gang supertype and the two Underhive
Journals' territories, created once, as a maintenance operation.

The rules (design/house-and-territory-tables.md): a Goliath gang may roll
its starting Territory on the House of Chains table, an Escher gang on
the House of Blades table, and each of those Territories carries a House
Controlled boon that applies only while a gang of that House holds it —
a Clan House Outcast gang of that House included. The fact all of that
reads is a hidden Gang supertype pick on the gang; the content that
writes it, and the journals' territories, tables and boons, is one seed
(``n26/library/gang_supertypes.py``, ``n26/library/journal_content.py``)
run from the maintenance console on the tasks framework.

What this file holds still: the seed creates every row exactly once and
a rerun creates nothing and says so; a gang type or Outcast pick that is
not there is skipped and said; a Goliath gang founded after the seed has
the pick, one founded before catches up by propagation, a Clan House
Goliath Outcast gang has it once House Goliath is picked, and an Escher
gang and a Clanless Outcast never do; a journal territory's income and
boons reach the holder the condition names; the House table reaches a
gang through its pick and its starting-roll dialog offers it, while a
reader who may not see staged content is not offered a staged table;
both D6 tables cover every roll once; the House tables are never built
into the campaign type; and the console previews, enqueues, records and
stands down on a redelivery.
"""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from gyrinx.site.models import Availability, FeatureFlag
from n26.core import history, select
from n26.core.campaigns import tables_held_by
from n26.core.card import build_card, build_gang_card, build_modifier_index, carriers
from n26.core.effects import _Facts, compute, compute_gang
from n26.core.history import campaign_history
from n26.core.models import BuiltInPropagationTask, CampaignAsset
from n26.core.operations import Refusal
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_campaign, render_gang
from n26.flags import BUILT_IN_PROPAGATION, CAMPAIGNS
from n26.library.core_campaign import CAMPAIGN_TYPE, seed_core_campaign
from n26.library.gang_supertypes import (
    HOUSES,
    PICKLIST,
    SLOT,
    SLOT_TYPE,
    clan_house_pickable_name,
    seed_gang_supertypes,
    supertype_pick,
)
from n26.library.income import INCOME, income_of
from n26.library.journal_content import (
    JOURNALS,
    NOTHING_TO_DO,
    controlled_rule_name,
    preview,
    seed_all,
)
from n26.library.models import (
    Asset,
    AssetTable,
    AssetTableEntry,
    CampaignType,
    DefaultAssignment,
    Modifier,
    Pickable,
    Picklist,
    Rule,
    Slot,
    SlotType,
)
from n26.library.tables import build_in_missing
from n26.library.territory_table import TABLE, seed_territory_table
from n26.maintenance import Operation, seed_journal_content
from n26.tests.sandbox.actions import (
    add_asset,
    add_built_in,
    assign_asset,
    choose,
    create_gang_type,
    create_pickable,
    create_picklist,
    create_profile,
    create_slot,
    create_slot_type,
    found_campaign,
    found_gang,
    hire,
    join_campaign,
    open_table,
    roll_asset,
)

pytestmark = pytest.mark.django_db

GOLIATH_TABLE = JOURNALS[0][1]
ESCHER_TABLE = JOURNALS[1][1]


# --- The world the seed runs in --------------------------------------------


@pytest.fixture
def arbitrator(db):
    return User.objects.create_user("arbitrator")


@pytest.fixture
def staff_arbitrator(db):
    return User.objects.create_user("author", is_staff=True)


@pytest.fixture
def superuser(db):
    return User.objects.create_superuser("boss", "boss@example.com", "password")


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
    """The Territory campaign type as it ships, with the Territory
    Selection Table built in."""
    seed_core_campaign(apps)
    seed_territory_table(apps)
    return CampaignType.objects.get(name=CAMPAIGN_TYPE)


@pytest.fixture
def gang_types(default_pack):
    """The six Clan House gang types and Outcast, as the system pack has
    them, with no supertype built in yet."""
    made = {house: create_gang_type(house) for house in HOUSES}
    made["Outcast"] = create_gang_type("Outcast")
    return made


@pytest.fixture
def clan_house(default_pack, gang_types, person_type):
    """The Outcast gang's Clan House choice as it stands in the system
    pack: its own slot type and pickables, House Goliath among them, on
    a visible gang-level slot built into the Outcast Leader."""
    slot_type = create_slot_type("Clan House")
    picks = {
        house: create_pickable(clan_house_pickable_name(house), slot_type)
        for house in HOUSES
    }
    picklist = create_picklist("Clan House", slot_type, members=list(picks.values()))
    slot = create_slot("Clan House", slot_type, picklist, assigned_to="gang")
    leader = create_profile(
        "Outcast Leader", person_type, gang_types["Outcast"], price=120
    )
    add_built_in(leader, slot)
    return {"slot": slot, "picks": picks, "leader": leader}


@pytest.fixture
def seeded(core, gang_types, clan_house):
    """The whole seed, run once over a world with everything it looks for.
    The gang types in hand are read again afterwards: the seed founds
    each type's built-ins set on a copy of its own."""
    lines = seed_all()
    for gang_type in gang_types.values():
        gang_type.refresh_from_db()
    return lines


def gang_facts(gang):
    """The gang as its own scopes see it: stored facts with the computed
    grants — a pick a grant dealt included — layered on."""
    card = build_gang_card(gang)
    index = build_modifier_index(carriers(card))
    return _Facts(card, compute(card, index)).model()


def has_picked(gang, house):
    return select.Has(supertype_pick(house)).matches(gang_facts(gang))


def gang_rules(gang):
    """The rules on the gang's own card, the campaign assets it holds
    among the carriers."""
    card = build_gang_card(gang)
    index = build_modifier_index(carriers(card))
    return [contribution.thing for contribution in compute_gang(card, index).rules]


def income_reading(gang):
    block = render_gang(gang).campaign
    return next(line.value for line in block.counters if line.name == INCOME)


def created_lines(lines):
    return [line for line in lines if not line.startswith("skipped")]


# --- What the seed creates -------------------------------------------------


class TestTheSeedCreatesEverythingOnce:
    """Every row the programme needs, in the system pack, matched by name
    and pack; a second run creates nothing and says so."""

    def test_the_supertype_is_one_slot_type_six_markers_one_list_one_hidden_slot(
        self, seeded, default_pack
    ):
        (slot_type,) = SlotType.objects.filter(name=SLOT_TYPE)
        assert slot_type.pack == default_pack
        assert not slot_type.allows_repeats
        picks = Pickable.objects.filter(slot_type=slot_type).order_by("name")
        assert sorted(p.name for p in picks) == sorted(HOUSES)
        # The Venator Gang Legacy picks hold the bare names in the pack,
        # so the markers are told apart by an author-facing qualifier.
        assert {p.qualifier for p in picks} == {SLOT_TYPE}
        # Markers: the Goliath and Escher picks carry their House table's
        # grant and nothing else; the other four carry nothing.
        by_name = {p.name: p for p in picks}
        for house in ("Orlock", "Van Saar", "Delaque", "Cawdor"):
            assert by_name[house].modifiers.count() == 0
        for house, table_name in (("Goliath", GOLIATH_TABLE), ("Escher", ESCHER_TABLE)):
            (grant,) = by_name[house].modifiers.all()
            assert grant.adds_assignable.asset_table.name == table_name
            assert grant.targets_gang.echoes is False
        (picklist,) = Picklist.objects.filter(name=PICKLIST)
        assert [m.pickable.name for m in picklist.members.order_by("position")] == list(
            HOUSES
        )
        (slot,) = Slot.objects.filter(name=SLOT)
        assert (slot.hidden, slot.min_picks, slot.max_picks, slot.assigned_to) == (
            True,
            1,
            1,
            "gang",
        )
        assert slot.picklist == picklist

    def test_each_clan_house_gang_type_builds_the_slot_in_with_its_house_picked(
        self, seeded, gang_types
    ):
        slot = Slot.objects.get(name=SLOT)
        for house in HOUSES:
            gang_type = gang_types[house]
            (member,) = DefaultAssignment.objects.filter(
                default_set=gang_type.built_ins, slot=slot, archived=False
            )
            assert member.default_pickable == supertype_pick(house)
        assert gang_types["Outcast"].built_ins is None

    def test_each_outcast_clan_house_pick_gives_the_slot_with_its_house_picked(
        self, seeded, clan_house
    ):
        slot = Slot.objects.get(name=SLOT)
        for house in HOUSES:
            clan_pick = clan_house["picks"][house]
            (grant,) = clan_pick.modifiers.filter(adds_assignable__slot=slot)
            assert grant.adds_assignable.with_pick == supertype_pick(house)
            assert grant.targets_gang.echoes is False

    def test_twelve_staged_territories_with_the_books_income(self, seeded, core):
        territory = core.asset_types.get(label_singular="Territory")
        for _house, _table, territories in JOURNALS:
            for entry in territories:
                asset = Asset.objects.get(name=entry.name)
                assert asset.asset_type == territory
                assert asset.staged
                assert income_of(asset) == entry.income

    def test_the_house_controlled_boons_are_income_or_a_named_rule(self, seeded):
        for house, _table, territories in JOURNALS:
            pick = supertype_pick(house)
            for entry in territories:
                asset = Asset.objects.get(name=entry.name)
                (boon,) = [
                    m for m in asset.modifiers.all() if m.targets_gang.is_conditional
                ]
                (condition,) = boon.targets_gang.has_gang_pickable.all()
                assert list(condition.pickables.all()) == [pick]
                assert boon.targets_gang.echoes is False
                if entry.more_income:
                    assert boon.contributes_to_counter.amount == entry.more_income
                    assert boon.contributes_to_counter.counter.name == INCOME
                else:
                    rule = boon.adds_assignable.rule
                    assert rule.name == controlled_rule_name(house)
                    assert rule.annotation == entry.name
                    assert rule.staged
        assert Rule.objects.filter(name__endswith="Controlled").count() == 11

    def test_two_staged_d6_tables_in_the_books_order(self, seeded):
        for _house, table_name, territories in JOURNALS:
            table = AssetTable.objects.get(name=table_name)
            assert table.staged
            assert table.dice == "d6"
            entries = list(table.entries.select_related("asset").order_by("position"))
            assert [(e.roll_low, e.roll_high, e.asset.name) for e in entries] == [
                (roll, roll, entry.name)
                for roll, entry in enumerate(territories, start=1)
            ]
            assert all(e.staged for e in entries)

    def test_the_house_tables_are_not_built_into_the_campaign_type(self, seeded, core):
        given = [m.assignable.name for m in core.built_in_members]
        assert TABLE in given
        assert GOLIATH_TABLE not in given and ESCHER_TABLE not in given

    def test_a_later_built_in_pass_leaves_the_house_tables_alone(self, seeded, core):
        """The rule that builds a table into its campaign type runs again
        whenever the Territory Selection Table is seeded; a table a pick
        gives is one House's and must not be swept up by it."""
        assert build_in_missing(apps, core) == []
        seed_territory_table(apps)
        assert not DefaultAssignment.objects.filter(
            asset_table__name__in=[GOLIATH_TABLE, ESCHER_TABLE]
        ).exists()

    def test_running_it_again_creates_nothing_and_says_so(self, seeded):
        before = {
            model: model.objects.count()
            for model in (
                SlotType,
                Pickable,
                Picklist,
                Slot,
                DefaultAssignment,
                Asset,
                AssetTable,
                AssetTableEntry,
                Rule,
                Modifier,
            )
        }

        again = seed_all()

        assert again == [NOTHING_TO_DO]
        assert before == {model: model.objects.count() for model in before}

    def test_the_first_run_says_what_it_made(self, seeded):
        assert f"created the {SLOT_TYPE} slot type" in seeded
        assert f"built the {SLOT} slot into Goliath, picked Goliath" in seeded
        assert f"House Goliath now gives the {SLOT} slot, picked Goliath" in seeded
        assert "created the Slug House Territory with income 20, staged" in seeded
        assert "Amneo-vats: 10 more income for gangs that have picked Goliath" in seeded
        assert f"Goliath gangs now hold the {GOLIATH_TABLE} table" in seeded
        assert not any(line.startswith("skipped") for line in seeded)

    def test_the_preview_says_the_same_and_writes_nothing(
        self, core, gang_types, clan_house, task_queue
    ):
        """Rolled back whole — the propagation filings the built-in members
        make included, whose messages would otherwise have a scheduled
        sweep reconcile every Clan House gang from a page load."""
        # The Clan House fixture filed its own passes; only new filings count.
        filed = BuiltInPropagationTask.objects.count()
        with task_queue.capture():
            lines = preview()

        assert f"created the {SLOT_TYPE} slot type" in lines
        assert not SlotType.objects.filter(name=SLOT_TYPE).exists()
        assert not AssetTable.objects.filter(name=GOLIATH_TABLE).exists()
        assert not Asset.objects.filter(staged=True).exists()
        assert BuiltInPropagationTask.objects.count() == filed
        assert task_queue.pending() == 0

        assert seed_all() == lines
        assert BuiltInPropagationTask.objects.count() == filed + 6

    def test_a_missing_gang_type_or_outcast_pick_is_skipped_and_said(self, core):
        """A fresh database has no gang lists; the seed creates none, and
        says which built-ins and grants it could not write."""
        lines = seed_all()

        assert "skipped Goliath: no gang type of that name" in lines
        assert (
            "skipped House Goliath: no Outcast Clan House pickable of that name"
            in lines
        )
        assert AssetTable.objects.filter(name=GOLIATH_TABLE).exists()
        # The skips are said on every run, but they are not work: a rerun
        # still reports nothing to do.
        again = seed_all()
        assert again[0] == NOTHING_TO_DO
        assert created_lines(again[1:]) == []

    def test_an_archived_built_in_member_is_left_archived(self, seeded, gang_types):
        """An author who took the slot out of a type's built-ins is not
        overruled by a rerun: the archived member is found, and said."""
        slot = Slot.objects.get(name=SLOT)
        member = DefaultAssignment.objects.get(
            default_set=gang_types["Goliath"].built_ins, slot=slot
        )
        member.archive()

        again = seed_all()

        assert again[0] == NOTHING_TO_DO
        assert any(line.startswith("skipped Goliath: its built-in") for line in again)
        assert (
            DefaultAssignment.objects.filter(
                default_set=gang_types["Goliath"].built_ins, slot=slot
            ).count()
            == 1
        )

    def test_the_supertype_alone_can_be_seeded(self, gang_types):
        outcome, picks = seed_gang_supertypes()
        assert set(picks) == set(HOUSES)
        assert f"created the {SLOT_TYPE} slot type" in outcome.created
        assert len(outcome.skipped) == 6  # the Outcast picks are not there


# --- Who has a supertype --------------------------------------------------


class TestWhoHasASupertype:
    """A Goliath gang has picked Goliath however it came to be one: founded
    on the type after the seed, founded before and caught up, or an
    Outcast gang that chose House Goliath. An Escher gang and a Clanless
    Outcast have not."""

    def test_a_goliath_gang_founded_after_the_seed_has_the_pick(
        self, seeded, gang_types, owner
    ):
        gang = found_gang("Irontooth", gang_types["Goliath"], owner=owner, budget=1000)

        assert has_picked(gang, "Goliath")
        assert not has_picked(gang, "Escher")
        (pick,) = gang.assignments.filter(pickable__isnull=False, archived=False)
        assert pick.pickable == supertype_pick("Goliath")
        assert SLOT_TYPE not in str(render_gang(gang).rows)
        gang.refresh_from_db()
        assert gang.rating == 0
        assert_reconciled(gang)

    def test_a_goliath_gang_founded_before_the_seed_catches_up(
        self, core, gang_types, clan_house, owner, propagating, task_queue
    ):
        gang = found_gang("Old Guard", gang_types["Goliath"], owner=owner, budget=1000)
        assert not gang.assignments.filter(pickable__isnull=False).exists()

        with task_queue.capture():
            seed_all()
        assert not has_picked(gang, "Goliath")
        task_queue.deliver_all()

        assert has_picked(gang, "Goliath")
        gang.refresh_from_db()
        assert gang.rating == 0
        assert_reconciled(gang)

    def test_a_clan_house_goliath_outcast_gang_counts_as_goliath(
        self, seeded, gang_types, clan_house, owner
    ):
        gang = found_gang(
            "The Cast Out", gang_types["Outcast"], owner=owner, budget=1000
        )
        boss = hire(gang, clan_house["leader"], "Boss")
        assert not has_picked(gang, "Goliath")

        card = build_card(boss, with_statlines=True)
        computed = compute(
            card, build_modifier_index([n.assignable for n in card.all_nodes()])
        )
        (choice,) = [c for c in computed.choices if c.kind_label == "Clan House"]
        choose(choice.anchor.assignment, clan_house["picks"]["Goliath"])

        assert has_picked(gang, "Goliath")
        assert not has_picked(gang, "Escher")
        # Dealt by the grant, not written: the gang's only stored pick is
        # the Clan House one.
        assert not gang.assignments.filter(
            pickable=supertype_pick("Goliath"), archived=False
        ).exists()
        gang.refresh_from_db()
        assert_reconciled(gang)
        assert boss.gang == gang

    def test_an_escher_gang_and_a_clanless_outcast_are_not_goliath(
        self, seeded, gang_types, clan_house, owner
    ):
        roses = found_gang("Wild Roses", gang_types["Escher"], owner=owner, budget=1000)
        clanless = found_gang(
            "The Nobodies", gang_types["Outcast"], owner=owner, budget=1000
        )
        hire(clanless, clan_house["leader"], "Boss")

        assert has_picked(roses, "Escher") and not has_picked(roses, "Goliath")
        assert not has_picked(clanless, "Goliath")
        assert not has_picked(clanless, "Escher")


# --- Nothing is told about the supertype ------------------------------------


def told(acts):
    """Every sentence and every line beneath one, flattened."""
    lines = []
    for act in acts:
        lines.append("".join(span.text for span in act.spans))
        lines.extend(f"{sub.name} {sub.note}" for sub in act.subs)
    return lines


class TestNothingIsToldAboutTheSupertype:
    """The supertype is a classification players never see, so the gang
    history and the campaign log say nothing when a gang gets it — at
    founding, or when propagation catches an older gang up — while a
    visible slot's pick is told as it always was."""

    @pytest.fixture(autouse=True)
    def flag(self, campaigns_open):
        return campaigns_open

    def test_founding_a_goliath_gang_writes_no_line_naming_it(
        self, seeded, gang_types, owner
    ):
        gang = found_gang("Irontooth", gang_types["Goliath"], owner=owner, budget=1000)

        lines = told(history.build(gang))

        assert lines
        assert not any(SLOT_TYPE in line for line in lines)
        assert not any("Goliath comes with" in line for line in lines)

    def test_the_propagation_pass_writes_no_line_naming_it(
        self,
        core,
        gang_types,
        clan_house,
        owner,
        arbitrator,
        propagating,
        task_queue,
    ):
        gang = found_gang("Old Guard", gang_types["Goliath"], owner=owner, budget=1000)
        campaign = found_campaign("Dust Falls", core, owner=arbitrator)
        join_campaign(gang, campaign)

        with task_queue.capture():
            seed_all()
        task_queue.deliver_all()

        assert has_picked(gang, "Goliath")
        for lines in (told(history.build(gang)), told(campaign_history(campaign))):
            assert lines
            assert not any(SLOT_TYPE in line for line in lines)
            assert not any("comes with" in line for line in lines)

    def test_a_visible_slots_pick_is_still_told(
        self, seeded, gang_types, clan_house, owner
    ):
        gang = found_gang(
            "The Cast Out", gang_types["Outcast"], owner=owner, budget=1000
        )
        boss = hire(gang, clan_house["leader"], "Boss")
        card = build_card(boss, with_statlines=True)
        computed = compute(
            card, build_modifier_index([n.assignable for n in card.all_nodes()])
        )
        (choice,) = [c for c in computed.choices if c.kind_label == "Clan House"]
        choose(choice.anchor.assignment, clan_house["picks"]["Goliath"])

        lines = told(history.build(gang))

        assert any("House Goliath" in line for line in lines)
        assert not any(SLOT_TYPE in line for line in lines)


# --- The boons on a held territory ------------------------------------------


class TestAJournalTerritoryInPlay:
    """Amneo-vats brings 15 to any holder and 10 more to a Goliath one;
    Slug House gives a Goliath holder the Goliath Controlled rule and an
    Escher holder nothing; the campaign page says who each boon is for."""

    @pytest.fixture(autouse=True)
    def flag(self, campaigns_open):
        return campaigns_open

    @pytest.fixture
    def campaign(self, seeded, core, arbitrator):
        return found_campaign("Dust Falls", core, owner=arbitrator, budget=1000)

    @pytest.fixture
    def gangs(self, campaign, gang_types):
        made = {}
        for name, house in (("Irontooth", "Goliath"), ("Wild Roses", "Escher")):
            gang = found_gang(
                name, gang_types[house], owner=User.objects.create_user(name)
            )
            join_campaign(gang, campaign)
            made[house] = gang
        return made

    def test_amneo_vats_reads_25_for_goliath_and_15_for_escher(self, campaign, gangs):
        vats = Asset.objects.get(name="Amneo-vats")
        held = add_asset(campaign, vats)

        assign_asset(held, gangs["Goliath"])
        assert income_reading(gangs["Goliath"]) == 25
        assert income_reading(gangs["Escher"]) == 0

        held = add_asset(campaign, vats)
        assign_asset(held, gangs["Escher"])
        assert income_reading(gangs["Escher"]) == 15
        for gang in gangs.values():
            gang.refresh_from_db()
            assert_reconciled(gang)

    def test_slug_house_gives_goliath_the_rule_and_escher_nothing(
        self, campaign, gangs
    ):
        slug_house = Asset.objects.get(name="Slug House")
        rule = Rule.objects.get(
            name=controlled_rule_name("Goliath"), annotation="Slug House"
        )
        for gang in gangs.values():
            assign_asset(add_asset(campaign, slug_house), gang)

        assert rule in gang_rules(gangs["Goliath"])
        assert rule not in gang_rules(gangs["Escher"])
        assert income_reading(gangs["Goliath"]) == 20
        assert income_reading(gangs["Escher"]) == 20

    def test_the_campaign_page_prints_each_boon_with_its_scope(self, campaign, gangs):
        for name in ("Amneo-vats", "Slug House"):
            add_asset(campaign, Asset.objects.get(name=name))

        (territories,) = render_campaign(campaign, viewer=campaign.owner).assets
        by_name = {entry.name: entry for entry in territories.entries}

        vats = by_name["Amneo-vats"]
        assert vats.income == 15
        (boon,) = vats.boons
        assert "gangs that have picked Goliath" in boon
        assert "10" in boon and INCOME in boon

        slug = by_name["Slug House"]
        assert slug.income == 20
        (boon,) = slug.boons
        assert "gangs that have picked Goliath" in boon
        assert "Goliath Controlled" in boon and "Slug House" in boon


# --- The House table and the starting roll ---------------------------------


class TestTheHouseTable:
    """A Goliath gang holds Goliath Territories through its pick and its
    starting-roll dialog offers it; an Escher gang's does not until the
    arbitrator opens the table. A staged table is offered only to a reader
    who may see staged content."""

    @pytest.fixture(autouse=True)
    def flag(self, campaigns_open):
        return campaigns_open

    @pytest.fixture
    def campaign(self, seeded, core, staff_arbitrator):
        return found_campaign("Dust Falls", core, owner=staff_arbitrator)

    @pytest.fixture
    def gangs(self, campaign, gang_types):
        made = {}
        for name, house in (("Irontooth", "Goliath"), ("Wild Roses", "Escher")):
            gang = found_gang(
                name, gang_types[house], owner=User.objects.create_user(name)
            )
            join_campaign(gang, campaign)
            made[house] = gang
        return made

    def dialog(self, client, campaign, gang):
        territory = campaign.campaign_type.asset_types.get(label_singular="Territory")
        page = reverse("n26-campaign", args=[campaign.pk])
        return client.get(
            f"{page}?starting={gang.pk}&type={territory.pk}"
        ).content.decode()

    def test_each_house_holds_its_own_table(self, campaign, gangs):
        goliath = AssetTable.objects.get(name=GOLIATH_TABLE)
        escher = AssetTable.objects.get(name=ESCHER_TABLE)
        selection = AssetTable.objects.get(name=TABLE)
        held = {
            house: set(tables_held_by(gang, campaign, include_staged=True))
            for house, gang in gangs.items()
        }
        assert held == {"Goliath": {goliath, selection}, "Escher": {escher, selection}}

    def test_a_staff_arbitrator_is_offered_the_house_table(
        self, client, campaign, gangs, staff_arbitrator
    ):
        client.force_login(staff_arbitrator)

        kings = self.dialog(client, campaign, gangs["Goliath"])
        assert GOLIATH_TABLE in kings and TABLE in kings
        assert ESCHER_TABLE not in kings

        cats = self.dialog(client, campaign, gangs["Escher"])
        assert ESCHER_TABLE in cats and TABLE in cats
        assert GOLIATH_TABLE not in cats

    def test_opening_the_table_offers_it_to_the_other_house(
        self, client, campaign, gangs, staff_arbitrator, propagating, task_queue
    ):
        goliath = AssetTable.objects.get(name=GOLIATH_TABLE)
        with task_queue.capture():
            open_table(campaign, goliath)
        task_queue.deliver_all()

        client.force_login(staff_arbitrator)
        assert GOLIATH_TABLE in self.dialog(client, campaign, gangs["Escher"])
        assert goliath in tables_held_by(gangs["Escher"], campaign, include_staged=True)

    def test_a_reader_who_may_not_see_staged_content_is_not_offered_a_staged_table(
        self, client, campaign, gangs, staff_arbitrator
    ):
        """The grant reaches the Goliath gang's card whoever is looking,
        but rolling on a table is where a Territory is newly chosen for
        the campaign, so the dialog holds a staged table back from a
        reader who may not see staged content."""
        goliath = AssetTable.objects.get(name=GOLIATH_TABLE)
        assert goliath in tables_held_by(
            gangs["Goliath"], campaign, include_staged=True
        )
        assert goliath not in tables_held_by(gangs["Goliath"], campaign)

        player = User.objects.create_user("arbitrator-player")
        campaign.owner = player
        campaign.save(update_fields=["owner"])
        client.force_login(player)
        kings = self.dialog(client, campaign, gangs["Goliath"])
        assert TABLE in kings
        assert GOLIATH_TABLE not in kings

        # Posting the staged table's key by hand is refused the same way.
        territory = campaign.campaign_type.asset_types.get(label_singular="Territory")
        response = client.post(
            reverse(
                "n26-campaign-roll-starting", args=[campaign.pk, gangs["Goliath"].pk]
            ),
            {"type": str(territory.pk), "table": str(goliath.pk), "rolled": "1"},
            follow=True,
        )
        assert not CampaignAsset.objects.filter(
            campaign=campaign, holder__gang=gangs["Goliath"]
        ).exists()
        assert response.status_code == 200

        # The act itself refuses too, whoever calls it: the gate is not
        # only the dialog's.
        with pytest.raises(Refusal, match="cannot roll for a territory from Goliath"):
            roll_asset(campaign, goliath, gang=gangs["Goliath"], rolled=1, actor=player)
        roll = roll_asset(
            campaign, goliath, gang=gangs["Goliath"], rolled=1, actor=staff_arbitrator
        )
        assert roll.campaign_asset.asset.name == "Slug House"

    def test_the_tables_page_shows_staged_tables_to_staff_only(
        self, client, campaign, staff_arbitrator
    ):
        client.force_login(staff_arbitrator)
        page = client.get(reverse("n26-campaign-tables", args=[campaign.pk]))
        assert GOLIATH_TABLE in page.content.decode()

        player = User.objects.create_user("arbitrator-player")
        campaign.owner = player
        campaign.save(update_fields=["owner"])
        client.force_login(player)
        page = client.get(reverse("n26-campaign-tables", args=[campaign.pk]))
        assert GOLIATH_TABLE not in page.content.decode()
        assert TABLE in page.content.decode()


# --- Coverage ----------------------------------------------------------------


class TestBothTablesCoverEveryRoll:
    def test_every_roll_of_a_d6_lands_on_exactly_one_entry(self, seeded):
        for table_name in (GOLIATH_TABLE, ESCHER_TABLE):
            table = AssetTable.objects.get(name=table_name)
            said = table.coverage()
            assert said.whole
            assert (said.covered, said.total) == (6, 6)
            assert [table.landing(roll).roll_low for roll in range(1, 7)] == list(
                range(1, 7)
            )


# --- The console -------------------------------------------------------------


class TestTheMaintenanceOperation:
    """The seed runs from the maintenance console: GET previews without
    writing, POST records a run and enqueues it, the task writes its
    outcome onto the record, and a redelivered message changes nothing."""

    @pytest.fixture
    def address(self):
        return reverse(f"admin:maintenance_{Operation.SEED_JOURNAL_CONTENT.value}")

    def test_the_preview_lists_the_rows_and_writes_nothing(
        self, client, superuser, core, gang_types, clan_house, address
    ):
        client.force_login(superuser)

        page = client.get(address).content.decode()

        assert f"created the {SLOT_TYPE} slot type" in page
        assert f"created the {GOLIATH_TABLE} table, staged" in page
        assert "Create the missing rows" in page
        assert not Backfill.objects.exists()
        assert not SlotType.objects.filter(name=SLOT_TYPE).exists()

    def test_posting_records_a_run_and_the_task_writes_its_outcome(
        self, client, superuser, core, gang_types, clan_house, address
    ):
        client.force_login(superuser)

        response = client.post(address)

        assert response.status_code == 302
        record = Backfill.objects.get(operation=Operation.SEED_JOURNAL_CONTENT)
        assert str(record.pk) in response["Location"]
        assert record.status == Backfill.Status.DONE
        assert record.triggered_by == superuser
        assert f"created the {SLOT_TYPE} slot type" in record.summary["report"]
        assert record.summary["attempts"] == 1
        assert AssetTable.objects.filter(name=GOLIATH_TABLE, staged=True).exists()

        detail = client.get(
            reverse("admin:maintenance_backfill_detail", args=[record.pk])
        ).content.decode()
        assert "What it did" in detail
        assert f"Goliath gangs now hold the {GOLIATH_TABLE} table" in detail

    def test_a_run_with_nothing_to_do_records_nothing(
        self, client, superuser, seeded, address
    ):
        client.force_login(superuser)

        response = client.post(address, follow=True)

        assert NOTHING_TO_DO in response.content.decode()
        assert not Backfill.objects.exists()
        page = client.get(address).content.decode()
        assert "Nothing to create" in page

    def test_a_redelivered_message_creates_nothing_more(
        self, core, gang_types, clan_house, task_queue
    ):
        record = Backfill.objects.create(
            operation=Operation.SEED_JOURNAL_CONTENT,
            status=Backfill.Status.RUNNING,
            summary={"attempts": 0},
        )

        with task_queue.capture():
            seed_journal_content.enqueue(backfill_id=str(record.pk))
        task_queue.deliver_all()
        task_queue.redeliver_last()

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert record.summary["attempts"] == 1
        assert SlotType.objects.filter(name=SLOT_TYPE).count() == 1
        assert AssetTable.objects.filter(name=GOLIATH_TABLE).count() == 1
        assert Modifier.objects.filter(name__endswith="Goliath Controlled").count() == 6

    def test_only_a_superuser_reaches_it(self, client, staff_arbitrator, address):
        client.force_login(staff_arbitrator)
        assert client.get(address).status_code in (302, 403)
