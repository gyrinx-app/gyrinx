"""The gang scope may name a pick: "gangs that have picked Goliath".

The Gang supertype (design/house-and-territory-tables.md): every Clan
House gang type builds a hidden slot in with its House already picked,
and an Outcast gang's Clan House pick gives the same slot with the House
picked. A journal's "Goliath Controlled" territory boon is then a
modifier that targets the gang alone, narrowed by ``GangHasPickable`` —
the gang-scope twin of ``HasPickable`` — and reaches a Goliath gang and
a Clan House Goliath Outcast gang alike, whether the pick was written at
founding or dealt by a grant.

What this file holds still: founding a Clan House gang writes the slot
and the pick with no open choice, no line and no rating; the gang
condition and the model condition read the same fact; taking the pick
back makes both false; a gang of another House, and a Clanless Outcast,
never match; ``negate`` inverts; a condition-less gang scope is exactly
what it was; a held asset's conditional Income reaches the holder the
condition names and prints as a boon with its scope wording; and the
authoring pages say the condition in the same words the plan does.
"""

import re

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gyrinx.site.models import Availability, FeatureFlag
from n26.core import select
from n26.core.card import build_card, build_gang_card, build_modifier_index
from n26.core.effects import compute, compute_gang
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_campaign, render_gang
from n26.flags import CAMPAIGNS
from n26.library.authoring import create_asset
from n26.library.authoring import targets_model as authoring_targets_model
from n26.library.core_campaign import seed_core_campaign
from n26.library.income import (
    INCOME,
    boons_of,
    income_counter,
    income_of,
    is_income_contribution,
)
from n26.library.models import CampaignType, Modifier
from n26.library.prose import sentence_for
from n26.tests.sandbox.actions import (
    add_asset,
    add_built_in,
    assign,
    assign_asset,
    choose,
    create_gang_type,
    create_hidden,
    create_pickable,
    create_picklist,
    create_profile,
    create_rule,
    create_slot,
    create_slot_type,
    ef_adds,
    ef_contributes_to_counter,
    found_campaign,
    found_gang,
    has_gang_pickable,
    has_pickable,
    hire,
    join_campaign,
    modifier,
    remove,
    targets_every_model,
    targets_gang,
    targets_gang_alone,
    transfer_asset,
)

pytestmark = pytest.mark.django_db


# --- The supertype: a hidden gang-level choice with marker pickables --------


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def supertype(default_pack):
    return create_slot_type(
        "Gang supertype", plural_name="Gang supertypes", allows_repeats=False
    )


@pytest.fixture
def houses(supertype):
    """Markers carrying no modifiers of their own; rules key on them."""
    return {name: create_pickable(name, supertype) for name in ("Goliath", "Escher")}


@pytest.fixture
def goliath(houses):
    return houses["Goliath"]


@pytest.fixture
def supertypes(supertype, houses):
    return create_picklist("Gang supertypes", supertype, members=list(houses.values()))


@pytest.fixture
def supertype_slot(supertype, supertypes):
    """Hidden: the sheet never prints a "Gang supertype" line."""
    return create_slot(
        "Gang supertype", supertype, supertypes, assigned_to="gang", hidden=True
    )


@pytest.fixture
def goliath_type(default_pack, supertype_slot, goliath):
    """A Clan House gang type: the slot built in, already settled."""
    made = create_gang_type("Goliath")
    add_built_in(made, supertype_slot, default_pickable=goliath)
    return made


@pytest.fixture
def escher_type(default_pack, supertype_slot, houses):
    made = create_gang_type("Escher")
    add_built_in(made, supertype_slot, default_pickable=houses["Escher"])
    return made


@pytest.fixture
def outcast_type(default_pack):
    """Builds no supertype in: the Clan House pick gives the slot."""
    return create_gang_type("Outcasts")


@pytest.fixture
def clan_house(default_pack, supertype_slot, goliath):
    """The Outcast choice: its own slot type, its own pickables. Picking
    Goliath gives the gang's supertype slot with Goliath already picked."""
    slot_type = create_slot_type("Clan House")
    clan_goliath = create_pickable("Clan House: Goliath", slot_type)
    modifier(
        "Clan House: Goliath — the gang counts as Goliath",
        targets_gang_alone(),
        ef_adds(supertype_slot, with_pick=goliath),
        carried_by=clan_goliath,
    )
    clan_houses = create_picklist("Clan Houses", slot_type, members=[clan_goliath])
    slot = create_slot("Clan House", slot_type, clan_houses, assigned_to="gang")
    return slot, clan_goliath


@pytest.fixture
def leader(person_type, outcast_type, clan_house):
    slot, _ = clan_house
    profile = create_profile("Outcast Leader", person_type, outcast_type, price=120)
    add_built_in(profile, slot)
    return profile


@pytest.fixture
def make_ganger(person_type):
    def make(gang_type, name=None):
        name = name or f"{gang_type.name} ganger"
        return create_profile(name, person_type, gang_type, price=40)

    return make


@pytest.fixture
def journal_boons(default_pack, goliath):
    """A journal's two "Goliath Controlled" shapes on one hidden carrier a
    gang is given: a rule for the gang alone, conditioned on the gang,
    and a rule for every fighter, conditioned on the model."""
    return create_hidden(
        "Goliath Controlled",
        effects=[
            (
                targets_gang_alone(has_gang_pickable(goliath)),
                ef_adds(create_rule("Goliath Controlled (gang)")),
            ),
            (
                targets_every_model(has_pickable(goliath)),
                ef_adds(create_rule("Goliath Controlled (fighter)")),
            ),
        ],
    )


def card_of(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return card, compute(card, index)


def gang_computed(gang):
    card = build_gang_card(gang)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute_gang(card, index)


def names(contributions):
    return [contribution.name for contribution in contributions]


def gang_rules(gang):
    return names(gang_computed(gang).rules)


def fighter_rules(miniature):
    return names(card_of(miniature)[1].rules)


def outcomes(gang, effect_word):
    """What the gang's plan did with the steps whose effect says this."""
    return [
        step.outcome
        for step in gang_computed(gang).plan
        if effect_word in str(step.effect)
    ]


def pick_clan_house(boss, clan_house):
    _, clan_goliath = clan_house
    (slot,) = [s for s in card_of(boss)[1].choices if s.kind_label == "Clan House"]
    choose(slot.anchor.assignment, clan_goliath)


# --- A Clan House gang type -------------------------------------------------


class TestFoundingAClanHouseGang:
    """The slot arrives settled: the gang has picked its House before
    anyone is asked anything, and both conditions read the pick."""

    @pytest.fixture
    def gang(self, owner, goliath_type):
        return found_gang("Irontooth", goliath_type, owner=owner, budget=1000)

    def test_the_slot_and_the_pick_are_written_and_no_choice_is_open(
        self, gang, supertype_slot, goliath
    ):
        assert gang.assignments.filter(slot=supertype_slot, archived=False).exists()
        (pick,) = gang.assignments.filter(pickable=goliath, archived=False)
        assert pick.chosen_for is not None
        assert gang_computed(gang).choices == []
        assert render_gang(gang).choices == []

    def test_a_gang_rule_conditioned_on_the_pick_reaches_the_gang(
        self, gang, journal_boons
    ):
        assign(journal_boons, gang=gang)

        assert gang_rules(gang) == ["Goliath Controlled (gang)"]
        assert outcomes(gang, "(gang)") == ["reached"]

    def test_a_model_rule_conditioned_on_the_pick_reaches_every_member(
        self, gang, goliath_type, make_ganger, journal_boons
    ):
        ganger = make_ganger(goliath_type)
        one = hire(gang, ganger, "One", paid=40)
        two = hire(gang, ganger, "Two", paid=40)
        assign(journal_boons, gang=gang)

        assert fighter_rules(one) == ["Goliath Controlled (fighter)"]
        assert fighter_rules(two) == ["Goliath Controlled (fighter)"]
        # The gang's own rule is the gang's alone: it prints on the sheet
        # and rides no fighter.
        assert "Goliath Controlled (gang)" not in fighter_rules(one)

    def test_the_sheet_draws_no_supertype_line_and_it_is_worth_nothing(
        self, gang, journal_boons
    ):
        assign(journal_boons, gang=gang)
        gang.refresh_from_db()

        sheet = render_gang(gang)

        assert "supertype" not in str(sheet.rows).lower()
        assert "supertype" not in str(sheet.rules).lower()
        assert "Goliath Controlled (gang)" in str(sheet.rules)
        assert gang.rating == 0
        assert_reconciled(gang)


# --- An Outcast gang --------------------------------------------------------


class TestAClanHouseOutcastGang:
    """Nothing built in: the Clan House pick gives the supertype slot
    with Goliath picked, and from then on both conditions read the
    gang as a Goliath gang — until the pick is taken back."""

    @pytest.fixture
    def gang(self, owner, outcast_type):
        return found_gang("The Forgotten", outcast_type, owner=owner, budget=1000)

    @pytest.fixture
    def crew(self, gang, leader, outcast_type, make_ganger):
        boss = hire(gang, leader, "Boss", paid=120)
        rat = hire(gang, make_ganger(outcast_type, "Scav"), "Rat", paid=40)
        return boss, rat

    def test_neither_rule_reaches_before_the_pick(self, gang, crew, journal_boons):
        boss, rat = crew
        assign(journal_boons, gang=gang)

        assert gang_rules(gang) == []
        assert outcomes(gang, "(gang)") == ["skipped"]
        assert fighter_rules(boss) == []
        assert fighter_rules(rat) == []

    def test_both_reach_once_the_clan_house_is_picked(
        self, gang, crew, clan_house, journal_boons
    ):
        boss, rat = crew
        assign(journal_boons, gang=gang)
        before = gang.rating

        pick_clan_house(boss, clan_house)

        assert names(gang_computed(gang).picks) == ["Goliath"]
        assert gang_rules(gang) == ["Goliath Controlled (gang)"]
        assert fighter_rules(boss) == ["Goliath Controlled (fighter)"]
        assert fighter_rules(rat) == ["Goliath Controlled (fighter)"]
        gang.refresh_from_db()
        assert gang.rating == before
        assert "supertype" not in str(render_gang(gang).rows).lower()
        assert_reconciled(gang)

    def test_taking_the_pick_back_makes_both_false(
        self, gang, crew, clan_house, journal_boons
    ):
        _, clan_goliath = clan_house
        boss, rat = crew
        assign(journal_boons, gang=gang)
        pick_clan_house(boss, clan_house)

        remove(Assignment.objects.get(pickable=clan_goliath, archived=False))

        assert names(gang_computed(gang).picks) == []
        assert gang_rules(gang) == []
        assert fighter_rules(boss) == []
        assert fighter_rules(rat) == []
        gang.refresh_from_db()
        assert_reconciled(gang)


# --- Who never matches -----------------------------------------------------


class TestWhoIsNotAGoliathGang:
    @pytest.fixture
    def escher(self, owner, escher_type):
        return found_gang("Wild Roses", escher_type, owner=owner, budget=1000)

    @pytest.fixture
    def clanless(self, owner, outcast_type):
        """An Outcast gang that picked no Clan House."""
        return found_gang("The Nameless", outcast_type, owner=owner, budget=1000)

    def test_an_escher_gang_and_a_clanless_outcast_gang_never_match(
        self, escher, clanless, escher_type, outcast_type, make_ganger, journal_boons
    ):
        rose = hire(escher, make_ganger(escher_type), "Rose", paid=40)
        nobody = hire(clanless, make_ganger(outcast_type), "Nobody", paid=40)
        assign(journal_boons, gang=escher)
        assign(journal_boons, gang=clanless)

        assert gang_rules(escher) == []
        assert gang_rules(clanless) == []
        assert fighter_rules(rose) == []
        assert fighter_rules(nobody) == []

    def test_negate_reaches_every_gang_except_those(
        self, owner, escher, clanless, goliath_type, goliath
    ):
        irontooth = found_gang("Irontooth", goliath_type, owner=owner, budget=1000)
        not_goliath = create_hidden(
            "Not Goliath",
            effects=[
                (
                    targets_gang_alone(has_gang_pickable(goliath, negate=True)),
                    ef_adds(create_rule("Outsiders")),
                )
            ],
        )
        for gang in (irontooth, escher, clanless):
            assign(not_goliath, gang=gang)

        assert gang_rules(irontooth) == []
        assert gang_rules(escher) == ["Outsiders"]
        assert gang_rules(clanless) == ["Outsiders"]

    def test_an_empty_condition_narrows_nothing(self, escher):
        scope = targets_gang_alone(has_gang_pickable())
        anyone = create_hidden(
            "Anyone", effects=[(scope, ef_adds(create_rule("For all")))]
        )
        assign(anyone, gang=escher)

        assert isinstance(scope.as_selector(), select.Anything)
        assert select.specificity(scope.as_selector()) == 0
        assert gang_rules(escher) == ["For all"]
        # Silent everywhere, not only in the selector: the words must not
        # claim a narrowing the reach does not have.
        assert str(scope) == "the gang alone"
        assert not scope.is_conditional
        (row,) = anyone.modifiers.all()
        assert sentence_for(row, carriage=None).text.startswith("The gang gains")


# --- A held asset's conditional boon ---------------------------------------


class TestAConditionalTerritoryBoon:
    """A journal territory's "Goliath Controlled: +10 Income" is a
    contribution on the asset, scoped to the gang alone and narrowed to
    gangs that have picked Goliath. It reaches the holder's Income only
    while a Goliath gang holds it, moves with the asset, and prints on
    the campaign page as a boon in its scope's words — apart from the
    plain figure every holder gets."""

    @pytest.fixture(autouse=True)
    def open_to_everyone(self):
        return FeatureFlag.objects.create(
            slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
        )

    @pytest.fixture
    def core(self, default_pack):
        seed_core_campaign(apps)
        return CampaignType.objects.get(name="Territory campaign")

    @pytest.fixture
    def campaign(self, core):
        arbitrator = User.objects.create_user("arbitrator")
        return found_campaign("Dust Falls", core, owner=arbitrator, budget=1000)

    @pytest.fixture
    def amneo_vats(self, core, goliath):
        territory = core.asset_types.get(label_singular="Territory")
        vats = create_asset("Amneo-vats", territory, income=20)
        modifier(
            "Amneo-vats: Goliath Controlled",
            targets_gang_alone(has_gang_pickable(goliath)),
            ef_contributes_to_counter(income_counter(), 10),
            carried_by=vats,
        )
        return vats

    @pytest.fixture
    def gangs(self, campaign, goliath_type, escher_type):
        made = {}
        for name, gang_type in (
            ("Irontooth", goliath_type),
            ("Wild Roses", escher_type),
        ):
            gang = found_gang(name, gang_type, owner=User.objects.create_user(name))
            join_campaign(gang, campaign)
            made[name] = gang
        return made

    def reading(self, gang):
        block = render_gang(gang).campaign
        return next(line.value for line in block.counters if line.name == INCOME)

    def test_the_boon_is_not_the_figure(self, amneo_vats):
        (boon,) = boons_of(amneo_vats)
        assert not is_income_contribution(boon)
        assert income_of(amneo_vats) == 20

    def test_a_goliath_holder_reads_the_boon_and_an_escher_holder_does_not(
        self, campaign, amneo_vats, gangs
    ):
        held = add_asset(campaign, amneo_vats)

        assign_asset(held, gangs["Irontooth"])
        assert self.reading(gangs["Irontooth"]) == 30
        assert self.reading(gangs["Wild Roses"]) == 0

        transfer_asset(held, gangs["Wild Roses"])
        assert self.reading(gangs["Irontooth"]) == 0
        assert self.reading(gangs["Wild Roses"]) == 20

    def test_the_campaign_page_prints_the_boon_in_its_scopes_words(
        self, campaign, amneo_vats, gangs
    ):
        add_asset(campaign, amneo_vats)

        (territories,) = render_campaign(campaign).assets
        (entry,) = territories.entries

        assert entry.income == 20
        (boon,) = entry.boons
        assert "gangs that have picked Goliath" in boon
        assert "10" in boon and INCOME in boon


# --- Nothing changes for a scope with no conditions ------------------------


class TestAConditionLessGangScopeIsUnchanged:
    def test_it_compiles_to_anything_in_round_nought(self, default_pack):
        for scope in (targets_gang(), targets_gang_alone()):
            assert isinstance(scope.as_selector(), select.Anything)
            assert select.specificity(scope.as_selector()) == 0
        assert str(targets_gang()) == "the gang"
        assert str(targets_gang_alone()) == "the gang alone"
        assert not targets_gang().narrows
        assert targets_gang_alone().narrows

    def test_the_sheet_reads_flat_however_many_members(
        self, owner, goliath_type, make_ganger, journal_boons
    ):
        """The condition rows ride the modifier index's prefetch, so a
        conditioned gang scope costs nothing per member."""
        gang = found_gang("Irontooth", goliath_type, owner=owner, budget=1000)
        ganger = make_ganger(goliath_type)
        assign(journal_boons, gang=gang)
        hire(gang, ganger, "One", paid=40)
        with CaptureQueriesContext(connection) as few:
            render_gang(gang)

        for name in ("Two", "Three", "Four"):
            hire(gang, ganger, name, paid=40)
        with CaptureQueriesContext(connection) as more:
            render_gang(gang)

        assert len(more) <= len(few)


# --- What the authoring pages say ------------------------------------------


class TestWhatTheAuthoringPagesSay:
    def test_the_scope_says_the_condition(self, goliath, houses):
        assert str(targets_gang(has_gang_pickable(goliath))) == (
            "gangs that have picked Goliath"
        )
        assert str(targets_gang_alone(has_gang_pickable(goliath))) == (
            "gangs that have picked Goliath (the gang alone)"
        )
        assert str(targets_gang(has_gang_pickable(goliath, negate=True))) == (
            "every gang except those that have picked Goliath"
        )
        assert str(targets_gang(has_gang_pickable(goliath, houses["Escher"]))) == (
            "gangs that have picked Escher or Goliath"
        )

    def test_the_sentence_leads_with_the_condition(self, goliath, default_pack):
        boon = modifier(
            "Goliath Controlled",
            targets_gang_alone(has_gang_pickable(goliath)),
            ef_adds(create_rule("Goliath Controlled")),
        )

        sentence = sentence_for(boon, carriage=None)

        assert sentence.text == (
            "For gangs that have picked Goliath, the gang gains Goliath "
            "Controlled, printed on the gang page."
        )

    def test_the_plan_names_the_condition(self, owner, goliath_type, journal_boons):
        gang = found_gang("Irontooth", goliath_type, owner=owner, budget=1000)
        assign(journal_boons, gang=gang)

        (step,) = [s for s in gang_computed(gang).plan if "(gang)" in str(s.effect)]

        assert "[gangs that have picked Goliath (the gang alone)]" in str(step)
        assert step.ran_in == 1

    def test_the_composer_names_the_modifier_after_its_scope_and_reads_it_back(
        self, client, goliath, default_pack
    ):
        client.force_login(User.objects.create_user("author", is_staff=True))
        rule = create_rule("Goliath Controlled")

        response = client.post(
            "/n26/authoring/modifiers/new/",
            {
                "scope_kind": "targets_gang_alone",
                "effect_kind": "ef_adds",
                "what-thing_kind": "rule",
                "what-thing_rule": str(rule.pk),
                "conditions-TOTAL_FORMS": "1",
                "conditions-INITIAL_FORMS": "0",
                "conditions-MIN_NUM_FORMS": "0",
                "conditions-MAX_NUM_FORMS": "1000",
                "conditions-0-kind": "has_gang_pickable",
                "conditions-0-pickables": [str(goliath.pk)],
            },
        )

        assert response.status_code == 302, response.content.decode()[:2000]
        (made,) = Modifier.objects.filter(targets_gang__isnull=False)
        assert made.name == (
            "gangs that have picked Goliath (the gang alone): adds Goliath Controlled"
        )
        assert [str(p) for p in made.scope.has_gang_pickable.get().pickables.all()] == [
            "Goliath"
        ]
        # Opened again, the page finds the condition it already carries.
        body = client.get(response["Location"]).content.decode()
        assert 'name="conditions-0-kind"' in body
        # The option is written across several lines.
        assert re.search(rf'<option\s+value="{goliath.pk}"[^>]*\sselected', body)


# --- Refusals ---------------------------------------------------------------


class TestAConditionBelongsToItsScope:
    def test_a_gang_condition_is_refused_on_the_model_scope(self, goliath):
        with pytest.raises(ValueError, match="narrows the gang"):
            authoring_targets_model(has_gang_pickable(goliath))
        with pytest.raises(ValueError, match="narrows the gang"):
            targets_every_model(has_gang_pickable(goliath))

    def test_a_model_condition_is_refused_on_the_gang_scope(self, goliath):
        with pytest.raises(ValueError, match="narrows models, not the gang"):
            targets_gang_alone(has_pickable(goliath))
        with pytest.raises(ValueError, match="narrows models, not the gang"):
            targets_gang(has_pickable(goliath))
