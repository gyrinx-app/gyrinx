"""Venator ranked skill trees: gang-chosen placements.

The 2026 Venator rule (design/venator-skill-trees.md): the
gang picks skill trees and ranks them 1–4; a fighter's primary and
secondary access is a function of the gang's ordered picks and the
fighter's rank:

    | fighter        | Primary | Secondary |
    | Hunt Leader    | 1 and 2 | 3 and 4   |
    | Hunt Champion  | 1 and 2 | 3         |
    | Specialist     | 1       | 2 and 3   |

The unlock is reading that table **per column**: each rank slot is one
gang-hosted assignable carrying everything except which tree was picked
— a gang-level choice (``TargetsGang`` + ``OffersChoice`` of a
``SkillTree`` token) and per-rank chosen-mode placements
(``PlacesCategory.the_chosen``). The tree pick contributes exactly one
datum, the token's ``category`` home; the whole mapping is authored
content, known to no code.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.browse import offered_by, placements_for
from n26.core.card import build_card, build_gang_card, build_modifier_index
from n26.core.effects import compute, compute_gang
from n26.core.render_text import gang_to_text
from n26.library.models import Skill, SkillTree
from n26.tests.sandbox.actions import (
    choose,
    create_category,
    create_collection,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_profile,
    create_skill,
    create_skill_tree,
    create_subtype,
    found_gang,
    hire_with_option,
    modifier,
    offers_choice,
    places_the_chosen,
    remove,
    section_of,
    targets_gang,
    targets_model,
)

pytestmark = pytest.mark.django_db


# --- The content library --------------------------------------------------


@pytest.fixture
def sets(db):
    """The six 2026 sets (core rules); the gang will rank four."""
    return {
        name.lower(): create_category("Skills", name, position)
        for position, name in enumerate(
            ["Agility", "Brawn", "Combat", "Cunning", "Savant", "Shooting"]
        )
    }


@pytest.fixture
def skills(sets):
    made = {}
    for set_key, names in [
        ("agility", ["Catfall", "Dodge"]),
        ("cunning", ["Backstab"]),
        ("savant", ["Medicate"]),
        ("shooting", ["Marksman"]),
    ]:
        for name in names:
            made[name] = create_skill(name, category=sets[set_key])
    return made


@pytest.fixture
def skills_collection(skills):
    collection = create_collection(
        "Skills & Powers", entries=[(skill, {}) for skill in skills.values()]
    )
    tiers = {
        "primary": section_of(collection, "Primary", 0),
        "secondary": section_of(collection, "Secondary", 1),
        "other": section_of(collection, "Other", 2, is_default=True),
    }
    return collection, tiers


@pytest.fixture
def tokens(sets):
    """One pickable token per set, homed where the set lives."""
    return {
        key: create_skill_tree(category.name, category)
        for key, category in sets.items()
    }


@pytest.fixture
def subtypes(db):
    return {
        "leader": create_subtype("Hunt Leader"),
        "champion": create_subtype("Hunt Champion"),
        "specialist": create_subtype("Specialist"),
    }


#: The table, read per column: rank slot -> who treats its pick as what.
RANKS = {
    1: [("primary", ("leader", "champion", "specialist"))],
    2: [("primary", ("leader", "champion")), ("secondary", ("specialist",))],
    3: [("secondary", ("leader", "champion", "specialist"))],
    4: [("secondary", ("leader",))],
}


@pytest.fixture
def venators(subtypes, skills_collection):
    """The gang type: four rank slots, each carrying the pick and what
    the pick means per fighter rank. No code knows this table."""
    _, tiers = skills_collection
    gang_type = create_gang_type("Venators")

    slots = []
    for rank, meanings in RANKS.items():
        slot = create_hidden(f"Skill Tree {rank}")
        modifier(
            f"Skill Tree {rank}: the gang picks",
            targets_gang(),
            offers_choice(SkillTree, label=f"skill tree {rank}"),
            carried_by=slot,
        )
        for tier, ranks in meanings:
            modifier(
                f"Skill Tree {rank}: {tier} for {', '.join(ranks)}",
                targets_model(with_subtypes=[subtypes[rank_] for rank_ in ranks]),
                places_the_chosen(tiers[tier]),
                carried_by=slot,
            )
        slots.append(slot)

    gang_type.built_ins = create_default_set("Venator gang built-ins", members=slots)
    gang_type.save()
    return gang_type


@pytest.fixture
def profiles(venators, subtypes, skills_collection, person_type):
    _, tiers = skills_collection
    made = {}
    for key, name, price in [
        ("leader", "Hunt Leader", 105),
        ("champion", "Hunt Champion", 85),
        ("specialist", "Hunted Specialist", 35),
    ]:
        profile = create_profile(name, person_type, venators, price=price)
        profile.built_ins = create_default_set(
            f"{name} built-ins", members=[subtypes[key]]
        )
        profile.save()
        made[key] = profile
    # Leaders start with a Primary skill — the ordinary, Escher-shaped
    # offer; which sets are Primary arrives from the gang's picks.
    modifier(
        "Hunt Leader: starts with a Primary skill",
        targets_model(),
        offers_choice(Skill, from_section=tiers["primary"]),
        carried_by=made["leader"],
    )
    return made


@pytest.fixture
def gang(venators):
    return found_gang("The Long Hunt", venators, owner=User.objects.create_user("tom"))


@pytest.fixture
def hunters(gang, profiles):
    return {
        key: hire_with_option(gang, profiles[key], name)
        for key, name in [
            ("leader", "Karrion"),
            ("champion", "Vex"),
            ("specialist", "Nyx"),
        ]
    }


def slot_row(gang, rank):
    return next(
        row
        for row in gang.assignments.all()
        if row.assignable.name == f"Skill Tree {rank}"
    )


def pick(gang, tokens, ranked):
    """Answer the rank slots: ``pick(gang, tokens, ["agility", ...])``."""
    return [
        choose(slot_row(gang, rank), tokens[key])
        for rank, key in enumerate(ranked, start=1)
    ]


def the_gang_computed(gang):
    card = build_gang_card(gang)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute_gang(card, index)


def fighter_computed(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def tiers_for(miniature, skills_collection, sets):
    """``{set key: tier name}`` as this fighter's sections would sit."""
    collection, _ = skills_collection
    placed = placements_for(fighter_computed(miniature), collection)
    return {
        key: placed[category].section.name
        for key, category in sets.items()
        if category in placed
    }


class TestTheGangPicks:
    def test_founding_materialises_four_open_slots(self, gang):
        computed = the_gang_computed(gang)
        assert {slot.kind_label for slot in computed.choices} == {
            f"skill tree {rank}" for rank in (1, 2, 3, 4)
        }
        assert not any(slot.is_resolved for slot in computed.choices)

    def test_the_pick_list_is_every_tree(self, gang, tokens):
        """ "Pick a selection of skill trees": all six sets offer, the
        gang ranks four of them."""
        computed = the_gang_computed(gang)
        offerable = offered_by(computed.choice("skill tree 1"), computed)
        assert {tree.name for tree in offerable} == {
            "Agility",
            "Brawn",
            "Combat",
            "Cunning",
            "Savant",
            "Shooting",
        }

    def test_answers_live_on_the_gang(self, gang, tokens):
        picks = pick(gang, tokens, ["agility", "cunning", "savant", "shooting"])
        assert all(row.gang == gang for row in picks)

        computed = the_gang_computed(gang)
        assert {(slot.kind_label, slot.chosen_name) for slot in computed.choices} == {
            ("skill tree 1", "Agility"),
            ("skill tree 2", "Cunning"),
            ("skill tree 3", "Savant"),
            ("skill tree 4", "Shooting"),
        }


class TestTheTable:
    """The rank table, asserted per fighter — the design's whole point."""

    @pytest.fixture(autouse=True)
    def picked(self, gang, hunters, tokens):
        pick(gang, tokens, ["agility", "cunning", "savant", "shooting"])

    def test_the_hunt_leader(self, hunters, skills_collection, sets):
        assert tiers_for(hunters["leader"], skills_collection, sets) == {
            "agility": "Primary",
            "cunning": "Primary",
            "savant": "Secondary",
            "shooting": "Secondary",
        }

    def test_the_hunt_champion(self, hunters, skills_collection, sets):
        """Nothing from slot 4 — not demoted: simply no modifier names them."""
        assert tiers_for(hunters["champion"], skills_collection, sets) == {
            "agility": "Primary",
            "cunning": "Primary",
            "savant": "Secondary",
        }

    def test_the_specialist(self, hunters, skills_collection, sets):
        assert tiers_for(hunters["specialist"], skills_collection, sets) == {
            "agility": "Primary",
            "cunning": "Secondary",
            "savant": "Secondary",
        }

    def test_the_leaders_primary_skill_offer_follows_the_picks(
        self, hunters, skills_collection
    ):
        """Trees 1 and 2 are both Primary, so the one Primary tier shows
        both — no union mechanism, just two placements into one tier."""
        computed = fighter_computed(hunters["leader"])
        offer = next(
            slot for slot in computed.choices if slot.kind_label == "Primary skill"
        )
        picklist = offered_by(offer, computed)
        assert {line.name for line in picklist.all_lines()} == {
            "Catfall",
            "Dodge",
            "Backstab",
        }


class TestChangingYourMind:
    def test_repicking_moves_every_fighter_at_once(
        self, gang, hunters, tokens, skills_collection, sets
    ):
        """Nothing stored chases the change: placements are computed, so
        a re-pick lands everywhere on the next read."""
        picks = pick(gang, tokens, ["agility", "cunning", "savant", "shooting"])
        assert (
            tiers_for(hunters["specialist"], skills_collection, sets)["agility"]
            == "Primary"
        )

        remove(picks[0])
        choose(slot_row(gang, 1), tokens["shooting"])

        placed = tiers_for(hunters["specialist"], skills_collection, sets)
        assert placed["shooting"] == "Primary"
        assert "agility" not in placed

    def test_the_same_tree_twice_is_noted_and_ordering_settles_it(
        self, gang, hunters, tokens, skills_collection, sets
    ):
        """Inform, not police: the owner may double-pick. The gang sheet
        says so, and the fighter's view takes the better tier — lowest
        section position wins, the ordering rule as everywhere."""
        pick(gang, tokens, ["agility", "cunning", "agility"])

        notes = the_gang_computed(gang).notes
        assert [note.about for note in notes] == [tokens["agility"]]
        assert (
            tiers_for(hunters["leader"], skills_collection, sets)["agility"]
            == "Primary"
        )

    def test_before_any_pick_the_plan_says_why(self, gang, hunters):
        """An unanswered slot places nothing, visibly: the step ran, found
        its fighter, and skipped for want of an answer."""
        computed = fighter_computed(hunters["leader"])
        steps = [
            step
            for step in computed.plan
            if "the chosen set" in step.effect and step.outcome == "skipped"
        ]
        # Five placement modifiers ride the four slots (slot 2 carries
        # two). Four name the Leader and skip for want of an answer; the
        # fifth names only the Specialist and skips at the scope. All
        # skipped, nothing placed — and the plan distinguishes why.
        assert len(steps) == 5
        assert computed.placements == []


class TestTheSheet:
    def test_the_text_renderer_reads_like_the_rulebook(self, gang, hunters, tokens):
        pick(gang, tokens, ["agility", "cunning", "savant"])
        text = gang_to_text(gang)
        print("\n" + text)

        assert "Skill tree 1: Agility" in text
        assert "Skill tree 2: Cunning" in text
        assert "Skill tree 3: Savant" in text
        assert "Skill tree 4: — (not chosen)" in text
        assert "Primary skill: — (not chosen)" in text  # the Leader's, open
