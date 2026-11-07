"""Register edition repairs for the shared maintenance console.

Registrations provide a stored operation slug, display text, trigger view
and optional result template. Retired operations use view=None so historical
records retain their labels without exposing a trigger page.

Editions register from their admin packages. Import this module or
gyrinx.maintenance.views, never gyrinx.maintenance.admin: that module patches
admin.site after analytics admin initialisation. Importing it earlier would
allow analytics to replace the maintenance routes.
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
    """A registered repair and its console metadata.

    operation is the registry key and the value stored on Backfill records.
    slug optionally preserves a different URL name. view=None retires the
    trigger page while retaining labels for historical records.
    """

    operation: str
    name: str
    description: str = ""
    view: Callable | None = None
    slug: str | None = None
    #: Template rendering this operation's ``summary`` on the detail page.
    detail_template: str | None = None
    #: Sort the console by release date, including repairs that have never run.
    added: datetime.date | None = None
    #: Registered write scope this operation mutates. Used by platform middleware.
    write_scope: str | None = None

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
