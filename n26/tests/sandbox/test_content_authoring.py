"""What authoring content actually looks like, in raw ORM.

Everywhere else in the sandbox tests uses the helpers in
``tests/sandbox/actions.py``. This file deliberately does not: it is the
reference for what a content ingest — or the admin — is really doing, with
every model spelled out.

Three things are built here: a Khimerix with built-in kit and priced
options, the Mounted chain of modifiers, and pet wargear.
"""

import pytest
from django.contrib.auth.models import User

from n26.core.models import Gang
from n26.core.operations import operation
from n26.core.render import build_model_card
from n26.core.render_text import render_model_card
from n26.library.models import (
    AddsAssignable,
    ChangesStat,
    DefaultAssignment,
    DefaultAssignmentSet,
    GangType,
    HasTrait,
    Modifier,
    OpAddsMiniature,
    Option,
    Profile,
    ProfileType,
    Skill,
    Stat,
    Statline,
    StatlineStat,
    StatlineType,
    StatlineTypeStat,
    Subtype,
    TargetsMiniature,
    TargetsWeapons,
    Trait,
    Wargear,
    Weapon,
    WeaponProfile,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def escher(db):
    return GangType.objects.create(name="Escher")


@pytest.fixture
def beast_type(db):
    """A profile type, and the statline shape it fixes."""
    shape = StatlineType.objects.create(name="Beast")
    for position, (short, full, flags) in enumerate(
        [
            ("M", "Movement", {"is_inches": True}),
            ("WS", "Weapon Skill", {"is_target": True, "is_inverted": True}),
            ("S", "Strength", {}),
            ("T", "Toughness", {}),
        ]
    ):
        StatlineTypeStat.objects.create(
            statline_type=shape,
            stat=Stat.objects.create(short_name=short, full_name=full, **flags),
            position=position,
            is_first_of_group=(position == 0),
        )
    return ProfileType.objects.create(name="Fighter", statline_type=shape)


def make_weapon(name):
    """A weapon and its one mandatory, free profile."""
    weapon = Weapon.objects.create(name=name, slots=1)
    WeaponProfile.objects.create(
        name="Attack", annotation=name, weapon=weapon, price=0, position=0
    )
    return weapon


class TestAuthoringAKhimerix:
    """Built-in kit, plus priced alternatives chosen at hire."""

    @pytest.fixture
    def khimerix(self, beast_type, escher):
        profile = Profile.objects.create(
            name="Khimerix",
            profile_type=beast_type,
            gang_type=escher,
            price=210,
        )

        statline = Statline.objects.create(owner=profile)
        for type_stat, value in zip(
            profile.statline_type.stats.order_by("position"),
            ["6", "4", "4", "4"],
            strict=True,
        ):
            StatlineStat.objects.create(
                statline=statline, statline_type_stat=type_stat, value=value
            )

        # Always granted. No choice is offered for these.
        built_ins = DefaultAssignmentSet.objects.create(
            name="Khimerix built-ins", price=0
        )
        DefaultAssignment.objects.create(
            default_set=built_ins,
            assignable=Subtype.objects.create(name="Exotic Beast"),
            position=0,
        )

        cloud = make_weapon("Chemical cloud breath")
        eruption = make_weapon("Gaseous eruption breath")
        talons = make_weapon("Talons")
        razors = make_weapon("Razor-sharp talons")

        profile.built_ins = built_ins
        profile.save()

        # The options. One-of, so two independent swaps become four
        # combinations, priced absolutely rather than as deltas. The head of
        # the list is what a hire takes unasked — a profile is
        # (built_ins, [options]), with no separate default slot.
        alternatives = [
            ("Standard Khimerix", cloud, talons, 0),
            ("Eruption breath", eruption, talons, 25),
            ("Razor talons", cloud, razors, 25),
            ("Eruption and razors", eruption, razors, 50),
        ]
        for position, (name, breath, claws, price) in enumerate(alternatives):
            option_set = DefaultAssignmentSet.objects.create(name=name, price=price)
            # ``assignable=`` routes to the right column, exactly as it
            # does on a player's Assignment — same mixin, same API.
            DefaultAssignment.objects.create(
                default_set=option_set, assignable=breath, position=0
            )
            DefaultAssignment.objects.create(
                default_set=option_set, assignable=claws, position=1
            )
            Option.objects.create(
                profile=profile, default_set=option_set, position=position
            )

        return profile

    @pytest.fixture
    def gang(self, escher):
        player = User.objects.create_user("tom")
        return Gang.objects.create(
            name="The Bad Girls",
            gang_type=escher,
            owner=player,
            starting_credits=1000,
            credits=1000,
        )

    def test_hiring_the_default(self, gang, khimerix):
        with operation(gang, actor=gang.owner) as op:
            beast = op.hire(khimerix, "Growler")

        card = build_model_card(beast)
        print("\n" + "\n".join(render_model_card(card)))

        assert card.rating == 210
        assert [w.name for w in card.weapons] == [
            "Chemical cloud breath",
            "Talons",
        ]
        assert card.type_line == "Fighter (Exotic Beast)"

    def test_hiring_with_an_option(self, gang, khimerix):
        razors = khimerix.options.get(
            default_set__name="Eruption and razors"
        ).default_set

        with operation(gang, actor=gang.owner) as op:
            beast = op.hire(khimerix, "Growler", option=razors)

        card = build_model_card(beast)
        print("\n" + "\n".join(render_model_card(card)))

        assert card.rating == 260  # 210 + 50
        assert [w.name for w in card.weapons] == [
            "Gaseous eruption breath",
            "Razor-sharp talons",
        ]
        assert [c.default_set for c in beast.membership.chosen_options.all()] == [
            razors
        ]


class TestAuthoringModifiers:
    """A Modifier is one scope plus one effect, each its own small row."""

    def test_the_mounted_chain(self, beast_type, escher):
        # Mounted grants a skill. Both rows are content; nothing is stored
        # on a player's model when this fires.
        mounted = Subtype.objects.create(name="Mounted")
        mounted.modifiers.add(
            Modifier.objects.create(
                name="Mounted grants Hit & Run",
                targets_miniature=TargetsMiniature.objects.create(),
                adds_assignable=AddsAssignable.objects.create(
                    skill=Skill.objects.create(name="Hit & Run")
                ),
            )
        )

        # The mount grants Mounted, which is what makes it a chain.
        cutter = Wargear.objects.create(name="Cutter")
        cutter.modifiers.add(
            Modifier.objects.create(
                name="Cutter grants Mounted",
                targets_miniature=TargetsMiniature.objects.create(),
                adds_assignable=AddsAssignable.objects.create(subtype=mounted),
            )
        )

        assert cutter.modifiers.get().adds_assignable.thing == mounted
        assert mounted.modifiers.get().adds_assignable.thing.name == "Hit & Run"

    def test_a_stat_change(self, beast_type):
        toughness = Stat.objects.get(full_name="Toughness")
        injury = Wargear.objects.create(name="Old Wound")
        injury.modifiers.add(
            Modifier.objects.create(
                name="Old Wound worsens Toughness",
                targets_miniature=TargetsMiniature.objects.create(),
                changes_stat=ChangesStat.objects.create(
                    stat=toughness, mode=ChangesStat.Mode.WORSEN, amount=1
                ),
            )
        )
        effect = injury.modifiers.get().changes_stat
        assert str(effect) == "worsen T by 1"

    def test_a_weapon_scoped_add(self, db):
        """Backstab: arm every Melee weapon. The scope carries the filter."""
        melee = Trait.objects.create(name="Melee")
        backstab_trait = Trait.objects.create(name="Backstab")

        skill = Skill.objects.create(name="Backstab")
        scope = TargetsWeapons.objects.create()
        HasTrait.objects.create(scope=scope).traits.add(melee)
        skill.modifiers.add(
            Modifier.objects.create(
                name="Backstab arms Melee weapons",
                targets_weapons=scope,
                adds_assignable=AddsAssignable.objects.create(trait=backstab_trait),
            )
        )

        modifier = skill.modifiers.get()
        assert str(modifier.scope) == "weapons with Melee"
        assert str(modifier.effect) == "adds Backstab"

    def test_the_compatibility_rule_refuses_nonsense(self, db):
        """A trait goes on a weapon; a subtype goes on a model."""
        from django.core.exceptions import ValidationError

        nonsense = Modifier(
            name="Trait on a model",
            targets_miniature=TargetsMiniature.objects.create(),
            adds_assignable=AddsAssignable.objects.create(
                trait=Trait.objects.create(name="Melee")
            ),
        )
        with pytest.raises(ValidationError, match="cannot apply"):
            nonsense.clean()


class TestAuthoringAPet:
    """Wargear that brings a model — a stored effect, run at assign time."""

    def test_pet_wargear(self, beast_type, escher):
        mastiff = Profile.objects.create(
            name="Cyber-mastiff",
            profile_type=beast_type,
            gang_type=escher,
            price=100,
        )

        wargear = Wargear.objects.create(name="Cyber-mastiff (pet)")
        wargear.modifiers.add(
            Modifier.objects.create(
                name="Cyber-mastiff wargear brings a pet",
                targets_miniature=TargetsMiniature.objects.create(),
                op_adds_miniature=OpAddsMiniature.objects.create(profile=mastiff),
            )
        )

        effect = wargear.modifiers.get().op_adds_miniature
        assert effect.is_stored is True
        assert str(effect) == "adds a Cyber-mastiff"
