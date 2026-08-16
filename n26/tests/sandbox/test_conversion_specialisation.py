"""The Specialisation conversion, proven on a prod-shaped world.

The Specialist subtype's whole-kind offer becomes a granted bearer
slot; the specialisations become pickables carrying their same skill
grants; the two fossil hiddens are handled each their own way — the
narrowed Subjugator one converts so its holder's page keeps asking the
same question, the unheld general one retires with its menu.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.capture import differences, gang_state
from n26.core.models import Assignment
from n26.core.reconcile import assert_reconciled
from n26.library.conversion import ConversionRefused, apply, plan_specialisation
from n26.library.models import (
    Collection,
    Hidden,
    Pickable,
    Slot,
    SlotType,
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


@pytest.fixture
def world(prod_shape, person_type, owner, default_pack):
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
        assert said.count("rewrite pick") == 4
        assert "retire “General offer”" in said
        assert (
            "retire the carrierless modifier "
            "“Specialist: adds Specialisation Offer”" in said
        )
        assert (
            "on the “Patrol Officer” profile: retire "
            "“Patrol Officer: removes Specialisation Offer”" in said
        )
        assert "retire library.AddsAssignable" in said
        assert "retire library.RemovesAssignable" in said
        assert "retire library.Hidden “Specialisation Offer" in said
        assert said.count("retire library.Collection") == 2
        assert said.count("retire library.Specialisation") == 4
        assert "prove 2 gangs read the same, or refuse" in said


class TestTheApply:
    def test_every_page_reads_the_same(self, world):
        gangs, _ = world
        before = {g.pk: gang_state(g) for g in gangs}

        apply(plan_specialisation())

        for gang in gangs:
            assert differences(before[gang.pk], gang_state(gang)) == []
            assert_reconciled(gang)

    def test_live_and_archived_picks_are_rewritten(self, world, prod_shape):
        specialist, _, _, _ = prod_shape
        _, fighters = world

        apply(plan_specialisation())

        live = Assignment.objects.get(
            miniature=fighters["switched"], pickable__isnull=False, archived=False
        )
        assert live.pickable.name == "Gunner"
        archived = Assignment.objects.get(
            miniature=fighters["switched"], pickable__isnull=False, archived=True
        )
        assert archived.pickable.name == "Medic"
        for row in (live, archived):
            assert row.specialisation_id is None
            assert row.chosen_for_id == row.caused_by_id
            assert row.chosen_for_slot == Slot.objects.get(name="Specialisation")

    def test_the_fossils_end_their_own_ways(self, world):
        apply(plan_specialisation())

        from n26.library.models import Modifier

        assert not Hidden.objects.filter(qualifier="(general)").exists()
        assert not Modifier.objects.filter(
            name__icontains="Specialisation Offer"
        ).exists()
        subjugator = Hidden.objects.get(name="Specialisation offer")
        grants = [m for m in subjugator.modifiers.all() if m.effect.slot is not None]
        assert len(grants) == 1
        assert not Collection.objects.filter(name__startswith="Specialisation").exists()
        assert not Specialisation.objects.exists()

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

    def test_a_general_fossil_with_no_offer_still_retires(self, world, prod_shape):
        _, _, _, general = prod_shape
        offer = next(
            m
            for m in general.modifiers.all()
            if getattr(m, "offers_choice", None) is not None
        )
        scope_row, effect_row = offer.scope, offer.effect
        general.modifiers.remove(offer)
        offer.delete()
        scope_row.delete()
        effect_row.delete()
        Collection.objects.get(name="Specialisation Offer").delete()

        apply(plan_specialisation())

        assert not Hidden.objects.filter(qualifier="(general)").exists()

    def test_a_dropped_removes_carriers_gangs_join_the_capture_set(
        self, world, prod_shape, person_type, owner
    ):
        _, _, _, general = prod_shape
        watch = create_gang_type("The Watch Rotation", starting_credits=1000)
        watchman = create_profile("Watchman", person_type, watch, price=50)
        modifier(
            "Watchman: removes Specialisation Offer",
            targets_model(),
            ef_removes(general),
            carried_by=watchman,
        )
        bystander = found_gang("The Shift", watch, owner=owner, budget=1000)
        hire(bystander, watchman, "Silas", paid=50)

        plan = plan_specialisation()

        assert plan.ok
        assert bystander.pk in plan.gang_ids
        assert_reconciled(bystander)

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
    def test_a_held_general_fossil_cannot_retire(self, world, prod_shape, owner):
        _, _, _, general = prod_shape
        _, fighters = world
        assign(general, miniature=fighters["open"])

        plan = plan_specialisation()

        assert not plan.ok
        assert "held by someone" in plan.problems[0]
        with pytest.raises(ConversionRefused):
            apply(plan)
        assert not SlotType.objects.filter(name="Specialisation").exists()

    def test_an_archived_specialisation_is_refused_not_skipped(self, world):
        ghost = create_specialisation("Forgotten")
        ghost.archived = True
        ghost.save()

        plan = plan_specialisation()

        assert not plan.ok
        assert any("Forgotten" in problem for problem in plan.problems)

    def test_two_hiddens_sharing_a_name_are_refused(self, world):
        create_hidden("Specialisation offer", qualifier="(a second one)")

        plan = plan_specialisation()

        assert not plan.ok
        assert any("2 hiddens named" in problem for problem in plan.problems)

    def test_a_live_modifier_naming_the_general_fossil_is_refused(
        self, world, prod_shape
    ):
        _, _, _, general = prod_shape
        modifier(
            "Something grants the offer",
            targets_model(),
            ef_adds(general),
            carried_by=create_subtype("Latecomer"),
        )

        plan = plan_specialisation()

        assert not plan.ok
        assert any("Something grants the offer" in problem for problem in plan.problems)

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

    def test_a_shared_general_offer_is_refused(self, world, prod_shape):
        from n26.library.authoring import attach_modifiers_to

        _, _, _, general = prod_shape
        offer = next(
            m
            for m in general.modifiers.all()
            if getattr(m, "offers_choice", None) is not None
        )
        attach_modifiers_to(create_hidden("Another bystander"), [offer])

        plan = plan_specialisation()

        assert not plan.ok
        assert any("shared" in problem for problem in plan.problems)

    def test_a_granted_specialist_subtype_is_refused(self, world, prod_shape):
        specialist, _, _, _ = prod_shape
        modifier(
            "Rank grants Specialist",
            targets_model(),
            ef_adds(specialist),
            carried_by=create_subtype("Sergeant"),
        )

        plan = plan_specialisation()

        assert not plan.ok
        assert any("cannot find the gangs" in problem for problem in plan.problems)


def _computed_for(miniature):
    from n26.core.card import build_card, build_modifier_index
    from n26.core.effects import compute

    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def _choices_of(miniature):
    return _computed_for(miniature).choices
