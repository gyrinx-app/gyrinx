import pytest

from gyrinx.content.models import (
    ContentFighter,
    ContentStat,
    ContentStatline,
    ContentStatlineStat,
    ContentStatlineType,
    ContentStatlineTypeStat,
)
from gyrinx.core.forms.advancement import AdvancementDiceChoiceForm, AdvancementTypeForm
from gyrinx.core.models import ListFighter
from gyrinx.core.views.fighter.advancements import AdvancementFlowParams


@pytest.mark.django_db
def test_advancement_type_form_with_fighter_statline(
    user, content_house, make_list, make_list_fighter
):
    """Test that advancement choices are correctly generated based on fighter's statline."""
    # Create a custom statline type
    vehicle_type = ContentStatlineType.objects.create(name="Vehicle")

    # Create stat definitions for vehicle
    stats_data = [
        ("movement", "M", "Movement"),
        ("front", "Fr", "Front"),
        ("side", "Sd", "Side"),
        ("rear", "Rr", "Rear"),
        ("hit_points", "HP", "Hit Points"),
        ("handling", "Hnd", "Handling"),
        ("crew", "Sv", "Crew"),
    ]

    type_stats = []
    for field_name, short_name, full_name in stats_data:
        # Create or get the stat definition
        stat_def, _ = ContentStat.objects.get_or_create(
            field_name=field_name,
            defaults={
                "short_name": short_name,
                "full_name": full_name,
            },
        )

        # Create the statline type stat
        stat = ContentStatlineTypeStat.objects.create(
            statline_type=vehicle_type,
            stat=stat_def,
            position=len(type_stats) + 1,
        )
        type_stats.append(stat)

    # Create a fighter with vehicle statline type
    fighter_template = ContentFighter.objects.create(
        type="Test Vehicle",
        house=content_house,
        category="CREW",
    )

    # Create custom statline for the fighter
    custom_statline = ContentStatline.objects.create(
        content_fighter=fighter_template,
        statline_type=vehicle_type,
    )

    # Create stat values
    stat_values = ['8"', "12", "10", "9", "3", "6+", "5+"]
    for stat, value in zip(type_stats, stat_values):
        ContentStatlineStat.objects.create(
            statline=custom_statline,
            statline_type_stat=stat,
            value=value,
        )

    # Create a list and fighter
    lst = make_list("Test List", content_house=content_house)
    list_fighter = ListFighter.objects.create(
        list=lst,
        name="Test Fighter",
        owner=user,
        content_fighter=fighter_template,
    )

    # Create form with the fighter
    form = AdvancementTypeForm(fighter=list_fighter)

    # Get the stat choices from the form
    stat_choices = [
        choice
        for choice in form.fields["advancement_choice"].choices
        if choice[0].startswith("stat_")
    ]

    # Verify that all vehicle stats are present in choices
    expected_stat_choices = [
        ("stat_movement", "Movement"),
        ("stat_front", "Front"),
        ("stat_side", "Side"),
        ("stat_rear", "Rear"),
        ("stat_hit_points", "Hit Points"),
        ("stat_handling", "Handling"),
        ("stat_crew", "Crew"),
    ]

    for expected in expected_stat_choices:
        assert expected in stat_choices, f"Missing expected stat choice: {expected}"

    # Verify no standard fighter stats are present
    standard_stats = [
        "stat_weapon_skill",
        "stat_ballistic_skill",
        "stat_strength",
        "stat_toughness",
        "stat_wounds",
        "stat_initiative",
        "stat_attacks",
        "stat_leadership",
        "stat_cool",
        "stat_willpower",
        "stat_intelligence",
    ]

    stat_choice_keys = [choice[0] for choice in stat_choices]
    for standard_stat in standard_stats:
        assert standard_stat not in stat_choice_keys, (
            f"Standard stat {standard_stat} should not be in vehicle fighter choices"
        )


@pytest.mark.django_db
def test_advancement_type_form_without_fighter():
    """Test that all stat choices are available when no fighter is provided."""
    # Create all standard stat definitions
    standard_stats_data = [
        ("movement", "M", "Movement"),
        ("weapon_skill", "WS", "Weapon Skill"),
        ("ballistic_skill", "BS", "Ballistic Skill"),
        ("strength", "S", "Strength"),
        ("toughness", "T", "Toughness"),
        ("wounds", "W", "Wounds"),
        ("initiative", "I", "Initiative"),
        ("attacks", "A", "Attacks"),
        ("leadership", "Ld", "Leadership"),
        ("cool", "Cl", "Cool"),
        ("willpower", "Wil", "Willpower"),
        ("intelligence", "Int", "Intelligence"),
    ]

    for field_name, short_name, full_name in standard_stats_data:
        ContentStat.objects.get_or_create(
            field_name=field_name,
            defaults={
                "short_name": short_name,
                "full_name": full_name,
            },
        )

    # Create form without fighter
    form = AdvancementTypeForm()

    # Get stat choices
    stat_choices = [
        choice
        for choice in form.fields["advancement_choice"].choices
        if choice[0].startswith("stat_")
    ]

    # Verify all stats are present
    expected_count = ContentStat.objects.count()
    assert len(stat_choices) == expected_count, (
        f"Expected {expected_count} stat choices, got {len(stat_choices)}"
    )


@pytest.mark.django_db
def test_advancement_type_form_skill_choices():
    """Test that skill advancement choices are always present."""
    form = AdvancementTypeForm()

    # Expected skill choices
    expected_skill_choices = [
        ("skill_primary_chosen", "Chosen Primary Skill"),
        ("skill_secondary_chosen", "Chosen Secondary Skill"),
        ("skill_primary_random", "Random Primary Skill"),
        ("skill_secondary_random", "Random Secondary Skill"),
        ("skill_promote_specialist", "Promote to Specialist (Random Primary Skill)"),
        ("skill_promote_champion", "Promote to Champion (Random Primary Skill)"),
        ("skill_any_random", "Random Skill (Any Set)"),
        ("other", "Other"),
    ]

    all_choices = form.fields["advancement_choice"].choices

    for expected in expected_skill_choices:
        assert expected in all_choices, f"Missing expected skill choice: {expected}"


@pytest.mark.django_db
def test_all_stat_choices_method():
    """Test the all_stat_choices class method."""
    # Create some stat definitions
    stats_data = [
        ("weapon_skill", "WS", "Weapon Skill"),
        ("ballistic_skill", "BS", "Ballistic Skill"),
        ("strength", "S", "Strength"),
    ]

    for field_name, short_name, full_name in stats_data:
        ContentStat.objects.get_or_create(
            field_name=field_name,
            defaults={
                "short_name": short_name,
                "full_name": full_name,
            },
        )

    # Get all stat choices
    stat_choices = AdvancementTypeForm.all_stat_choices()

    # Verify format and content
    assert isinstance(stat_choices, dict)
    assert "stat_weapon_skill" in stat_choices
    assert stat_choices["stat_weapon_skill"] == "Weapon Skill"
    assert "stat_ballistic_skill" in stat_choices
    assert stat_choices["stat_ballistic_skill"] == "Ballistic Skill"
    assert "stat_strength" in stat_choices
    assert stat_choices["stat_strength"] == "Strength"


@pytest.mark.django_db
def test_advancement_type_form_with_standard_fighter(
    user, content_fighter, make_list, make_list_fighter
):
    """Test advancement choices for a standard fighter without custom statline."""
    # Standard fighter should use default stats
    lst = make_list("Test List")
    list_fighter = make_list_fighter(lst, "Test Fighter")

    form = AdvancementTypeForm(fighter=list_fighter)

    # Get the stat choices from the form
    stat_choices = [
        choice
        for choice in form.fields["advancement_choice"].choices
        if choice[0].startswith("stat_")
    ]

    # Standard fighters should have the standard stats from their content_fighter_statline
    # This will include the standard set of stats
    # The form should have stats based on what's in the fighter's statline
    assert len(stat_choices) > 0, "Standard fighter should have stat choices"


@pytest.mark.django_db
def test_advancement_validation_with_stat_choice():
    """Test validation accepts valid stat advancement choices."""
    # Create a stat definition
    ContentStat.objects.get_or_create(
        field_name="strength",
        defaults={
            "short_name": "S",
            "full_name": "Strength",
        },
    )

    # This should validate successfully
    params = AdvancementFlowParams(
        list_id="00000000-0000-0000-0000-000000000000",
        fighter_id="00000000-0000-0000-0000-000000000000",
        advancement_choice="stat_strength",
        xp_cost=5,
        cost_increase=10,
    )

    assert params.is_stat_advancement()
    assert not params.is_skill_advancement()
    assert params.stat_from_choice() == "strength"


@pytest.mark.django_db
def test_advancement_validation_with_skill_choice():
    """Test validation should accept skill advancement choices."""
    params = AdvancementFlowParams(
        list_id="00000000-0000-0000-0000-000000000000",
        fighter_id="00000000-0000-0000-0000-000000000000",
        advancement_choice="skill_primary_chosen",
        xp_cost=3,
        cost_increase=5,
    )

    assert params.is_skill_advancement()
    assert not params.is_stat_advancement()


@pytest.mark.django_db
def test_advancement_choice_fallback_display(
    user, content_house, make_list, monkeypatch
):
    """Test the fallback display name when stat is not in all_stat_choices."""
    # Create a custom statline type and stat
    custom_type = ContentStatlineType.objects.create(name="CustomType")

    custom_stat = ContentStat.objects.create(
        field_name="custom_stat",
        short_name="CS",
        full_name="Custom Stat",
    )

    type_stat = ContentStatlineTypeStat.objects.create(
        statline_type=custom_type,
        stat=custom_stat,
        position=1,
    )

    # Create a fighter and assign a statline with the custom stat
    fighter_template = ContentFighter.objects.create(
        type="Test Custom",
        house=content_house,
        category="CREW",
    )

    custom_statline = ContentStatline.objects.create(
        content_fighter=fighter_template,
        statline_type=custom_type,
    )

    ContentStatlineStat.objects.create(
        statline=custom_statline,
        statline_type_stat=type_stat,
        value="1",
    )

    # Create a list and list fighter
    lst = make_list("Test List", content_house=content_house)
    list_fighter = ListFighter.objects.create(
        list=lst,
        name="Test Fighter",
        owner=user,
        content_fighter=fighter_template,
    )

    # Monkeypatch all_stat_choices to simulate missing from the global choices map
    monkeypatch.setattr(
        AdvancementTypeForm, "all_stat_choices", classmethod(lambda cls: {})
    )

    # Build the form and extract choices
    form = AdvancementTypeForm(fighter=list_fighter)
    choices = dict(form.fields["advancement_choice"].choices)

    # The fallback should be used for the custom stat
    assert "stat_custom_stat" in choices, "Custom stat key missing from choices"
    # Accept either 'Custom Stat' or 'Custom_Stat' depending on implementation
    label = choices["stat_custom_stat"]
    assert label.replace("_", " ") == "Custom Stat", (
        f"Unexpected fallback label: {label}"
    )


@pytest.mark.parametrize(
    "roll_action,d6_1,d6_2,expected_valid",
    [
        ("roll_auto", None, None, True),
        ("roll_manual", None, None, False),
        ("roll_manual", 0, 7, False),
        ("roll_manual", 3, 4, True),
    ],
)
def test_advancement_choice_form_validations(roll_action, d6_1, d6_2, expected_valid):
    """Test the validations of the AdvancementDiceChoiceForm."""

    form = AdvancementDiceChoiceForm(
        data={
            "roll_action": roll_action,
            "d6_1": d6_1,
            "d6_2": d6_2,
        }
    )
    is_valid = form.is_valid()
    if expected_valid:
        assert is_valid
    else:
        assert not is_valid
