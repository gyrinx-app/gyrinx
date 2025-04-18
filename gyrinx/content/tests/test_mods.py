import pytest

from gyrinx.content.models import ContentModFighterStat, ContentModStat


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
