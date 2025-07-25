"""Tests for fighter advancement system."""

import pytest
from django.contrib.auth import get_user_model
from django.core.exceptions import ValidationError
from django.urls import reverse

from gyrinx.content.models import (
    ContentFighter,
    ContentSkill,
    ContentSkillCategory,
)
from gyrinx.core.models import List, ListFighter, ListFighterAdvancement

User = get_user_model()


@pytest.fixture
def content_fighter(house):
    return ContentFighter.objects.create(
        type="Test Fighter Type",
        house=house,
        movement='4"',
        weapon_skill="3+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7",
        cool="7",
        willpower="7",
        intelligence="7",
        category="ganger",
        base_cost=50,
    )


@pytest.fixture
def skill_category():
    category, _ = ContentSkillCategory.objects.get_or_create(name="Combat")
    return category


@pytest.fixture
def skill(skill_category):
    skill, _ = ContentSkill.objects.get_or_create(
        name="Iron Jaw",
        category=skill_category,
    )
    return skill


@pytest.fixture
def fighter_with_xp(list_with_campaign, content_fighter):
    return ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=list_with_campaign,
        xp_current=50,
        xp_total=50,
    )


@pytest.mark.django_db
def test_advancement_model_creation(fighter_with_xp, skill):
    """Test creating a fighter advancement."""
    advancement = ListFighterAdvancement.objects.create(
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        skill=skill,
        xp_cost=10,
        cost_increase=5,
    )

    assert advancement.fighter == fighter_with_xp
    assert advancement.advancement_type == ListFighterAdvancement.ADVANCEMENT_SKILL
    assert advancement.skill == skill
    assert advancement.xp_cost == 10
    assert advancement.cost_increase == 5
    assert str(advancement) == f"Test Fighter - {skill.name}"


@pytest.mark.django_db
def test_stat_advancement_application(fighter_with_xp):
    """Test applying a stat advancement."""
    # ListFighter gets base stats from content_fighter

    advancement = ListFighterAdvancement.objects.create(
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="weapon_skill",
        xp_cost=10,
        cost_increase=20,
    )

    advancement.apply_advancement()
    fighter_with_xp.refresh_from_db()

    # Since original_ws is "3+", the override should be "2+" (improved by 1)
    assert fighter_with_xp.weapon_skill_override == "2+"
    assert fighter_with_xp.xp_current == 40  # 50 - 10


@pytest.mark.django_db
def test_stat_advancement_application_movement(fighter_with_xp):
    """Test applying a stat advancement."""
    # ListFighter gets base stats from content_fighter

    advancement = ListFighterAdvancement.objects.create(
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        stat_increased="movement",
        xp_cost=10,
        cost_increase=20,
    )

    advancement.apply_advancement()
    fighter_with_xp.refresh_from_db()

    # Since original is '4"', the override should be '5"' (improved by 1)
    assert fighter_with_xp.movement_override == '5"'
    assert fighter_with_xp.xp_current == 40  # 50 - 10


@pytest.mark.django_db
def test_skill_advancement_application(fighter_with_xp, skill):
    """Test applying a skill advancement."""
    assert skill not in fighter_with_xp.skills.all()

    advancement = ListFighterAdvancement.objects.create(
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        skill=skill,
        xp_cost=10,
        cost_increase=5,
    )

    advancement.apply_advancement()
    fighter_with_xp.refresh_from_db()

    assert skill in fighter_with_xp.skills.all()
    assert fighter_with_xp.xp_current == 40  # 50 - 10


@pytest.mark.django_db
def test_advancement_list_view(client, user, fighter_with_xp):
    """Test the advancement list view."""
    client.login(username="testuser", password="password")

    url = reverse(
        "core:list-fighter-advancements",
        args=[fighter_with_xp.list.id, fighter_with_xp.id],
    )
    response = client.get(url)

    assert response.status_code == 200
    assert "Advancements for Test Fighter" in response.content.decode()


@pytest.mark.django_db
def test_advancement_start_works_in_any_mode(client, user, house, content_fighter):
    """Test that advancement works in any list mode."""
    client.login(username="testuser", password="password")

    # Create a non-campaign list
    lst = List.objects.create(
        name="Non-Campaign List",
        content_house=house,
        owner=user,
        status=List.LIST_BUILDING,
    )
    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    url = reverse("core:list-fighter-advancement-start", args=[lst.id, fighter.id])
    response = client.get(url)

    assert response.status_code == 302  # Redirect to dice choice
    assert response.url == reverse(
        "core:list-fighter-advancement-dice-choice", args=[lst.id, fighter.id]
    )


@pytest.mark.django_db
def test_advancement_dice_choice_flow(client, user, fighter_with_xp):
    """Test the dice choice step of advancement flow."""
    client.login(username="testuser", password="password")

    url = reverse(
        "core:list-fighter-advancement-dice-choice",
        args=[fighter_with_xp.list.id, fighter_with_xp.id],
    )

    # GET request
    response = client.get(url)
    assert response.status_code == 200
    assert "Roll for Advancement?" in response.content.decode()

    # POST without rolling
    response = client.post(url, {"roll_dice": ""})
    assert response.status_code == 302
    assert response.url == reverse(
        "core:list-fighter-advancement-type",
        args=[fighter_with_xp.list.id, fighter_with_xp.id],
    )


@pytest.mark.django_db
def test_advancement_clean_validation(fighter_with_xp):
    """Test advancement model validation."""
    # Test stat advancement without stat selected
    advancement = ListFighterAdvancement(
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        xp_cost=10,
        cost_increase=5,
    )

    with pytest.raises(ValidationError) as excinfo:
        advancement.clean()
    assert "Stat advancement requires a stat to be selected" in str(excinfo.value)

    # Test skill advancement without skill selected
    advancement = ListFighterAdvancement(
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        xp_cost=10,
        cost_increase=5,
    )

    with pytest.raises(ValidationError) as excinfo:
        advancement.clean()
    assert "Skill advancement requires a skill to be selected" in str(excinfo.value)
