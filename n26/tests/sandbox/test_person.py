"""Build profile types, statlines and gang profiles through the authoring API. Verify
formatted characteristics, shared statline definitions, pack isolation and unknown-stat
validation.
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

    escher = create_gang_type("Escher")

    # Cover distance, roll-target and plain-number display rules.
    person_statline = create_statline_type(
        "Person",
        stats=[
            create_stat("M", "Movement", is_inches=True),
            create_stat("WS", "Weapon Skill", is_target=True, is_inverted=True),
            create_stat("T", "Toughness"),
        ],
    )

    person = create_profile_type("Fighter", statline_type=person_statline)

    juve = create_profile(
        "Escher Juve", profile_type=person, gang_type=escher, price=25
    )

    assert juve.has_statline is False
    assert juve.stats() == {}

    set_statline(juve, movement=4, weapon_skill=3, toughness=3)

    assert juve.stats() == {
        "movement": '4"',
        "weapon_skill": "3+",
        "toughness": "3",
    }

    assert juve.pack == default_pack
    assert escher.pack == default_pack
    assert person_statline.pack == default_pack

    assert juve.gang_type == escher
    assert juve.profile_type == person
    assert juve.statline_type == person_statline
    assert juve.price == 25
    juve.statline.full_clean()


def test_one_statline_type_serves_many_gangs_and_profiles():
    """Share one statline definition across Fighter and Vehicle profile types and multiple
    gang types.
    """
    person_statline = create_statline_type(
        "Person",
        stats=[
            create_stat("M", "Movement", is_inches=True),
            create_stat("T", "Toughness"),
        ],
    )
    # Fighter and Vehicle profile types can share their characteristic definitions.
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

    assert person_statline.profile_types.count() == 2

    assert [p.name for p in escher.profiles.all()] == ["Escher Juve"]
    assert [p.name for p in goliath.profiles.all()] == ["Goliath Mauler"]


def test_a_pack_brings_its_own_content(default_pack):
    """Allow same-named content in separate packs and apply pack filtering only when
    requested.
    """
    homebrew = create_pack("Homebrew")

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

    # The default manager includes all packs.
    assert sorted(Profile.objects.values_list("name", flat=True)) == [
        "Escher Juve",
        "Shadow",
    ]
    # Pack-specific managers narrow explicitly; selectable includes default content too.
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
    """Reject unknown field names instead of silently dropping statline values."""
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
