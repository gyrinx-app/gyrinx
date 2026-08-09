"""Extension point: the nouns an event may be recorded against, and the
edition each noun belongs to.

The platform owns the event log, but it does not own the words. "List" and
"fighter" mean something in one edition; "gang" and "model" mean something in
another; "user" and "banner" belong to neither, because an account and a
site-wide announcement are the same thing whichever edition you are reading.
So each edition declares its own nouns here and the platform stores what it is
told.

Two rules make the arrangement work:

- **A noun value belongs to exactly one edition.** Registering a value a
  different edition already claimed raises at import, so the app refuses to
  boot rather than filing one edition's rows under another's word. This is
  what lets the edition be *derived* from the noun instead of passed in: there
  is no edition argument to thread through several hundred call sites, and so
  none to forget.
- **A noun nobody registered is recorded as** :attr:`Edition.UNKNOWN`, with an
  error in the log. The row still lands — tracking must not break the thing it
  observes — but it lands in a bucket of its own rather than being guessed into
  a real edition, so a missing registration shows up as a visible slice on the
  dashboard instead of a quietly wrong graph.

Editions register from a module their app config imports, so registration is
complete before any request is served — ``n23.core.events`` and
``n26.analytics``.
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
    """Which product an event came from.

    ``PLATFORM`` is a real answer, not a fallback: signing in, changing an
    email address and dismissing a site banner happen on the way to both
    editions and belong to neither. ``UNKNOWN`` is the fallback, and seeing it
    in the data means a noun was recorded that no edition claimed.
    """

    PLATFORM = "platform", "Platform"
    N23 = "n23", "N23"
    N26 = "n26", "N26"
    UNKNOWN = "unknown", "Unknown"


#: noun value -> (edition, human label)
_nouns: dict[str, tuple[str, str]] = {}


def register_nouns(edition, nouns) -> None:
    """Claim a set of noun values for ``edition``.

    ``nouns`` is anything with ``.choices`` (a ``TextChoices`` class) or an
    iterable of ``(value, label)`` pairs.

    Re-registering the same value for the same edition is allowed and does
    nothing; claiming one another edition already holds is a configuration
    error, because the stored noun is what says which edition a row came from.
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
    """The ``choices`` for ``Event.noun``, grouped by edition.

    A callable rather than a list because editions register during startup,
    after this module is imported, and because the set of nouns is then not a
    database concern — the migration records the callable, so adding a noun
    never writes one.
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
