"""Test that no options error message is displayed immediately on form render."""

import pytest
from django.template import Context, Template

from gyrinx.content.models import (
    ContentAdvancementAssignment,
    ContentAdvancementEquipment,
    ContentEquipmentUpgrade,
)
from gyrinx.core.forms.advancement import EquipmentAssignmentSelectionForm
from gyrinx.core.models import ListFighterEquipmentAssignment
from gyrinx.models import FighterCategoryChoices


@pytest.mark.django_db
def test_no_options_error_displays_before_submission(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test that error message shows immediately when no options are available."""
    house = make_content_house("Test House")

    # Create equipment and upgrade
    weapon = make_equipment(name="Special Gun", cost=50)
    upgrade1 = ContentEquipmentUpgrade.objects.create(
        equipment=weapon, name="Special Mod", cost=25
    )

    # Create advancement with only one assignment that has the upgrade
    advancement = ContentAdvancementEquipment.objects.create(
        name="Special Equipment",
        xp_cost=20,
        enable_chosen=True,
    )

    assignment = ContentAdvancementAssignment.objects.create(
        advancement=advancement,
        equipment=weapon,
    )
    assignment.upgrades_field.add(upgrade1)

    # Create fighter
    fighter_type = make_content_fighter(
        type="Specialist",
        category=FighterCategoryChoices.CHAMPION,
        house=house,
        base_cost=100,
    )
    gang_list = make_list("Test Gang", content_house=house)
    fighter = make_list_fighter(gang_list, "Specialist", content_fighter=fighter_type)

    # Give fighter equipment with the same upgrade
    existing_assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=weapon,
    )
    existing_assignment.upgrades_field.add(upgrade1)

    # Create form - should have error message available immediately
    form = EquipmentAssignmentSelectionForm(advancement=advancement, fighter=fighter)

    # Check that the error message is available via property
    assert form.no_options_error_message is not None
    assert "No available options" in form.no_options_error_message
    assert advancement.name in form.no_options_error_message

    # Check that the assignment field is disabled
    assert form.fields["assignment"].widget.attrs.get("disabled") is True

    # Test that template can access and display the error
    template = Template(
        "{% if form.no_options_error_message %}"
        "{{ form.no_options_error_message }}"
        "{% endif %}"
    )
    context = Context({"form": form})
    rendered = template.render(context)

    assert "No available options" in rendered
    assert advancement.name in rendered


@pytest.mark.django_db
def test_no_error_message_when_options_available(
    user,
    make_content_house,
    make_content_fighter,
    make_equipment,
    make_list,
    make_list_fighter,
):
    """Test that no error message appears when options are available."""
    house = make_content_house("Test House")

    # Create equipment
    weapon = make_equipment(name="Normal Gun", cost=30)

    # Create advancement with an assignment
    advancement = ContentAdvancementEquipment.objects.create(
        name="Standard Equipment",
        xp_cost=10,
        enable_chosen=True,
    )

    ContentAdvancementAssignment.objects.create(
        advancement=advancement,
        equipment=weapon,
    )

    # Create fighter
    fighter_type = make_content_fighter(
        type="Ganger",
        category=FighterCategoryChoices.GANGER,
        house=house,
        base_cost=50,
    )
    gang_list = make_list("Test Gang", content_house=house)
    fighter = make_list_fighter(gang_list, "Ganger", content_fighter=fighter_type)

    # Create form - should not have error message
    form = EquipmentAssignmentSelectionForm(advancement=advancement, fighter=fighter)

    # Check that no error message is available
    assert form.no_options_error_message is None

    # Check that the assignment field is NOT disabled
    assert form.fields["assignment"].widget.attrs.get("disabled") is None

    # Test that template doesn't show any error
    template = Template(
        "{% if form.no_options_error_message %}"
        "ERROR: {{ form.no_options_error_message }}"
        "{% else %}"
        "No error"
        "{% endif %}"
    )
    context = Context({"form": form})
    rendered = template.render(context)

    assert rendered == "No error"
