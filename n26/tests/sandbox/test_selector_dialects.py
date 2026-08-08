"""One grammar, four dialects — the selector convergence, pinned.

Route B of design/selectors.md: every persisted "which things match"
shape keeps its own tailored fields, but compiles to ``n26.core.select`` and
executes through it. These tests pin three things:

* each stored dialect **compiles** to the algebra;
* matching runs through the **one engine**, so the semantics (default
  open, any-of within a field) are encoded once;
* the printed-vs-computed divergence between the two fact adapters is
  **policy, documented and asserted** — not an accident that a refactor
  may silently flip.
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
    """The stored shapes stay tailored; the grammar underneath is one."""

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
        """Being an entry is identity, not possession — "(Wyld Runner
        only)" compiles to the algebra's ``Exactly``, its first real use."""
        runner = make_profile("Wyld Runner")
        bow = create_wargear("Wyld bow")
        restrict_use(bow, runner)
        assert str(bow.usable_by_selector()) == "exactly Wyld Runner"

    def test_a_sweep_with_a_category_narrowing(self, db):
        pistols = create_category("Ranged Weapons", "Pistols", 0)
        shop = create_collection("Shop", contains=[(Weapon, pistols)])
        (sweep,) = shop.selectors.all()
        assert str(sweep.as_selector()) == "any weapon and homed in Pistols"

    def test_the_narrowed_sweep_compiles_to_sql_and_agrees_with_memory(self, db):
        """``HomedIn`` works in both worlds: the queryset it compiles to
        and the in-memory match give the same answer."""
        pistols = create_category("Ranged Weapons", "Pistols", 0)
        stub = create_wargear("Stub gun", category=pistols)  # wargear for ease
        mesh = create_wargear("Mesh armour")
        shop = create_collection("Shop", contains=[(Wargear, pistols)])
        (sweep,) = shop.selectors.all()

        assert list(sweep.contents()) == [stub]
        assert sweep.as_selector().matches(select.matchable(stub))
        assert not sweep.as_selector().matches(select.matchable(mesh))


class TestRoundsBySpecificity:
    """Compute runs in rounds; a scope's round is its selector's specificity.

    Unconditional modifiers (specificity 0)
    settle first; filtered scopes (specificity 1+) then ask against the
    settled facts, all seeing the same snapshot. So a wargear's
    unconditional "grants Mounted" lands in round 0, and a rule for
    Mounted models — round 1 — reaches the rider. Add settles before
    remove within a round. The whole run is data: ``computed.plan``.
    """

    @pytest.fixture
    def rider(self, gang, make_profile):
        mounted = create_subtype("Mounted")
        hit_and_run = create_skill("Hit & Run")
        profile = make_profile("Outrider", price=50)
        # The filtered rule (round 1), carried by the profile itself.
        modifier(
            "Mounted models gain Hit & Run",
            targets_model(with_subtypes=[mounted]),
            adds(hit_and_run),
            carried_by=profile,
        )
        # The unconditional grant (round 0), carried by bought kit.
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
        """One world: the fighter the shop sees is the fighter the rules
        see. The divergence this class used to pin is resolved by rounds."""
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
        """The listing-noting path builds one fighter matchable and asks
        each line's compiled selector — no bespoke comparison code left."""
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
