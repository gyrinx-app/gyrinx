"""Extension point: who a notification broadcast can be addressed to.

The broadcast page is platform furniture, but most useful audiences are
edition-shaped ("everyone in this campaign"). Rather than have the platform
import edition models to offer them, each audience is registered here: a label
for the dropdown, an optional extra form field to qualify it, and a callable
that turns the submitted form data into a queryset of users.

The platform contributes "All active users" at the bottom of this module, so it
is always first in the dropdown no matter when editions register theirs — they
have to import this module to register, which runs that line first. Editions
register from their admin package (see ``n23/core/admin/broadcast.py``).
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass

from django import forms
from django.contrib.auth import get_user_model
from django.db.models import QuerySet

__all__ = [
    "BroadcastAudience",
    "broadcast_audiences",
    "get_broadcast_audience",
    "register_broadcast_audience",
]

User = get_user_model()


@dataclass(frozen=True)
class BroadcastAudience:
    """One option in the broadcast form's "audience" dropdown.

    ``recipients`` receives the form's ``cleaned_data`` and returns the users to
    notify. An audience that needs qualifying — which campaign? — declares
    ``field_name`` plus a ``field`` factory; the form adds that field, and
    requires it only when this audience is the one selected.
    """

    key: str
    label: str
    recipients: Callable[[Mapping], QuerySet]
    field_name: str | None = None
    #: Called per form instance — form fields are stateful, so never share one.
    field: Callable[[], forms.Field] | None = None
    field_required_error: str = "This is required for the selected audience."


_audiences: dict[str, BroadcastAudience] = {}


def register_broadcast_audience(audience: BroadcastAudience) -> None:
    """Offer ``audience`` on the broadcast page, replacing any with its key."""
    _audiences[audience.key] = audience


def broadcast_audiences() -> tuple[BroadcastAudience, ...]:
    """Every registered audience, in registration order (= dropdown order)."""
    return tuple(_audiences.values())


def get_broadcast_audience(key: str) -> BroadcastAudience | None:
    return _audiences.get(key)


def _all_active_users(cleaned_data):
    return User.objects.filter(is_active=True)


# The platform's own audience. Registered at import time so it leads the
# dropdown regardless of the order editions are autodiscovered in.
register_broadcast_audience(
    BroadcastAudience(
        key="all_active",
        label="All active users",
        recipients=_all_active_users,
    )
)
