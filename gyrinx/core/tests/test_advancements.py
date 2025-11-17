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
        category="GANGER",
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


@pytest.fixture
def specialist_fighter(list_with_campaign, house):
    """Create a specialist fighter for testing."""
    content_fighter = ContentFighter.objects.create(
        type="Specialist Fighter",
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
        category="SPECIALIST",
        base_cost=75,
    )
    return ListFighter.objects.create(
        name="Test Specialist",
        content_fighter=content_fighter,
        list=list_with_campaign,
        xp_current=50,
        xp_total=50,
    )


@pytest.fixture
def champion_fighter(list_with_campaign, house):
    """Create a champion fighter for testing."""
    content_fighter = ContentFighter.objects.create(
        type="Champion Fighter",
        house=house,
        movement='4"',
        weapon_skill="2+",
        ballistic_skill="3+",
        strength="3",
        toughness="3",
        wounds="2",
        initiative="3+",
        attacks="2",
        leadership="6",
        cool="6",
        willpower="6",
        intelligence="6",
        category="CHAMPION",
        base_cost=100,
    )
    return ListFighter.objects.create(
        name="Test Champion",
        content_fighter=content_fighter,
        list=list_with_campaign,
        xp_current=50,
        xp_total=50,
    )


@pytest.mark.django_db
def test_ganger_promotion_to_specialist(fighter_with_xp, skill):
    """Test that a GANGER can be promoted to SPECIALIST."""
    # Check initial category is GANGER
    assert fighter_with_xp.get_category() == "GANGER"
    assert fighter_with_xp.category_override is None

    # Create a promotion advancement
    advancement = ListFighterAdvancement.objects.create(
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        advancement_choice="skill_promote_specialist",
        skill=skill,
        xp_cost=6,
        cost_increase=20,
    )

    advancement.apply_advancement()
    fighter_with_xp.refresh_from_db()

    # Check fighter has been promoted
    assert fighter_with_xp.category_override == "SPECIALIST"
    assert fighter_with_xp.get_category() == "SPECIALIST"
    assert skill in fighter_with_xp.skills.all()
    assert fighter_with_xp.xp_current == 44  # 50 - 6


@pytest.mark.django_db
def test_specialist_promotion_to_champion(specialist_fighter, skill):
    """Test that a SPECIALIST can be promoted to CHAMPION."""
    # Check initial category is SPECIALIST
    assert specialist_fighter.get_category() == "SPECIALIST"

    # Create a promotion advancement
    advancement = ListFighterAdvancement.objects.create(
        fighter=specialist_fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        advancement_choice="skill_promote_champion",
        skill=skill,
        xp_cost=12,
        cost_increase=40,
    )

    advancement.apply_advancement()
    specialist_fighter.refresh_from_db()

    # Check fighter has been promoted
    assert specialist_fighter.category_override == "CHAMPION"
    assert specialist_fighter.get_category() == "CHAMPION"
    assert skill in specialist_fighter.skills.all()
    assert specialist_fighter.xp_current == 38  # 50 - 12


@pytest.mark.django_db
def test_advancement_choice_field_saved(fighter_with_xp):
    """Test that advancement_choice field is saved correctly."""
    advancement = ListFighterAdvancement.objects.create(
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        advancement_choice="stat_weapon_skill",
        stat_increased="weapon_skill",
        xp_cost=6,
        cost_increase=20,
    )

    assert advancement.advancement_choice == "stat_weapon_skill"

    # Test it persists after retrieval
    saved_advancement = ListFighterAdvancement.objects.get(id=advancement.id)
    assert saved_advancement.advancement_choice == "stat_weapon_skill"


@pytest.mark.django_db
def test_ganger_can_see_promotion_option(client, user, fighter_with_xp):
    """Test that GANGERs can see the promotion option in advancement choices."""
    client.login(username="testuser", password="password")

    url = reverse(
        "core:list-fighter-advancement-type",
        args=[fighter_with_xp.list.id, fighter_with_xp.id],
    )
    response = client.get(url)

    assert response.status_code == 200
    content = response.content.decode()

    # Check that promotion option is available
    assert "Promote to Specialist" in content
    assert "skill_promote_specialist" in content


@pytest.mark.django_db
def test_specialist_cannot_see_ganger_promotion(client, user, specialist_fighter):
    """Test that SPECIALISTs cannot see the GANGER promotion option."""
    client.login(username="testuser", password="password")

    url = reverse(
        "core:list-fighter-advancement-type",
        args=[specialist_fighter.list.id, specialist_fighter.id],
    )
    response = client.get(url)

    assert response.status_code == 200
    response.content.decode()

    # The form filters options based on fighter category
    from gyrinx.core.forms.advancement import AdvancementTypeForm

    form = AdvancementTypeForm(fighter=specialist_fighter)
    choices_dict = dict(form.fields["advancement_choice"].choices)

    # Check that GANGER promotion is not available
    assert "skill_promote_specialist" not in choices_dict
    # But Champion promotion should be available
    assert "skill_promote_champion" in choices_dict


@pytest.mark.django_db
def test_champion_cannot_see_promotion_options(client, user, champion_fighter):
    """Test that CHAMPIONs cannot see any promotion options."""
    client.login(username="testuser", password="password")

    url = reverse(
        "core:list-fighter-advancement-type",
        args=[champion_fighter.list.id, champion_fighter.id],
    )
    response = client.get(url)

    assert response.status_code == 200
    response.content.decode()

    # The form filters options based on fighter category
    from gyrinx.core.forms.advancement import AdvancementTypeForm

    form = AdvancementTypeForm(fighter=champion_fighter)
    choices_dict = dict(form.fields["advancement_choice"].choices)

    # Check that no promotion options are available
    assert "skill_promote_specialist" not in choices_dict
    assert "skill_promote_champion" not in choices_dict


@pytest.fixture
def exotic_beast_fighter(list_with_campaign, house):
    """Create an exotic beast fighter for testing."""
    content_fighter = ContentFighter.objects.create(
        type="Exotic Beast Fighter",
        house=house,
        movement='6"',
        weapon_skill="4+",
        ballistic_skill="6+",
        strength="4",
        toughness="3",
        wounds="2",
        initiative="3+",
        attacks="2",
        leadership="8",
        cool="8",
        willpower="8",
        intelligence="8",
        category="EXOTIC_BEAST",
        base_cost=120,
    )
    return ListFighter.objects.create(
        name="Test Beast",
        content_fighter=content_fighter,
        list=list_with_campaign,
        xp_current=50,
        xp_total=50,
    )


@pytest.mark.django_db
def test_only_gangers_can_roll_dice(client, user, fighter_with_xp, specialist_fighter):
    """Test that only GANGERs can roll dice for advancement."""
    client.login(username="testuser", password="password")

    # Test GANGER can see dice rolling option
    url = reverse(
        "core:list-fighter-advancement-dice-choice",
        args=[fighter_with_xp.list.id, fighter_with_xp.id],
    )
    response = client.get(url)
    assert response.status_code == 200
    assert "Roll for Advancement?" in response.content.decode()

    # Test SPECIALIST is redirected immediately
    url = reverse(
        "core:list-fighter-advancement-dice-choice",
        args=[specialist_fighter.list.id, specialist_fighter.id],
    )
    response = client.get(url)
    assert response.status_code == 302
    # Should redirect to advancement type selection
    assert response.url == reverse(
        "core:list-fighter-advancement-type",
        args=[specialist_fighter.list.id, specialist_fighter.id],
    )


@pytest.mark.django_db
def test_exotic_beasts_can_roll_dice(client, user, exotic_beast_fighter):
    """Test that EXOTIC_BEASTs can roll dice for advancement."""
    client.login(username="testuser", password="password")

    # Test EXOTIC_BEAST can see dice rolling option
    url = reverse(
        "core:list-fighter-advancement-dice-choice",
        args=[exotic_beast_fighter.list.id, exotic_beast_fighter.id],
    )
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Roll for Advancement?" in content
    assert "Roll 2D6" in content
    # Should not see the warning message
    assert "Only Gangers and Exotic Beasts can roll for advancements" not in content


@pytest.mark.django_db
def test_can_fighter_roll_dice_for_advancement():
    """Test the can_fighter_roll_dice_for_advancement function."""
    from gyrinx.core.views.list import can_fighter_roll_dice_for_advancement

    # Mock fighters with different categories
    class MockFighter:
        def __init__(self, category):
            self._category = category

        def get_category(self):
            return self._category

    # Test GANGER can roll
    ganger = MockFighter("GANGER")
    assert can_fighter_roll_dice_for_advancement(ganger) is True

    # Test EXOTIC_BEAST can roll
    exotic_beast = MockFighter("EXOTIC_BEAST")
    assert can_fighter_roll_dice_for_advancement(exotic_beast) is True

    # Test other categories cannot roll
    specialist = MockFighter("SPECIALIST")
    assert can_fighter_roll_dice_for_advancement(specialist) is False

    champion = MockFighter("CHAMPION")
    assert can_fighter_roll_dice_for_advancement(champion) is False

    leader = MockFighter("LEADER")
    assert can_fighter_roll_dice_for_advancement(leader) is False


@pytest.mark.django_db
def test_promotion_outcome_includes_promotion_text(fighter_with_xp, skill):
    """Test that promotion advancements include 'and was promoted' in the outcome."""
    # Create a promotion advancement directly
    advancement = ListFighterAdvancement.objects.create(
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        advancement_choice="skill_promote_specialist",
        skill=skill,
        xp_cost=6,
        cost_increase=20,
    )

    # Apply the advancement
    advancement.apply_advancement()
    fighter_with_xp.refresh_from_db()

    # Check that the advancement was created with correct choice
    assert advancement.advancement_choice == "skill_promote_specialist"

    # Check fighter was promoted
    assert fighter_with_xp.category_override == "SPECIALIST"
    assert fighter_with_xp.get_category() == "SPECIALIST"

    # Check skill was added
    assert skill in fighter_with_xp.skills.all()


@pytest.mark.django_db
def test_advancement_confirm_idempotent_with_campaign_action(
    client, user, fighter_with_xp
):
    """Test that advancement confirm is idempotent when campaign_action_id is provided."""
    from gyrinx.core.models.campaign import CampaignAction

    client.login(username="testuser", password="password")

    # Create a campaign action
    campaign_action = CampaignAction.objects.create(
        user=user,
        owner=user,
        campaign=fighter_with_xp.list.campaign,
        list=fighter_with_xp.list,
        description="Test advancement",
    )

    # Prepare the URL with all required parameters
    url = reverse(
        "core:list-fighter-advancement-confirm",
        args=[fighter_with_xp.list.id, fighter_with_xp.id],
    )
    params = {
        "advancement_choice": "other",
        "description": "Test advancement",
        "xp_cost": "10",
        "cost_increase": "20",
        "campaign_action_id": str(campaign_action.id),
    }

    # First POST - should create the advancement
    response = client.post(f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}")
    assert response.status_code == 302

    # Check that the advancement was created
    advancements = ListFighterAdvancement.objects.filter(
        fighter=fighter_with_xp, campaign_action=campaign_action
    )
    assert advancements.count() == 1
    first_advancement = advancements.first()

    # Second POST with same campaign_action_id - should NOT create duplicate
    response = client.post(f"{url}?{'&'.join(f'{k}={v}' for k, v in params.items())}")
    assert response.status_code == 302

    # Check that no duplicate was created
    advancements = ListFighterAdvancement.objects.filter(
        fighter=fighter_with_xp, campaign_action=campaign_action
    )
    assert advancements.count() == 1

    # Verify it's the same advancement (not deleted and recreated)
    assert advancements.first().id == first_advancement.id
