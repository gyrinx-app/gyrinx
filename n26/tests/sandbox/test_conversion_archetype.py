"""The Archetype conversion, proven on a prod-shaped world.

The Outcast shape, and the last system on the column: four Leader
profiles each offering the gang's archetype, a Champion profile
offering its own, and archetype tokens carrying their whole printed
tables — rank placements for everyone the gang's pick reaches, and
bearer-only rows for a Champion who picked personally.

What this suite is really for is the four behaviours the tables carry.
They ride the modifiers, so moving those wholesale should preserve
them — "should" being the word a test exists to remove:

* the gang's archetype reaches Leaders and Hive Scum, never Champions;
* a Champion's own pick reaches that Champion alone;
* the gang's archetype dies with the Leader who was asked;
* a Champion may hold what the gang holds, and nothing remarks on it.
"""

import pytest

from n26.core.browse import placements_for
from n26.core.capture import differences, gang_state
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.library.conversion import apply, plan_archetype
from n26.library.models import Archetype, Pickable, Slot
from n26.tests.sandbox.actions import (
    choose,
    create_archetype,
    create_category,
    create_collection,
    create_default_set,
    create_gang_type,
    create_profile,
    create_skill,
    create_slot_type,
    create_subtype,
    found_gang,
    has_subtypes,
    hire,
    modifier,
    offers_choice,
    places,
    remove,
    section_of,
    targets_every_model,
    targets_model,
)

pytestmark = pytest.mark.django_db

#: Who each archetype's rank rows reach, and what they place. The
#: Champion row is the bearer-only one: what a Champion gets from
#: picking this personally, inert in the gang's radiated copy.
TABLES = {
    "Brawler": {"leader": "Combat", "scum": "Brawn", "own": "Combat"},
    "Mastermind": {"leader": "Cunning", "scum": "Savant", "own": "Cunning"},
    "Wyrd": {"leader": "Savant", "scum": "Cunning", "own": "Savant"},
}


@pytest.fixture
def prod_shape(default_pack, person_type):
    return build_prod_shape(person_type)


@pytest.fixture
def world(prod_shape, owner):
    return build_world(prod_shape, owner)


def build_prod_shape(person_type):
    """The system as production holds it: four Leader profiles each
    with their own gang-landing offer, a Champion profile with its own
    bearer-landing one, and the archetype tables as modifiers."""
    sets = {
        name: create_category("Skills", name, position)
        for position, name in enumerate(["Brawn", "Combat", "Cunning", "Savant"])
    }
    for name, category in sets.items():
        create_skill(f"{name} Trick", category=category)
    collection = create_collection("Skills & Powers")
    tiers = {
        "primary": section_of(collection, "Primary", 0),
        "other": section_of(collection, "Other", 1, is_default=True),
    }
    subtypes = {
        "leader": create_subtype("Outcast Leader"),
        "champion": create_subtype("Outcast Champion"),
        "scum": create_subtype("Hive Scum"),
    }

    tokens = {}
    for name, table in TABLES.items():
        token = create_archetype(name)
        modifier(
            f"{name}: Leader models — {table['leader']} is Primary",
            targets_every_model(has_subtypes(subtypes["leader"])),
            places(sets[table["leader"]], tiers["primary"]),
            carried_by=token,
        )
        modifier(
            f"{name}: Hive Scum — {table['scum']} is Primary",
            targets_every_model(has_subtypes(subtypes["scum"])),
            places(sets[table["scum"]], tiers["primary"]),
            carried_by=token,
        )
        # The bearer-only row: what a Champion gets by picking this
        # themselves. Never reached through the gang's radiated copy.
        modifier(
            f"{name}: Champion (own pick) — {table['own']} is Primary",
            targets_model(),
            places(sets[table["own"]], tiers["primary"]),
            carried_by=token,
        )
        tokens[name] = token

    menu = create_collection("Outcast Archetypes", entries=list(tokens.values()))
    section = section_of(menu, "Archetypes", 0, is_default=True)

    gang_type = create_gang_type("Outcast", starting_credits=2000)
    leaders = []
    for n in (1, 2):
        profile = create_profile(f"Leader {n}", person_type, gang_type, price=135)
        profile.built_ins = create_default_set(
            f"Leader {n} kit", members=[subtypes["leader"]]
        )
        profile.save()
        modifier(
            f"Leader {n}: chooses the gang's Archetype",
            targets_model(),
            offers_choice(
                Archetype,
                from_section=section,
                label="Archetype",
                will_be_assigned_to="gang",
            ),
            carried_by=profile,
        )
        leaders.append(profile)

    champion = create_profile("Champion", person_type, gang_type, price=95)
    champion.built_ins = create_default_set(
        "Champion kit", members=[subtypes["champion"]]
    )
    champion.save()
    modifier(
        "Champion: chooses an Archetype",
        targets_model(),
        offers_choice(Archetype, from_section=section, label="Archetype"),
        carried_by=champion,
    )

    scum = create_profile("Hive Scum", person_type, gang_type, price=40)
    scum.built_ins = create_default_set("Scum kit", members=[subtypes["scum"]])
    scum.save()

    return gang_type, tokens, leaders, champion, scum, (collection, tiers, sets)


def build_world(prod_shape, owner):
    """Four gangs: one answered throughout with a Champion who chose
    differently, one whose Champion matches the gang, one asked twice
    over (two Leaders), and one that never answered."""
    gang_type, tokens, leaders, champion, scum, _ = prod_shape

    gangs = {
        "answered": found_gang("The Cast Out", gang_type, owner=owner, budget=2000),
        "matching": found_gang("The Echoes", gang_type, owner=owner, budget=2000),
        "twice": found_gang("The Two Crowns", gang_type, owner=owner, budget=2000),
        "quiet": found_gang("The Unspoken", gang_type, owner=owner, budget=2000),
    }
    fighters = {
        "leader": hire(gangs["answered"], leaders[0], "Grim", paid=135),
        "champion": hire(gangs["answered"], champion, "Vex", paid=95),
        "scum": hire(gangs["answered"], scum, "Nub", paid=40),
        "match_leader": hire(gangs["matching"], leaders[0], "Karn", paid=135),
        "match_champion": hire(gangs["matching"], champion, "Sable", paid=95),
        "first_leader": hire(gangs["twice"], leaders[0], "Ash", paid=135),
        "second_leader": hire(gangs["twice"], leaders[1], "Bram", paid=135),
        "quiet_leader": hire(gangs["quiet"], leaders[0], "Mute", paid=135),
    }

    def line(fighter, profile):
        return Assignment.objects.get(profile=profile, miniature_root=fighter)

    # The answered gang: a re-choice leaving an archived answer behind,
    # and a Champion who chose differently from the gang.
    choose(line(fighters["leader"], leaders[0]), tokens["Brawler"])
    remove(
        Assignment.objects.get(
            archetype=tokens["Brawler"], gang=gangs["answered"], archived=False
        )
    )
    choose(line(fighters["leader"], leaders[0]), tokens["Mastermind"])
    choose(line(fighters["champion"], champion), tokens["Wyrd"])

    # The matching gang: the Champion holds what the gang holds.
    choose(line(fighters["match_leader"], leaders[0]), tokens["Brawler"])
    choose(line(fighters["match_champion"], champion), tokens["Brawler"])

    # Two Leaders, two questions, two answers on one gang.
    choose(line(fighters["first_leader"], leaders[0]), tokens["Brawler"])
    choose(line(fighters["second_leader"], leaders[1]), tokens["Wyrd"])

    return gangs, fighters


class TestThePlan:
    def test_it_says_everything_it_would_do(self, world):
        plan = plan_archetype()

        assert plan.ok and not plan.nothing_here
        said = "\n".join(plan.preview())
        assert "create slot type “Archetype”" in said
        assert "refusing repeats" not in said  # a Champion may match the gang
        assert said.count("create pickable") == 3
        assert "told apart as “Archetype”" in said
        assert "create slot “Archetype” drawing on “Archetypes”" in said
        assert "pick landing on the gang" in said
        assert "create slot “Archetype (Champion)”" in said
        assert said.count("replace “Leader") == 2
        assert "replace “Champion: chooses an Archetype”" in said
        # Six live answers; the archived re-choice stays where it is.
        assert said.count("rewrite pick") == 6
        assert "prove 4 of 4 reached gangs read the same, or refuse" in said

    def test_it_deletes_nothing(self, world):
        assert "retire" not in "\n".join(plan_archetype().preview())


class TestTheApply:
    def test_every_page_reads_the_same(self, world):
        gangs, _ = world
        before = {key: gang_state(g) for key, g in gangs.items()}

        apply(plan_archetype())

        for key, gang in gangs.items():
            assert differences(before[key], gang_state(gang)) == []
            assert_reconciled(gang)

    def test_the_gang_pick_still_lands_on_the_gang(self, world):
        gangs, _ = world

        apply(plan_archetype())

        pick = Assignment.objects.get(
            gang=gangs["answered"], pickable__isnull=False, archived=False
        )
        assert pick.pickable.name == "Mastermind"
        assert pick.archetype_id is None
        assert pick.chosen_for_slot == Slot.objects.get(name="Archetype")
        assert pick.miniature_id is None

    def test_the_champion_pick_still_lands_on_the_champion(self, world):
        _, fighters = world

        apply(plan_archetype())

        pick = Assignment.objects.get(
            miniature=fighters["champion"], pickable__isnull=False, archived=False
        )
        assert pick.pickable.name == "Wyrd"
        assert pick.chosen_for_slot == Slot.objects.get(name="Archetype (Champion)")

    def test_the_archived_answer_stays_as_it_was(self, world):
        gangs, _ = world

        apply(plan_archetype())

        archived = Assignment.objects.get(
            gang=gangs["answered"], archived=True, archetype__isnull=False
        )
        assert archived.archetype.name == "Brawler"
        assert archived.pickable_id is None


class TestTheBehaviourThatMustSurvive:
    """The four things the printed tables do, asserted per fighter
    before and after. These ride the modifiers rather than the
    conversion, which is the claim being tested."""

    def test_the_gangs_archetype_reaches_everyone_except_champions(
        self, world, prod_shape
    ):
        _, _, _, _, _, (collection, _, _) = prod_shape
        _, fighters = world
        before = {
            who: _tiers(fighters[who], collection)
            for who in ("leader", "champion", "scum")
        }
        # The gang chose Mastermind: its Leader row places Cunning, its
        # Hive Scum row places Savant, and no row of it names Champions
        # — the Champion's Savant comes from their own Wyrd pick.
        assert before["leader"] == {"Cunning": "Primary"}
        assert before["scum"] == {"Savant": "Primary"}

        apply(plan_archetype())

        for who, was in before.items():
            assert _tiers(fighters[who], collection) == was

    def test_a_champions_own_pick_reaches_that_champion_alone(self, world, prod_shape):
        """Wyrd's bearer-only row places Savant for the Champion who
        picked it; nobody else in the gang reads it."""
        _, _, _, _, _, (collection, _, _) = prod_shape
        _, fighters = world
        before = _tiers(fighters["champion"], collection)
        assert before == {"Savant": "Primary"}

        apply(plan_archetype())

        assert _tiers(fighters["champion"], collection) == before
        # The gang's own pick is Mastermind; the Champion's Wyrd reaches
        # nobody else, so the Hive Scum still reads the gang's table.
        assert _tiers(fighters["scum"], collection) == {"Savant": "Primary"}
        assert _tiers(fighters["leader"], collection) == {"Cunning": "Primary"}

    def test_the_gangs_archetype_dies_with_the_leader(self, world, prod_shape):
        """The pick hangs from the Leader's own line, so removing the
        Leader takes the gang's archetype with it — the whole reason
        the answer is anchored where it is."""
        gang_type, tokens, leaders, _, _, _ = prod_shape
        gangs, fighters = world
        apply(plan_archetype())
        assert Assignment.objects.filter(
            gang=gangs["answered"], pickable__isnull=False, archived=False
        ).exists()

        remove(
            Assignment.objects.get(
                profile=leaders[0], miniature_root=fighters["leader"]
            )
        )

        assert not Assignment.objects.filter(
            gang=gangs["answered"], pickable__isnull=False, archived=False
        ).exists()
        gangs["answered"].refresh_from_db()
        assert_reconciled(gangs["answered"])

    def test_a_champion_may_hold_what_the_gang_holds_silently(self, world):
        """Ten do in production. An offer never remarks on a repeat, and
        the slot type allowing them is what keeps that silence."""
        gangs, _ = world
        before = gang_state(gangs["matching"])
        assert before["notes"] == []

        apply(plan_archetype())

        after = gang_state(gangs["matching"])
        assert differences(before, after) == []
        assert after["notes"] == []

    def test_a_gang_asked_twice_keeps_both_answers(self, world):
        gangs, _ = world
        before = gang_state(gangs["twice"])

        apply(plan_archetype())

        assert differences(before, gang_state(gangs["twice"])) == []
        held = Assignment.objects.filter(
            gang=gangs["twice"], pickable__isnull=False, archived=False
        )
        assert sorted(p.pickable.name for p in held) == ["Brawler", "Wyrd"]


class TestTheGangSheetShowsWhatTheGangHolds:
    """A pick answering a question asked of somebody else would
    otherwise appear on no card at all: drawn as its choice's answer,
    on a card that draws no such choice. The gang's archetype is the
    first system with that shape, and the sheet must still list it."""

    def test_the_gang_sheet_lists_the_archetype_before_and_after(self, world):
        gangs, _ = world
        before = gang_state(gangs["answered"])
        assert "Mastermind" in before["rows"]

        apply(plan_archetype())

        assert "Mastermind" in gang_state(gangs["answered"])["rows"]

    def test_a_pick_its_own_card_asks_about_draws_no_line_of_its_own(
        self, world, prod_shape
    ):
        """The ordinary shape is untouched: where the question is asked
        on the same card as the answer, the pick is still drawn under
        the choice row and nowhere else."""
        _, fighters = world

        apply(plan_archetype())

        card = gang_state(fighters["champion"].gang)["models"][
            str(fighters["champion"].pk)
        ]
        assert ("Archetype", "Wyrd") in card["choices"]
        # Drawn as the choice's answer and nowhere else: not among the
        # kit, the rules, or anything else the card lists.
        assert not any(
            "Wyrd" in str(value)
            for key, value in card.items()
            if key not in {"choices", "remarks"}
        )


class TestTheStory:
    def test_the_words_already_written_do_not_move(self, world):
        from n26.core import history
        from n26.core.history import _kindword

        gangs, _ = world
        said = _story(history.build(gangs["answered"]))

        apply(plan_archetype())

        assert _story(history.build(gangs["answered"])) == said
        pick = Assignment.objects.filter(
            gang=gangs["answered"], pickable__isnull=False
        ).first()
        # The slot type wears the kind's own name, so the word a pick
        # answers to is the word it always had.
        assert _kindword(pick) == "archetype"


class TestRechoosing:
    def test_both_slots_answer_again_on_the_new_machinery(self, world, prod_shape):
        gang_type, tokens, leaders, champion, _, _ = prod_shape
        gangs, fighters = world
        apply(plan_archetype())

        remove(
            Assignment.objects.get(gang=gangs["answered"], pickable__name="Mastermind")
        )
        choose(
            Assignment.objects.get(
                profile=leaders[0], miniature_root=fighters["leader"]
            ),
            Pickable.objects.get(name="Wyrd"),
            slot=Slot.objects.get(name="Archetype"),
        )
        remove(
            Assignment.objects.get(
                miniature=fighters["champion"], pickable__name="Wyrd"
            )
        )
        choose(
            Assignment.objects.get(
                profile=champion, miniature_root=fighters["champion"]
            ),
            Pickable.objects.get(name="Brawler"),
            slot=Slot.objects.get(name="Archetype (Champion)"),
        )

        state = gang_state(gangs["answered"])
        # The gang holds the answer, so its sheet lists it; the question
        # itself is asked on the Leader's card, where the offer used to
        # be, and that card shows the choice row.
        assert "Wyrd" in state["rows"]
        leader_card = state["models"][str(fighters["leader"].pk)]
        assert ("Archetype", "Wyrd") in leader_card["choices"]
        card = state["models"][str(fighters["champion"].pk)]
        assert ("Archetype", "Brawler") in card["choices"]
        gangs["answered"].refresh_from_db()
        assert_reconciled(gangs["answered"])

    def test_a_second_run_is_a_clean_no_op(self, world):
        apply(plan_archetype())

        assert plan_archetype().nothing_here


class TestTheRefusals:
    def test_a_standing_slot_type_is_refused(self, world):
        create_slot_type("Archetype")

        plan = plan_archetype()

        assert not plan.ok
        assert any("already stands" in problem for problem in plan.problems)

    def test_a_colliding_pickable_is_refused(self, world):
        """The qualifier is what clears the way; one wearing it too is
        a collision the plan must name rather than crash on."""
        from n26.tests.sandbox.actions import create_pickable

        other = create_slot_type("Something Else")
        create_pickable("Brawler", other, qualifier="Archetype")

        plan = plan_archetype()

        assert not plan.ok
        assert any("already wear these names" in p for p in plan.problems)

    def test_a_differently_cased_collision_is_refused_in_words(self, world):
        """The name constraint folds case, so the check must too: an
        exact-match look would call “brawler” free and let the collision
        arrive as a database error where a sentence was promised."""
        from n26.tests.sandbox.actions import create_pickable

        other = create_slot_type("Something Else")
        create_pickable("brawler", other, qualifier="archetype")

        plan = plan_archetype()

        assert not plan.ok
        assert any("already wear these names" in p for p in plan.problems)

    def test_a_differently_cased_slot_type_is_refused(self, world):
        create_slot_type("ARCHETYPE")

        plan = plan_archetype()

        assert not plan.ok
        assert any("already stands" in problem for problem in plan.problems)

    def test_a_shared_offer_is_refused(self, world, prod_shape):
        """Every offer here is one profile's own; a shared one is a
        different shape and needs a different step."""
        from n26.library.authoring import attach_modifiers_to

        _, _, leaders, _, scum, _ = prod_shape
        offer = next(
            m
            for m in leaders[0].modifiers.all()
            if getattr(m, "offers_choice", None) is not None
        )
        attach_modifiers_to(scum, [offer])

        plan = plan_archetype()

        assert not plan.ok
        assert any("expected one profile" in p for p in plan.problems)

    def test_a_profile_asking_both_questions_is_refused(self, world, prod_shape):
        """A profile carrying both offers asks two questions no anchor
        tells apart, so its picks could settle on either slot."""
        from n26.library.authoring import attach_modifiers_to

        _, _, leaders, champion, _, _ = prod_shape
        champion_offer = next(
            m
            for m in champion.modifiers.all()
            if getattr(m, "offers_choice", None) is not None
        )
        attach_modifiers_to(leaders[0], [champion_offer])

        plan = plan_archetype()

        assert not plan.ok
        assert any("cannot be told apart" in p for p in plan.problems) or any(
            "expected one profile" in p for p in plan.problems
        )

    def test_an_off_menu_pick_is_refused(self, world, prod_shape):
        _, _, leaders, _, _, _ = prod_shape
        gangs, fighters = world
        offmenu = create_archetype("Something Else Entirely")
        line = Assignment.objects.get(
            profile=leaders[0], miniature_root=fighters["quiet_leader"]
        )
        Assignment.objects.create(
            archetype=offmenu,
            gang=gangs["quiet"],
            caused_by=line,
            chosen_for=line,
            gang_root=gangs["quiet"],
        )

        plan = plan_archetype()

        assert not plan.ok
        assert any("the menu does not offer" in p for p in plan.problems)

    def test_an_archived_archetype_is_not_resurrected(self, world, prod_shape):
        _, tokens, _, _, _, _ = prod_shape
        tokens["Wyrd"].archived = True
        tokens["Wyrd"].save()

        plan = plan_archetype()

        assert not plan.ok
        assert any("Wyrd" in problem for problem in plan.problems)


def _tiers(miniature, collection):
    """``{category name: tier}`` as this fighter's sections sit."""
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute

    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    placed = placements_for(compute(card, index), collection)
    return {
        category.name: where.section.name
        for category, where in placed.items()
        if where.section.name != "Other"
    }


def _story(acts):
    """Every word a gang's history page puts on the screen."""
    told = []
    for act in acts:
        told.append("".join(span.text for span in act.spans))
        told.extend(f"{sub.name}|{sub.kind}|{sub.note}" for sub in act.subs)
    return told
