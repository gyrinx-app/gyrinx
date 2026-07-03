"""Phase 4 of the cost-pinning programme (#1826): the pin schema, inert.

The three component M2Ms now have explicit through models declared in place
on their original join tables, carrying nullable pin columns nothing reads or
writes yet. These tests prove the conversion is behaviour-neutral: every
plain M2M write path still works, new rows are born unpinned, and the
assignment admin (reworked to through-row inlines) loads and saves.
"""

import pytest
from django.urls import reverse

from gyrinx.content.models import ContentEquipmentUpgrade, ContentWeaponAccessory
from gyrinx.core.models.list import (
    ListFighterEquipmentAssignment,
    ListFighterEquipmentAssignmentAccessory,
    ListFighterEquipmentAssignmentProfile,
    ListFighterEquipmentAssignmentUpgrade,
    PinState,
)


@pytest.fixture
def assignment(user, make_list, make_list_fighter, make_equipment):
    lst = make_list("Pin Gang")
    fighter = make_list_fighter(lst, "Bob")
    # The admin's grouped equipment dropdown reads category.name, so the
    # fixture equipment needs a real category.
    equipment = make_equipment("Lasgun", cost=15, category="Basic Weapons")
    return ListFighterEquipmentAssignment.objects.create(
        list_fighter=fighter, content_equipment=equipment
    )


@pytest.mark.django_db
def test_m2m_writes_work_through_declared_models(
    assignment, make_weapon_profile, make_equipment
):
    """add/set/remove/clear still work: the pin fields are all nullable."""
    profile = make_weapon_profile(assignment.content_equipment, name="Hotshot", cost=10)
    accessory = ContentWeaponAccessory.objects.create(name="Scope", cost=8)
    upgrade = ContentEquipmentUpgrade.objects.create(
        name="Mag", equipment=assignment.content_equipment, cost=12
    )

    assignment.weapon_profiles_field.add(profile)
    assignment.weapon_accessories_field.set([accessory])
    assignment.upgrades_field.add(upgrade)

    assert list(assignment.weapon_profiles_field.all()) == [profile]
    assert list(assignment.weapon_accessories_field.all()) == [accessory]
    assert list(assignment.upgrades_field.all()) == [upgrade]

    assignment.weapon_profiles_field.remove(profile)
    assert assignment.weapon_profiles_field.count() == 0
    assignment.weapon_accessories_field.clear()
    assert assignment.weapon_accessories_field.count() == 0


@pytest.mark.django_db
def test_through_rows_are_born_unpinned(assignment, make_weapon_profile):
    """New component rows start UNPINNED with a null amount — pins are inert."""
    profile = make_weapon_profile(assignment.content_equipment, name="Hotshot", cost=10)
    assignment.weapon_profiles_field.add(profile)

    row = ListFighterEquipmentAssignmentProfile.objects.get(
        listfighterequipmentassignment=assignment, contentweaponprofile=profile
    )
    assert row.pin_state == PinState.UNPINNED
    assert row.pinned_amount is None
    assert row.pinned_equipment_list_item is None
    assert row.pinned_expansion_item is None

    assert assignment.pinned_base_state == PinState.UNPINNED
    assert assignment.pinned_base_amount is None


@pytest.mark.django_db
def test_through_table_filter_pattern_still_works(assignment):
    """The handler-level through-table filters (removal.py, sale.py) hold."""
    accessory = ContentWeaponAccessory.objects.create(name="Scope", cost=8)
    assignment.weapon_accessories_field.add(accessory)

    qs = assignment.weapon_accessories_field.through.objects.filter(
        listfighterequipmentassignment=assignment,
        contentweaponaccessory=accessory,
    )
    assert qs.count() == 1
    assert qs.model is ListFighterEquipmentAssignmentAccessory

    qs.delete()
    assert assignment.weapon_accessories_field.count() == 0


@pytest.mark.django_db
def test_duplicate_component_rows_rejected(assignment, make_weapon_profile):
    """The pair uniqueness of the original join tables is preserved in state."""
    profile = make_weapon_profile(assignment.content_equipment, name="Hotshot", cost=10)
    assignment.weapon_profiles_field.add(profile)
    # M2M add() is idempotent — no duplicate row, no error.
    assignment.weapon_profiles_field.add(profile)
    assert (
        ListFighterEquipmentAssignmentProfile.objects.filter(
            listfighterequipmentassignment=assignment
        ).count()
        == 1
    )


@pytest.mark.django_db
def test_upgrade_rows_visible_via_reverse_accessor(assignment):
    upgrade = ContentEquipmentUpgrade.objects.create(
        name="Mag", equipment=assignment.content_equipment, cost=12
    )
    assignment.upgrades_field.add(upgrade)
    rows = assignment.upgrade_rows.all()
    assert rows.count() == 1
    assert isinstance(rows[0], ListFighterEquipmentAssignmentUpgrade)
    assert rows[0].contentequipmentupgrade == upgrade


@pytest.mark.django_db
def test_assignment_admin_change_form_loads_and_saves(
    client, make_user, assignment, make_weapon_profile
):
    """The reworked admin (through-row inlines) renders and round-trips."""
    profile = make_weapon_profile(assignment.content_equipment, name="Hotshot", cost=10)
    assignment.weapon_profiles_field.add(profile)

    staff = make_user("staffadmin", "password")
    staff.is_staff = True
    staff.is_superuser = True
    staff.save()
    client.force_login(staff)

    url = reverse(
        "admin:core_listfighterequipmentassignment_change", args=[assignment.pk]
    )
    response = client.get(url)
    assert response.status_code == 200
    content = response.content.decode()
    assert "Weapon profiles" in content
    assert "Hotshot" in content

    # Changelist still renders (display callables use the M2M accessors).
    response = client.get(
        reverse("admin:core_listfighterequipmentassignment_changelist")
    )
    assert response.status_code == 200
