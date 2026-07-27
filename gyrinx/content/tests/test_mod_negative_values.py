import pytest
from gyrinx.content.models import ContentModStat, ContentStat


@pytest.mark.django_db
def test_a_negative_intermediate_stays_a_plain_number():
    """A plain stat driven below zero and back must not gain a "+" sign.

    "-2" contains a "-", and reading it as the "S-1" stat-linked shape made
    the rendered result depend on the order mods were applied in.
    """
    ContentStat.objects.get_or_create(
        field_name="plainstat",
        defaults={"short_name": "P", "full_name": "Plain Stat"},
    )
    worsen = ContentModStat.objects.create(stat="plainstat", mode="worsen", value="3")
    improve = ContentModStat.objects.create(stat="plainstat", mode="improve", value="4")

    # 1 -> -2 -> 2, rather than 1 -> -2 -> "+2"
    assert worsen.apply("1") == "-2"
    assert improve.apply(worsen.apply("1")) == "2"

    # The other order gives the same answer, which is the point
    assert worsen.apply(improve.apply("1")) == "2"


@pytest.mark.django_db
def test_stat_linked_values_are_still_read_as_such():
    ContentStat.objects.get_or_create(
        field_name="plainstat",
        defaults={"short_name": "P", "full_name": "Plain Stat"},
    )
    mod = ContentModStat.objects.create(stat="plainstat", mode="improve", value="1")
    assert mod.apply("S") == "S+1"
    assert mod.apply("S+1") == "S+2"
    assert mod.apply("S-1") == "S"
