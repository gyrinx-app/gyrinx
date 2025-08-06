"""
Test that ListFighterStatOverride entries are cloned for regular fighters.
"""

import pytest

from gyrinx.content.models import (
    ContentStat,
    ContentStatlineType,
    ContentStatlineTypeStat,
)
from gyrinx.core.models.list import ListFighterStatOverride
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_clone_regular_fighter_with_stat_overrides(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
):
    """
    Test that ListFighterStatOverride entries on regular (non-linked) fighters are cloned.
    """
    # Setup
    house = make_content_house("Test House")

    # Create a regular fighter
    gang_leader_cf = make_content_fighter(
        type="Gang Leader",
        category=FighterCategoryChoices.LEADER,
        house=house,
        base_cost=120,
    )

    # Create the list and add the leader
    original_list = make_list("Original List", content_house=house, owner=user)
    leader_lf = make_list_fighter(
        original_list, "Boss", content_fighter=gang_leader_cf, owner=user
    )

    # Create minimal statline infrastructure for testing
    stat = ContentStat.objects.first()
    if not stat:
        stat = ContentStat.objects.create(
            field_name="test_stat",
            full_name="Test Stat",
            short_name="TS",
        )

    statline_type = ContentStatlineType.objects.first()
    if not statline_type:
        statline_type = ContentStatlineType.objects.create(
            name="Test Statline Type",
        )

    type_stat = ContentStatlineTypeStat.objects.filter(
        statline_type=statline_type, stat=stat
    ).first()
    if not type_stat:
        type_stat = ContentStatlineTypeStat.objects.create(
            statline_type=statline_type,
            stat=stat,
            position=1,
        )

    # Add stat overrides to the leader
    ListFighterStatOverride.objects.create(
        list_fighter=leader_lf,
        content_stat=type_stat,
        value="3+",
        owner=user,
    )

    # Create another stat and override
    stat2 = ContentStat.objects.create(
        field_name="another_stat",
        full_name="Another Stat",
        short_name="AS",
    )
    type_stat2 = ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        stat=stat2,
        position=2,
    )
    ListFighterStatOverride.objects.create(
        list_fighter=leader_lf,
        content_stat=type_stat2,
        value="6",
        owner=user,
    )

    # Verify the leader has stat overrides
    assert leader_lf.stat_overrides.count() == 2

    # Clone the list
    cloned_list = original_list.clone(name="Cloned List")

    # Find the cloned leader
    cloned_leader = (
        cloned_list.fighters().filter(content_fighter=gang_leader_cf).first()
    )
    assert cloned_leader is not None
    assert cloned_leader.name == "Boss"

    # Check that stat overrides were cloned
    assert cloned_leader.stat_overrides.count() == 2, (
        f"Expected cloned leader to have 2 stat overrides, "
        f"but found {cloned_leader.stat_overrides.count()}"
    )

    # Verify the values
    cloned_override1 = cloned_leader.stat_overrides.filter(
        content_stat=type_stat
    ).first()
    assert cloned_override1 is not None
    assert cloned_override1.value == "3+"

    cloned_override2 = cloned_leader.stat_overrides.filter(
        content_stat=type_stat2
    ).first()
    assert cloned_override2 is not None
    assert cloned_override2.value == "6"


@pytest.mark.django_db
def test_clone_fighter_directly_with_stat_overrides(
    user,
    make_list,
    make_content_house,
    make_content_fighter,
    make_list_fighter,
):
    """
    Test that ListFighterStatOverride entries are cloned when cloning a fighter directly.
    """
    # Setup
    house = make_content_house("Test House")

    # Create a fighter
    champion_cf = make_content_fighter(
        type="Champion",
        category=FighterCategoryChoices.CHAMPION,
        house=house,
        base_cost=95,
    )

    # Create two lists
    original_list = make_list("Original List", content_house=house, owner=user)
    target_list = make_list("Target List", content_house=house, owner=user)

    # Add the champion to the original list
    champion_lf = make_list_fighter(
        original_list, "Champion Rex", content_fighter=champion_cf, owner=user
    )

    # Create minimal statline infrastructure
    stat = ContentStat.objects.first()
    if not stat:
        stat = ContentStat.objects.create(
            field_name="weapon_skill",
            full_name="Weapon Skill",
            short_name="WS",
        )

    statline_type = ContentStatlineType.objects.first()
    if not statline_type:
        statline_type = ContentStatlineType.objects.create(
            name="Fighter Statline",
        )

    type_stat = ContentStatlineTypeStat.objects.filter(
        statline_type=statline_type, stat=stat
    ).first()
    if not type_stat:
        type_stat = ContentStatlineTypeStat.objects.create(
            statline_type=statline_type,
            stat=stat,
            position=1,
        )

    # Add stat override to the champion
    ListFighterStatOverride.objects.create(
        list_fighter=champion_lf,
        content_stat=type_stat,
        value="2+",
        owner=user,
    )

    # Verify the champion has the stat override
    assert champion_lf.stat_overrides.count() == 1

    # Clone the fighter to the target list
    cloned_champion = champion_lf.clone(list=target_list)

    # Verify the clone
    assert cloned_champion.list == target_list
    assert cloned_champion.name == "Champion Rex"

    # Check that stat override was cloned
    assert cloned_champion.stat_overrides.count() == 1, (
        f"Expected cloned champion to have 1 stat override, "
        f"but found {cloned_champion.stat_overrides.count()}"
    )

    cloned_override = cloned_champion.stat_overrides.first()
    assert cloned_override is not None
    assert cloned_override.value == "2+"
    assert cloned_override.content_stat == type_stat
