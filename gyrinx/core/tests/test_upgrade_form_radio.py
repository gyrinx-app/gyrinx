import pytest
from django import forms

from gyrinx.content.models import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentUpgrade,
)
from gyrinx.core.forms import BsRadioSelect
from gyrinx.core.forms.list import ListFighterEquipmentAssignmentUpgradeForm
from gyrinx.core.models.list import ListFighterEquipmentAssignment


@pytest.fixture
def equipment_category():
    """Get or create test equipment category."""
    return ContentEquipmentCategory.objects.get_or_create(
        name="Personal Equipment",
        defaults={"group": "Gear"},
    )[0]


@pytest.fixture
def single_mode_equipment(equipment_category):
    """Create equipment with SINGLE upgrade mode."""
    return ContentEquipment.objects.create(
        name="Cyberteknika Implant",
        category=equipment_category,
        rarity="C",
        cost="50",
        upgrade_mode=ContentEquipment.UpgradeMode.SINGLE,
        upgrade_stack_name="Augmentation",
    )


@pytest.fixture
def multi_mode_equipment(equipment_category):
    """Create equipment with MULTI upgrade mode."""
    return ContentEquipment.objects.create(
        name="Genesmithed Equipment",
        category=equipment_category,
        rarity="C",
        cost="50",
        upgrade_mode=ContentEquipment.UpgradeMode.MULTI,
        upgrade_stack_name="Gene Mod",
    )


@pytest.fixture
def single_upgrades(single_mode_equipment):
    """Create upgrades for single-mode equipment."""
    upgrades = []
    for i, name in enumerate(["Basic", "Advanced", "Superior"]):
        upgrades.append(
            ContentEquipmentUpgrade.objects.create(
                name=name,
                equipment=single_mode_equipment,
                cost=str((i + 1) * 10),
                position=i,
            )
        )
    return upgrades


@pytest.fixture
def multi_upgrades(multi_mode_equipment):
    """Create upgrades for multi-mode equipment."""
    upgrades = []
    for i, name in enumerate(["Mod A", "Mod B", "Mod C"]):
        upgrades.append(
            ContentEquipmentUpgrade.objects.create(
                name=name,
                equipment=multi_mode_equipment,
                cost=str((i + 1) * 10),
                position=i,
            )
        )
    return upgrades


@pytest.fixture
def single_assignment(make_list, make_list_fighter, single_mode_equipment):
    """Create an equipment assignment with single-mode equipment."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")
    return ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=single_mode_equipment,
    )


@pytest.fixture
def multi_assignment(make_list, make_list_fighter, multi_mode_equipment):
    """Create an equipment assignment with multi-mode equipment."""
    lst = make_list("Test List")
    fighter = make_list_fighter(lst, "Test Fighter")
    return ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter,
        content_equipment=multi_mode_equipment,
    )


@pytest.mark.django_db
def test_single_mode_uses_radio_widget(single_assignment, single_upgrades):
    """SINGLE-mode upgrades should use a radio button widget."""
    form = ListFighterEquipmentAssignmentUpgradeForm(instance=single_assignment)
    field = form.fields["upgrades_field"]
    assert isinstance(field, forms.ModelChoiceField)
    assert isinstance(field.widget, BsRadioSelect)


@pytest.mark.django_db
def test_multi_mode_uses_checkbox_widget(multi_assignment, multi_upgrades):
    """MULTI-mode upgrades should use a checkbox widget."""
    form = ListFighterEquipmentAssignmentUpgradeForm(instance=multi_assignment)
    field = form.fields["upgrades_field"]
    assert isinstance(field, forms.ModelMultipleChoiceField)
    assert not isinstance(field.widget, BsRadioSelect)


@pytest.mark.django_db
def test_single_mode_has_none_option(single_assignment, single_upgrades):
    """SINGLE-mode radio should include a 'None' empty option."""
    form = ListFighterEquipmentAssignmentUpgradeForm(instance=single_assignment)
    field = form.fields["upgrades_field"]
    assert field.empty_label == "None"
    assert field.required is False


@pytest.mark.django_db
def test_single_mode_form_submit_with_upgrade(single_assignment, single_upgrades):
    """Submitting the form with a radio selection should return a queryset with one item."""
    upgrade = single_upgrades[1]  # "Advanced"
    form = ListFighterEquipmentAssignmentUpgradeForm(
        data={"upgrades_field": str(upgrade.pk)},
        instance=single_assignment,
    )
    assert form.is_valid(), form.errors
    result = form.cleaned_data["upgrades_field"]
    assert list(result) == [upgrade]


@pytest.mark.django_db
def test_single_mode_form_submit_none(single_assignment, single_upgrades):
    """Submitting the form with no radio selection should return an empty queryset."""
    form = ListFighterEquipmentAssignmentUpgradeForm(
        data={"upgrades_field": ""},
        instance=single_assignment,
    )
    assert form.is_valid(), form.errors
    result = form.cleaned_data["upgrades_field"]
    assert list(result) == []


@pytest.mark.django_db
def test_multi_mode_form_submit_multiple(multi_assignment, multi_upgrades):
    """MULTI mode should accept multiple selections."""
    selected = [multi_upgrades[0], multi_upgrades[2]]
    form = ListFighterEquipmentAssignmentUpgradeForm(
        data={"upgrades_field": [str(u.pk) for u in selected]},
        instance=multi_assignment,
    )
    assert form.is_valid(), form.errors
    result = form.cleaned_data["upgrades_field"]
    assert set(result) == set(selected)


@pytest.mark.django_db
def test_single_mode_label(single_assignment, single_upgrades):
    """SINGLE-mode form should use the equipment's upgrade stack name as label."""
    form = ListFighterEquipmentAssignmentUpgradeForm(instance=single_assignment)
    assert form.fields["upgrades_field"].label == "Augmentation"


@pytest.mark.django_db
def test_single_mode_initial_value_when_upgrade_set(single_assignment, single_upgrades):
    """When the assignment already has an upgrade, the radio should be pre-selected."""
    upgrade = single_upgrades[0]
    single_assignment.upgrades_field.set([upgrade])
    form = ListFighterEquipmentAssignmentUpgradeForm(instance=single_assignment)
    assert form.initial["upgrades_field"] == upgrade.pk
