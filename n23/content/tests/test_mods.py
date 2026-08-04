import logging

import pytest

from n23.content.models import ContentModFighterStat, ContentModStat, ContentStat
from n23.content.models import modifier


@pytest.mark.django_db
def test_stat_mod():
    # A unique constraint now prevents duplicate (stat, mode, value) rows, so
    # create each distinct mod once and reuse it — apply() is stateless.
    str_improve = ContentModStat.objects.create(
        stat="strength", mode="improve", value="1"
    )
    assert str_improve.apply("3") == "4"
    assert str_improve.apply("S") == "S+1"
    assert str_improve.apply("S+1") == "S+2"
    assert str_improve.apply("S-1") == "S"

    str_worsen = ContentModStat.objects.create(
        stat="strength", mode="worsen", value="1"
    )
    assert str_worsen.apply("3") == "2"
    assert str_worsen.apply("S") == "S-1"
    assert str_worsen.apply("S+1") == "S"

    rng_improve = ContentModStat.objects.create(
        stat="range_short", mode="improve", value="2"
    )
    assert rng_improve.apply('4"') == '6"'

    rng_worsen = ContentModStat.objects.create(
        stat="range_short", mode="worsen", value="2"
    )
    assert rng_worsen.apply('4"') == '2"'
    assert rng_worsen.apply('2"') == ""


@pytest.mark.django_db
def test_fighter_stat_mod():
    # Reuse each distinct mod — the unique constraint forbids duplicate rows.
    assert (
        ContentModFighterStat.objects.create(
            stat="strength", mode="improve", value="1"
        ).apply("3")
        == "4"
    )

    ws_improve = ContentModFighterStat.objects.create(
        stat="weapon_skill", mode="improve", value="1"
    )
    assert ws_improve.apply("3+") == "2+"
    assert (
        ContentModFighterStat.objects.create(
            stat="weapon_skill", mode="worsen", value="1"
        ).apply("3+")
        == "4+"
    )
    assert ws_improve.apply("3+") == "2+"

    assert (
        ContentModFighterStat.objects.create(
            stat="movement", mode="improve", value="1"
        ).apply('2"')
        == '3"'
    )
    assert (
        ContentModFighterStat.objects.create(
            stat="movement", mode="worsen", value="1"
        ).apply('2"')
        == '1"'
    )


@pytest.mark.django_db
def test_content_stat_configuration():
    """Test that ContentModStatApplyMixin uses ContentStat configuration when available."""
    # Create a ContentStat with specific configuration
    ContentStat.objects.create(
        field_name="test_stat",
        short_name="TS",
        full_name="Test Stat",
        is_inverted=True,
        is_inches=False,
        is_modifier=False,
        is_target=True,
    )

    # Test inverted target stat (like weapon_skill)
    mod = ContentModStat.objects.create(
        stat="test_stat",
        mode="improve",
        value="1",
    )

    # When improving an inverted stat, the number should go down
    assert mod.apply("4+") == "3+"

    # Test with worsen mode
    mod.mode = "worsen"
    assert mod.apply("4+") == "5+"


@pytest.mark.django_db
def test_content_stat_inches():
    """Test ContentStat with inches configuration."""
    ContentStat.objects.create(
        field_name="test_inches",
        short_name="TI",
        full_name="Test Inches",
        is_inverted=False,
        is_inches=True,
        is_modifier=False,
        is_target=False,
    )

    mod = ContentModStat.objects.create(
        stat="test_inches",
        mode="improve",
        value="2",
    )

    assert mod.apply('4"') == '6"'

    mod.mode = "worsen"
    assert mod.apply('4"') == '2"'


@pytest.mark.django_db
def test_content_stat_modifier():
    """Test ContentStat with modifier configuration."""
    ContentStat.objects.create(
        field_name="test_modifier",
        short_name="TM",
        full_name="Test Modifier",
        is_inverted=False,
        is_inches=False,
        is_modifier=True,
        is_target=False,
    )

    mod = ContentModStat.objects.create(
        stat="test_modifier",
        mode="improve",
        value="1",
    )

    assert mod.apply("+2") == "+3"

    mod.mode = "worsen"
    assert mod.apply("+2") == "+1"


@pytest.mark.django_db
def test_standard_stats_are_classified_from_their_definitions():
    """The stats every environment defines behave according to those definitions."""

    # Inverted: improving a target roll lowers the number
    mod = ContentModStat.objects.create(
        stat="weapon_skill",
        mode="improve",
        value="1",
    )
    assert mod.apply("4+") == "3+"

    # Inches: keeps its quote mark
    mod = ContentModStat.objects.create(
        stat="movement",
        mode="improve",
        value="1",
    )
    assert mod.apply('4"') == '5"'

    # Modifier: keeps its plus prefix
    mod = ContentModStat.objects.create(
        stat="accuracy_short",
        mode="improve",
        value="1",
    )
    assert mod.apply("+2") == "+3"

    # Target roll: ammo is both inverted and a target, so improving decreases it
    mod = ContentModStat.objects.create(
        stat="ammo",
        mode="improve",
        value="1",
    )
    assert mod.apply("5+") == "4+"


@pytest.mark.django_db
def test_stat_definition_drives_classification():
    """Classification follows the ContentStat row, not the stat's name.

    Weapon Skill is conventionally an inverted target roll. Redefining it
    proves the behaviour is data-driven rather than baked into the code.
    """
    ContentStat.objects.update_or_create(
        field_name="weapon_skill",
        defaults={
            "short_name": "WS",
            "full_name": "Weapon Skill",
            "is_inverted": False,
            "is_inches": False,
            "is_modifier": False,
            "is_target": False,
        },
    )

    mod = ContentModStat.objects.create(
        stat="weapon_skill",
        mode="improve",
        value="1",
    )

    # No longer inverted, and no longer formatted as a target roll
    assert mod.apply("4") == "5"


@pytest.mark.django_db
def test_undefined_stat_is_modified_without_reformatting(caplog):
    """A stat with no definition still applies, it just gains no formatting.

    Every stat a modification can name has a definition, so this is a data
    problem rather than a supported configuration — but it must not take a
    page down when it happens.
    """
    # Warnings are emitted once per stat per process, so make sure this one
    # has not already been reported by an earlier test in the same worker.
    modifier._undefined_stats_warned.discard("undefined_stat")

    mod = ContentModStat.objects.create(
        stat="undefined_stat",
        mode="improve",
        value="1",
    )

    with caplog.at_level(logging.WARNING, logger=modifier.__name__):
        assert mod.apply("3") == "4"

    assert "undefined_stat" in caplog.text

    mod.mode = "worsen"
    assert mod.apply("3") == "2"


@pytest.mark.django_db
def test_undefined_stat_is_only_warned_about_once(caplog):
    """One bad stat name must not flood the logs on every render."""
    modifier._undefined_stats_warned.discard("noisy_stat")

    mod = ContentModStat.objects.create(
        stat="noisy_stat",
        mode="improve",
        value="1",
    )

    with caplog.at_level(logging.WARNING, logger=modifier.__name__):
        for _ in range(5):
            mod.apply("3")

    assert len([r for r in caplog.records if "noisy_stat" in r.getMessage()]) == 1


@pytest.mark.django_db
def test_all_stat_types_with_content_stat():
    """Test all four stat types when configured through ContentStat."""
    # Test 1: Regular stat (no special flags)
    ContentStat.objects.create(
        field_name="strength_test",
        short_name="S",
        full_name="Strength Test",
        is_inverted=False,
        is_inches=False,
        is_modifier=False,
        is_target=False,
    )

    mod = ContentModStat.objects.create(
        stat="strength_test",
        mode="improve",
        value="1",
    )
    assert mod.apply("3") == "4"

    # Test 2: Inverted stat (like Cool, WS)
    ContentStat.objects.create(
        field_name="cool_test",
        short_name="Cl",
        full_name="Cool Test",
        is_inverted=True,
        is_inches=False,
        is_modifier=False,
        is_target=True,  # Usually inverted stats are also target stats
    )

    mod = ContentModStat.objects.create(
        stat="cool_test",
        mode="improve",
        value="1",
    )
    assert mod.apply("6+") == "5+"

    # Test 3: Inches stat (like Movement, Range)
    ContentStat.objects.create(
        field_name="range_test",
        short_name="Rng",
        full_name="Range Test",
        is_inverted=False,
        is_inches=True,
        is_modifier=False,
        is_target=False,
    )

    mod = ContentModStat.objects.create(
        stat="range_test",
        mode="improve",
        value="3",
    )
    assert mod.apply('12"') == '15"'

    # Test 4: Modifier stat (like Accuracy, AP)
    ContentStat.objects.create(
        field_name="accuracy_test",
        short_name="Acc",
        full_name="Accuracy Test",
        is_inverted=False,
        is_inches=False,
        is_modifier=True,
        is_target=False,
    )

    mod = ContentModStat.objects.create(
        stat="accuracy_test",
        mode="improve",
        value="2",
    )
    assert mod.apply("+1") == "+3"

    # Test edge case: Modifier stat that starts at 0
    assert mod.apply("0") == "+2"


@pytest.mark.django_db
def test_content_mod_fighter_stat_with_content_stat():
    """Test that ContentModFighterStat also uses ContentStat configuration."""
    # Create a fighter-specific stat
    ContentStat.objects.create(
        field_name="initiative_test",
        short_name="I",
        full_name="Initiative Test",
        is_inverted=True,
        is_inches=False,
        is_modifier=False,
        is_target=True,
    )

    mod = ContentModFighterStat.objects.create(
        stat="initiative_test",
        mode="improve",
        value="1",
    )

    # Initiative is inverted and target, so improving should decrease
    assert mod.apply("4+") == "3+"
