import pytest
from django.core.exceptions import ValidationError

from n23.content.models import (
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

    # Create a statline type with required stats. Not called "Vehicle": the
    # canonical types are seeded already and the name is unique.
    statline_type = ContentStatlineType.objects.create(
        name="Two-Stat Vehicle",
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

    # Saving the fighter already gave it a statline, so adopt that row rather
    # than inserting a second one (the FK is one-to-one). Fetched rather than
    # read off `fighter`: constructing the unsaved ContentStatline above put
    # itself in the fighter's cached relation.
    statline = ContentStatline.objects.get(content_fighter=fighter)
    statline.statline_type = statline_type
    statline.save(update_fields=["statline_type"])
    statline.stats.all().delete()

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

    # Point the fighter's statline at the empty type
    statline = fighter.custom_statline
    statline.statline_type = statline_type
    statline.save(update_fields=["statline_type"])
    statline.stats.all().delete()

    # Even though the statline exists and has no stats,
    # clean should not raise an error if no stats exist at all
    try:
        statline.clean()
    except ValidationError:
        pytest.fail("clean() raised ValidationError when no stats exist")
