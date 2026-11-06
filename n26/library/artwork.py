"""Bind N26 artwork uploads to an edition-specific storage folder.

``gyrinx.artwork`` validates addresses and reads bytes from the site's own
storage; it does not fetch arbitrary URLs. Rendering sanitises markup in
``n26.core.templatetags.artwork``.
"""

from gyrinx.artwork import (
    MAX_BYTES,
    NOT_OURS,
    read,
    storage_bases,
    storage_key,
)
from gyrinx.artwork import clean_onto as _clean_onto
from gyrinx.artwork import store as _store

#: Where an uploaded gang type icon is written inside the site's storage.
UPLOAD_PREFIX = "gang-type-icons/"

__all__ = [
    "MAX_BYTES",
    "NOT_OURS",
    "UPLOAD_PREFIX",
    "clean_onto",
    "read",
    "storage_bases",
    "storage_key",
    "store",
]


def store(upload):
    """Put an uploaded icon in this edition's folder; return its address."""
    return _store(upload, prefix=UPLOAD_PREFIX)


def clean_onto(form, cleaned, name, upload_name):
    """Settle an icon address field from its two controls, in place."""
    return _clean_onto(form, cleaned, name, upload_name, prefix=UPLOAD_PREFIX)
