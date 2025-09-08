import pytest
from unittest.mock import patch

from gyrinx.content.models import ContentModFighterStat, ContentModStat, ContentStat


@pytest.mark.django_db
def test_stat_mod():
    assert (
        ContentModStat.objects.create(
            stat="strength",
            mode="improve",
            value="1",
        ).apply("3")
        == "4"
    )

    assert (
        ContentModStat.objects.create(
            stat="strength",
            mode="worsen",
            value="1",
        ).apply("3")
        == "2"
    )

    assert (
        ContentModStat.objects.create(
            stat="strength",
            mode="improve",
            value="1",
        ).apply("S")
        == "S+1"
    )

    assert (
        ContentModStat.objects.create(
            stat="strength",
            mode="improve",
            value="1",
        ).apply("S+1")
        == "S+2"
    )

    assert (
        ContentModStat.objects.create(
            stat="strength",
            mode="improve",
            value="1",
        ).apply("S-1")
        == "S"
    )

    assert (
        ContentModStat.objects.create(
            stat="strength",
            mode="worsen",
            value="1",
        ).apply("S")
        == "S-1"
    )

    assert (
        ContentModStat.objects.create(
            stat="strength",
            mode="worsen",
            value="1",
        ).apply("S+1")
        == "S"
    )

    assert (
        ContentModStat.objects.create(
            stat="range_short",
            mode="improve",
            value="2",
        ).apply('4"')
        == '6"'
    )

    assert (
        ContentModStat.objects.create(
            stat="range_short",
            mode="worsen",
            value="2",
        ).apply('4"')
        == '2"'
    )

    assert (
        ContentModStat.objects.create(
            stat="range_short",
            mode="worsen",
            value="2",
        ).apply('2"')
        == ""
    )


@pytest.mark.django_db
def test_fighter_stat_mod():
    assert (
        ContentModFighterStat.objects.create(
            stat="strength",
            mode="improve",
            value="1",
        ).apply("3")
        == "4"
    )

    assert (
        ContentModFighterStat.objects.create(
            stat="weapon_skill",
            mode="improve",
            value="1",
        ).apply("3+")
        == "2+"
    )

    assert (
        ContentModFighterStat.objects.create(
            stat="weapon_skill",
            mode="worsen",
            value="1",
        ).apply("3+")
        == "4+"
    )

    assert (
        ContentModFighterStat.objects.create(
            stat="weapon_skill",
            mode="improve",
            value="1",
        ).apply("3+")
        == "2+"
    )

    assert (
        ContentModFighterStat.objects.create(
            stat="movement",
            mode="improve",
            value="1",
        ).apply('2"')
        == '3"'
    )

    assert (
        ContentModFighterStat.objects.create(
            stat="movement",
            mode="worsen",
            value="1",
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
def test_content_stat_backward_compatibility():
    """Test that stats work correctly when ContentStat doesn't exist."""
    # Test with a stat that doesn't have a ContentStat object
    # Should fall back to hardcoded values

    # Test inverted stat (weapon_skill is in inverted_stats)
    mod = ContentModStat.objects.create(
        stat="weapon_skill",
        mode="improve",
        value="1",
    )
    assert mod.apply("4+") == "3+"

    # Test inches stat (movement is in inch_stats)
    mod = ContentModStat.objects.create(
        stat="movement",
        mode="improve",
        value="1",
    )
    assert mod.apply('4"') == '5"'

    # Test modifier stat (accuracy_short is in modifier_stats)
    mod = ContentModStat.objects.create(
        stat="accuracy_short",
        mode="improve",
        value="1",
    )
    assert mod.apply("+2") == "+3"

    # Test target roll stat (ammo is in target_roll_stats)
    mod = ContentModStat.objects.create(
        stat="ammo",
        mode="improve",
        value="1",
    )
    # ammo is both inverted and target, so improving should decrease the number
    assert mod.apply("5+") == "4+"


@pytest.mark.django_db
def test_content_stat_fields_missing():
    """Test backward compatibility when ContentStat exists but fields don't."""
    # Simulate old ContentStat without the new boolean fields
    with patch.object(ContentStat, "__init__", lambda self, **kwargs: None):
        content_stat = ContentStat()
        content_stat.field_name = "test_old_stat"
        content_stat.short_name = "TO"
        content_stat.full_name = "Test Old Stat"
        # Don't set the boolean fields to simulate missing attributes
        content_stat.save = lambda *args, **kwargs: None

        # Mock the database query
        with patch("gyrinx.content.models.ContentStat.objects.get") as mock_get:
            mock_get.return_value = content_stat

            # Should fall back to hardcoded values
            mod = ContentModStat.objects.create(
                stat="test_old_stat",
                mode="improve",
                value="1",
            )

            # Since test_old_stat isn't in any hardcoded list, it should be treated as a regular stat
            assert mod.apply("5") == "6"


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
