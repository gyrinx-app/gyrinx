"""The Skill Tree conversion, proven on a prod-shaped world.

The four rank hiddens' gang-wide offers become granted slots and the
tree tokens become pickables linking the categories the tokens name —
that link being this system's whole payload: the per-rank placements
read whatever was chosen and place its category, before and after.

Nothing is deleted; the slot type refuses repeats, which is both the
game's rule (four different trees) and what keeps a doubling gang's
warning note drawn: an offer always notes a doubled settling, and a
slot only notes one where its type refuses them.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.browse import placements_for
from n26.core.capture import differences, gang_state
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.library.conversion import apply, plan_skill_tree
from n26.library.models import Hidden, Pickable, SkillTree, Slot
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
    has_subtypes,
    hire,
    modifier,
    offers_choice,
    places_the_chosen,
    remove,
    section_of,
    targets_every_model,
    targets_gang,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def prod_shape(default_pack):
    return build_prod_shape()


@pytest.fixture
def world(prod_shape, person_type, owner, default_pack):
    return build_world(prod_shape, person_type, owner)


def build_prod_shape():
    """The system as production holds it: four rank hiddens each with a
    gang-wide whole-kind offer and a chosen-mode placement, and six tree
    tokens naming the sets they stand for."""
    sets = {
        name.lower(): create_category("Skills", name, position)
        for position, name in enumerate(
            ["Agility", "Brawn", "Combat", "Cunning", "Savant", "Shooting"]
        )
    }
    create_skill("Catfall", category=sets["agility"])
    create_skill("Backstab", category=sets["cunning"])
    collection = create_collection("Skills & Powers")
    tiers = {
        "primary": section_of(collection, "Primary", 0),
        "secondary": section_of(collection, "Secondary", 1),
        "other": section_of(collection, "Other", 2, is_default=True),
    }
    tokens = {
        key: create_skill_tree(category.name, category)
        for key, category in sets.items()
    }
    hunter = create_subtype("Hunter")
    carriers = {}
    for rank, tier in [
        (1, "primary"),
        (2, "primary"),
        (3, "secondary"),
        (4, "secondary"),
    ]:
        carrier = create_hidden(f"Skill Tree {rank}")
        modifier(
            f"Skill Tree {rank}: offers a choice of skill tree",
            targets_gang(),
            offers_choice(SkillTree, label=f"Skill Tree {rank}"),
            carried_by=carrier,
        )
        modifier(
            f"Skill Tree {rank}: {tier} for hunters",
            targets_every_model(has_subtypes(hunter)),
            places_the_chosen(tiers[tier]),
            carried_by=carrier,
        )
        carriers[rank] = carrier
    return sets, tokens, carriers, hunter, (collection, tiers)


def build_world(prod_shape, person_type, owner):
    """Four gangs: fully answered, doubling one tree across two ranks,
    partially answered, and never answered — plus a doubled answer (one
    rank clicked twice) and an archived re-choice."""
    sets, tokens, carriers, hunter, _ = prod_shape
    gang_type = create_gang_type("Venators", starting_credits=2000)
    gang_type.built_ins = create_default_set(
        "Venator built-ins", members=list(carriers.values())
    )
    gang_type.save()
    profile = create_profile("Hunter", person_type, gang_type, price=50)
    profile.built_ins = create_default_set("Hunter kit", members=[hunter])
    profile.save()

    gangs = {
        "full": found_gang("The Long Hunt", gang_type, owner=owner, budget=2000),
        "doubling": found_gang("The Echo", gang_type, owner=owner, budget=2000),
        "partial": found_gang("The Half Answer", gang_type, owner=owner, budget=2000),
        "quiet": found_gang("The Quiet", gang_type, owner=owner, budget=2000),
    }
    fighters = {"leader": hire(gangs["full"], profile, "Karrion", paid=50)}

    def anchor(gang, rank):
        return Assignment.objects.get(hidden=carriers[rank], gang=gang)

    # The full gang: four distinct trees, the first re-chosen once (an
    # archived answer left behind) and the fourth clicked twice (a spare).
    choose(anchor(gangs["full"], 1), tokens["agility"])
    remove(
        Assignment.objects.get(
            skill_tree=tokens["agility"], gang=gangs["full"], archived=False
        )
    )
    choose(anchor(gangs["full"], 1), tokens["cunning"])
    choose(anchor(gangs["full"], 2), tokens["savant"])
    choose(anchor(gangs["full"], 3), tokens["shooting"])
    choose(anchor(gangs["full"], 4), tokens["brawn"])
    choose(anchor(gangs["full"], 4), tokens["brawn"])  # the same click, landing twice

    # The doubling gang ranks one tree twice — four honest answers is
    # what production holds, two is enough to draw the note.
    choose(anchor(gangs["doubling"], 1), tokens["agility"])
    choose(anchor(gangs["doubling"], 2), tokens["agility"])

    choose(anchor(gangs["partial"], 1), tokens["combat"])
    return gangs, fighters


class TestThePlan:
    def test_it_says_everything_it_would_do(self, world):
        plan = plan_skill_tree()

        assert plan.ok and not plan.nothing_here
        said = "\n".join(plan.preview())
        assert "create slot type “Skill Tree”, refusing repeats" in said
        assert said.count("create pickable") == 6
        assert "linked to category “Agility”" in said
        assert said.count("drawing on") == 4
        assert said.count("replace “Skill Tree") == 4
        # Seven live answers. The archived re-choice stays where it is,
        # and the doubled click's spare is left alone.
        assert said.count("rewrite pick") == 7
        assert "leave 1 spare assignment exactly as they are" in said
        assert "prove 4 of 4 reached gangs read the same, or refuse" in said

    def test_it_deletes_nothing(self, world):
        said = "\n".join(plan_skill_tree().preview())

        assert "retire" not in said


class TestTheApply:
    def test_every_page_reads_the_same(self, world):
        gangs, _ = world
        before = {key: gang_state(g) for key, g in gangs.items()}

        apply(plan_skill_tree())

        for key, gang in gangs.items():
            assert differences(before[key], gang_state(gang)) == []
            assert_reconciled(gang)

    def test_the_live_answer_moves_and_the_archived_one_stays(self, world):
        gangs, _ = world

        apply(plan_skill_tree())

        live = Assignment.objects.get(
            gang=gangs["full"],
            pickable__name="Cunning",
            archived=False,
        )
        assert live.skill_tree_id is None
        assert live.chosen_for_id == live.caused_by_id
        assert live.chosen_for_slot == Slot.objects.get(name="Skill Tree 1")

        archived = Assignment.objects.get(
            gang=gangs["full"], archived=True, skill_tree__isnull=False
        )
        assert archived.skill_tree.name == "Agility"
        assert archived.pickable_id is None

    def test_a_doubled_answer_keeps_its_spare_untouched(self, world):
        gangs, _ = world
        before = gang_state(gangs["full"])

        plan = plan_skill_tree()
        apply(plan)

        assert plan.left_alone == 1
        assert differences(before, gang_state(gangs["full"])) == []
        spare = Assignment.objects.get(
            gang=gangs["full"], skill_tree__isnull=False, archived=False
        )
        assert spare.skill_tree.name == "Brawn"
        assert spare.pickable_id is None

    def test_one_tree_ranked_twice_still_draws_its_note(self, world):
        """The doubling gang's page carries a warning today because an
        offer always notes a doubled settling. The slot type refusing
        repeats is what keeps that note drawn afterwards."""
        gangs, _ = world
        before = gang_state(gangs["doubling"])
        assert any("Agility" in note for note in before["notes"])

        apply(plan_skill_tree())

        assert differences(before, gang_state(gangs["doubling"])) == []

    def test_every_fighter_keeps_its_tiers(self, world, prod_shape):
        """The placements read the chosen thing's home through the same
        anchor before and after — the whole payload of this system."""
        _, _, _, _, (collection, _) = prod_shape
        _, fighters = world
        before = _tiers_of(fighters["leader"], collection)
        assert before  # the picks must actually place something

        apply(plan_skill_tree())

        assert _tiers_of(fighters["leader"], collection) == before

    def test_the_story_already_written_says_the_same_words(self, world):
        from n26.core import history

        gangs, _ = world
        said = _story(history.build(gangs["full"]))

        apply(plan_skill_tree())

        assert _story(history.build(gangs["full"])) == said
        assert any("Cunning" in line for line in said)

    def test_a_pick_names_its_kind_by_the_slot_type(self, world):
        """Where a surface does say what sort of thing a pick is, the
        word is the slot type's — "skill tree" — never the slot's own
        label, which names one question among four."""
        from n26.core.history import _kindword

        apply(plan_skill_tree())

        pick = Assignment.objects.filter(pickable__isnull=False).first()
        assert _kindword(pick) == "skill tree"

    def test_the_old_rows_are_left_alone(self, world, prod_shape):
        _, _, carriers, _, _ = prod_shape

        apply(plan_skill_tree())

        assert SkillTree.objects.filter(archived=False).count() == 6
        for carrier in carriers.values():
            held = Hidden.objects.get(pk=carrier.pk)
            # The placement stays; only the offer was replaced by a grant.
            assert held.modifiers.count() == 2

    def test_rechoosing_works_on_the_new_machinery(self, world, prod_shape):
        _, _, carriers, _, _ = prod_shape
        gangs, _ = world
        apply(plan_skill_tree())
        gang = gangs["partial"]
        anchor = Assignment.objects.get(hidden=carriers[1], gang=gang)

        remove(Assignment.objects.get(pickable__name="Combat", gang=gang))
        choose(
            anchor,
            Pickable.objects.get(name="Savant"),
            slot=Slot.objects.get(name="Skill Tree 1"),
        )

        state = gang_state(gang)
        assert ("Skill Tree 1", "Savant") in state["choices"]
        assert_reconciled(gang)

    def test_a_second_run_is_a_clean_no_op(self, world):
        apply(plan_skill_tree())

        assert plan_skill_tree().nothing_here


class TestTheRefusals:
    def test_a_granted_carrier_is_refused(self, world, prod_shape):
        _, _, carriers, _, _ = prod_shape
        from n26.tests.sandbox.actions import ef_adds, targets_model

        modifier(
            "Something grants Skill Tree 2",
            targets_model(),
            ef_adds(carriers[2]),
            carried_by=create_subtype("Warden"),
        )

        plan = plan_skill_tree()

        assert not plan.ok
        assert any("cannot be counted" in problem for problem in plan.problems)

    def test_a_shared_offer_is_refused(self, world, prod_shape):
        from n26.library.authoring import attach_modifiers_to

        _, _, carriers, _, _ = prod_shape
        offer = next(
            m
            for m in carriers[3].modifiers.all()
            if getattr(m, "offers_choice", None) is not None
        )
        attach_modifiers_to(create_hidden("Bystander"), [offer])

        plan = plan_skill_tree()

        assert not plan.ok
        assert any("shared" in problem for problem in plan.problems)

    def test_two_hiddens_sharing_a_rank_name_are_refused(self, world):
        create_hidden("Skill Tree 3", qualifier="(a second one)")

        plan = plan_skill_tree()

        assert not plan.ok
        assert any("2 hiddens named" in problem for problem in plan.problems)

    def test_a_missing_rank_carrier_is_refused(self, world, prod_shape):
        """All four or none: a database holding some of the carriers is
        not one this plan understands."""
        _, _, carriers, _, _ = prod_shape
        carriers[4].archived = True
        carriers[4].save()

        plan = plan_skill_tree()

        assert not plan.ok
        assert any("rank carriers missing" in problem for problem in plan.problems)

    def test_a_tree_naming_no_category_is_refused(self, world):
        SkillTree.objects.filter(name="Brawn").update(category=None)

        plan = plan_skill_tree()

        assert not plan.ok
        assert any("naming no category" in problem for problem in plan.problems)

    def test_two_trees_sharing_a_name_are_refused(self, world, prod_shape):
        sets, _, _, _, _ = prod_shape
        create_skill_tree("Agility", sets["cunning"], qualifier="(again)")

        plan = plan_skill_tree()

        assert not plan.ok
        assert any(
            "more than one live skill tree" in problem for problem in plan.problems
        )


def _tiers_of(miniature, collection):
    """``{category name: tier name}`` as this fighter's sections sit."""
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute

    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    placed = placements_for(compute(card, index), collection)
    return {str(category): section.section.name for category, section in placed.items()}


def _story(acts):
    """Every word a gang's history page puts on the screen."""
    told = []
    for act in acts:
        told.append("".join(span.text for span in act.spans))
        told.extend(f"{sub.name}|{sub.kind}|{sub.note}" for sub in act.subs)
    return told
