import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse

from gyrinx.content.models import (
    ContentFighter,
    ContentHouse,
    ContentModFighterStat,
    ContentSkill,
    ContentSkillCategory,
)
from gyrinx.core.models import List, ListFighter, ListFighterAdvancement

User = get_user_model()


@pytest.fixture
def user():
    return User.objects.create_user(username="testuser", password="testpass")


@pytest.fixture
def house():
    return ContentHouse.objects.create(
        name="Test House",
        owner=None,
    )


@pytest.fixture
def skill_category():
    return ContentSkillCategory.objects.create(
        name="Test Category",
        owner=None,
    )


@pytest.fixture
def content_fighter(house, skill_category):
    fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category="LEADER",
        cost=100,
        house=house,
        owner=None,
    )
    fighter.primary_skill_categories.add(skill_category)
    return fighter


@pytest.fixture
def skill(skill_category):
    return ContentSkill.objects.create(
        name="Test Skill",
        category=skill_category,
        owner=None,
    )


@pytest.fixture
def campaign_list(user, house):
    return List.objects.create(
        name="Test Campaign List",
        content_house=house,
        owner=user,
        status=List.CAMPAIGN_MODE,
    )


@pytest.fixture
def list_fighter(campaign_list, content_fighter):
    return ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=campaign_list,
        owner=campaign_list.owner,
        xp_current=10,
        xp_total=10,
    )


@pytest.mark.django_db
def test_advancement_model_creation(list_fighter):
    """Test creating an advancement with different types."""
    # Custom advancement
    custom_advancement = ListFighterAdvancement.objects.create(
        fighter=list_fighter,
        xp_spent=5,
        cost_increase=10,
        description="Custom improvement",
        owner=list_fighter.owner,
    )
    assert custom_advancement.get_summary() == "Custom improvement"
    assert list_fighter.xp_current == 5  # XP was deducted

    # Stat advancement
    stat_mod = ContentModFighterStat.objects.create(
        stat="strength",
        mode="improve",
        value="+1",
        owner=list_fighter.owner,
    )
    stat_advancement = ListFighterAdvancement.objects.create(
        fighter=list_fighter,
        xp_spent=3,
        cost_increase=20,
        stat_mod=stat_mod,
        owner=list_fighter.owner,
    )
    assert "Improved Strength by +1" in stat_advancement.get_summary()
    assert list_fighter.xp_current == 2  # More XP was deducted


@pytest.mark.django_db
def test_advancement_skill(list_fighter, skill):
    """Test creating a skill advancement."""
    advancement = ListFighterAdvancement.objects.create(
        fighter=list_fighter,
        xp_spent=6,
        cost_increase=15,
        skill=skill,
        owner=list_fighter.owner,
    )
    assert advancement.get_summary() == f"Gained {skill.name} skill"

    # Check that the skill is included in all_skills
    assert skill in list_fighter.all_skills()


@pytest.mark.django_db
def test_advancement_validation(list_fighter, skill_category):
    """Test advancement validation rules."""
    # Cannot spend more XP than available
    with pytest.raises(Exception):  # Will raise ValidationError
        advancement = ListFighterAdvancement(
            fighter=list_fighter,
            xp_spent=20,  # Fighter only has 10 XP
            cost_increase=10,
            description="Too expensive",
            owner=list_fighter.owner,
        )
        advancement.clean()

    # Must have at least one advancement type
    with pytest.raises(Exception):
        advancement = ListFighterAdvancement(
            fighter=list_fighter,
            xp_spent=5,
            cost_increase=10,
            owner=list_fighter.owner,
        )
        advancement.clean()

    # Cannot have multiple advancement types
    with pytest.raises(Exception):
        advancement = ListFighterAdvancement(
            fighter=list_fighter,
            xp_spent=5,
            cost_increase=10,
            description="Custom",
            skill=skill,
            owner=list_fighter.owner,
        )
        advancement.clean()


@pytest.mark.django_db
def test_advancement_cost_integration(list_fighter):
    """Test that advancements increase fighter cost."""
    original_cost = list_fighter.cost_int()

    ListFighterAdvancement.objects.create(
        fighter=list_fighter,
        xp_spent=5,
        cost_increase=25,
        description="Expensive upgrade",
        owner=list_fighter.owner,
    )

    assert list_fighter.cost_int() == original_cost + 25


@pytest.mark.django_db
def test_advancement_stat_mod_integration(list_fighter):
    """Test that stat mods from advancements are applied."""
    stat_mod = ContentModFighterStat.objects.create(
        stat="strength",
        mode="improve",
        value="+1",
        owner=list_fighter.owner,
    )

    ListFighterAdvancement.objects.create(
        fighter=list_fighter,
        xp_spent=5,
        cost_increase=10,
        stat_mod=stat_mod,
        owner=list_fighter.owner,
    )

    # Check that the mod is included in _mods
    assert stat_mod in list_fighter._mods


@pytest.mark.django_db
def test_advancement_dice_rolling(list_fighter):
    """Test dice rolling functionality."""
    advancement = ListFighterAdvancement.objects.create(
        fighter=list_fighter,
        xp_spent=5,
        cost_increase=10,
        description="Lucky roll",
        dice_count=3,
        owner=list_fighter.owner,
    )

    assert len(advancement.dice_results) == 3
    assert all(1 <= die <= 6 for die in advancement.dice_results)
    assert advancement.dice_total == sum(advancement.dice_results)


@pytest.mark.django_db
def test_advancement_views_campaign_mode_only(client, user, house):
    """Test that advancement views require campaign mode."""
    client.login(username="testuser", password="testpass")

    # Create a list building mode list
    list_building = List.objects.create(
        name="List Building",
        content_house=house,
        owner=user,
        status=List.LIST_BUILDING,
    )
    fighter = ListFighter.objects.create(
        name="Fighter",
        content_fighter=ContentFighter.objects.create(
            type="Test", category="LEADER", cost=100, house=house, owner=None
        ),
        list=list_building,
        owner=user,
    )

    # Should redirect when not in campaign mode
    response = client.get(
        reverse(
            "core:list-fighter-advancements-list", args=[list_building.id, fighter.id]
        )
    )
    assert response.status_code == 302


@pytest.mark.django_db
def test_advancement_list_view(client, user, list_fighter):
    """Test the advancement list view."""
    client.login(username="testuser", password="testpass")

    # Create some advancements
    ListFighterAdvancement.objects.create(
        fighter=list_fighter,
        xp_spent=3,
        cost_increase=10,
        description="First advancement",
        owner=user,
    )
    ListFighterAdvancement.objects.create(
        fighter=list_fighter,
        xp_spent=2,
        cost_increase=5,
        description="Second advancement",
        owner=user,
    )

    response = client.get(
        reverse(
            "core:list-fighter-advancements-list",
            args=[list_fighter.list.id, list_fighter.id],
        )
    )
    assert response.status_code == 200
    assert "First advancement" in response.content.decode()
    assert "Second advancement" in response.content.decode()
    assert "5 XP" in response.content.decode()  # Remaining XP


@pytest.mark.django_db
def test_advancement_add_custom(client, user, list_fighter):
    """Test adding a custom advancement."""
    client.login(username="testuser", password="testpass")

    response = client.post(
        reverse(
            "core:list-fighter-advancement-add",
            args=[list_fighter.list.id, list_fighter.id],
        )
        + "?type=custom",
        {
            "custom_description": "Bionic arm upgrade",
            "xp_spent": 6,
            "cost_increase": 20,
            "dice_count": 2,
            "notes": "Won in pit fight",
        },
    )
    assert response.status_code == 302

    advancement = ListFighterAdvancement.objects.get(fighter=list_fighter)
    assert advancement.description == "Bionic arm upgrade"
    assert advancement.xp_spent == 6
    assert advancement.cost_increase == 20
    assert advancement.dice_count == 2
    assert len(advancement.dice_results) == 2
    assert list_fighter.xp_current == 4  # 10 - 6


@pytest.mark.django_db
def test_advancement_add_skill(client, user, list_fighter, skill):
    """Test adding a skill advancement."""
    client.login(username="testuser", password="testpass")

    response = client.post(
        reverse(
            "core:list-fighter-advancement-add",
            args=[list_fighter.list.id, list_fighter.id],
        )
        + "?type=skill",
        {
            "skill": skill.id,
            "xp_spent": 6,
            "cost_increase": 12,
            "dice_count": 0,
            "notes": "",
        },
    )
    assert response.status_code == 302

    advancement = ListFighterAdvancement.objects.get(fighter=list_fighter)
    assert advancement.skill == skill
    assert list_fighter.all_skills().filter(id=skill.id).exists()


@pytest.mark.django_db
def test_advancement_delete_refunds_xp(client, user, list_fighter):
    """Test that deleting an advancement refunds XP."""
    client.login(username="testuser", password="testpass")

    advancement = ListFighterAdvancement.objects.create(
        fighter=list_fighter,
        xp_spent=7,
        cost_increase=15,
        description="To be deleted",
        owner=user,
    )

    assert list_fighter.xp_current == 3  # 10 - 7

    response = client.post(
        reverse(
            "core:list-fighter-advancement-delete",
            args=[list_fighter.list.id, list_fighter.id, advancement.id],
        )
    )
    assert response.status_code == 302

    list_fighter.refresh_from_db()
    assert list_fighter.xp_current == 10  # Refunded
    assert not ListFighterAdvancement.objects.filter(id=advancement.id).exists()
