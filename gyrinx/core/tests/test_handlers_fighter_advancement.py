"""
Tests for fighter advancement handler.

These tests directly test the handle_fighter_advancement function in
gyrinx.core.handlers.fighter.advancement, ensuring that business logic works
correctly without involving HTTP machinery.
"""

import uuid

import pytest
from django.core.exceptions import ValidationError

from gyrinx.content.models import (
    ContentAdvancementAssignment,
    ContentAdvancementEquipment,
)
from gyrinx.core.handlers.fighter import (
    handle_fighter_advancement,
    handle_fighter_advancement_deletion,
)
from gyrinx.core.models.action import ListActionType
from gyrinx.core.models.campaign import CampaignAction
from gyrinx.core.models.list import (
    ListFighter,
    ListFighterAdvancement,
    ListFighterEquipmentAssignment,
)
from gyrinx.models import FighterCategoryChoices


# --- Fixtures ---


@pytest.fixture
def content_skill(make_content_skill):
    """Create a ContentSkill for testing."""
    return make_content_skill("Iron Jaw", category="Combat")


@pytest.fixture
def content_skill_for_promotion(make_content_skill):
    """Create a ContentSkill for promotion testing."""
    return make_content_skill("Mentor", category="Leadership")


@pytest.fixture
def content_advancement_assignment(make_equipment):
    """Create a ContentAdvancementAssignment for equipment advancement testing."""
    equipment = make_equipment("Plasma Pistol", cost="75")

    # Create advancement equipment first
    advancement_equipment = ContentAdvancementEquipment.objects.create(
        name="Plasma Pistol Advancement",
        xp_cost=8,
        cost_increase=75,
    )

    return ContentAdvancementAssignment.objects.create(
        equipment=equipment,
        advancement=advancement_equipment,
    )


@pytest.fixture
def fighter_with_xp(list_with_campaign, content_fighter, user):
    """Fighter with enough XP for advancement testing."""
    return ListFighter.objects.create(
        list=list_with_campaign,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
        xp_current=100,
        xp_total=100,
    )


@pytest.fixture
def stash_fighter_type(content_house, make_content_fighter):
    """Create a stash fighter type."""
    return make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )


@pytest.fixture
def stash_fighter_with_xp(list_with_campaign, stash_fighter_type, user):
    """Stash fighter with XP for advancement testing."""
    return ListFighter.objects.create(
        list=list_with_campaign,
        owner=user,
        content_fighter=stash_fighter_type,
        name="Stash Fighter",
        xp_current=100,
        xp_total=100,
    )


# --- Core Functionality Tests (1-5) ---


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_advancement_stat_campaign_mode(
    user, fighter_with_xp, settings, feature_flag_enabled
):
    """Test stat advancement in campaign mode creates correct ListAction."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = fighter_with_xp.list
    lst.credits_current = 1000
    lst.rating_current = 500
    lst.save()

    rating_before = lst.rating_current
    cost_increase = 20

    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        xp_cost=10,
        cost_increase=cost_increase,
        advancement_choice="stat_weapon_skill",
        stat_increased="weapon_skill",
    )

    # Verify result (always present regardless of flag)
    assert result is not None
    assert result.advancement is not None
    assert result.cost_increase == cost_increase

    # Verify ListAction based on feature flag
    if feature_flag_enabled:
        assert result.update_action is not None
        assert result.update_action.action_type == ListActionType.UPDATE_FIGHTER
        assert result.update_action.rating_delta == cost_increase
        assert result.update_action.stash_delta == 0
        assert result.update_action.credits_delta == 0
        assert result.update_action.rating_before == rating_before
    else:
        assert result.update_action is None

    # Verify fighter XP deducted (always happens)
    fighter_with_xp.refresh_from_db()
    assert fighter_with_xp.xp_current == 90

    # Verify CampaignAction created (always in campaign mode)
    assert result.campaign_action is not None


@pytest.mark.django_db
def test_handle_fighter_advancement_skill_campaign_mode(
    user, fighter_with_xp, content_skill, settings
):
    """Test skill advancement creates correct ListAction."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    lst = fighter_with_xp.list
    lst.rating_current = 500
    lst.save()

    cost_increase = 15

    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        xp_cost=12,
        cost_increase=cost_increase,
        advancement_choice="skill_primary",
        skill=content_skill,
    )

    assert result is not None
    assert result.update_action.action_type == ListActionType.UPDATE_FIGHTER
    assert result.update_action.rating_delta == cost_increase
    assert "Gained Iron Jaw skill" in result.outcome

    # Verify skill added to fighter
    fighter_with_xp.refresh_from_db()
    assert content_skill in fighter_with_xp.skills.all()


@pytest.mark.django_db
def test_handle_fighter_advancement_equipment_campaign_mode(
    user, fighter_with_xp, content_advancement_assignment, settings
):
    """Test equipment advancement creates both UPDATE_FIGHTER and ADD_EQUIPMENT actions."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    lst = fighter_with_xp.list
    lst.rating_current = 500
    lst.save()

    cost_increase = 75

    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
        xp_cost=8,
        cost_increase=cost_increase,
        advancement_choice="equipment_primary",
        equipment_assignment=content_advancement_assignment,
    )

    assert result is not None

    # Verify UPDATE_FIGHTER action
    assert result.update_action is not None
    assert result.update_action.action_type == ListActionType.UPDATE_FIGHTER
    assert result.update_action.rating_delta == cost_increase

    # Verify ADD_EQUIPMENT action
    assert result.equipment_action is not None
    assert result.equipment_action.action_type == ListActionType.ADD_EQUIPMENT
    assert result.equipment_action.rating_delta == 0  # Cost tracked in UPDATE_FIGHTER
    assert result.equipment_action.stash_delta == 0
    assert result.equipment_action.credits_delta == 0

    # Verify equipment assignment created
    assert result.equipment_assignment is not None


@pytest.mark.django_db
def test_handle_fighter_advancement_other_campaign_mode(
    user, fighter_with_xp, settings
):
    """Test 'other' advancement with free-text description."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    lst = fighter_with_xp.list
    lst.rating_current = 500
    lst.save()

    cost_increase = 10

    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_OTHER,
        xp_cost=5,
        cost_increase=cost_increase,
        advancement_choice="other",
        description="Gained a mysterious power",
    )

    assert result is not None
    assert result.update_action.rating_delta == cost_increase
    assert "Gained a mysterious power" in result.outcome


@pytest.mark.django_db
@pytest.mark.parametrize("feature_flag_enabled", [True, False])
def test_handle_fighter_advancement_list_building_mode(
    user, make_list, content_fighter, content_skill, settings, feature_flag_enabled
):
    """Test advancement in list building mode (no CampaignAction created)."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = feature_flag_enabled

    lst = make_list("List Building List")
    lst.rating_current = 500
    lst.save()

    fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=content_fighter,
        name="Test Fighter",
        xp_current=100,
        xp_total=100,
    )

    result = handle_fighter_advancement(
        user=user,
        fighter=fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        xp_cost=10,
        cost_increase=15,
        advancement_choice="skill_primary",
        skill=content_skill,
    )

    assert result is not None

    # ListAction based on feature flag
    if feature_flag_enabled:
        assert result.update_action is not None
    else:
        assert result.update_action is None

    # No CampaignAction in list building mode (regardless of flag)
    assert result.campaign_action is None


# --- ListAction Verification Tests (6-9) ---


@pytest.mark.django_db
def test_handle_fighter_advancement_rating_delta_regular_fighter(
    user, fighter_with_xp, settings
):
    """Test regular fighter: rating_delta = cost_increase, stash_delta = 0."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    lst = fighter_with_xp.list
    lst.rating_current = 500
    lst.stash_current = 100
    lst.save()

    cost_increase = 25

    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        xp_cost=10,
        cost_increase=cost_increase,
        advancement_choice="stat_strength",
        stat_increased="strength",
    )

    assert result.update_action.rating_delta == cost_increase
    assert result.update_action.stash_delta == 0


@pytest.mark.django_db
def test_handle_fighter_advancement_stash_fighter_rejected(user, stash_fighter_with_xp):
    """Test stash fighters cannot receive advancements."""
    with pytest.raises(ValidationError) as excinfo:
        handle_fighter_advancement(
            user=user,
            fighter=stash_fighter_with_xp,
            advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
            xp_cost=10,
            cost_increase=25,
            advancement_choice="stat_strength",
            stat_increased="strength",
        )

    assert "Stash fighters cannot receive advancements" in str(excinfo.value)
    assert stash_fighter_with_xp.name in str(excinfo.value)


@pytest.mark.django_db
def test_handle_fighter_advancement_before_values_captured(
    user, fighter_with_xp, settings
):
    """Test correct rating_before, stash_before, credits_before values."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    lst = fighter_with_xp.list
    lst.rating_current = 500
    lst.stash_current = 100
    lst.credits_current = 1000
    lst.save()

    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        xp_cost=10,
        cost_increase=20,
        advancement_choice="stat_toughness",
        stat_increased="toughness",
    )

    assert result.update_action.rating_before == 500
    assert result.update_action.stash_before == 100
    assert result.update_action.credits_before == 1000


@pytest.mark.django_db
def test_handle_fighter_advancement_credits_delta_zero(user, fighter_with_xp, settings):
    """Test advancements cost XP not credits, so credits_delta = 0."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    lst = fighter_with_xp.list
    lst.credits_current = 1000
    lst.save()

    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        xp_cost=10,
        cost_increase=20,
        advancement_choice="stat_wounds",
        stat_increased="wounds",
    )

    assert result.update_action.credits_delta == 0

    # Credits unchanged
    lst.refresh_from_db()
    assert lst.credits_current == 1000


# --- Validation & Error Handling Tests (10-11) ---


@pytest.mark.django_db
def test_handle_fighter_advancement_insufficient_xp(user, fighter_with_xp):
    """Test raises ValidationError when XP insufficient."""
    fighter_with_xp.xp_current = 5
    fighter_with_xp.save()

    with pytest.raises(ValidationError) as excinfo:
        handle_fighter_advancement(
            user=user,
            fighter=fighter_with_xp,
            advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
            xp_cost=10,
            cost_increase=20,
            advancement_choice="stat_weapon_skill",
            stat_increased="weapon_skill",
        )

    assert "insufficient XP" in str(excinfo.value)
    assert "Required: 10" in str(excinfo.value)
    assert "Available: 5" in str(excinfo.value)


@pytest.mark.django_db
def test_handle_fighter_advancement_campaign_action_not_found(user, fighter_with_xp):
    """Test raises ValidationError for invalid campaign_action_id."""
    fake_campaign_action_id = uuid.uuid4()

    with pytest.raises(ValidationError) as excinfo:
        handle_fighter_advancement(
            user=user,
            fighter=fighter_with_xp,
            advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
            xp_cost=10,
            cost_increase=20,
            advancement_choice="stat_weapon_skill",
            stat_increased="weapon_skill",
            campaign_action_id=fake_campaign_action_id,
        )

    assert "not found" in str(excinfo.value)


# --- CampaignAction Integration Tests (12-14) ---


@pytest.mark.django_db
def test_handle_fighter_advancement_creates_campaign_action(user, fighter_with_xp):
    """Test CampaignAction created in campaign mode."""
    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        xp_cost=10,
        cost_increase=20,
        advancement_choice="stat_weapon_skill",
        stat_increased="weapon_skill",
    )

    assert result.campaign_action is not None
    assert result.campaign_action.campaign == fighter_with_xp.list.campaign
    assert result.campaign_action.list == fighter_with_xp.list
    assert "XP" in result.campaign_action.description


@pytest.mark.django_db
def test_handle_fighter_advancement_links_existing_campaign_action(
    user, fighter_with_xp
):
    """Test links to provided campaign_action_id."""
    lst = fighter_with_xp.list

    # Create existing campaign action
    existing_action = CampaignAction.objects.create(
        user=user,
        owner=user,
        campaign=lst.campaign,
        list=lst,
        description="Pre-existing action",
    )

    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        xp_cost=10,
        cost_increase=20,
        advancement_choice="stat_weapon_skill",
        stat_increased="weapon_skill",
        campaign_action_id=existing_action.id,
    )

    assert result.campaign_action == existing_action

    # Verify outcome was updated
    existing_action.refresh_from_db()
    assert "Improved" in existing_action.outcome


@pytest.mark.django_db
def test_handle_fighter_advancement_idempotent_with_campaign_action(
    user, fighter_with_xp
):
    """Test returns None if advancement already applied for campaign_action_id."""
    lst = fighter_with_xp.list

    # Create campaign action
    existing_action = CampaignAction.objects.create(
        user=user,
        owner=user,
        campaign=lst.campaign,
        list=lst,
        description="Pre-existing action",
    )

    # First call - should succeed
    result1 = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        xp_cost=10,
        cost_increase=20,
        advancement_choice="stat_weapon_skill",
        stat_increased="weapon_skill",
        campaign_action_id=existing_action.id,
    )
    assert result1 is not None

    # Second call with same campaign_action_id - should return None (idempotent)
    result2 = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        xp_cost=10,
        cost_increase=20,
        advancement_choice="stat_weapon_skill",
        stat_increased="weapon_skill",
        campaign_action_id=existing_action.id,
    )
    assert result2 is None

    # Only one advancement should exist
    assert (
        ListFighterAdvancement.objects.filter(
            campaign_action_id=existing_action.id
        ).count()
        == 1
    )


# --- Edge Case Tests (15-16) ---


@pytest.mark.django_db
def test_handle_fighter_advancement_child_fighter_stash_linked(
    user,
    list_with_campaign,
    content_house,
    make_content_fighter,
    make_equipment,
    content_equipment_categories,
    settings,
):
    """Test child fighter (vehicle/beast) linked to stash parent uses stash_delta."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    from gyrinx.content.models import ContentEquipmentFighterProfile

    lst = list_with_campaign
    lst.rating_current = 500
    lst.stash_current = 100
    lst.save()

    # Create stash fighter type
    stash_type = make_content_fighter(
        type="Stash",
        category=FighterCategoryChoices.CREW,
        house=content_house,
        base_cost=0,
        is_stash=True,
    )

    # Create stash fighter
    stash_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=stash_type,
        name="Stash Fighter",
    )

    # Create vehicle equipment with fighter profile
    vehicle_equipment = make_equipment("Test Vehicle", cost="200")
    vehicle_fighter_type = make_content_fighter(
        type="Vehicle",
        category=FighterCategoryChoices.VEHICLE,
        house=content_house,
        base_cost=200,
    )
    ContentEquipmentFighterProfile.objects.create(
        equipment=vehicle_equipment,
        content_fighter=vehicle_fighter_type,
    )

    # Create equipment assignment on stash fighter
    equipment_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=stash_fighter,
        content_equipment=vehicle_equipment,
    )

    # Create child fighter linked to equipment on stash
    child_fighter = ListFighter.objects.create(
        list=lst,
        owner=user,
        content_fighter=vehicle_fighter_type,
        name="Child Vehicle",
        xp_current=50,
        xp_total=50,
    )
    child_fighter.source_assignment.add(equipment_assignment)

    cost_increase = 30

    result = handle_fighter_advancement(
        user=user,
        fighter=child_fighter,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        xp_cost=10,
        cost_increase=cost_increase,
        advancement_choice="stat_toughness",
        stat_increased="toughness",
    )

    # Child fighter linked to stash should use stash_delta
    assert result.update_action.rating_delta == 0
    assert result.update_action.stash_delta == cost_increase


@pytest.mark.django_db
def test_handle_fighter_advancement_skill_with_promotion(
    user, fighter_with_xp, content_skill_for_promotion
):
    """Test promotion outcomes include 'and was promoted'."""
    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        xp_cost=15,
        cost_increase=25,
        advancement_choice="skill_promote_specialist",
        skill=content_skill_for_promotion,
    )

    assert result is not None
    assert "and was promoted" in result.outcome
    assert "Gained Mentor skill" in result.outcome


# --- Advancement Deletion Tests ---


@pytest.mark.django_db
def test_handle_fighter_advancement_deletion_stat_basic(
    user, fighter_with_xp, settings
):
    """Test deleting a stat advancement restores XP and creates ListAction."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    lst = fighter_with_xp.list
    lst.rating_current = 500
    lst.save()

    xp_before = fighter_with_xp.xp_current
    xp_cost = 10
    cost_increase = 20

    # Create advancement
    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        xp_cost=xp_cost,
        cost_increase=cost_increase,
        advancement_choice="stat_weapon_skill",
        stat_increased="weapon_skill",
    )

    fighter_with_xp.refresh_from_db()
    assert fighter_with_xp.xp_current == xp_before - xp_cost

    # Delete advancement
    delete_result = handle_fighter_advancement_deletion(
        user=user,
        fighter=fighter_with_xp,
        advancement=result.advancement,
    )

    # Verify result
    assert delete_result.xp_restored == xp_cost
    assert delete_result.cost_decrease == cost_increase
    assert delete_result.list_action is not None
    assert delete_result.list_action.rating_delta == -cost_increase

    # Verify XP restored
    fighter_with_xp.refresh_from_db()
    assert fighter_with_xp.xp_current == xp_before

    # Verify advancement archived
    result.advancement.refresh_from_db()
    assert result.advancement.archived is True


@pytest.mark.django_db
def test_handle_fighter_advancement_deletion_skill_basic(
    user, fighter_with_xp, content_skill, settings
):
    """Test deleting a skill advancement removes the skill."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    lst = fighter_with_xp.list
    lst.rating_current = 500
    lst.save()

    # Create skill advancement
    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        xp_cost=12,
        cost_increase=15,
        advancement_choice="skill_primary",
        skill=content_skill,
    )

    # Verify skill added
    fighter_with_xp.refresh_from_db()
    assert content_skill in fighter_with_xp.skills.all()

    # Delete advancement
    delete_result = handle_fighter_advancement_deletion(
        user=user,
        fighter=fighter_with_xp,
        advancement=result.advancement,
    )

    # Verify skill removed
    fighter_with_xp.refresh_from_db()
    assert content_skill not in fighter_with_xp.skills.all()
    assert len(delete_result.warnings) == 0


@pytest.mark.django_db
def test_handle_fighter_advancement_deletion_promotion_reversal(
    user, fighter_with_xp, content_skill, settings
):
    """Test deleting a promotion advancement clears category_override."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    lst = fighter_with_xp.list
    lst.rating_current = 500
    lst.save()

    # Create promotion advancement
    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        xp_cost=15,
        cost_increase=25,
        advancement_choice="skill_promote_specialist",
        skill=content_skill,
    )

    # Verify promoted to specialist
    fighter_with_xp.refresh_from_db()
    assert fighter_with_xp.category_override == FighterCategoryChoices.SPECIALIST

    # Delete advancement
    handle_fighter_advancement_deletion(
        user=user,
        fighter=fighter_with_xp,
        advancement=result.advancement,
    )

    # Verify category_override cleared
    fighter_with_xp.refresh_from_db()
    assert fighter_with_xp.category_override is None


@pytest.mark.django_db
def test_handle_fighter_advancement_deletion_equipment_warns(
    user, fighter_with_xp, content_advancement_assignment, settings
):
    """Test deleting equipment advancement warns about manual removal."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    lst = fighter_with_xp.list
    lst.rating_current = 500
    lst.save()

    # Create equipment advancement
    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_EQUIPMENT,
        xp_cost=8,
        cost_increase=75,
        advancement_choice="equipment_primary",
        equipment_assignment=content_advancement_assignment,
    )

    # Delete advancement
    delete_result = handle_fighter_advancement_deletion(
        user=user,
        fighter=fighter_with_xp,
        advancement=result.advancement,
    )

    # Verify warning about equipment
    assert len(delete_result.warnings) == 1
    assert "manually" in delete_result.warnings[0]


@pytest.mark.django_db
def test_handle_fighter_advancement_deletion_wrong_fighter(
    user, fighter_with_xp, content_fighter, list_with_campaign
):
    """Test deleting advancement from wrong fighter raises ValidationError."""
    # Create advancement on fighter_with_xp
    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        xp_cost=10,
        cost_increase=20,
        advancement_choice="stat_weapon_skill",
        stat_increased="weapon_skill",
    )

    # Create different fighter
    other_fighter = ListFighter.objects.create(
        list=list_with_campaign,
        owner=user,
        content_fighter=content_fighter,
        name="Other Fighter",
        xp_current=100,
    )

    # Try to delete from wrong fighter
    with pytest.raises(ValidationError) as excinfo:
        handle_fighter_advancement_deletion(
            user=user,
            fighter=other_fighter,
            advancement=result.advancement,
        )

    assert "does not belong" in str(excinfo.value)


@pytest.mark.django_db
def test_handle_fighter_advancement_deletion_already_archived(user, fighter_with_xp):
    """Test deleting already archived advancement raises ValidationError."""
    # Create advancement
    result = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_STAT,
        xp_cost=10,
        cost_increase=20,
        advancement_choice="stat_weapon_skill",
        stat_increased="weapon_skill",
    )

    # Archive it manually
    result.advancement.archive()

    # Try to delete again
    with pytest.raises(ValidationError) as excinfo:
        handle_fighter_advancement_deletion(
            user=user,
            fighter=fighter_with_xp,
            advancement=result.advancement,
        )

    assert "already archived" in str(excinfo.value)


@pytest.mark.django_db
def test_handle_fighter_advancement_deletion_multiple_promotions(
    user, fighter_with_xp, make_content_skill, settings
):
    """Test deleting one promotion when another remains keeps correct category."""
    settings.FEATURE_LIST_ACTION_CREATE_INITIAL = True

    lst = fighter_with_xp.list
    lst.rating_current = 500
    lst.save()

    skill1 = make_content_skill("Skill 1", category="Combat")
    skill2 = make_content_skill("Skill 2", category="Combat")

    # Create first promotion to specialist
    result1 = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        xp_cost=15,
        cost_increase=25,
        advancement_choice="skill_promote_specialist",
        skill=skill1,
    )

    fighter_with_xp.refresh_from_db()
    assert fighter_with_xp.category_override == FighterCategoryChoices.SPECIALIST

    # Create second promotion to champion
    result2 = handle_fighter_advancement(
        user=user,
        fighter=fighter_with_xp,
        advancement_type=ListFighterAdvancement.ADVANCEMENT_SKILL,
        xp_cost=20,
        cost_increase=40,
        advancement_choice="skill_promote_champion",
        skill=skill2,
    )

    fighter_with_xp.refresh_from_db()
    assert fighter_with_xp.category_override == FighterCategoryChoices.CHAMPION

    # Delete champion promotion
    handle_fighter_advancement_deletion(
        user=user,
        fighter=fighter_with_xp,
        advancement=result2.advancement,
    )

    # Should revert to specialist (still have that promotion)
    fighter_with_xp.refresh_from_db()
    assert fighter_with_xp.category_override == FighterCategoryChoices.SPECIALIST

    # Delete specialist promotion
    handle_fighter_advancement_deletion(
        user=user,
        fighter=fighter_with_xp,
        advancement=result1.advancement,
    )

    # Should have no override
    fighter_with_xp.refresh_from_db()
    assert fighter_with_xp.category_override is None
