import pytest

from gyrinx.content.models import ContentModStat


@pytest.mark.django_db
def test_stat_mod():
    ContentModStat.objects.create(
        stat="strength",
        mode="improve",
        value="1",
    ).apply("3") == "4"

    ContentModStat.objects.create(
        stat="strength",
        mode="worsen",
        value="1",
    ).apply("3") == "2"

    ContentModStat.objects.create(
        stat="strength",
        mode="worsen",
        value="1",
    ).apply("S+1") == "S+2"

    ContentModStat.objects.create(
        stat="strength",
        mode="improve",
        value="1",
    ).apply("S") == "S+1"

    ContentModStat.objects.create(
        stat="strength",
        mode="worsen",
        value="1",
    ).apply("S") == "S-1"

    ContentModStat.objects.create(
        stat="range_short",
        mode="improve",
        value="2",
    ).apply('2"') == '6"'

    ContentModStat.objects.create(
        stat="range_short",
        mode="worsen",
        value="2",
    ).apply('4"') == '2"'

    ContentModStat.objects.create(
        stat="range_short",
        mode="worsen",
        value="2",
    ).apply('2"') == ""
