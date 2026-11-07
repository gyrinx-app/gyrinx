"""Verify that stored scopes, usability restrictions and collection selectors compile to
n26.core.select and share its matching semantics. Cover exact profile identity,
SQL/in-memory agreement and specificity rounds that let conditional rules see earlier
grants; see n26/design/selectors.md.
"""

import pytest
from django.contrib.auth.models import User

from n26.core import select
from n26.core.browse import browse, usability_for, with_use_notes
from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.library.models import Skill, Wargear, Weapon
from n26.tests.sandbox.actions import (
    adds,
    create_category,
    create_collection,
    create_skill,
    create_subtype,
    create_wargear,
    found_gang,
    hire_with_option,
    modifier,
    restrict_use,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def gang(gang_type):
    return found_gang("The Bad Girls", gang_type, owner=User.objects.create_user("tom"))


def computed_for(miniature):
    card = build_card(miniature)
    index = build_modifier_index([n.assignable for n in card.all_nodes()])
    return card, compute(card, index)


class TestEveryDialectCompiles:
    """Compile each persisted selector shape to the shared algebra."""

    def test_a_scope_s_subtype_filter(self, db):
        scope = targets_model(with_subtypes=[create_subtype("Leader")])
        assert str(scope.as_selector()) == "has Leader"

        broad = targets_model()
        assert str(broad.as_selector()) == "anything"

    def test_a_use_restriction(self, person_type):
        skill = create_skill("Fated")
        assert str(skill.usable_by_selector()) == "anything"

        restrict_use(skill, person_type, create_subtype("Walker"))
        assert str(skill.usable_by_selector()) == "has Fighter or has Walker"

    def test_a_restriction_to_a_fighter_entry_is_an_exactly(self, make_profile):
        """A fighter-entry restriction matches profile identity with Exactly rather than
        checking for a held assignment.
        """
        runner = make_profile("Wyld Runner")
        bow = create_wargear("Wyld bow")
        restrict_use(bow, runner)
        assert str(bow.usable_by_selector()) == "exactly Wyld Runner"

    def test_a_sweep_with_a_category_narrowing(self, db):
        pistols = create_category("Ranged Weapons", "Pistols", 0)
        catalogue = create_collection("Catalogue", contains=[(Weapon, pistols)])
        (sweep,) = catalogue.selectors.all()
        assert str(sweep.as_selector()) == "any weapon and homed in Pistols"

    def test_the_narrowed_sweep_compiles_to_sql_and_agrees_with_memory(self, db):
        """Use the same category selector for queryset filtering and in-memory matching."""
        pistols = create_category("Ranged Weapons", "Pistols", 0)
        stub = create_wargear("Stub gun", category=pistols)  # Use wargear to isolate
        # category matching from
        # weapon-profile setup.
        mesh = create_wargear("Mesh armour")
        catalogue = create_collection("Catalogue", contains=[(Wargear, pistols)])
        (sweep,) = catalogue.selectors.all()

        assert list(sweep.contents()) == [stub]
        assert sweep.as_selector().matches(select.matchable(stub))
        assert not sweep.as_selector().matches(select.matchable(mesh))


class TestRoundsBySpecificity:
    """Apply unconditional grants in round zero, then evaluate filtered scopes against the
    resulting facts in later rounds. Record those rounds in computed.plan.
    """

    @pytest.fixture
    def rider(self, gang, make_profile):
        mounted = create_subtype("Mounted")
        hit_and_run = create_skill("Hit & Run")
        profile = make_profile("Outrider", price=50)
        # Evaluate the profile's Mounted condition in round one.
        modifier(
            "Mounted models gain Hit & Run",
            targets_model(with_subtypes=[mounted]),
            adds(hit_and_run),
            carried_by=profile,
        )
        # Grant Mounted from equipment in round zero.
        saddle = create_wargear("Saddle")
        modifier(
            "Saddle grants Mounted", targets_model(), adds(mounted), carried_by=saddle
        )
        fighter = hire_with_option(gang, profile, "Sly")
        from n26.tests.sandbox.actions import assign

        assign(saddle, miniature=fighter)
        return fighter, mounted

    def test_a_filtered_rule_sees_an_unconditional_grant(self, rider):
        fighter, mounted = rider
        _, computed = computed_for(fighter)

        assert [c.name for c in computed.subtypes] == ["Mounted"]
        assert [c.name for c in computed.skills] == ["Hit & Run"]

    def test_usability_and_scopes_now_agree(self, rider):
        """Use computed facts, including unconditional grants, for equipment usability as
        well as rule scopes.
        """
        fighter, mounted = rider
        _, computed = computed_for(fighter)

        skill = create_skill("Ride-by Attack")
        restrict_use(skill, mounted)
        assert skill.is_usable_by(usability_for(computed)) is True

    def test_the_plan_shows_the_rounds(self, rider):
        fighter, _ = rider
        _, computed = computed_for(fighter)

        grant = next(s for s in computed.plan if "Mounted" in s.effect)
        rule = next(s for s in computed.plan if "Hit & Run" in s.effect)

        assert (grant.ran_in, grant.outcome) == (0, "reached")
        assert (rule.ran_in, rule.outcome) == (1, "reached")
        assert computed.plan.index(grant) < computed.plan.index(rule)
        assert "granted Mounted" in str(grant)


class TestTheEngineIsShared:
    def test_use_notes_flow_through_the_same_match(self, gang, make_profile):
        """Evaluate browse use notes through compiled selectors against the model's
        computed facts.
        """
        runner = make_profile("Wyld Runner", price=45)
        other = make_profile("Gang Queen", price=135)
        bow = create_skill("Bowcraft")
        restrict_use(bow, runner)
        skills = create_collection("Skills", contains=[Skill])

        sly = hire_with_option(gang, runner, "Sly")
        yolanda = hire_with_option(gang, other, "Yolanda")

        def noted(miniature):
            _, computed = computed_for(miniature)
            view = with_use_notes(browse(skills), usability_for(computed))
            line = next(x for x in view.all_lines() if x.name == "Bowcraft")
            return line.notes

        assert noted(sly) == ()
        (note,) = noted(yolanda)
        assert "Wyld Runner" in note.text
