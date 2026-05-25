"""Tests for pack support for VEHICLE and EXOTIC_BEAST fighters.

Each pack-defined vehicle/beast also gets an auto-created, read-only
ContentEquipment + ContentEquipmentFighterProfile bridge so list buyers
can purchase it and have the child fighter spawned.

These tests are written red-first — they describe the desired outcomes
before the implementation lands.
"""

from unittest.mock import patch

import pytest
from django.contrib.contenttypes.models import ContentType
from django.urls import reverse

from gyrinx.content.models.equipment import (
    ContentEquipment,
    ContentEquipmentCategory,
    ContentEquipmentFighterProfile,
)
from gyrinx.content.models.default_assignment import ContentFighterDefaultAssignment
from gyrinx.content.models.fighter import ContentFighter
from gyrinx.content.models.statline import (
    ContentStat,
    ContentStatlineType,
    ContentStatlineTypeStat,
)
from gyrinx.core.models.list import ListFighter, ListFighterEquipmentAssignment
from gyrinx.core.models.pack import CustomContentPackItem


# --- Fixtures ------------------------------------------------------------------


@pytest.fixture
def fighter_statline_type():
    """Standard Fighter statline (covers everything except VEHICLE).

    Migration 0156 + 0159 do this in production, but tests run with
    ``--nomigrations`` by default so we re-establish it here.
    """
    statline_type, _ = ContentStatlineType.objects.get_or_create(
        name="Fighter",
        defaults={
            "default_for_categories": [
                "LEADER",
                "CHAMPION",
                "GANGER",
                "JUVE",
                "EXOTIC_BEAST",
                "HANGER_ON",
                "BRUTE",
                "HIRED_GUN",
                "BOUNTY_HUNTER",
                "HOUSE_AGENT",
                "HIVE_SCUM",
                "DRAMATIS_PERSONAE",
                "PROSPECT",
                "SPECIALIST",
                "ALLY",
            ]
        },
    )
    return statline_type


@pytest.fixture
def vehicle_statline_type():
    """Statline type whose default applies to VEHICLE fighters."""
    statline_type, _ = ContentStatlineType.objects.get_or_create(
        name="Vehicle",
        defaults={"default_for_categories": ["VEHICLE"]},
    )
    if "VEHICLE" not in (statline_type.default_for_categories or []):
        statline_type.default_for_categories = ["VEHICLE"]
        statline_type.save()
    # A minimal vehicle statline schema — just one stat to make the form happy.
    stat, _ = ContentStat.objects.get_or_create(
        field_name="hull_points",
        defaults={"short_name": "HP", "full_name": "Hull Points"},
    )
    ContentStatlineTypeStat.objects.get_or_create(
        statline_type=statline_type,
        stat=stat,
        defaults={"position": 1},
    )
    return statline_type


@pytest.fixture
def beast_statline_type():
    """Statline type for EXOTIC_BEAST fighters.

    EXOTIC_BEAST uses the standard ``Fighter`` statline (created by migration
    0156 + 0159, which configures Fighter's default_for_categories to include
    EXOTIC_BEAST). This fixture just ensures the Fighter type exists and
    returns it.
    """
    statline_type, _ = ContentStatlineType.objects.get_or_create(
        name="Fighter",
        defaults={"default_for_categories": ["EXOTIC_BEAST"]},
    )
    if "EXOTIC_BEAST" not in (statline_type.default_for_categories or []):
        statline_type.default_for_categories = list(
            statline_type.default_for_categories or []
        ) + ["EXOTIC_BEAST"]
        statline_type.save()
    # Make sure at least one stat is wired up.
    stat, _ = ContentStat.objects.get_or_create(
        field_name="movement",
        defaults={"short_name": "M", "full_name": "Movement"},
    )
    ContentStatlineTypeStat.objects.get_or_create(
        statline_type=statline_type,
        stat=stat,
        defaults={"position": 1},
    )
    return statline_type


@pytest.fixture
def vehicles_category():
    cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Vehicles", defaults={"group": "Vehicle & Mount"}
    )
    return cat


@pytest.fixture
def status_items_category():
    cat, _ = ContentEquipmentCategory.objects.get_or_create(
        name="Status Items", defaults={"group": "Gear"}
    )
    return cat


def _step1_post(client, pack, **overrides):
    """Submit Step 1 of the pack create-fighter flow."""
    data = {
        "type": "Goliath Mauler",
        "category": "VEHICLE",
        "house": "",
        "base_cost": "150",
    }
    data.update(overrides)
    return client.post(f"/pack/{pack.id}/add/fighter/", data)


def _step2_post(client, pack, params, stats=None):
    """Submit Step 2 (stats) of the pack create-fighter flow."""
    qs = "&".join(f"{k}={v}" for k, v in params.items())
    return client.post(f"/pack/{pack.id}/add/fighter/stats/?{qs}", stats or {})


def _create_pack_fighter_full(client, pack, *, type_, category, base_cost, house_id):
    """Drive the full 2-step add-fighter flow to completion."""
    response = _step1_post(
        client,
        pack,
        type=type_,
        category=category,
        house=str(house_id),
        base_cost=str(base_cost),
    )
    assert response.status_code == 302, response.content
    response = _step2_post(
        client,
        pack,
        {
            "type": type_,
            "category": category,
            "house_id": str(house_id),
            "base_cost": str(base_cost),
        },
    )
    assert response.status_code == 302, response.content
    return ContentFighter.objects.all_content().get(type=type_)


# --- Form layer ---------------------------------------------------------------


@pytest.mark.django_db
def test_create_vehicle_form_allows_vehicle_category(
    client, user, pack, content_house, vehicle_statline_type, vehicles_category
):
    """Pack create-fighter form must not exclude VEHICLE."""
    client.force_login(user)
    response = _step1_post(
        client,
        pack,
        type="Goliath Mauler",
        category="VEHICLE",
        house=str(content_house.pk),
        base_cost="150",
    )
    assert response.status_code == 302


@pytest.mark.django_db
def test_create_vehicle_form_allows_exotic_beast_category(
    client, user, pack, content_house, beast_statline_type, status_items_category
):
    """Pack create-fighter form must not exclude EXOTIC_BEAST."""
    client.force_login(user)
    response = _step1_post(
        client,
        pack,
        type="Hive Cur",
        category="EXOTIC_BEAST",
        house=str(content_house.pk),
        base_cost="25",
    )
    assert response.status_code == 302


@pytest.mark.django_db
def test_vehicle_statline_auto_selected(
    client, user, pack, content_house, vehicle_statline_type, vehicles_category
):
    """When the user picks VEHICLE, the form auto-resolves the matching statline."""
    client.force_login(user)
    fighter = _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    assert hasattr(fighter, "custom_statline")
    assert fighter.custom_statline.statline_type == vehicle_statline_type


@pytest.mark.django_db
def test_exotic_beast_statline_auto_selected(
    client, user, pack, content_house, beast_statline_type, status_items_category
):
    client.force_login(user)
    fighter = _create_pack_fighter_full(
        client,
        pack,
        type_="Hive Cur",
        category="EXOTIC_BEAST",
        base_cost=25,
        house_id=content_house.pk,
    )
    assert hasattr(fighter, "custom_statline")
    assert fighter.custom_statline.statline_type == beast_statline_type


@pytest.mark.django_db
def test_create_vehicle_fails_if_no_statline_type_exists(
    client, user, pack, content_house, vehicles_category
):
    """If the DB has no ContentStatlineType for VEHICLE, the create flow
    must NOT silently create a fighter at all (let alone with the wrong
    fallback Fighter statline). Drives both Step 1 and Step 2 so the
    assertion isn't vacuous — the previous version of this test only
    POSTed Step 1 (which never creates a fighter) and would pass even
    if Step 2 silently fell back.

    NOTE: today Step 2 raises ContentStatlineType.DoesNotExist → 500.
    That's a loud failure mode, which is fine for correctness; the UX
    gap (form-level error) is a separate follow-up.
    """
    # Deliberately do NOT include vehicle_statline_type fixture.
    client.force_login(user)
    _step1_post(
        client,
        pack,
        type="Bare Vehicle",
        category="VEHICLE",
        house=str(content_house.pk),
        base_cost="100",
    )
    # Step 2 — the request will 500 because no Vehicle statline type exists.
    # Use raise_request_exception=False so the test client returns the 500
    # response instead of re-raising the exception.
    client.raise_request_exception = False
    try:
        _step2_post(
            client,
            pack,
            {
                "type": "Bare Vehicle",
                "category": "VEHICLE",
                "house_id": str(content_house.pk),
                "base_cost": "100",
            },
        )
    finally:
        client.raise_request_exception = True

    # No "Bare Vehicle" ContentFighter must have been created.
    assert not ContentFighter.objects.all_content().filter(type="Bare Vehicle").exists()


# --- Equipment + bridge auto-creation -----------------------------------------


@pytest.mark.django_db
def test_creating_pack_vehicle_creates_equipment(
    client, user, pack, content_house, vehicle_statline_type, vehicles_category
):
    client.force_login(user)
    _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    equipment = ContentEquipment.objects.all_content().get(name="Goliath Mauler")
    assert equipment.category == vehicles_category
    assert equipment.cost == "150"


@pytest.mark.django_db
def test_creating_pack_vehicle_creates_bridge(
    client, user, pack, content_house, vehicle_statline_type, vehicles_category
):
    client.force_login(user)
    fighter = _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    equipment = ContentEquipment.objects.all_content().get(name="Goliath Mauler")
    assert ContentEquipmentFighterProfile.objects.filter(
        equipment=equipment, content_fighter=fighter
    ).exists()


@pytest.mark.django_db
def test_creating_pack_vehicle_registers_equipment_as_pack_item(
    client, user, pack, content_house, vehicle_statline_type, vehicles_category
):
    client.force_login(user)
    _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    equipment = ContentEquipment.objects.all_content().get(name="Goliath Mauler")
    eq_ct = ContentType.objects.get_for_model(ContentEquipment)
    assert CustomContentPackItem.objects.filter(
        pack=pack, content_type=eq_ct, object_id=equipment.pk
    ).exists()


@pytest.mark.django_db
def test_creating_pack_beast_uses_status_items_category(
    client, user, pack, content_house, beast_statline_type, status_items_category
):
    client.force_login(user)
    _create_pack_fighter_full(
        client,
        pack,
        type_="Hive Cur",
        category="EXOTIC_BEAST",
        base_cost=25,
        house_id=content_house.pk,
    )
    equipment = ContentEquipment.objects.all_content().get(name="Hive Cur")
    assert equipment.category == status_items_category
    assert equipment.cost == "25"


@pytest.mark.django_db
def test_pack_vehicle_equipment_has_no_edit_or_archive_links(
    client, user, pack, content_house, vehicle_statline_type, vehicles_category
):
    """Auto-created equipment is read-only on the pack detail page."""
    client.force_login(user)
    _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    equipment = ContentEquipment.objects.all_content().get(name="Goliath Mauler")
    eq_pack_item = CustomContentPackItem.objects.get(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentEquipment),
        object_id=equipment.pk,
    )
    response = client.get(reverse("core:pack", args=(pack.id,)))
    assert response.status_code == 200
    content = response.content.decode()
    # The auto-equipment's pack item should NOT have edit / archive links.
    edit_url = reverse("core:pack-edit-item", args=(pack.id, eq_pack_item.id))
    delete_url = reverse("core:pack-delete-item", args=(pack.id, eq_pack_item.id))
    assert edit_url not in content
    assert delete_url not in content


# --- Cost sync -----------------------------------------------------------------


@pytest.mark.django_db
def test_editing_pack_vehicle_base_cost_updates_equipment_cost(
    client, user, pack, content_house, vehicle_statline_type, vehicles_category
):
    """When a pack fighter's base_cost changes, the linked equipment cost
    updates so list-buyers see the new price."""
    client.force_login(user)
    fighter = _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    fighter.base_cost = 175
    fighter.save()

    equipment = ContentEquipment.objects.all_content().get(name="Goliath Mauler")
    assert equipment.cost == "175"


# --- Equipping flow on subscribed lists ---------------------------------------


@pytest.mark.django_db
def test_subscribed_list_vehicle_crew_view_resolves_pack_vehicle(
    client,
    user,
    pack,
    content_house,
    vehicle_statline_type,
    vehicles_category,
    make_list,
):
    """Regression: the vehicle_crew view must look up the pack-scoped
    vehicle equipment via ``with_packs`` — without that, the default
    ContentEquipment manager 404s on a pack vehicle."""
    client.force_login(user)
    _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    vehicle_equipment = ContentEquipment.objects.all_content().get(
        name="Goliath Mauler"
    )

    lst = make_list("Crew Test", content_house=content_house)
    lst.packs.add(pack)

    url = reverse("core:list-vehicle-crew", args=(lst.id,))
    response = client.get(
        f"{url}?action=select_crew&vehicle_equipment_id={vehicle_equipment.id}"
    )
    assert response.status_code == 200, response.content


@pytest.mark.django_db
def test_subscribed_list_vehicle_confirm_view_resolves_pack_vehicle(
    client,
    user,
    pack,
    content_house,
    vehicle_statline_type,
    vehicles_category,
    make_list,
):
    """Regression: the vehicle_confirm view (add-to-stash branch) must
    look up the pack-scoped vehicle equipment via ``with_packs``."""
    client.force_login(user)
    _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    vehicle_equipment = ContentEquipment.objects.all_content().get(
        name="Goliath Mauler"
    )

    lst = make_list("Confirm Test", content_house=content_house)
    lst.packs.add(pack)

    url = reverse("core:list-vehicle-confirm", args=(lst.id,))
    response = client.get(
        f"{url}?action=add_to_stash&vehicle_equipment_id={vehicle_equipment.id}"
    )
    assert response.status_code == 200, response.content


@pytest.mark.django_db
def test_crew_selection_form_includes_pack_crew(
    client,
    user,
    pack,
    content_house,
    fighter_statline_type,
    vehicle_statline_type,
    vehicles_category,
    make_list,
):
    """The crew-type selector on the vehicle purchase flow must include
    CREW fighters defined in subscribed packs."""
    from gyrinx.core.forms.vehicle import CrewSelectionForm

    client.force_login(user)
    # Create the vehicle (auto-creates the equipment).
    _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    vehicle_equipment = ContentEquipment.objects.all_content().get(
        name="Goliath Mauler"
    )
    # Create a pack-scoped CREW fighter that should appear in the picker.
    crew_statline, _ = ContentStatlineType.objects.get_or_create(
        name="Crew", defaults={"default_for_categories": ["CREW"]}
    )
    if "CREW" not in (crew_statline.default_for_categories or []):
        crew_statline.default_for_categories = ["CREW"]
        crew_statline.save()
    _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Wheelman",
        category="CREW",
        base_cost=40,
        house_id=content_house.pk,
    )

    lst = make_list("Crew Pack Test", content_house=content_house)
    lst.packs.add(pack)

    form = CrewSelectionForm(list_instance=lst, vehicle_equipment=vehicle_equipment)
    crew_names = {cf.type for cf in form.fields["crew_fighter"].queryset}
    assert "Goliath Wheelman" in crew_names


@pytest.mark.django_db
def test_subscribed_list_can_buy_pack_vehicle(
    client,
    user,
    pack,
    content_house,
    vehicle_statline_type,
    vehicles_category,
    make_list,
):
    """The vehicle picker on a subscribed list must include pack vehicles."""
    from gyrinx.core.forms.vehicle import VehicleSelectionForm

    client.force_login(user)
    _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )

    lst = make_list("Buy Vehicle", content_house=content_house)
    lst.packs.add(pack)

    form = VehicleSelectionForm(list_instance=lst)
    available_names = {e.name for e in form.fields["vehicle_equipment"].queryset}
    assert "Goliath Mauler" in available_names


@pytest.mark.django_db
def test_unsubscribed_list_cannot_buy_pack_vehicle(
    client,
    user,
    pack,
    content_house,
    vehicle_statline_type,
    vehicles_category,
    make_list,
):
    from gyrinx.core.forms.vehicle import VehicleSelectionForm

    client.force_login(user)
    _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )

    lst = make_list("No Sub", content_house=content_house)
    # NOT subscribed
    form = VehicleSelectionForm(list_instance=lst)
    available_names = {e.name for e in form.fields["vehicle_equipment"].queryset}
    assert "Goliath Mauler" not in available_names


@pytest.mark.django_db
def test_subscribed_list_can_buy_pack_exotic_beast_via_equipment(
    client,
    user,
    pack,
    content_house,
    beast_statline_type,
    status_items_category,
    make_list,
    make_list_fighter,
):
    """Buying a pack-scoped beast equipment on a subscribed list spawns the
    child fighter via the existing ContentEquipmentFighterProfile signal."""
    client.force_login(user)
    _create_pack_fighter_full(
        client,
        pack,
        type_="Hive Cur",
        category="EXOTIC_BEAST",
        base_cost=25,
        house_id=content_house.pk,
    )
    beast_equipment = ContentEquipment.objects.all_content().get(name="Hive Cur")

    lst = make_list("Beast List", content_house=content_house)
    lst.packs.add(pack)
    parent = make_list_fighter(lst, "Owner")

    # Direct M2M-style add — the same path the equipment picker would use.
    assignment = ListFighterEquipmentAssignment.objects.create(
        list_fighter=parent, content_equipment=beast_equipment
    )
    assignment.refresh_from_db()
    assert assignment.child_fighter is not None
    assert assignment.child_fighter.list == lst
    assert assignment.child_fighter.content_fighter.type == "Hive Cur"


# --- Default assignments ------------------------------------------------------


@pytest.mark.django_db
def test_default_assignment_picker_includes_pack_vehicle(
    client,
    user,
    pack,
    content_house,
    fighter_statline_type,
    vehicle_statline_type,
    vehicles_category,
):
    """Fighter-linked equipment (vehicles / exotic beasts) appears in the
    pack-fighter default-equipment picker.

    The interim block that hid such equipment was lifted in issue #1803 now
    that issue #1725 propagates default child-fighter assignments to existing
    subscribed gangs.
    """
    client.force_login(user)
    # Create a pack vehicle (auto-makes the equipment)
    _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    # And a regular pack ganger to be the parent
    ganger_response = client.post(
        f"/pack/{pack.id}/add/fighter/",
        {
            "type": "Goliath Ganger",
            "category": "GANGER",
            "house": str(content_house.pk),
            "base_cost": "60",
        },
    )
    assert ganger_response.status_code == 302
    client.post(
        f"/pack/{pack.id}/add/fighter/stats/"
        f"?type=Goliath+Ganger&category=GANGER"
        f"&house_id={content_house.pk}&base_cost=60",
        {},
    )
    ganger = ContentFighter.objects.all_content().get(type="Goliath Ganger")
    ganger_pack_item = CustomContentPackItem.objects.get(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=ganger.pk,
    )

    url = reverse(
        "core:pack-fighter-default-gear-add", args=(pack.id, ganger_pack_item.id)
    )
    response = client.get(url)
    assert response.status_code == 200
    assert b"Goliath Mauler" in response.content


@pytest.mark.django_db
def test_default_assignment_post_accepts_pack_vehicle(
    client,
    user,
    pack,
    content_house,
    fighter_statline_type,
    vehicle_statline_type,
    vehicles_category,
    django_capture_on_commit_callbacks,
):
    """Posting a fighter-linked equipment to the default-equipment handler
    creates the default and enqueues propagation (issue #1803, building on
    #1725)."""
    client.force_login(user)
    _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    vehicle_equipment = ContentEquipment.objects.all_content().get(
        name="Goliath Mauler"
    )

    client.post(
        f"/pack/{pack.id}/add/fighter/",
        {
            "type": "Goliath Ganger",
            "category": "GANGER",
            "house": str(content_house.pk),
            "base_cost": "60",
        },
    )
    client.post(
        f"/pack/{pack.id}/add/fighter/stats/"
        f"?type=Goliath+Ganger&category=GANGER"
        f"&house_id={content_house.pk}&base_cost=60",
        {},
    )
    ganger = ContentFighter.objects.all_content().get(type="Goliath Ganger")
    ganger_pack_item = CustomContentPackItem.objects.get(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=ganger.pk,
    )

    url = reverse(
        "core:pack-fighter-default-gear-add", args=(pack.id, ganger_pack_item.id)
    )
    with patch(
        "gyrinx.core.models.list.propagate_default_child_fighter_assignment"
    ) as mock_task:
        with django_capture_on_commit_callbacks(execute=True):
            response = client.post(
                url, {"content_equipment": str(vehicle_equipment.id)}
            )
        assert response.status_code == 302
        default = ContentFighterDefaultAssignment.objects.get(
            fighter=ganger, equipment=vehicle_equipment
        )
        mock_task.enqueue.assert_called_once_with(default_assignment_id=str(default.pk))


@pytest.mark.django_db
def test_default_vehicle_assignment_spawns_child_when_fighter_hired(
    client,
    user,
    pack,
    content_house,
    fighter_statline_type,
    vehicle_statline_type,
    vehicles_category,
    make_list,
):
    """When a pack fighter has a default vehicle assignment, hiring that
    fighter on a subscribed list automatically spawns the child vehicle.

    This exercises the hire-time materialisation path
    (``create_linked_objects`` signal on ListFighter). For propagation to
    existing list-fighters of an already-subscribed gang see the
    ``test_propagate_default_child_fighter`` module.
    """
    client.force_login(user)
    vehicle_fighter = _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    vehicle_equipment = ContentEquipment.objects.all_content().get(
        name="Goliath Mauler"
    )

    # Add a custom ganger and give them a default vehicle assignment.
    client.post(
        f"/pack/{pack.id}/add/fighter/",
        {
            "type": "Goliath Driver",
            "category": "GANGER",
            "house": str(content_house.pk),
            "base_cost": "60",
        },
    )
    client.post(
        f"/pack/{pack.id}/add/fighter/stats/"
        f"?type=Goliath+Driver&category=GANGER"
        f"&house_id={content_house.pk}&base_cost=60",
        {},
    )
    driver = ContentFighter.objects.all_content().get(type="Goliath Driver")
    ContentFighterDefaultAssignment.objects.create(
        fighter=driver, equipment=vehicle_equipment
    )

    lst = make_list("Driving School", content_house=content_house)
    lst.packs.add(pack)

    # Hire the driver — child vehicle fighter should appear.
    ListFighter.objects.create(
        list=lst, content_fighter=driver, name="My Driver", owner=user
    )

    assert ListFighter.objects.filter(
        list=lst, content_fighter=vehicle_fighter
    ).exists(), (
        "default vehicle assignment did not materialise into a child fighter "
        "on the new list-fighter"
    )


# --- Pack detail rendering ----------------------------------------------------


@pytest.mark.django_db
def test_pack_detail_shows_inline_equipment_note_on_vehicle_fighter(
    client, user, pack, content_house, vehicle_statline_type, vehicles_category
):
    """The fighter card on the pack detail page contains an 'available as
    equipment' note with the cost."""
    client.force_login(user)
    _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    response = client.get(reverse("core:pack", args=(pack.id,)))
    assert response.status_code == 200
    content = response.content.decode()
    # Find the fighter card and look for the inline equipment note.
    idx = content.find("Goliath Mauler")
    assert idx >= 0
    # Look for an inline note marker near the fighter name.
    snippet = content[idx : idx + 800]
    assert "Available as equipment" in snippet or "150¢" in snippet


# --- Archive / restore cascade ------------------------------------------------


@pytest.mark.django_db
def test_archiving_pack_vehicle_cascades_to_companion_equipment(
    client, user, pack, content_house, vehicle_statline_type, vehicles_category
):
    """Archiving a pack vehicle/beast fighter must also archive its companion
    equipment's pack item. Otherwise the companion stays purchasable while
    the source fighter is hidden."""
    client.force_login(user)
    fighter = _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    fighter_pack_item = CustomContentPackItem.objects.get(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=fighter.pk,
    )
    companion = ContentEquipment.objects.all_content().get(
        auto_companion_for_fighter=fighter
    )
    companion_pack_item = CustomContentPackItem.objects.get(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentEquipment),
        object_id=companion.pk,
    )
    assert not companion_pack_item.archived

    response = client.post(
        reverse("core:pack-delete-item", args=(pack.id, fighter_pack_item.id))
    )
    assert response.status_code == 302

    fighter_pack_item.refresh_from_db()
    companion_pack_item.refresh_from_db()
    assert fighter_pack_item.archived
    assert companion_pack_item.archived


@pytest.mark.django_db
def test_restoring_pack_vehicle_cascades_to_companion_equipment(
    client, user, pack, content_house, vehicle_statline_type, vehicles_category
):
    """Restoring a previously-archived pack vehicle fighter must also restore
    its companion equipment's pack item."""
    client.force_login(user)
    fighter = _create_pack_fighter_full(
        client,
        pack,
        type_="Goliath Mauler",
        category="VEHICLE",
        base_cost=150,
        house_id=content_house.pk,
    )
    fighter_pack_item = CustomContentPackItem.objects.get(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentFighter),
        object_id=fighter.pk,
    )
    companion = ContentEquipment.objects.all_content().get(
        auto_companion_for_fighter=fighter
    )
    companion_pack_item = CustomContentPackItem.objects.get(
        pack=pack,
        content_type=ContentType.objects.get_for_model(ContentEquipment),
        object_id=companion.pk,
    )

    # Archive both via the cascade.
    client.post(reverse("core:pack-delete-item", args=(pack.id, fighter_pack_item.id)))
    fighter_pack_item.refresh_from_db()
    companion_pack_item.refresh_from_db()
    assert fighter_pack_item.archived and companion_pack_item.archived

    # Now restore the fighter pack item — companion should follow.
    response = client.post(
        reverse("core:pack-restore-item", args=(pack.id, fighter_pack_item.id))
    )
    assert response.status_code == 302

    fighter_pack_item.refresh_from_db()
    companion_pack_item.refresh_from_db()
    assert not fighter_pack_item.archived
    assert not companion_pack_item.archived


# --- Singular label override --------------------------------------------------


@pytest.mark.django_db
def test_add_fighter_page_uses_singular_label_override(client, user, pack):
    """The "Fighters & Vehicles" section can't mechanically singularise.

    Without the ``singular_label`` override on ``ContentTypeEntry``, the
    add-page title would render as "Add Fighters & Vehicle" (the dumb
    "-s" stripper trims the trailing "s"). The override should produce
    "Add Fighter or Vehicle" instead.
    """
    client.force_login(user)
    response = client.get(reverse("core:pack-add-item", args=(pack.id, "fighter")))
    assert response.status_code == 200
    body = response.content.decode()
    assert "Add Fighter or Vehicle" in body
    assert "Add Fighters & Vehicle" not in body
