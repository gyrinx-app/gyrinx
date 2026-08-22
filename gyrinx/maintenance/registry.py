"""Extension point: which repairs the maintenance console offers.

The console itself is platform furniture — a superuser-gated index, an audit
record per run, a detail page, a cancel button. What it can actually repair is
edition knowledge, so each repair is registered rather than hard-coded: a name
and description for the index, a view for its own trigger page, and optionally
a template fragment that renders that operation's summary on the detail page.

Registration also carries the ``operation`` slug written into
``Backfill.operation``, which is how a historical record recovers its label.
Retired operations stay registered with ``view=None`` — no page, no index row,
but old records still render a name instead of a bare slug.

Editions register from their admin package (see ``n23/core/admin/maintenance.py``).
Note what they must *not* import: ``gyrinx.maintenance.admin`` patches
``admin.site.__class__`` at import time and has to run after
``gyrinx.analytics.admin`` to compose with it. Editions are autodiscovered
first, so importing that module from an edition would install the maintenance
site too early and analytics would then overwrite it, silently dropping every
maintenance route. Import from this module and ``gyrinx.maintenance.views``
instead — neither touches the admin site.
"""

import datetime
from collections.abc import Callable
from dataclasses import dataclass

__all__ = [
    "MaintenanceOperation",
    "all_operations",
    "operation_label",
    "operations",
    "register_operation",
    "resolve_operation",
]


@dataclass(frozen=True)
class MaintenanceOperation:
    """One repair the console knows about.

    ``operation`` is the slug stored on the ``Backfill`` records this repair
    produces, and the registry's key. ``slug`` is the URL-facing name, defaulting
    to ``operation``; the two differ where a URL has already been published under
    a different name.

    A ``view`` of ``None`` means retired: the entry exists only so historical
    records keep their label.
    """

    operation: str
    name: str
    description: str = ""
    view: Callable | None = None
    slug: str | None = None
    #: Template rendering this operation's ``summary`` on the detail page.
    detail_template: str | None = None
    #: The day this repair was offered, which the index sorts newest first.
    #: One-off repairs accumulate and are nearly always run soon after being
    #: written, so the newest is the one somebody has come to the page for.
    #: Stated rather than derived: a repair has a date before it has ever run,
    #: and that is exactly when it needs to be easy to find.
    added: datetime.date | None = None

    @property
    def url_slug(self) -> str:
        return self.slug or self.operation

    @property
    def route(self) -> str:
        """Path this operation's page is mounted at, under the admin site."""
        return f"maintenance/{self.url_slug.replace('_', '-')}/"

    @property
    def url_name(self) -> str:
        """Name to reverse as ``admin:<url_name>``."""
        return f"maintenance_{self.url_slug}"


_operations: dict[str, MaintenanceOperation] = {}


def register_operation(operation: MaintenanceOperation) -> None:
    """Offer ``operation`` in the console, replacing any with the same slug."""
    _operations[operation.operation] = operation


def operations() -> tuple[MaintenanceOperation, ...]:
    """Runnable operations, in registration order — the index and the routes."""
    return tuple(op for op in _operations.values() if op.view is not None)


def all_operations() -> tuple[MaintenanceOperation, ...]:
    """Every registered operation, retired ones included."""
    return tuple(_operations.values())


def resolve_operation(operation: str | None) -> MaintenanceOperation | None:
    return _operations.get(operation) if operation else None


def operation_label(operation: str) -> str:
    """Display name for a stored slug, falling back to the slug itself."""
    known = _operations.get(operation)
    return known.name if known else operation
