"""Register analytics nouns and derive the edition for each event.

A noun value belongs to one edition; conflicting registrations raise
ImproperlyConfigured during startup. Unknown nouns are logged and recorded
under UNKNOWN so event collection can continue without misclassifying them.
Editions register through modules imported by their app configs.
"""

import logging
from collections import defaultdict

from django.core.exceptions import ImproperlyConfigured
from django.db import models

__all__ = [
    "Edition",
    "PlatformNoun",
    "edition_for_noun",
    "noun_choices",
    "register_nouns",
    "registered_nouns",
]

logger = logging.getLogger(__name__)


class Edition(models.TextChoices):
    """The event source: an edition, shared platform activity, or an unknown noun."""

    PLATFORM = "platform", "Platform"
    N23 = "n23", "N23"
    N26 = "n26", "N26"
    UNKNOWN = "unknown", "Unknown"


#: noun value -> (edition, human label)
_nouns: dict[str, tuple[str, str]] = {}


def register_nouns(edition, nouns) -> None:
    """Register noun values and labels for one edition.

    Accept TextChoices or an iterable of value-label pairs. Re-registration
    within the same edition updates labels; cross-edition reuse raises
    ImproperlyConfigured.
    """
    edition = Edition(edition).value
    pairs = getattr(nouns, "choices", nouns)
    for value, label in pairs:
        held = _nouns.get(value)
        if held is not None and held[0] != edition:
            raise ImproperlyConfigured(
                f"Event noun {value!r} is already registered to the "
                f"{held[0]!r} edition and cannot also mean something in "
                f"{edition!r}. Two editions sharing a noun would make the "
                f"edition of a stored event unknowable — pick a different word."
            )
        _nouns[value] = (edition, label)


def registered_nouns() -> dict[str, tuple[str, str]]:
    """Every registered noun, mapped to its edition and label."""
    return dict(_nouns)


def edition_for_noun(noun) -> str:
    """The edition that claimed ``noun``, or ``UNKNOWN`` if nobody did.

    Never raises: this runs on the write path of every event, and an event
    that cannot be classified must still be recorded.
    """
    held = _nouns.get(str(noun) if noun is not None else "")
    if held is None:
        logger.error(
            "Event noun %r belongs to no edition — recording it as unknown. "
            "Register it with gyrinx.analytics.nouns.register_nouns.",
            noun,
        )
        return Edition.UNKNOWN.value
    return held[0]


def noun_choices():
    """Return Event.noun choices grouped by edition.

    Resolve registrations after app startup. Migrations store this callable,
    so adding a noun does not require a new migration.
    """
    grouped: dict[str, list[tuple[str, str]]] = defaultdict(list)
    for value, (edition, label) in _nouns.items():
        grouped[edition].append((value, label))
    return [(Edition(edition).label, pairs) for edition, pairs in grouped.items()]


class PlatformNoun(models.TextChoices):
    """Things that belong to the site rather than to either edition."""

    USER = "user", "User"
    BANNER = "banner", "Banner"


register_nouns(Edition.PLATFORM, PlatformNoun)
