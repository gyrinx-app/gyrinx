import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.utils import timezone

from gyrinx.content.models import (
    ContentFighter,
    ContentHouse,
    ContentInjury,
    ContentInjuryPhase,
)
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List, ListFighter, ListFighterInjury
from gyrinx.models import FighterCategoryChoices


def create_test_data():
    """Helper function to create test data."""
    user = User.objects.create_user(username="testuser", password="testpass")

    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
    )

    campaign = Campaign.objects.create(
        name="Test Campaign",
        owner=user,
        status=Campaign.IN_PROGRESS,
    )

    lst = List.objects.create(
        name="Test List",
        content_house=house,
        owner=user,
        status=List.CAMPAIGN_MODE,
        campaign=campaign,
    )

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    injury, _ = ContentInjury.objects.get_or_create(
        name="Test Spinal Injury",
        defaults={
            "description": "Recovery, -1 Strength",
            "phase": ContentInjuryPhase.RECOVERY,
        },
    )

    return user, house, content_fighter, campaign, lst, fighter, injury


@pytest.mark.django_db
def test_list_fighter_injury_creation():
    """Test basic ListFighterInjury creation."""
    user, _, _, _, lst, fighter, injury = create_test_data()

    fighter_injury = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury,
        notes="Injured in battle against Goliaths",
        owner=user,
    )

    assert fighter_injury.fighter == fighter
    assert fighter_injury.injury == injury
    assert fighter_injury.notes == "Injured in battle against Goliaths"
    assert fighter_injury.owner == user
    assert str(fighter_injury) == "Test Fighter - Test Spinal Injury"


@pytest.mark.django_db
def test_list_fighter_injury_date_tracking():
    """Test that injury date is automatically set."""
    user, _, _, _, lst, fighter, injury = create_test_data()

    before = timezone.now()
    fighter_injury = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury,
        owner=user,
    )
    after = timezone.now()

    assert before <= fighter_injury.date_received <= after


@pytest.mark.django_db
def test_injury_only_in_campaign_mode():
    """Test that injuries can only be added to fighters in campaign mode."""
    user, house, content_fighter, _, _, _, injury = create_test_data()

    # Create a non-campaign list
    normal_list = List.objects.create(
        name="Normal List",
        content_house=house,
        owner=user,
        status=List.LIST_BUILDING,  # Not in campaign mode
    )

    fighter = ListFighter.objects.create(
        name="Normal Fighter",
        content_fighter=content_fighter,
        list=normal_list,
        owner=user,
    )

    # Try to add injury
    fighter_injury = ListFighterInjury(
        fighter=fighter,
        injury=injury,
        owner=user,
    )

    with pytest.raises(ValidationError) as exc_info:
        fighter_injury.clean()

    assert "Injuries can only be added to fighters in campaign mode" in str(
        exc_info.value
    )


@pytest.mark.django_db
def test_fighter_injuries_relationship():
    """Test the reverse relationship from fighter to injuries."""
    user, _, _, _, lst, fighter, _ = create_test_data()

    # Create multiple injuries
    injury1, _ = ContentInjury.objects.get_or_create(
        name="Test Eye Injury",
        defaults={"phase": ContentInjuryPhase.RECOVERY},
    )
    injury2, _ = ContentInjury.objects.get_or_create(
        name="Test Old Battle Wound",
        defaults={"phase": ContentInjuryPhase.PERMANENT},
    )

    # Add injuries to fighter
    fighter_injury1 = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury1,
        owner=user,
    )
    fighter_injury2 = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury2,
        owner=user,
    )

    # Check injuries through fighter
    injuries = list(fighter.injuries.all())
    assert len(injuries) == 2
    assert fighter_injury2 in injuries  # Most recent first (ordering)
    assert fighter_injury1 in injuries


@pytest.mark.django_db
def test_injury_ordering():
    """Test that injuries are ordered by date_received descending."""
    user, _, _, _, lst, fighter, _ = create_test_data()

    # Create injuries with specific order
    injury1, _ = ContentInjury.objects.get_or_create(
        name="Test First Injury", defaults={"phase": ContentInjuryPhase.RECOVERY}
    )
    injury2, _ = ContentInjury.objects.get_or_create(
        name="Test Second Injury", defaults={"phase": ContentInjuryPhase.PERMANENT}
    )
    injury3, _ = ContentInjury.objects.get_or_create(
        name="Test Third Injury", defaults={"phase": ContentInjuryPhase.CONVALESCENCE}
    )

    # Add injuries to fighter (will have different timestamps)
    fi1 = ListFighterInjury.objects.create(fighter=fighter, injury=injury1, owner=user)
    fi2 = ListFighterInjury.objects.create(fighter=fighter, injury=injury2, owner=user)
    fi3 = ListFighterInjury.objects.create(fighter=fighter, injury=injury3, owner=user)

    # Check ordering - most recent first
    injuries = list(fighter.injuries.all())
    assert injuries[0] == fi3  # Most recent
    assert injuries[1] == fi2
    assert injuries[2] == fi1  # Oldest


@pytest.mark.django_db
def test_injury_deletion_cascade():
    """Test that deleting a fighter deletes their injuries."""
    user, _, _, _, lst, fighter, injury = create_test_data()

    # Add injury to fighter
    fighter_injury = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury,
        owner=user,
    )

    # Verify injury exists
    assert ListFighterInjury.objects.filter(id=fighter_injury.id).exists()

    # Delete fighter
    fighter.delete()

    # Verify injury is deleted
    assert not ListFighterInjury.objects.filter(id=fighter_injury.id).exists()


@pytest.mark.django_db
def test_injury_blank_notes():
    """Test that injury notes can be blank."""
    user, _, _, _, lst, fighter, injury = create_test_data()

    fighter_injury = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury,
        notes="",
        owner=user,
    )

    assert fighter_injury.notes == ""
    fighter_injury.full_clean()  # Should not raise validation error


@pytest.mark.django_db
def test_injury_history_tracking():
    """Test that injury assignments have history tracking."""
    user, _, _, _, lst, fighter, injury = create_test_data()

    fighter_injury = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury,
        owner=user,
    )

    # Check that history is tracked
    assert hasattr(fighter_injury, "history")
    assert fighter_injury.history.count() == 1

    # Update the injury
    fighter_injury.notes = "Updated notes"
    fighter_injury.save()

    # Check history was updated
    assert fighter_injury.history.count() == 2
    latest_history = fighter_injury.history.first()
    assert latest_history.notes == "Updated notes"


@pytest.mark.django_db
def test_multiple_fighters_with_same_injury():
    """Test that multiple fighters can have the same injury type."""
    user, _, content_fighter, _, lst, fighter1, injury = create_test_data()

    # Create second fighter
    fighter2 = ListFighter.objects.create(
        name="Fighter 2",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Add same injury to both fighters
    injury1 = ListFighterInjury.objects.create(
        fighter=fighter1,
        injury=injury,
        owner=user,
    )
    injury2 = ListFighterInjury.objects.create(
        fighter=fighter2,
        injury=injury,
        owner=user,
    )

    # Both should have the injury
    assert fighter1.injuries.count() == 1
    assert fighter2.injuries.count() == 1
    assert injury1.injury == injury2.injury


@pytest.mark.django_db
def test_fighter_cannot_have_duplicate_injuries():
    """Test that a fighter cannot have multiple instances of the same injury."""
    user, _, _, _, lst, fighter, injury = create_test_data()

    # Add injury once
    ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury,
        notes="First occurrence",
        owner=user,
    )

    # Try to add same injury again should fail
    with pytest.raises(
        Exception
    ):  # Will raise IntegrityError when migration is applied
        ListFighterInjury.objects.create(
            fighter=fighter,
            injury=injury,
            notes="Second occurrence",
            owner=user,
        )


@pytest.mark.django_db
def test_injury_with_user_tracking():
    """Test that injuries track user who created them."""
    user1, _, _, _, lst, fighter, injury = create_test_data()
    user2 = User.objects.create_user(username="user2", password="pass2")

    # Create injury with create_with_user
    fighter_injury = ListFighterInjury.objects.create_with_user(
        user=user2,
        fighter=fighter,
        injury=injury,
        owner=user1,  # Owner is different from creator
    )

    # Check history tracks the correct user
    assert fighter_injury.history.count() == 1
    history = fighter_injury.history.first()
    assert history.history_user == user2
