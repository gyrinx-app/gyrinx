"""The selector library: one vocabulary, two contexts.

Selecting a kind of thing, a subset of a kind, or a specific thing — each
works in memory (``matches``) and compiles to a database filter (``as_q``).
The two contexts may legitimately disagree: queries see the library as
printed, in-memory targets can carry computed assignables.
"""

import pytest

from n26.core import select
from n26.library.models import Skill, Specialisation, Trait, Weapon, WeaponProfile

pytestmark = pytest.mark.django_db


@pytest.fixture
def melee(db):
    return Trait.objects.create(name="Melee")


@pytest.fixture
def heavy(db):
    return Trait.objects.create(name="Heavy")


@pytest.fixture
def knife_profile(melee):
    weapon = Weapon.objects.create(name="Stiletto knife")
    profile = WeaponProfile.objects.create(
        name="Blade", annotation="Stiletto knife", weapon=weapon
    )
    profile.traits.add(melee)
    return profile


@pytest.fixture
def gun_profile(heavy):
    weapon = Weapon.objects.create(name="Heavy stubber")
    profile = WeaponProfile.objects.create(
        name="Burst", annotation="Heavy stubber", weapon=weapon
    )
    profile.traits.add(heavy)
    return profile


class TestHas:
    def test_matches_a_printed_possession(self, melee, knife_profile):
        assert select.Has(melee).matches(select.matchable(knife_profile))

    def test_rejects_what_is_not_possessed(self, melee, gun_profile):
        assert not select.Has(melee).matches(select.matchable(gun_profile))

    def test_the_instance_carries_its_kind(self, melee, db):
        """One Has for every kind — a skill works exactly like a trait."""
        skill = Skill.objects.create(name="Fast Shot")
        target = select.matchable(skill, assignables=[skill])
        assert select.Has(skill).matches(target)

    def test_computed_possessions_are_the_adapter_s_business(self, melee, gun_profile):
        """The card can hand in computed traits; the leaf does not care."""
        computed = select.matchable(gun_profile, assignables=[melee])
        assert select.Has(melee).matches(computed)

    def test_as_q_filters_weapon_profiles(self, melee, knife_profile, gun_profile):
        found = WeaponProfile.objects.filter(select.Has(melee).as_q(WeaponProfile))
        assert list(found) == [knife_profile]

    def test_as_q_reaches_weapons_through_their_profiles(
        self, melee, knife_profile, gun_profile
    ):
        found = Weapon.objects.filter(select.Has(melee).as_q(Weapon))
        assert [weapon.name for weapon in found] == ["Stiletto knife"]

    def test_an_unregistered_path_fails_loudly(self, melee):
        from n26.core.models import Gang

        with pytest.raises(select.NotExpressibleAsQuery, match="register_lookup"):
            select.Has(melee).as_q(Gang)


class TestOfKindAndExactly:
    def test_of_kind_matches_and_lists(self, db):
        sharp = Specialisation.objects.create(name="Sharpshooter")
        Specialisation.objects.create(name="Medicae")

        kind = select.OfKind(Specialisation)
        assert kind.matches(select.matchable(sharp))
        assert not kind.matches(select.matchable(Trait.objects.create(name="Melee")))
        assert sorted(s.name for s in kind.choosables()) == [
            "Medicae",
            "Sharpshooter",
        ]

    def test_exactly_is_one_thing(self, db):
        sharp = Specialisation.objects.create(name="Sharpshooter")
        medic = Specialisation.objects.create(name="Medicae")

        one = select.Exactly(sharp)
        assert one.matches(select.matchable(sharp))
        assert not one.matches(select.matchable(medic))
        assert list(Specialisation.objects.filter(one.as_q(Specialisation))) == [sharp]


class TestCombinators:
    def test_quantifiers_are_composition_not_leaf_variants(
        self, melee, heavy, knife_profile, gun_profile
    ):
        """HasAnyTrait(a, b) is spelled Any(Has(a), Has(b))."""
        any_of = select.Any(select.Has(melee), select.Has(heavy))
        assert any_of.matches(select.matchable(knife_profile))
        assert any_of.matches(select.matchable(gun_profile))

        both = select.All(select.Has(melee), select.Has(heavy))
        assert not both.matches(select.matchable(knife_profile))

    def test_combinators_compile_too(self, melee, heavy, knife_profile, gun_profile):
        any_of = select.Any(select.Has(melee), select.Has(heavy))
        assert WeaponProfile.objects.filter(any_of.as_q(WeaponProfile)).count() == 2

        neither = select.Not(any_of)
        assert WeaponProfile.objects.filter(neither.as_q(WeaponProfile)).count() == 0

    def test_the_mounted_rule_reads_as_one_selector(
        self, melee, heavy, knife_profile, gun_profile
    ):
        """The parked warnings design, expressed: (Heavy or Paired) weapons."""
        paired = Trait.objects.create(name="Paired")
        forbidden = select.Any(select.Has(heavy), select.Has(paired))

        assert forbidden.matches(select.matchable(gun_profile))
        assert not forbidden.matches(select.matchable(knife_profile))
        assert str(forbidden) == "has Heavy or has Paired"


class TestReadableness:
    def test_selectors_describe_themselves(self, melee):
        assert str(select.Has(melee)) == "has Melee"
        assert str(select.OfKind(Specialisation)) == "any specialisation"
        assert str(select.Not(select.Has(melee))) == "not (has Melee)"
