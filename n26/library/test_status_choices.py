"""Authored status conditions and the standard-content upgrade."""

from importlib import import_module
from types import SimpleNamespace

import pytest
from django.apps import apps
from django.db import connection

from n26.core.status import Status
from n26.library.authoring import (
    create_pack,
    create_pickable,
    create_slot_type,
    ef_adds,
    has_status,
    modifier,
    revise,
    targets_every_model,
)
from n26.library.models import HasStatus, Modifier, Pickable, Slot
from n26.library.standard_content import STANDARD_CONTENT

pytestmark = pytest.mark.django_db


def test_status_condition_is_authored_and_compiled(default_pack, gang_type):
    from n26.core import select

    condition = has_status(Status.CAPTURED)
    scope = targets_every_model(condition)
    assert HasStatus.objects.get(scope=scope).status == Status.CAPTURED
    selector = scope.as_selector()
    assert selector.matches(select.Matchable(thing=None, status=Status.CAPTURED))
    assert not selector.matches(select.Matchable(thing=None, status=Status.RECOVERY))


def test_standard_upgrade_is_idempotent_and_leaves_other_packs(default_pack, gang_type):
    STANDARD_CONTENT["lasting-effect-tables"].create()
    escape = Slot.objects.get(name="Escape")
    captured = Pickable.objects.get(name="Captured", slot_type__name="Lasting Injury")
    revise(captured, record_only=False)
    revise(escape, follows_status=False)
    modifier(
        "Old capture grant", targets_every_model(), ef_adds(escape), attach_to=captured
    )
    homebrew = create_pack("Homebrew")
    other = create_pickable(
        "Captured", create_slot_type("Lasting Injury", pack=homebrew), pack=homebrew
    )
    upgrade = import_module(
        "n26.library.migrations.0120_status_follow_up_choices"
    ).update_standard_choices
    editor = SimpleNamespace(connection=connection)
    upgrade(apps, editor)
    count = Modifier.objects.count()
    upgrade(apps, editor)
    assert Modifier.objects.count() == count
    captured.refresh_from_db()
    escape.refresh_from_db()
    other.refresh_from_db()
    assert captured.record_only and escape.follows_status
    assert not other.record_only
    assert not captured.modifiers.filter(adds_assignable__slot=escape).exists()
    grant = gang_type.modifiers.get(name="Captured models: Escape")
    assert grant.targets_miniature.has_status.get().status == Status.CAPTURED
