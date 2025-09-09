import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentFighter,
    ContentHouse,
    ContentStat,
    ContentStatline,
    ContentStatlineStat,
    ContentStatlineType,
    ContentStatlineTypeStat,
)


@pytest.mark.django_db
def test_content_statline_clean_during_creation():
    """Test that the clean method doesn't fail during ContentStatline creation."""
    # Create test data
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category="LEADER",
        house=house,
        base_cost=100,
    )

    # Create a statline type with required stats
    statline_type = ContentStatlineType.objects.create(
        name="Vehicle",
    )

    # Create stat definitions
    movement_stat, _ = ContentStat.objects.get_or_create(
        field_name="movement",
        short_name="M",
        full_name="Movement",
    )
    toughness_stat, _ = ContentStat.objects.get_or_create(
        field_name="toughness",
        short_name="T",
        full_name="Toughness",
    )

    # Create required stats for the type
    ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        stat=movement_stat,
        position=1,
    )
    ContentStatlineTypeStat.objects.create(
        statline_type=statline_type,
        stat=toughness_stat,
        position=2,
    )

    # Create a new statline - this should not raise ValidationError during creation
    statline = ContentStatline(
        content_fighter=fighter,
        statline_type=statline_type,
    )

    # The clean method should not raise an error during creation
    try:
        statline.clean()
    except ValidationError:
        pytest.fail("clean() raised ValidationError during creation")

    # Save the statline
    statline.save()

    # Now test that validation works after the object is saved
    # The statline exists but has no stats yet
    with pytest.raises(ValidationError, match="Missing required stats"):
        statline.clean()

    # Add one stat
    movement_stat = statline_type.stats.get(stat__field_name="movement")
    ContentStatlineStat.objects.create(
        statline=statline,
        statline_type_stat=movement_stat,
        value='8"',
    )

    # Should still fail because we're missing toughness
    with pytest.raises(ValidationError, match="Missing required stats"):
        statline.clean()

    # Add the second stat
    toughness_stat = statline_type.stats.get(stat__field_name="toughness")
    ContentStatlineStat.objects.create(
        statline=statline,
        statline_type_stat=toughness_stat,
        value="10",
    )

    # Now clean should pass
    try:
        statline.clean()
    except ValidationError:
        pytest.fail("clean() raised ValidationError when all stats are present")


@pytest.mark.django_db
def test_content_statline_clean_with_no_stats():
    """Test that clean handles the case where no stats exist yet."""
    # Create test data
    house = ContentHouse.objects.create(name="Test House")
    fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category="LEADER",
        house=house,
        base_cost=100,
    )

    # Create a statline type (without any required stats)
    statline_type = ContentStatlineType.objects.create(
        name="BasicStatline",
    )

    # Create a statline
    statline = ContentStatline.objects.create(
        content_fighter=fighter,
        statline_type=statline_type,
    )

    # Even though the statline exists and has no stats,
    # clean should not raise an error if no stats exist at all
    try:
        statline.clean()
    except ValidationError:
        pytest.fail("clean() raised ValidationError when no stats exist")
