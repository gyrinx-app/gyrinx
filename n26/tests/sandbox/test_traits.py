"""Weapon traits: content rows, defaults on weapon profiles, computed reads.

The parameter is the annotation — Knockback (5+) and Knockback (6+) are two
rows. Traits are never copied player-side: the profile's set is the truth,
so a content fix reaches every existing weapon. No rules text anywhere —
the rulebook's words are copyrighted (CLAUDE.md).
"""

import pytest
from django.contrib.auth.models import User
from django.db import IntegrityError, transaction

from n26.library.models import Trait
from n26.core.render import build_model_card
from n26.core.render_text import render_model_card
from n26.tests.sandbox.actions import (
    create_trait,
    create_weapon,
    found_gang,
    give_weapon,
    hire,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def traits(default_pack):
    return {
        "knockback6": create_trait("Knockback", "6+"),
        "knockback5": create_trait("Knockback", "5+"),
        "rapid_fire": create_trait("Rapid Fire", "1"),
        "melee": create_trait("Melee"),
        "template": create_trait("Template"),
    }


@pytest.fixture
def combat_shotgun(traits):
    """Salvo and shredder ammo, traits as the rulebook prints them."""
    return create_weapon(
        "Combat shotgun",
        profiles=[
            ("Salvo ammo", 0, [traits["knockback6"]]),
            ("Shredder ammo", 0, [traits["rapid_fire"], traits["template"]]),
        ],
    )


class TestTraitRows:
    def test_the_parameter_is_the_annotation(self, traits):
        assert str(traits["knockback6"]) == "Knockback (6+)"
        assert str(traits["melee"]) == "Melee"

    def test_the_same_name_may_carry_different_parameters(self, traits):
        assert Trait.objects.filter(name="Knockback").count() == 2

    def test_but_not_the_same_parameter_twice_in_a_pack(self, traits):
        with pytest.raises(IntegrityError), transaction.atomic():
            create_trait("Knockback", "6+")

    def test_a_trait_stores_no_rules_text(self):
        """The copyright constraint, pinned structurally: name, annotation,
        pricing numbers and content plumbing — nothing that could hold the
        rulebook's words. Grow this set only deliberately, and never for a
        field meant to carry the book's prose."""
        fields = {f.name for f in Trait._meta.get_fields() if not f.is_relation}
        assert fields == {
            "id",
            "created",
            "modified",
            "archived",
            "archived_at",
            "name",
            "annotation",
            # The reference price every assignable carries — numbers and a
            # flag, no prose. See design/collections.md.
            "price",
            "trade_point_price",
            "is_exclusive",
            # Order within its home category (a skill's D6 number) — an
            # integer, no prose.
            "position",
            # Tells two same-named traits apart for an author. Not
            # prose about the rule, and never seen by a player — the
            # money-words suite guards that it cannot leak.
            "qualifier",
            # The one deliberate prose field: authoring help for whoever
            # wields this while building other content, never the book's
            # wording — the field's own help_text carries that guardrail,
            # and this comment is the conscious decision this test demands.
            "library_author_help",
        }


class TestDefaults:
    def test_profiles_carry_their_own_traits(self, combat_shotgun):
        salvo, shredder = combat_shotgun.profiles.order_by("position")
        assert salvo.trait_names == ["Knockback (6+)"]
        assert shredder.trait_names == ["Rapid Fire (1)", "Template"]

    def test_the_weapon_level_question_is_derived(self, combat_shotgun, traits):
        """ "A weapon with the X trait" means any of its profiles has it."""
        assert combat_shotgun.has_trait("Knockback")
        assert combat_shotgun.has_trait("template")  # case-insensitive
        assert not combat_shotgun.has_trait("Melee")

    def test_a_content_fix_reaches_every_existing_weapon(
        self, combat_shotgun, traits, gang_type, make_profile
    ):
        """The reason traits are computed rather than copied."""
        player = User.objects.create_user("player")
        gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        mini = hire(gang, make_profile("Ganger"), "Yolanda", paid=55)
        give_weapon(mini, combat_shotgun, paid=35)

        # Errata: salvo ammo's Knockback becomes 5+.
        salvo = combat_shotgun.profiles.get(name="Salvo ammo")
        salvo.traits.set([traits["knockback5"]])

        card = build_model_card(mini)
        by_name = {p.name: p for p in card.weapons[0].profiles}
        salvo_traits = [t.name for t in by_name["Salvo ammo"].traits]
        assert salvo_traits == ["Knockback (5+)"]


class TestOnTheCard:
    @pytest.fixture
    def armed(self, combat_shotgun, gang_type, make_profile):
        player = User.objects.create_user("player")
        gang = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        mini = hire(gang, make_profile("Ganger"), "Yolanda", paid=55)
        give_weapon(mini, combat_shotgun, paid=35)
        return mini

    def test_each_profile_line_lists_its_traits(self, armed):
        weapon = build_model_card(armed).weapons[0]
        by_name = {p.name: [t.name for t in p.traits] for p in weapon.profiles}
        assert by_name == {
            "Salvo ammo": ["Knockback (6+)"],
            "Shredder ammo": ["Rapid Fire (1)", "Template"],
        }

    def test_the_text_renderer_shows_them_after_the_stats(self, armed):
        text = "\n".join(render_model_card(build_model_card(armed)))
        print("\n" + text)
        assert "- Salvo ammo   Knockback (6+)" in text
        assert "Rapid Fire (1), Template" in text

    def test_more_traits_do_not_mean_more_queries(self, armed, traits):
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        def measure():
            with CaptureQueriesContext(connection) as captured:
                card = build_model_card(armed)
                assert any(p.traits for p in card.weapons[0].profiles)
            return len(captured.captured_queries)

        few = measure()

        heavy = create_weapon(
            "Kitted gun",
            profiles=[
                ("Shot A", 0, [traits["melee"], traits["knockback5"]]),
                ("Shot B", 0, [traits["rapid_fire"], traits["template"]]),
            ],
        )
        give_weapon(armed, heavy, paid=10)
        give_weapon(
            armed,
            create_weapon("Plain gun", profiles=[("Shot", 0, [traits["melee"]])]),
            paid=10,
        )

        many = measure()
        assert few == many, f"{few} queries before, {many} after adding traits"
