"""Issue #1992 — core model-save signal receivers must skip fixture loads.

``loaddata`` (and ``loaddata_overwrite``) save deserialized rows with
``raw=True`` while FK checks are disabled, so a receiver that dereferences a
relation can hit a row that isn't inserted yet, and side effects would corrupt
data the fixture already carries in its final state. Each test sends the
signal exactly as loaddata does — ``raw=True`` on an instance with dangling
FKs — and asserts every receiver on that sender skips cleanly.

The content-side counterparts live in
``test_pack_vehicles_beasts.test_companion_sync_skips_raw_fixture_saves`` and
``test_propagate_default_child_fighter.test_signal_skips_raw_fixture_saves``
(PR #1991, which motivated this sweep).
"""

import uuid

import pytest
from django.db.models.signals import post_save

from n23.core.models.list import (
    ListFighter,
    ListFighterEquipmentAssignment,
)


@pytest.mark.django_db
def test_list_fighter_receivers_skip_raw_fixture_saves(make_list):
    """``create_linked_objects`` (dereferences ``content_fighter`` and creates
    default assignments) and ``touch_list_modified_on_fighter_save`` (writes to
    the parent list) must both no-op on a raw save.

    The list is real so the touch handler's ``update()`` would be observable
    if its guard were removed; the ``content_fighter`` FK dangles, as it can
    mid-fixture."""
    lst = make_list("Raw Load Gang")
    modified_before = lst.modified

    fighter = ListFighter(
        id=uuid.uuid4(),
        name="Raw Fighter",
        content_fighter_id=uuid.uuid4(),
        list_id=lst.pk,
        owner_id=uuid.uuid4(),
    )

    post_save.send(
        sender=ListFighter,
        instance=fighter,
        created=True,
        raw=True,
        using="default",
    )

    lst.refresh_from_db()
    assert lst.modified == modified_before
    assert ListFighterEquipmentAssignment.objects.count() == 0


@pytest.mark.django_db
def test_assignment_receivers_skip_raw_fixture_saves():
    """``create_related_objects`` (dereferences ``content_equipment``, creates
    child fighters) and ``clear_fighter_cached_properties_for_assignment``
    (dereferences ``list_fighter``) must both no-op on a raw save with
    dangling FKs."""
    assignment = ListFighterEquipmentAssignment(
        id=uuid.uuid4(),
        list_fighter_id=uuid.uuid4(),
        content_equipment_id=uuid.uuid4(),
    )

    post_save.send(
        sender=ListFighterEquipmentAssignment,
        instance=assignment,
        created=True,
        raw=True,
        using="default",
    )

    assert ListFighter.objects.count() == 0
