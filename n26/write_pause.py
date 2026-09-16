"""The n26 boundary onto the platform's write-pause service."""

from functools import wraps

from django.db import transaction

from gyrinx.site.write_pause import (
    WritesPaused,
    bind_paused_consumer,
    exclusive_write_scope,
    pause_scope,
    pause_status,
    register_write_scope,
    release_paused_consumer,
    resume_scope,
)
from gyrinx.site.write_pause import (
    require_paused_consumer as _require_paused_consumer,
)
from gyrinx.site.write_pause import (
    write_guard as _write_guard,
)

SCOPE = "n26"

register_write_scope(
    SCOPE,
    path_prefixes=("/n26/",),
    admin_app_labels=("n26", "library"),
)


def write_guard():
    """Admit one n26 transaction, or refuse while its scope is paused."""
    return _write_guard(SCOPE)


def guarded_write(function):
    """Put a public n26 write service behind the transaction barrier."""

    @wraps(function)
    def guarded(*args, **kwargs):
        with transaction.atomic(), write_guard():
            return function(*args, **kwargs)

    return guarded


def require_paused_consumer(*, run_id, generation):
    """Require this delivery's exact n26 paused-run authorisation."""
    return _require_paused_consumer(SCOPE, run_id=run_id, generation=generation)


__all__ = [
    "SCOPE",
    "WritesPaused",
    "bind_paused_consumer",
    "exclusive_write_scope",
    "guarded_write",
    "pause_scope",
    "pause_status",
    "release_paused_consumer",
    "require_paused_consumer",
    "resume_scope",
    "write_guard",
]
