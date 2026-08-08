"""Building a Person profile, end to end.

These read top-to-bottom as a flow rather than isolating one behaviour each —
the point is to see the whole shape of the content library in one place, and
to have somewhere obvious to try an idea out.
"""

import pytest

from n26.library.models import Profile
from n26.tests.sandbox.actions import (
    create_gang_type,
    create_pack,
    create_profile,
    create_profile_type,
    create_stat,
    create_statline_type,
    set_statline,
)

pytestmark = pytest.mark.django_db


def test_building_a_person_from_scratch(default_pack):
    # A kind of gang for the profile to belong to.
    escher = create_gang_type("Escher")

    # The shape of a Person's statline: a distance, a roll target, a number.
    person_statline = create_statline_type(
        "Person",
        stats=[
            create_stat("M", "Movement", is_inches=True),
            create_stat("WS", "Weapon Skill", is_target=True, is_inverted=True),
            create_stat("T", "Toughness"),
        ],
    )

    # A Type, pinned to that shape. There are only ever two.
    person = create_profile_type("Fighter", statline_type=person_statline)

    # And a profile of that kind.
    juve = create_profile(
        "Escher Juve", profile_type=person, gang_type=escher, price=25
    )

    # Nothing has a statline until one is given.
    assert juve.has_statline is False
    assert juve.stats() == {}

    set_statline(juve, movement=4, weapon_skill=3, toughness=3)

    # Values come back formatted by each stat's own display rules, in order.
    assert juve.stats() == {
        "movement": '4"',
        "weapon_skill": "3+",
        "toughness": "3",
    }

    # Everything landed in N26, because nothing said otherwise.
    assert juve.pack == default_pack
    assert escher.pack == default_pack
    assert person_statline.pack == default_pack

    # And it all hangs together.
    assert juve.gang_type == escher
    assert juve.profile_type == person
    assert juve.statline_type == person_statline
    assert juve.price == 25
    juve.statline.full_clean()


def test_one_statline_type_serves_many_gangs_and_profiles():
    """Content is shared: define the shape once, reuse it everywhere."""
    person_statline = create_statline_type(
        "Person",
        stats=[
            create_stat("M", "Movement", is_inches=True),
            create_stat("T", "Toughness"),
        ],
    )
    # One shape serves both Types — which is how the rules print it:
    # a Vehicle's characteristics profile is a Fighter's.
    fighter = create_profile_type("Fighter", statline_type=person_statline)
    vehicle = create_profile_type("Vehicle", statline_type=person_statline)

    escher = create_gang_type("Escher")
    goliath = create_gang_type("Goliath")

    juve = create_profile(
        "Escher Juve", profile_type=fighter, gang_type=escher, price=25
    )
    bruiser = create_profile(
        "Goliath Mauler", profile_type=vehicle, gang_type=goliath, price=80
    )

    set_statline(juve, movement=5, toughness=3)
    set_statline(bruiser, movement=4, toughness=4)

    assert juve.stats() == {"movement": '5"', "toughness": "3"}
    assert bruiser.stats() == {"movement": '4"', "toughness": "4"}

    # Both Types point at the same shape.
    assert person_statline.profile_types.count() == 2
    # Each gang type sees only its own profiles.
    assert [p.name for p in escher.profiles.all()] == ["Escher Juve"]
    assert [p.name for p in goliath.profiles.all()] == ["Goliath Mauler"]


def test_a_pack_brings_its_own_content(default_pack):
    """A homebrew pack defines everything itself, N26 untouched."""
    homebrew = create_pack("Homebrew")

    # Base content in N26.
    base_statline = create_statline_type(
        "Person", stats=[create_stat("M", "Movement", is_inches=True)]
    )
    base_type = create_profile_type("Fighter", statline_type=base_statline)
    create_profile(
        "Escher Juve",
        profile_type=base_type,
        gang_type=create_gang_type("Escher"),
        price=25,
    )

    # A parallel set in the pack — same names, no collision.
    pack_statline = create_statline_type(
        "Person",
        stats=[create_stat("Sn", "Sneak", is_target=True, pack=homebrew)],
        pack=homebrew,
    )
    pack_type = create_profile_type(
        "Fighter", statline_type=pack_statline, pack=homebrew
    )
    shadow = create_profile(
        "Shadow",
        profile_type=pack_type,
        gang_type=create_gang_type("Delaque", pack=homebrew),
        pack=homebrew,
    )
    set_statline(shadow, pack=homebrew, sneak=2)

    assert shadow.stats() == {"sneak": "2+"}

    # The default manager filters nothing — both packs' profiles come back.
    assert sorted(Profile.objects.values_list("name", flat=True)) == [
        "Escher Juve",
        "Shadow",
    ]
    # Narrowing is opt-in, and only then does the pack matter.
    assert list(Profile.objects.in_default_pack().values_list("name", flat=True)) == [
        "Escher Juve"
    ]
    assert list(
        Profile.objects.in_packs([homebrew]).values_list("name", flat=True)
    ) == ["Shadow"]
    assert sorted(
        Profile.objects.selectable([homebrew]).values_list("name", flat=True)
    ) == ["Escher Juve", "Shadow"]


def test_a_typo_in_a_stat_name_fails_loudly():
    """set_statline should never silently drop a value."""
    person_statline = create_statline_type(
        "Person", stats=[create_stat("M", "Movement", is_inches=True)]
    )
    juve = create_profile(
        "Escher Juve",
        profile_type=create_profile_type("Fighter", statline_type=person_statline),
        gang_type=create_gang_type("Escher"),
    )
    with pytest.raises(KeyError, match="movment"):
        set_statline(juve, movment=4)
