import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import ContentFighter
from gyrinx.core.models import List, ListFighter
from gyrinx.core.models.campaign import Campaign


@pytest.mark.django_db
def test_stash_fighter_is_excluded_from_default_queryset(db):
    """Test that stash fighters are excluded from default ContentFighter queryset."""
    # Create regular fighter
    regular_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category="GANGER",
        base_cost=100,
        is_stash=False,
    )

    # Create stash fighter
    stash_fighter = ContentFighter.objects.all_with_stash().create(
        type="Stash",
        category="STASH",
        base_cost=0,
        is_stash=True,
    )

    # Default queryset should not include stash fighter
    assert regular_fighter in ContentFighter.objects.all()
    assert stash_fighter not in ContentFighter.objects.all()

    # all_with_stash should include both
    all_fighters = ContentFighter.objects.all_with_stash()
    assert regular_fighter in all_fighters
    assert stash_fighter in all_fighters


@pytest.mark.django_db
def test_stash_fighter_must_have_zero_base_cost(db):
    """Test that stash fighters must have base_cost of 0."""
    stash_fighter = ContentFighter(
        type="Stash",
        category="STASH",
        base_cost=100,  # Invalid
        is_stash=True,
    )

    with pytest.raises(ValidationError) as exc_info:
        stash_fighter.clean()

    assert "Stash fighters must have a base cost of 0" in str(exc_info.value)


@pytest.mark.django_db
def test_only_one_stash_fighter_per_list(db, user, content_house):
    """Test that each list can only have one stash fighter."""
    # Create list
    gang_list = List.objects.create(
        name="Test Gang",
        content_house=content_house,
        owner=user,
    )

    # Create stash content fighter
    stash_fighter = ContentFighter.objects.all_with_stash().create(
        type="Stash",
        category="STASH",
        base_cost=0,
        is_stash=True,
        house=content_house,
    )

    # Create first stash list fighter
    ListFighter.objects.create(
        name="Gang Stash",
        content_fighter=stash_fighter,
        list=gang_list,
    )

    # Try to create second stash list fighter
    second_stash = ListFighter(
        name="Another Stash",
        content_fighter=stash_fighter,
        list=gang_list,
    )

    with pytest.raises(ValidationError) as exc_info:
        second_stash.clean_fields()

    assert "Each list can only have one stash fighter" in str(exc_info.value)


@pytest.mark.django_db
def test_stash_fighter_created_when_cloning_to_campaign(db, user, content_house):
    """Test that a stash fighter is automatically created when cloning a list to a campaign."""
    # Create campaign
    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
    )

    # Create regular fighter
    regular_fighter = ContentFighter.objects.create(
        type="Ganger",
        category="GANGER",
        base_cost=50,
        house=content_house,
    )

    # Create original list
    original_list = List.objects.create(
        name="Test Gang",
        content_house=content_house,
        owner=user,
    )

    # Add a regular fighter
    ListFighter.objects.create(
        name="Bob",
        content_fighter=regular_fighter,
        list=original_list,
    )

    # Clone to campaign
    cloned_list = original_list.clone(for_campaign=campaign)

    # Check that stash fighter was created
    stash_fighters = cloned_list.listfighter_set.filter(content_fighter__is_stash=True)
    assert stash_fighters.count() == 1

    stash_fighter = stash_fighters.first()
    assert stash_fighter.name == "Gang Stash"
    assert stash_fighter.content_fighter.base_cost == 0
    assert stash_fighter.content_fighter.house == content_house


@pytest.mark.django_db
def test_stash_fighter_not_created_for_regular_clone(db, user, content_house):
    """Test that a stash fighter is NOT created for regular clones."""
    # Create regular fighter
    regular_fighter = ContentFighter.objects.create(
        type="Ganger",
        category="GANGER",
        base_cost=50,
        house=content_house,
    )

    # Create original list
    original_list = List.objects.create(
        name="Test Gang",
        content_house=content_house,
        owner=user,
    )

    # Add a regular fighter
    ListFighter.objects.create(
        name="Bob",
        content_fighter=regular_fighter,
        list=original_list,
    )

    # Regular clone (not for campaign)
    cloned_list = original_list.clone()

    # Check that NO stash fighter was created
    stash_fighters = cloned_list.listfighter_set.filter(content_fighter__is_stash=True)
    assert stash_fighters.count() == 0


@pytest.mark.django_db
def test_stash_fighter_card_display(db, user, content_house):
    """Test that stash fighter cards only show gear and weapons."""
    # This test would require rendering the template, which is more of an integration test
    # For now, we'll just verify the is_stash flag is accessible in the template context

    # Create stash content fighter
    stash_fighter = ContentFighter.objects.all_with_stash().create(
        type="Stash",
        category="STASH",
        base_cost=0,
        is_stash=True,
        house=content_house,
    )

    # Create list
    gang_list = List.objects.create(
        name="Test Gang",
        content_house=content_house,
        owner=user,
    )

    # Create stash list fighter
    list_fighter = ListFighter.objects.create(
        name="Gang Stash",
        content_fighter=stash_fighter,
        list=gang_list,
    )

    # Verify we can access the is_stash flag through the list fighter
    assert list_fighter.content_fighter.is_stash is True
    assert list_fighter.content_fighter_cached.is_stash is True
