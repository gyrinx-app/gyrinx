import pytest
from django import forms
from django.contrib.auth.models import User

from gyrinx.content.models import (
    ContentInjury,
    ContentInjuryDefaultOutcome,
    ContentFighter,
    ContentHouse,
)
from gyrinx.core.forms.list import AddInjuryForm
from gyrinx.core.models.list import List, ListFighter


@pytest.mark.django_db
def test_add_injury_form_initialization():
    """Test that AddInjuryForm initializes correctly."""
    # Create some test injuries
    ContentInjury.objects.create(
        name="Eye Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )
    ContentInjury.objects.create(
        name="Old Battle Wound",
        phase=ContentInjuryDefaultOutcome.ACTIVE,
    )
    ContentInjury.objects.create(
        name="Humiliated",
        phase=ContentInjuryDefaultOutcome.CONVALESCENCE,
    )

    form = AddInjuryForm()

    # Check form fields
    assert "injury" in form.fields
    assert "fighter_state" in form.fields
    assert "notes" in form.fields

    # Check injury field properties
    injury_field = form.fields["injury"]
    assert isinstance(injury_field, forms.ModelChoiceField)
    assert injury_field.label == "Select Injury"
    assert injury_field.help_text == "Choose the injury to apply to this fighter."
    assert injury_field.required is True

    # Check notes field properties
    notes_field = form.fields["notes"]
    assert isinstance(notes_field, forms.CharField)
    assert notes_field.label == "Notes"
    assert (
        notes_field.help_text
        == "Optional notes about how this injury was received (will be included in campaign log)."
    )
    assert notes_field.required is False
    assert isinstance(notes_field.widget, forms.Textarea)
    assert notes_field.widget.attrs["rows"] == 3


@pytest.mark.django_db
def test_add_injury_form_queryset_ordering():
    """Test that injuries are ordered correctly in the form."""
    # Create injuries in specific order to test sorting
    ContentInjury.objects.create(
        name="Z Permanent", phase=ContentInjuryDefaultOutcome.ACTIVE
    )
    ContentInjury.objects.create(
        name="A Recovery", phase=ContentInjuryDefaultOutcome.RECOVERY
    )
    ContentInjury.objects.create(
        name="B Recovery", phase=ContentInjuryDefaultOutcome.RECOVERY
    )
    ContentInjury.objects.create(
        name="A Convalescence", phase=ContentInjuryDefaultOutcome.CONVALESCENCE
    )
    ContentInjury.objects.create(
        name="A Out Cold", phase=ContentInjuryDefaultOutcome.RECOVERY
    )
    ContentInjury.objects.create(
        name="A Permanent", phase=ContentInjuryDefaultOutcome.ACTIVE
    )

    form = AddInjuryForm()
    queryset_injuries = list(form.fields["injury"].queryset)

    # Check ordering - should be by group (empty groups first), then by name
    # Since no groups are specified, all injuries should be ordered by name
    assert queryset_injuries[0].name == "A Convalescence"
    assert queryset_injuries[1].name == "A Out Cold"
    assert queryset_injuries[2].name == "A Permanent"
    assert queryset_injuries[3].name == "A Recovery"
    assert queryset_injuries[4].name == "B Recovery"
    assert queryset_injuries[5].name == "Z Permanent"


@pytest.mark.django_db
def test_add_injury_form_valid_data():
    """Test form validation with valid data."""
    injury = ContentInjury.objects.create(
        name="Test Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    form = AddInjuryForm(
        data={
            "injury": injury.id,
            "fighter_state": "recovery",
            "notes": "Injured during gang war",
        }
    )

    assert form.is_valid()
    assert form.cleaned_data["injury"] == injury
    assert form.cleaned_data["fighter_state"] == "recovery"
    assert form.cleaned_data["notes"] == "Injured during gang war"


@pytest.mark.django_db
def test_add_injury_form_valid_without_notes():
    """Test form validation without notes (optional field)."""
    injury = ContentInjury.objects.create(
        name="Test Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    form = AddInjuryForm(
        data={
            "injury": injury.id,
            "fighter_state": "recovery",
            "notes": "",
        }
    )

    assert form.is_valid()
    assert form.cleaned_data["injury"] == injury
    assert form.cleaned_data["fighter_state"] == "recovery"
    assert form.cleaned_data["notes"] == ""


@pytest.mark.django_db
def test_add_injury_form_invalid_no_injury():
    """Test form validation without selecting an injury."""
    form = AddInjuryForm(
        data={
            "injury": "",
            "notes": "Some notes",
        }
    )

    assert not form.is_valid()
    assert "injury" in form.errors
    assert "This field is required." in form.errors["injury"]


@pytest.mark.django_db
def test_add_injury_form_invalid_nonexistent_injury():
    """Test form validation with non-existent injury ID."""
    form = AddInjuryForm(
        data={
            "injury": 99999,  # Non-existent ID
            "notes": "Some notes",
        }
    )

    assert not form.is_valid()
    assert "injury" in form.errors


@pytest.mark.django_db
def test_add_injury_form_widget_classes():
    """Test that form widgets have correct CSS classes."""
    form = AddInjuryForm()

    # Check injury select widget
    injury_widget = form.fields["injury"].widget
    assert injury_widget.attrs["class"] == "form-select"

    # Check notes textarea widget
    notes_widget = form.fields["notes"].widget
    assert notes_widget.attrs["class"] == "form-control"
    assert notes_widget.attrs["rows"] == 3


@pytest.mark.django_db
def test_add_injury_form_queryset_includes_all_injuries():
    """Test that the form includes all injuries in the database."""
    # Create various injuries
    injuries = [
        ContentInjury.objects.create(
            name=f"Injury {i}",
            phase=phase,
        )
        for i, phase in enumerate(
            [
                ContentInjuryDefaultOutcome.NO_CHANGE,
                ContentInjuryDefaultOutcome.ACTIVE,
                ContentInjuryDefaultOutcome.RECOVERY,
                ContentInjuryDefaultOutcome.CONVALESCENCE,
                ContentInjuryDefaultOutcome.DEAD,
            ]
        )
    ]

    form = AddInjuryForm()
    form_injuries = list(form.fields["injury"].queryset)

    # All injuries should be in the form
    assert len(form_injuries) == len(injuries)
    for injury in injuries:
        assert injury in form_injuries


@pytest.mark.django_db
def test_add_injury_form_select_related():
    """Test that the form queryset uses select_related for efficiency."""
    # Create an injury
    injury = ContentInjury.objects.create(
        name="Test Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    form = AddInjuryForm()

    # The queryset should use select_related (this is in the form's __init__)
    # We can't directly test select_related was called, but we can verify
    # the queryset works correctly
    queryset = form.fields["injury"].queryset
    assert injury in queryset


@pytest.mark.django_db
def test_add_injury_form_empty_choice():
    """Test that the injury field has an empty choice option."""
    form = AddInjuryForm()

    # ModelChoiceField should have empty_label by default
    injury_field = form.fields["injury"]
    assert injury_field.empty_label is not None  # Default is "---------"


@pytest.mark.django_db
def test_add_injury_form_uses_equipment_list_fighter_house():
    """Test that AddInjuryForm uses the fighter's equipment_list_fighter house for filtering injuries."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")

    # Create two different houses
    main_house = ContentHouse.objects.create(name="Main House")
    legacy_house = ContentHouse.objects.create(name="Legacy House")

    # Create fighters for each house
    main_fighter = ContentFighter.objects.create(
        type="Main Fighter",
        category="GANGER",
        house=main_house,
    )
    legacy_fighter = ContentFighter.objects.create(
        type="Legacy Fighter",
        category="GANGER",
        house=legacy_house,
        can_be_legacy=True,
    )

    # Create list with main house
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=main_house,
    )

    # Create a fighter with a legacy
    fighter = ListFighter.objects.create(
        name="Fighter with Legacy",
        content_fighter=main_fighter,
        legacy_content_fighter=legacy_fighter,
        list=lst,
        owner=user,
    )

    # Create injury groups specific to each house
    from gyrinx.content.models import ContentInjuryGroup

    main_group = ContentInjuryGroup.objects.create(
        name="Main House Injuries",
    )
    main_group.restricted_to_house.set([main_house])

    legacy_group = ContentInjuryGroup.objects.create(
        name="Legacy House Injuries",
    )
    legacy_group.restricted_to_house.set([legacy_house])

    # Create injuries for each group
    main_injury = ContentInjury.objects.create(
        name="Main House Injury",
        injury_group=main_group,
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )
    legacy_injury = ContentInjury.objects.create(
        name="Legacy House Injury",
        injury_group=legacy_group,
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )
    generic_injury = ContentInjury.objects.create(
        name="Generic Injury",
        phase=ContentInjuryDefaultOutcome.RECOVERY,
    )

    # Create form with fighter
    form = AddInjuryForm(fighter=fighter)

    # The form should use the legacy fighter's house since equipment_list_fighter
    # returns legacy_content_fighter when it exists
    available_injuries = list(form.fields["injury"].queryset)

    # Should include legacy house injuries and generic injuries
    assert legacy_injury in available_injuries
    assert generic_injury in available_injuries
    # Should NOT include main house injuries since we're using the legacy fighter's house
    assert main_injury not in available_injuries

    # Test without legacy fighter - should use main house
    fighter_no_legacy = ListFighter.objects.create(
        name="Fighter without Legacy",
        content_fighter=main_fighter,
        list=lst,
        owner=user,
    )

    form_no_legacy = AddInjuryForm(fighter=fighter_no_legacy)
    available_injuries_no_legacy = list(form_no_legacy.fields["injury"].queryset)

    # Should include main house injuries and generic injuries
    assert main_injury in available_injuries_no_legacy
    assert generic_injury in available_injuries_no_legacy
    # Should NOT include legacy house injuries
    assert legacy_injury not in available_injuries_no_legacy


@pytest.mark.django_db
def test_add_injury_form_defaults_to_fighter_current_state():
    """Test that the fighter_state field defaults to the fighter's current injury state."""
    # Create test data
    user = User.objects.create_user(username="testuser", password="testpass")
    house = ContentHouse.objects.create(name="Test House")
    content_fighter = ContentFighter.objects.create(
        type="Test Fighter",
        category="GANGER",
        house=house,
    )
    lst = List.objects.create(
        name="Test List",
        owner=user,
        content_house=house,
    )

    # Create fighter in RECOVERY state
    fighter = ListFighter.objects.create(
        name="Injured Fighter",
        content_fighter=content_fighter,
        list=lst,
        owner=user,
        injury_state=ListFighter.RECOVERY,
    )

    # Create form with fighter
    form = AddInjuryForm(fighter=fighter)

    # Check that fighter_state initial value matches fighter's current state
    assert form.fields["fighter_state"].initial == ListFighter.RECOVERY

    # Test with fighter in CONVALESCENCE state
    fighter.injury_state = ListFighter.CONVALESCENCE
    fighter.save()

    form = AddInjuryForm(fighter=fighter)
    assert form.fields["fighter_state"].initial == ListFighter.CONVALESCENCE

    # Test with no fighter passed
    form = AddInjuryForm()
    assert form.fields["fighter_state"].initial is None

    # Test with bound form (POST data) - initial should not be set
    form = AddInjuryForm(
        {"injury": "1", "fighter_state": ListFighter.ACTIVE}, fighter=fighter
    )
    assert (
        form.fields["fighter_state"].initial is None
    )  # Initial is not set for bound forms
