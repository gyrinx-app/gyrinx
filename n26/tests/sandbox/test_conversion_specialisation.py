"""The Specialisation conversion, proven on a prod-shaped world.

The Specialist subtype's whole-kind offer becomes a granted bearer slot
and the specialisations become pickables carrying their same skill
grants. The narrowed Subjugator hidden converts too, so its holder's
page keeps asking the same question.

Nothing is deleted, which is most of what these tests are for: the old
rows, the abandoned experiment's fossil and its stray wiring, an
archived answer, and a spare left by a click that landed twice are all
still there afterwards, saying exactly what they said before.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.capture import differences, gang_state
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.library.conversion import apply, plan_specialisation
from n26.library.models import (
    Collection,
    Hidden,
    Pickable,
    Slot,
    Specialisation,
)
from n26.tests.sandbox.actions import (
    assign,
    choose,
    create_collection,
    create_default_set,
    create_gang_type,
    create_hidden,
    create_profile,
    create_skill,
    create_specialisation,
    create_subtype,
    ef_adds,
    ef_removes,
    found_gang,
    hire,
    modifier,
    offers_choice,
    remove,
    section_of,
    targets_model,
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
    """The system as production holds it: the subtype's whole-kind
    offer, four specialisations, and the two fossil hiddens."""
    specs = {}
    for name, skill in [
        ("Gunner", "Hip-shooting"),
        ("Medic", "Medicate"),
        ("Scout", "Clamber"),
        ("Sniper", "Precision Shot"),
    ]:
        specs[name] = create_specialisation(name)
        modifier(
            f"{name}: its skill",
            targets_model(),
            ef_adds(create_skill(skill)),
            carried_by=specs[name],
        )
    specialist = create_subtype("Specialist")
    modifier(
        "Specialist: offers a choice of specialisation",
        targets_model(),
        offers_choice(Specialisation),
        carried_by=specialist,
    )

    narrow_menu = create_collection(
        "Specialisations for Subjugator Patrol Officer",
        entries=[specs["Gunner"], specs["Medic"]],
    )
    narrow_section = section_of(narrow_menu, "Options", 0, is_default=True)
    narrow = create_hidden("Specialisation offer", qualifier="(Subjugator)")
    modifier(
        "Subjugator offer",
        targets_model(),
        offers_choice(
            Specialisation, from_section=narrow_section, label="Specialisation"
        ),
        carried_by=narrow,
    )

    general_menu = create_collection(
        "Specialisation Offer", entries=list(specs.values())
    )
    general_section = section_of(general_menu, "Specialisation", 0, is_default=True)
    general = create_hidden("Specialisation Offer", qualifier="(general)")
    modifier(
        "General offer",
        targets_model(),
        offers_choice(
            Specialisation, from_section=general_section, label="Specialisation"
        ),
        carried_by=general,
    )
    # The abandoned narrowing experiment left wiring that still names
    # the general hidden and protects it from retiring: a grant whose
    # modifier nothing carries any more, and bare effect rows whose
    # modifiers are gone entirely.
    from n26.library.models import AddsAssignable, RemovesAssignable

    modifier(
        "Specialist: adds Specialisation Offer",
        targets_model(),
        ef_adds(general),
    )
    AddsAssignable.objects.create(hidden=general)
    RemovesAssignable.objects.create(hidden=general)
    return specialist, specs, narrow, general


def build_world(prod_shape, person_type, owner):
    """Two gangs of specialists: a settled pick, a switched pick, an
    open question, and one fighter holding the Subjugator fossil."""
    specialist, specs, narrow, general = prod_shape
    gang_type = create_gang_type("Enforcers", starting_credits=2000)
    profile = create_profile("Patrol Officer", person_type, gang_type, price=50)
    profile.built_ins = create_default_set("Officer kit", members=[specialist])
    profile.save()
    # The experiment's live leftover: the profile still removes the
    # general hidden, which nothing grants — a read-time no-op.
    modifier(
        "Patrol Officer: removes Specialisation Offer",
        targets_model(),
        ef_removes(general),
        carried_by=profile,
    )

    first = found_gang("The Watch", gang_type, owner=owner, budget=2000)
    second = found_gang("The Patrol", gang_type, owner=owner, budget=2000)
    fighters = {
        "settled": hire(first, profile, "Vex", paid=50),
        "switched": hire(first, profile, "Kade", paid=50),
        "open": hire(second, profile, "Mara", paid=50),
        "subjugator": hire(second, profile, "Odo", paid=50),
    }

    def anchor(fighter):
        return Assignment.objects.get(subtype=specialist, miniature=fighter)

    choose(anchor(fighters["settled"]), specs["Sniper"])
    choose(anchor(fighters["switched"]), specs["Medic"])
    remove(
        Assignment.objects.get(
            specialisation=specs["Medic"], miniature=fighters["switched"]
        )
    )
    choose(anchor(fighters["switched"]), specs["Gunner"])
    assign(narrow, miniature=fighters["subjugator"])
    # Odo answers the narrowed question, so the world holds a pick
    # anchored on the hidden rather than the subtype.
    choose(
        Assignment.objects.get(hidden=narrow, miniature=fighters["subjugator"]),
        specs["Gunner"],
    )
    return (first, second), fighters


class TestThePlan:
    def test_it_says_everything_it_would_do(self, world):
        plan = plan_specialisation()

        assert plan.ok and not plan.nothing_here
        said = "\n".join(plan.preview())
        assert "create slot type “Specialisation”" in said
        assert said.count("create pickable") == 4
        assert "pick landing on the bearer" in said
        assert "replace “Specialist: offers a choice of specialisation”" in said
        assert (
            "create picklist “Subjugator Patrol Officer options” offering Gunner, Medic"
            in said
        )
        assert "replace “Subjugator offer”" in said
        # The three live answers. The switched fighter's archived one
        # stays where it is: nothing is deleted, so nothing makes it move.
        assert said.count("rewrite pick") == 3
        assert "prove 2 of 2 reached gangs read the same, or refuse" in said

    def test_it_deletes_nothing(self, world):
        """Retiring the old rows is tidiness, and tidiness is what made
        this hard. Left alone they go on saying what they say now."""
        said = "\n".join(plan_specialisation().preview())

        assert "retire" not in said


class TestTheApply:
    def test_every_page_reads_the_same(self, world):
        gangs, _ = world
        before = {g.pk: gang_state(g) for g in gangs}

        apply(plan_specialisation())

        for gang in gangs:
            assert differences(before[gang.pk], gang_state(gang)) == []
            assert_reconciled(gang)

    def test_the_live_answer_moves_and_the_archived_one_stays(self, world):
        """History is not drawn, and nothing is being deleted out from
        under it, so it keeps the shape it was written in."""
        _, fighters = world

        apply(plan_specialisation())

        live = Assignment.objects.get(
            miniature=fighters["switched"], pickable__isnull=False, archived=False
        )
        assert live.pickable.name == "Gunner"
        assert live.specialisation_id is None
        assert live.chosen_for_id == live.caused_by_id
        assert live.chosen_for_slot == Slot.objects.get(name="Specialisation")

        archived = Assignment.objects.get(
            miniature=fighters["switched"], archived=True, specialisation__isnull=False
        )
        assert archived.specialisation.name == "Medic"
        assert archived.pickable_id is None

    def test_a_doubled_answer_keeps_its_spare_untouched(self, world, prod_shape):
        """A click that landed twice leaves the answer plus a spare line
        in the gear list. Moving the answer must leave that page alone."""
        specialist, specs, _, _ = prod_shape
        _, fighters = world
        anchor = Assignment.objects.get(
            subtype=specialist, miniature=fighters["settled"]
        )
        choose(anchor, specs["Sniper"])  # the same answer, a second time
        gang = fighters["settled"].gang
        before = gang_state(gang)

        plan = plan_specialisation()
        apply(plan)

        assert plan.ok
        assert plan.left_alone == 1
        assert differences(before, gang_state(gang)) == []
        spare = Assignment.objects.get(
            miniature=fighters["settled"], specialisation__isnull=False, archived=False
        )
        assert spare.specialisation.name == "Sniper"
        assert spare.pickable_id is None

    def test_the_story_already_written_says_the_same_words(self, world):
        """History describes an old event by what its assignment names
        now, so a conversion can rewrite the past by accident. The pick
        reports the question it answered, which is the word it always
        had."""
        from n26.core import history

        gang = world[0][0]
        said = _story(history.build(gang))

        apply(plan_specialisation())

        assert _story(history.build(gang)) == said
        assert any("Sniper" in line for line in said)

    def test_the_old_rows_and_the_fossil_are_left_alone(self, world, prod_shape):
        _, _, _, general = prod_shape

        apply(plan_specialisation())

        assert Specialisation.objects.filter(archived=False).count() == 4
        assert Hidden.objects.filter(pk=general.pk).exists()
        assert Collection.objects.filter(name__icontains="specialisation").count() == 2

    def test_the_subjugator_holder_still_asks_a_narrow_question(self, world):
        _, fighters = world
        before = sorted(
            (slot.kind_label, slot.is_resolved)
            for slot in _choices_of(fighters["subjugator"])
        )

        apply(plan_specialisation())

        after = _choices_of(fighters["subjugator"])
        assert sorted((s.kind_label, s.is_resolved) for s in after) == before
        from n26.core.render import build_choice_offer

        card_computed = _computed_for(fighters["subjugator"])
        narrow_q = next(
            s
            for s in card_computed.choices
            if s.slot is not None and "Subjugator" in s.slot.name
        )
        names = {
            option.name
            for group in build_choice_offer(narrow_q, card_computed).groups
            for option in group.options
            if option.key != "none"
        }
        assert names == {"Gunner", "Medic"}

    def test_an_answered_narrow_question_settles_on_the_narrow_slot(self, world):
        _, fighters = world

        apply(plan_specialisation())

        pick = Assignment.objects.get(
            miniature=fighters["subjugator"], pickable__isnull=False
        )
        assert pick.pickable.name == "Gunner"
        assert pick.chosen_for_slot == Slot.objects.get(
            name="Specialisation (Subjugator Patrol Officer)"
        )

    def test_rechoosing_works_on_the_new_machinery(self, world, prod_shape):
        specialist, _, _, _ = prod_shape
        _, fighters = world
        apply(plan_specialisation())
        fighter = fighters["settled"]
        anchor = Assignment.objects.get(subtype=specialist, miniature=fighter)

        remove(Assignment.objects.get(pickable__name="Sniper", miniature=fighter))
        choose(
            anchor,
            Pickable.objects.get(name="Scout"),
            slot=Slot.objects.get(name="Specialisation"),
            miniature=fighter,
        )

        gang = fighter.gang
        state = gang_state(gang)
        card = state["models"][str(fighter.pk)]
        assert ("Specialisation", "Scout") in card["choices"]
        assert "Clamber" in card["skills"]
        assert_reconciled(gang)

    def test_a_second_run_is_a_clean_no_op(self, world):
        apply(plan_specialisation())

        plan = plan_specialisation()

        assert plan.nothing_here


class TestTheRefusals:
    def test_two_hiddens_sharing_a_name_are_refused(self, world):
        create_hidden("Specialisation offer", qualifier="(a second one)")

        plan = plan_specialisation()

        assert not plan.ok
        assert any("2 hiddens named" in problem for problem in plan.problems)

    def test_a_shared_offer_is_refused(self, world, prod_shape):
        from n26.library.authoring import attach_modifiers_to

        specialist, _, _, _ = prod_shape
        offer = next(
            m
            for m in specialist.modifiers.all()
            if getattr(m, "offers_choice", None) is not None
        )
        attach_modifiers_to(create_subtype("Understudy"), [offer])

        plan = plan_specialisation()

        assert not plan.ok
        assert "shared" in plan.problems[0]

    def test_a_shared_narrow_offer_is_refused(self, world, prod_shape):
        from n26.library.authoring import attach_modifiers_to

        _, _, narrow, _ = prod_shape
        offer = next(
            m
            for m in narrow.modifiers.all()
            if getattr(m, "offers_choice", None) is not None
        )
        attach_modifiers_to(create_hidden("Bystander"), [offer])

        plan = plan_specialisation()

        assert not plan.ok
        assert any("shared" in problem for problem in plan.problems)


def _computed_for(miniature):
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute

    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def _choices_of(miniature):
    return _computed_for(miniature).choices


def _story(acts):
    """Every word a gang's history page puts on the screen."""
    told = []
    for act in acts:
        told.append("".join(span.text for span in act.spans))
        told.extend(f"{sub.name}|{sub.kind}|{sub.note}" for sub in act.subs)
    return told
