import pytest
from django.contrib.auth.models import User

from gyrinx.content.models import (
    ContentFighter,
    ContentHouse,
    ContentInjury,
    ContentInjuryDefaultOutcome,
    ContentModFighterStat,
)
from gyrinx.core.models.campaign import Campaign
from gyrinx.core.models.list import List, ListFighter, ListFighterInjury
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_multiple_injury_modifiers_stack():
    """Test that multiple injuries with stat modifiers all apply correctly."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
        # Base stats
        movement="4",
        weapon_skill="4+",
        ballistic_skill="4+",
        strength="3",
        toughness="3",
        wounds="1",
        initiative="4+",
        attacks="1",
        leadership="7+",
        cool="7+",
        willpower="7+",
        intelligence="7+",
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

    # Create injury modifiers
    mod_bs_minus_1 = ContentModFighterStat.objects.create(
        stat="ballistic_skill",
        mode="worsen",
        value="1",
    )

    mod_ws_minus_1 = ContentModFighterStat.objects.create(
        stat="weapon_skill",
        mode="worsen",
        value="1",
    )

    mod_move_minus_1 = ContentModFighterStat.objects.create(
        stat="movement",
        mode="worsen",
        value="1",
    )

    mod_leadership_minus_1 = ContentModFighterStat.objects.create(
        stat="leadership",
        mode="worsen",
        value="1",
    )

    mod_cool_minus_1 = ContentModFighterStat.objects.create(
        stat="cool",
        mode="worsen",
        value="1",
    )

    # Create injuries with modifiers
    injury1 = ContentInjury.objects.create(
        name="Eye Injury",
        description="Recovery, -1 Ballistic Skill",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )
    injury1.modifiers.add(mod_bs_minus_1)

    injury2 = ContentInjury.objects.create(
        name="Hand Injury",
        description="Recovery, -1 Weapon Skill",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )
    injury2.modifiers.add(mod_ws_minus_1)

    injury3 = ContentInjury.objects.create(
        name="Hobbled",
        description='Permanent, -1" Movement',
        phase=ContentInjuryDefaultOutcome.ACTIVE,
    )
    injury3.modifiers.add(mod_move_minus_1)

    injury4 = ContentInjury.objects.create(
        name="Humiliated",
        description="Convalescence, -1 Leadership, -1 Cool",
        phase=ContentInjuryDefaultOutcome.CONVALESCENCE,
    )
    injury4.modifiers.add(mod_leadership_minus_1)
    injury4.modifiers.add(mod_cool_minus_1)

    # Check initial stats
    statline = fighter.statline
    stat_dict = {stat.field_name: stat.value for stat in statline}

    assert stat_dict["movement"] == "4"
    assert stat_dict["weapon_skill"] == "4+"
    assert stat_dict["ballistic_skill"] == "4+"
    assert stat_dict["leadership"] == "7+"
    assert stat_dict["cool"] == "7+"

    # Apply first injury
    ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury1,
        owner=user,
    )

    # Refresh fighter instance to get updated relationships
    fighter.refresh_from_db()

    # Force recalculation by clearing cached properties
    if hasattr(fighter, "_mods"):
        del fighter._mods
    if hasattr(fighter, "statline"):
        del fighter.statline

    statline = fighter.statline
    stat_dict = {stat.field_name: stat.value for stat in statline}

    # BS should be worsened by 1
    assert stat_dict["ballistic_skill"] == "5+"
    assert stat_dict["weapon_skill"] == "4+"  # unchanged

    # Apply second injury
    ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury2,
        owner=user,
    )

    # Refresh fighter instance
    fighter.refresh_from_db()

    # Force recalculation
    if hasattr(fighter, "_mods"):
        del fighter._mods
    if hasattr(fighter, "statline"):
        del fighter.statline

    statline = fighter.statline
    stat_dict = {stat.field_name: stat.value for stat in statline}

    # Both BS and WS should be worsened
    assert stat_dict["ballistic_skill"] == "5+"
    assert stat_dict["weapon_skill"] == "5+"

    # Apply third injury
    ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury3,
        owner=user,
    )

    # Refresh fighter instance
    fighter.refresh_from_db()

    # Force recalculation
    if hasattr(fighter, "_mods"):
        del fighter._mods
    if hasattr(fighter, "statline"):
        del fighter.statline

    statline = fighter.statline
    stat_dict = {stat.field_name: stat.value for stat in statline}

    # Movement should be reduced
    assert stat_dict["movement"] == '3"'
    assert stat_dict["ballistic_skill"] == "5+"
    assert stat_dict["weapon_skill"] == "5+"

    # Apply fourth injury (with multiple modifiers)
    ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury4,
        owner=user,
    )

    # Refresh fighter instance
    fighter.refresh_from_db()

    # Force recalculation
    if hasattr(fighter, "_mods"):
        del fighter._mods
    if hasattr(fighter, "statline"):
        del fighter.statline

    statline = fighter.statline
    stat_dict = {stat.field_name: stat.value for stat in statline}

    # All modifiers should be applied
    assert stat_dict["movement"] == '3"'
    assert stat_dict["ballistic_skill"] == "5+"
    assert stat_dict["weapon_skill"] == "5+"
    assert stat_dict["leadership"] == "8+"
    assert stat_dict["cool"] == "8+"

    # Also check that modded flags are set correctly
    stat_modded = {stat.field_name: stat.modded for stat in statline}
    assert stat_modded["movement"] is True
    assert stat_modded["ballistic_skill"] is True
    assert stat_modded["weapon_skill"] is True
    assert stat_modded["leadership"] is True
    assert stat_modded["cool"] is True
    assert stat_modded["strength"] is False  # unchanged
    assert stat_modded["toughness"] is False  # unchanged


@pytest.mark.django_db
def test_injury_modifiers_only_apply_in_campaign_mode():
    """Test that injury modifiers only apply when list is in campaign mode."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
        ballistic_skill="4+",
    )

    # Create list in LIST_BUILDING mode
    lst = List.objects.create(
        name="Test List",
        content_house=house,
        owner=user,
        status=List.LIST_BUILDING,  # Not in campaign mode
    )

    fighter = ListFighter.objects.create(
        name="Test Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
    )

    # Create injury with modifier
    mod_bs_minus_1 = ContentModFighterStat.objects.create(
        stat="ballistic_skill",
        mode="worsen",
        value="1",
    )

    injury = ContentInjury.objects.create(
        name="Eye Injury",
        description="Recovery, -1 Ballistic Skill",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )
    injury.modifiers.add(mod_bs_minus_1)

    # Try to add injury (should fail validation)
    from django.core.exceptions import ValidationError

    with pytest.raises(ValidationError):
        injury_assignment = ListFighterInjury(
            fighter=fighter,
            injury=injury,
            owner=user,
        )
        injury_assignment.full_clean()  # This will trigger validation

    # Even if we bypass validation and create the injury, modifiers shouldn't apply
    injury_assignment = ListFighterInjury(
        fighter=fighter,
        injury=injury,
        owner=user,
    )
    injury_assignment.save(force_insert=True)  # Bypass validation

    # Check that modifier is NOT applied in list building mode
    statline = fighter.statline
    stat_dict = {stat.field_name: stat.value for stat in statline}

    assert stat_dict["ballistic_skill"] == "4+"  # unchanged


@pytest.mark.django_db
def test_injury_modifiers_removed_when_injury_removed():
    """Test that modifiers are removed when injuries are removed."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")

    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=100,
        ballistic_skill="4+",
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

    # Create injury with modifier
    mod_bs_minus_1 = ContentModFighterStat.objects.create(
        stat="ballistic_skill",
        mode="worsen",
        value="1",
    )

    injury = ContentInjury.objects.create(
        name="Eye Injury",
        description="Recovery, -1 Ballistic Skill",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )
    injury.modifiers.add(mod_bs_minus_1)

    # Apply injury
    injury_assignment = ListFighterInjury.objects.create(
        fighter=fighter,
        injury=injury,
        owner=user,
    )

    # Check modifier is applied
    statline = fighter.statline
    stat_dict = {stat.field_name: stat.value for stat in statline}
    assert stat_dict["ballistic_skill"] == "5+"

    # Remove injury
    injury_assignment.delete()

    # Refresh fighter instance
    fighter.refresh_from_db()

    # Force recalculation
    if hasattr(fighter, "_mods"):
        del fighter._mods
    if hasattr(fighter, "statline"):
        del fighter.statline

    # Check modifier is removed
    statline = fighter.statline
    stat_dict = {stat.field_name: stat.value for stat in statline}
    assert stat_dict["ballistic_skill"] == "4+"  # back to original
