"""Two archetype choices share a slot type but have separate hosts: the Leader’s pick
belongs to the gang and reaches non-Champions, while a Champion’s pick belongs to that
model. Authored display modifiers can show the gang pick on affected member cards
without adding controls.
"""

import pytest
from django.apps import apps as model_registry
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import Assignment
from n26.core.printing import detail_groups
from n26.core.reconcile import assert_reconciled
from n26.core.render import build_choice_offer, render_gang
from n26.core.views.choose import link_slots
from n26.library.archetype_display import EVERY_MODEL, draw_gang_archetypes
from n26.library.authoring import (
    add_built_in,
    attach_modifiers_to,
    create_pickable,
    create_picklist,
    create_profile,
    create_rule,
    create_slot,
    create_slot_type,
    create_subtype,
    ef_adds,
    ef_draws_pick,
    has_subtypes,
    modifier,
    targets_every_model,
    targets_model,
)
from n26.tests.sandbox.actions import found_gang, hire

pytestmark = pytest.mark.django_db


#: Gang and Champion menus overlap on Mutant.
GANG_ARCHETYPES = ("Mutant", "Renegade")
CHAMPION_ARCHETYPES = ("Mutant", "Duellist")

#: Ranks and hire prices.
RANKS = (
    ("Outcast Leader", 120),
    ("Outcast Champion", 90),
    ("Outcast Ganger", 50),
)

#: Rules supplied by gang and personal archetype picks.
GANG_PAYLOAD = "Unstable"
CHAMPION_PAYLOAD = "Duellist's Poise"

#: Negating the excluded rank also covers ranks added later.
EXCEPTED = "Outcast Champion"


@pytest.fixture
def owner(db):
    return User.objects.create_user("archetype-player")


@pytest.fixture
def ranks(default_pack):
    return {name: create_subtype(name) for name, _ in RANKS}


@pytest.fixture
def slot_type(default_pack):
    """Both choices share duplicate-pick guidance, evaluated separately per holder."""
    return create_slot_type("Archetype", allows_repeats=False)


@pytest.fixture
def archetypes(slot_type, ranks):
    """Mutant grants a gang-wide rule excluding Champions; Duellist grants a rule to its
    own bearer.
    """
    made = {
        name: create_pickable(name, slot_type)
        for name in dict.fromkeys(GANG_ARCHETYPES + CHAMPION_ARCHETYPES)
    }
    modifier(
        f"Mutant: {GANG_PAYLOAD}",
        targets_every_model(has_subtypes(ranks[EXCEPTED], negate=True)),
        ef_adds(create_rule(GANG_PAYLOAD)),
        attach_to=made["Mutant"],
    )
    modifier(
        f"Duellist: {CHAMPION_PAYLOAD}",
        targets_model(),
        ef_adds(create_rule(CHAMPION_PAYLOAD)),
        attach_to=made["Duellist"],
    )
    return made


@pytest.fixture
def gang_choice(slot_type, archetypes):
    """Offered to the leader, answered by the gang."""
    return create_slot(
        "Gang archetype",
        slot_type,
        create_picklist(
            "Outcast Archetypes",
            slot_type,
            members=[archetypes[name] for name in GANG_ARCHETYPES],
        ),
        label="Archetype",
        min_picks=1,
        max_picks=1,
        assigned_to="gang",
    )


@pytest.fixture
def champion_choice(slot_type, archetypes):
    """A Champion-hosted archetype slot."""
    return create_slot(
        "Champion archetype",
        slot_type,
        create_picklist(
            "Champion Archetypes",
            slot_type,
            members=[archetypes[name] for name in CHAMPION_ARCHETYPES],
        ),
        label="Archetype",
        min_picks=1,
        max_picks=1,
        assigned_to="bearer",
    )


@pytest.fixture
def profiles(person_type, gang_type, ranks, gang_choice, champion_choice):
    """Each rank has a profile; the Leader carries the gang slot and the Champion carries a
    personal slot.
    """
    made = {}
    for name, price in RANKS:
        profile = create_profile(name, person_type, gang_type, price=price)
        add_built_in(profile, ranks[name])
        made[name] = profile
    add_built_in(made["Outcast Leader"], gang_choice)
    add_built_in(made[EXCEPTED], champion_choice)
    return made


@pytest.fixture
def gang(owner, gang_type):
    return found_gang("The Unmade", gang_type, owner=owner, budget=1000)


@pytest.fixture
def crew(gang, profiles):
    return {name: hire(gang, profiles[name], name, paid=price) for name, price in RANKS}


@pytest.fixture
def reader(client, owner):
    client.force_login(owner)
    return client


def sheet_of(gang):
    sheet = render_gang(gang)
    link_slots(gang, sheet, *sheet.models)
    return sheet


def card_of(gang, name):
    return next(card for card in sheet_of(gang).models if card.name == name)


def picker_url(gang, name):
    (line,) = card_of(gang, name).questions
    return line.href


def choose(reader, gang, name, pickable):
    return reader.post(
        picker_url(gang, name), {"thing": f"library.pickable:{pickable.pk}"}
    )


def computed_card(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def rules_on(miniature):
    return [line.name for line in computed_card(miniature).rules]


def offer_for(miniature):
    """Build the choice offer for this model’s single slot."""
    computed = computed_card(miniature)
    (slot,) = computed.choices
    return build_choice_offer(slot, computed)


class TestTheLeaderIsAskedAndTheGangAnswers:
    """The Leader card displays the question while the slot directs its answer onto the
    gang.
    """

    def test_the_choice_row_is_on_the_leaders_card(self, reader, gang, crew):
        (line,) = card_of(gang, "Outcast Leader").questions

        assert line.kind_label == "Archetype"
        assert line.chosen is None

    def test_the_gangs_own_card_does_not_draw_it(self, reader, gang, crew):
        """The gang owns the answer, but the Leader’s assigned slot owns the question."""
        assert sheet_of(gang).questions == []

    def test_the_ganger_is_not_asked_at_all(self, reader, gang, crew):
        assert card_of(gang, "Outcast Ganger").questions == []

    def test_the_gang_page_draws_the_control_on_his_card(self, reader, gang, crew):
        body = reader.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert picker_url(gang, "Outcast Leader") in body

    def test_what_he_picks_belongs_to_the_gang(self, reader, gang, crew, archetypes):
        response = choose(reader, gang, "Outcast Leader", archetypes["Mutant"])

        assert response.status_code == 302
        pick = Assignment.objects.get(pickable=archetypes["Mutant"])
        assert (pick.gang, pick.miniature) == (gang, None)
        assert card_of(gang, "Outcast Leader").questions[0].chosen == "Mutant"
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestReachingEveryoneExceptOneRank:
    """Negated Champion matching includes existing and newly added non-Champion ranks."""

    @pytest.fixture
    def mutant(self, reader, gang, crew, archetypes):
        choose(reader, gang, "Outcast Leader", archetypes["Mutant"])
        return crew

    def test_the_leader_and_the_ganger_are_reached(self, mutant):
        assert GANG_PAYLOAD in rules_on(mutant["Outcast Leader"])
        assert GANG_PAYLOAD in rules_on(mutant["Outcast Ganger"])

    def test_the_champion_is_untouched(self, mutant):
        assert rules_on(mutant[EXCEPTED]) == []

    def test_a_rank_that_did_not_exist_yet_is_reached_too(
        self, reader, gang, mutant, person_type, default_pack
    ):
        """A negated Champion condition also includes newly authored ranks."""
        later = create_profile("Hive Scum", person_type, gang.gang_type, price=20)
        add_built_in(later, create_subtype("Hive Scum"))
        scum = hire(gang, later, "Scum", paid=20)

        assert GANG_PAYLOAD in rules_on(scum)
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_no_card_draws_a_line_for_the_gangs_pick(self, reader, gang, mutant):
        """Gang-owned picks are not automatically repeated as member equipment."""
        for card in sheet_of(gang).models:
            assert [line.name for line in card.equipment] == []


class TestTheChampionsOwnChoice:
    """A bearer-hosted choice affects only the Champion holding its answer."""

    def test_his_card_asks_it(self, reader, gang, crew):
        (line,) = card_of(gang, EXCEPTED).questions

        assert line.kind_label == "Archetype"

    def test_his_picker_offers_his_own_list(self, reader, gang, crew, archetypes):
        body = reader.get(picker_url(gang, EXCEPTED)).content.decode()

        for name in CHAMPION_ARCHETYPES:
            assert f"library.pickable:{archetypes[name].pk}" in body, name
        assert f"library.pickable:{archetypes['Renegade'].pk}" not in body

    def test_the_pick_is_his(self, reader, gang, crew, archetypes):
        choose(reader, gang, EXCEPTED, archetypes["Duellist"])

        pick = Assignment.objects.get(pickable=archetypes["Duellist"])
        assert pick.miniature == crew[EXCEPTED]
        assert pick.gang is None

    def test_what_it_gives_reaches_him_alone(self, reader, gang, crew, archetypes):
        choose(reader, gang, EXCEPTED, archetypes["Duellist"])

        assert rules_on(crew[EXCEPTED]) == [CHAMPION_PAYLOAD]
        assert rules_on(crew["Outcast Ganger"]) == []
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestTwoChoicesOfOneSlotTypeOnTwoHolders:
    """Duplicate-choice marks and notes compare answers belonging to the same holder. Gang
    and Champion picks do not mark each other.
    """

    @pytest.fixture
    def settled(self, reader, gang, crew, archetypes):
        choose(reader, gang, "Outcast Leader", archetypes["Mutant"])
        return crew

    def test_settling_one_leaves_the_other_open(self, reader, gang, settled):
        assert card_of(gang, EXCEPTED).questions[0].chosen is None

    def test_the_champions_picker_marks_nothing(self, reader, gang, settled):
        marks = {
            pickable.name: pickable.taken_for
            for group in offer_for(settled[EXCEPTED]).groups
            for pickable in group.options
        }

        assert marks == {name: "" for name in CHAMPION_ARCHETYPES}

    def test_taking_the_same_one_again_is_allowed_and_lands_on_him(
        self, reader, gang, settled, archetypes
    ):
        """The same pickable can answer choices on separate holders."""
        choose(reader, gang, EXCEPTED, archetypes["Mutant"])

        held = Assignment.objects.filter(pickable=archetypes["Mutant"], archived=False)
        assert sorted(pick.gang is not None for pick in held) == [False, True]
        assert card_of(gang, EXCEPTED).questions[0].chosen == "Mutant"

    def test_neither_card_says_anything_about_the_repeat(
        self, reader, gang, settled, archetypes
    ):
        choose(reader, gang, EXCEPTED, archetypes["Mutant"])

        assert card_of(gang, EXCEPTED).remarks == []
        assert render_gang(gang).remarks == []


class TestTheGangPageStaysFlat:
    """More available pickables must not add gang-page queries."""

    def test_more_pickables_do_not_mean_more_queries(
        self, reader, gang, crew, archetypes, slot_type, django_assert_num_queries
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.authoring import add_picklist_member
        from n26.library.models import Picklist

        choose(reader, gang, "Outcast Leader", archetypes["Mutant"])
        page = reverse("n26-gang", args=[gang.pk])

        with CaptureQueriesContext(connection) as few:
            assert reader.get(page).status_code == 200

        offered = Picklist.objects.get(name="Outcast Archetypes")
        for index in range(20):
            add_picklist_member(
                offered, create_pickable(f"Archetype {index}", slot_type)
            )

        with django_assert_num_queries(len(few), exact=False):
            assert reader.get(page).status_code == 200


class TestDrawingTheGangsPickOnTheCardsItGoverns:
    """A scoped display modifier shows the gang’s pick as a read-only line on affected
    member cards. The Leader’s original choice retains its picker.
    """

    @pytest.fixture
    def gang_choice(self, slot_type, archetypes):
        """Use a question label distinct from the slot-type label so display rows can be
        checked separately.
        """
        return create_slot(
            "Gang archetype",
            slot_type,
            create_picklist(
                "Outcast Archetypes",
                slot_type,
                members=[archetypes[name] for name in GANG_ARCHETYPES],
            ),
            label="Gang archetype",
            min_picks=1,
            max_picks=1,
            assigned_to="gang",
        )

    @pytest.fixture
    def drawing(self, archetypes, ranks):
        """Share one scoped display modifier across the gang archetypes."""
        rule = modifier(
            "Archetype: drawn on every model except Champions",
            targets_every_model(has_subtypes(ranks[EXCEPTED], negate=True)),
            ef_draws_pick(),
        )
        for name in GANG_ARCHETYPES:
            attach_modifiers_to(archetypes[name], [rule])
        return rule

    @pytest.fixture
    def mutant(self, reader, gang, crew, drawing, archetypes):
        choose(reader, gang, "Outcast Leader", archetypes["Mutant"])
        return crew

    def test_the_ganger_draws_what_the_gang_picked(self, gang, mutant):
        (line,) = card_of(gang, "Outcast Ganger").choices

        assert (line.kind_label, line.chosen) == ("Archetype", "Mutant")

    def test_the_line_has_nothing_to_click(self, gang, mutant):
        """Displayed copies have no picker URL or writable choice key."""
        (line,) = card_of(gang, "Outcast Ganger").choices

        assert (line.href, line.key) == ("", "")
        assert line.is_full

    def test_it_says_the_slot_type_rather_than_the_question(self, gang, mutant):
        """Display copies use the slot-type label; the original question uses its own
        label.
        """
        (drawn,) = card_of(gang, "Outcast Ganger").choices
        (asked,) = card_of(gang, "Outcast Leader").choices

        assert (drawn.kind_label, asked.kind_label) == ("Archetype", "Gang archetype")

    def test_the_champion_draws_none_of_it(self, gang, mutant):
        """The Champion retains only its own open question."""
        lines = card_of(gang, EXCEPTED).choices

        assert [(line.kind_label, line.chosen) for line in lines] == [
            ("Archetype", None)
        ]

    def test_the_champions_step_says_it_was_skipped(self, mutant):
        """The plan records the excluded Champion’s display step as skipped."""
        outcomes = [
            step.outcome
            for step in computed_card(mutant[EXCEPTED]).plan
            if step.effect == "draws the pick"
        ]

        assert outcomes == ["skipped"]

    def test_the_leaders_card_draws_it_once_and_it_is_the_live_one(self, gang, mutant):
        (line,) = card_of(gang, "Outcast Leader").choices

        assert line.chosen == "Mutant"
        assert line.href, "the card that asks the question keeps its picker"

    def test_the_leaders_step_is_skipped_because_his_card_asks_it(self, mutant):
        outcomes = [
            step.outcome
            for step in computed_card(mutant["Outcast Leader"]).plan
            if step.effect == "draws the pick"
        ]

        assert outcomes == ["skipped"]

    def test_a_rank_hired_afterwards_draws_it_too(
        self, reader, gang, mutant, person_type, default_pack
    ):
        later = create_profile("Hive Scum", person_type, gang.gang_type, price=20)
        add_built_in(later, create_subtype("Hive Scum"))
        hire(gang, later, "Scum", paid=20)

        (line,) = card_of(gang, "Scum").choices
        assert (line.kind_label, line.chosen) == ("Archetype", "Mutant")
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_the_gangs_own_card_is_untouched(self, gang, mutant):
        """The gang retains its owned pick among its own rows."""
        sheet = sheet_of(gang)

        assert sheet.questions == []
        assert "Mutant" in [line.name for line in sheet.rows]

    def test_a_champions_own_pick_of_the_same_archetype_draws_nothing(
        self, reader, gang, crew, drawing, archetypes
    ):
        """A bearer-owned pick does not broadcast the gang-pick display to other models."""
        choose(reader, gang, EXCEPTED, archetypes["Mutant"])

        assert card_of(gang, "Outcast Ganger").choices == []
        (his,) = card_of(gang, EXCEPTED).choices
        assert (his.chosen, bool(his.href)) == ("Mutant", True)

    def test_the_print_sheet_prints_it_as_text(self, gang, mutant):
        printed = detail_groups(card_of(gang, "Outcast Ganger"))

        assert ("Archetype", "Mutant") in [
            (group.label, group.text) for group in printed
        ]

    def test_more_pickables_do_not_mean_more_queries(
        self, reader, gang, mutant, slot_type, django_assert_num_queries
    ):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        from n26.library.authoring import add_picklist_member
        from n26.library.models import Picklist

        page = reverse("n26-gang", args=[gang.pk])
        with CaptureQueriesContext(connection) as few:
            assert reader.get(page).status_code == 200

        offered = Picklist.objects.get(name="Outcast Archetypes")
        for index in range(20):
            add_picklist_member(
                offered, create_pickable(f"Archetype {index}", slot_type)
            )

        with django_assert_num_queries(len(few), exact=False):
            assert reader.get(page).status_code == 200


class TestTheWiringTheMigrationWrites:
    """Exercise migration wiring with the current model registry and explicit fixture
    pickable IDs; production IDs remain declared by archetype_display.
    """

    @pytest.fixture
    def wired(self, archetypes, ranks):
        return draw_gang_archetypes(
            model_registry,
            pickable_ids=[archetypes[name].pk for name in GANG_ARCHETYPES],
            excepted=EXCEPTED,
        )

    def test_it_reaches_every_model_except_the_rank_it_names(self, wired, ranks):
        (condition,) = wired.targets_miniature.has_subtypes.all()

        assert (wired.targets_miniature.reach, condition.negate) == (EVERY_MODEL, True)
        assert list(condition.subtypes.all()) == [ranks[EXCEPTED]]
        assert str(wired.effect) == "draws the pick"

    def test_the_reach_it_writes_is_the_one_the_model_declares(self):
        """Verify the stored migration constant against the current model choice."""
        from n26.library.models import TargetsMiniature

        assert EVERY_MODEL == TargetsMiniature.Reach.EVERY_MODEL

    def test_every_archetype_on_the_leaders_list_carries_it(self, wired, archetypes):
        carrying = {
            name
            for name, pickable in archetypes.items()
            if wired in pickable.modifiers.all()
        }

        assert carrying == set(GANG_ARCHETYPES)

    def test_running_it_again_finds_what_the_first_run_made(
        self, wired, archetypes, ranks
    ):
        from n26.library.models import Modifier

        again = draw_gang_archetypes(
            model_registry,
            pickable_ids=[archetypes[name].pk for name in GANG_ARCHETYPES],
            excepted=EXCEPTED,
        )

        assert again == wired
        assert Modifier.objects.filter(draws_pick__isnull=False).count() == 1
        assert (
            archetypes["Mutant"].modifiers.filter(draws_pick__isnull=False).count() == 1
        )

    def test_a_database_without_the_content_is_left_alone(self, db):
        """Missing source content leaves the migration wiring unchanged."""
        from n26.library.models import Modifier

        assert draw_gang_archetypes(model_registry) is None
        assert Modifier.objects.count() == 0

    def test_a_rank_by_that_name_is_what_it_looks_for(self, archetypes, default_pack):
        """Without the excluded rank, skip wiring rather than granting the rule to
        everyone.
        """
        from n26.library.models import Modifier

        assert draw_gang_archetypes(model_registry, excepted="Nobody") is None
        assert Modifier.objects.filter(draws_pick__isnull=False).count() == 0

    def test_what_it_wires_draws_the_pick_the_leader_made(
        self, reader, gang, crew, wired, archetypes
    ):
        choose(reader, gang, "Outcast Leader", archetypes["Mutant"])

        assert [line.chosen for line in card_of(gang, "Outcast Ganger").choices] == [
            "Mutant"
        ]
        assert [line.chosen for line in card_of(gang, EXCEPTED).choices] == [None]
