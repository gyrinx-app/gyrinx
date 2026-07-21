"""Deterministic world builder for render-equivalence goldens.

Every value that would otherwise vary between two runs is pinned at its SOURCE
rather than regexed out of the rendered HTML afterwards. Regex-scrubbing works,
but each scrub is a class of change the harness can no longer see; pinning
keeps the comparison byte-exact.

  * UUID primary keys  -> see deterministic_uuids() below.
  * created / modified -> auto_now(_add) bypassed via queryset.update().
  * {% cachebuster %}  -> random.seed() before each request (test module).
  * CSRF token         -> scrubbed (cannot be pinned; see render_normalise).

GOTCHA that costs an afternoon: patching `uuid.uuid4` does NOT work.
`Base.id` is declared `models.UUIDField(default=uuid.uuid4)`, which binds the
function OBJECT at import time. By the time a test patches the `uuid` module the
field is already holding the original reference. The default must be replaced on
the FIELD.
"""

import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

from django.apps import apps

FROZEN = datetime(2020, 1, 1, 12, 0, 0, tzinfo=timezone.utc)


def _uuid_pk_fields():
    """Every concrete UUID pk field still using the uuid4 default."""
    for model in apps.get_models():
        pk = model._meta.pk
        if getattr(pk, "get_internal_type", lambda: "")() == "UUIDField":
            if pk.default is uuid.uuid4:
                yield pk


@contextmanager
def deterministic_uuids():
    """Swap every UUID pk default for a counter: 00000000-...-0001, -0002, ...

    Applies to ALL models, so objects created indirectly (equipment
    assignments, history rows, actions) are pinned too -- not just the ones the
    fixture names explicitly.
    """
    counter = iter(range(1, 1_000_000))
    fields = list(_uuid_pk_fields())
    for field in fields:
        field.default = lambda: uuid.UUID(int=next(counter))
    try:
        yield
    finally:
        for field in fields:
            field.default = uuid.uuid4


def freeze_timestamps():
    """Stamp created/modified to FROZEN. queryset.update() skips auto_now."""
    for model in apps.get_models():
        names = {f.name for f in model._meta.fields}
        stamp = {f: FROZEN for f in ("created", "modified") if f in names}
        if stamp and model._meta.managed:
            try:
                model.objects.all().update(**stamp)
            except Exception:  # unmanaged / historical tables without the column
                pass
