"""Where a gang type's icon lives — this edition's corner of the site's storage.

The mechanism is the platform's (``gyrinx.artwork``): what an address is allowed
to name, and how bytes come back from it, is a property of the site's storage
rather than of this edition's content. What is edition-specific is only the
folder uploads land in, which this module binds so no call site has to remember
it.

The rules that matter are stated where they are enforced. Two worth knowing from
here: an address is resolved against this site's own storage and never fetched,
so a pasted address cannot make the server reach anything; and the markup is
cleaned at render (``n26.core.templatetags.artwork``), not on the way in.
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
