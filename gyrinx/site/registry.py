"""Broadcast audience registration shared by both editions.

Editions register labels, optional form fields and recipient querysets from
their admin packages. This avoids platform imports of edition models. The
all-active-users audience registers at import time and appears first.
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
    """A broadcast audience and its recipient lookup.

    recipients receives cleaned_data and returns a user queryset. Optional
    field_name and field provide a qualifying input, required only when this
    audience is selected.
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
