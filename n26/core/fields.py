"""
ULID primary keys.

A ULID is 128 bits — a 48-bit big-endian millisecond timestamp followed by 80
random bits — canonically rendered as 26 Crockford Base32 characters. Same
width as a UUID, so we store it in a native Postgres ``uuid`` column (16
bytes) and get the ORM, index, and psycopg support for free.

Why not a ``CharField(26)``: it would be 27 bytes on disk, collate under the
database's text collation, and compare far more slowly in a B-tree.

Because the timestamp occupies the high-order bytes and Postgres compares
``uuid`` values bytewise, ``ORDER BY id`` is creation order, and inserts land at
the right-hand edge of the index rather than scattering across it like UUIDv4.
That locality is the main practical win: published benchmarks put time-ordered
keys around 28% ahead of UUIDv4 on insert throughput, mostly because a random
key forces the whole PK index to stay resident in the buffer cache.

Ordering is exact, not just millisecond-resolution: ``python-ulid`` 4.x
generates through a lock-guarded ``StrictMonotonicPolicy``, which increments
the random component for IDs minted in the same millisecond. Two caveats —
that guarantee is per-process, so IDs from different workers only order to the
millisecond; and the strict policy raises if the 80-bit random component
overflows within one millisecond, which needs a wildly implausible burst.
``n26/tests.py`` pins both behaviours in case a future release changes the
default policy.

Python-side values are :class:`ulid.ULID`, rendering as the 26-character Base32
form — which is what the Django admin puts in its URLs. Lookups accept either
that or the UUID form. In ``psql`` you will see the hyphenated UUID rendering
of the same bytes; :func:`ulid.ULID.from_uuid` converts back.

If this ever grows a DRF layer, note that DRF will introspect this as a
``UUIDField`` and serialise the UUID form unless told otherwise — decide
deliberately which form is the API contract.
"""

import uuid as uuid_module

from django.core.exceptions import ValidationError
from django.db import models
from ulid import ULID


def to_ulid(value):
    """Coerce ``value`` to a :class:`~ulid.ULID`, or raise ``ValueError``.

    Accepts a ULID, a ``uuid.UUID``, 16 raw bytes, a 26-character Base32
    string, or a 32/36-character hex UUID string.
    """
    if isinstance(value, ULID):
        return value
    if isinstance(value, uuid_module.UUID):
        return ULID.from_uuid(value)
    if isinstance(value, (bytes, bytearray, memoryview)):
        return ULID.from_bytes(bytes(value))
    if isinstance(value, str):
        text = value.strip()
        if len(text) == 26:
            return ULID.from_str(text)
        return ULID.from_uuid(uuid_module.UUID(text))
    raise ValueError(f"Cannot interpret {value!r} as a ULID")


class ULIDField(models.UUIDField):
    """A ULID stored in a native Postgres ``uuid`` column."""

    description = "Universally Unique Lexicographically Sortable Identifier"
    default_error_messages = {
        "invalid": "“%(value)s” is not a valid ULID.",
    }

    def __init__(self, *args, **kwargs):
        kwargs.setdefault("default", ULID)
        super().__init__(*args, **kwargs)

    def from_db_value(self, value, expression, connection):
        if value is None:
            return None
        return to_ulid(value)

    def to_python(self, value):
        if value is None or value == "":
            return None
        try:
            return to_ulid(value)
        except (ValueError, AttributeError, TypeError):
            raise ValidationError(
                self.error_messages["invalid"],
                code="invalid",
                params={"value": value},
            ) from None

    def get_prep_value(self, value):
        # Deliberately skips UUIDField.get_prep_value, which would coerce to
        # uuid.UUID and lose the ULID type on the way back out.
        return self.to_python(value)

    def get_db_prep_value(self, value, connection, prepared=False):
        value = self.to_python(value)
        if value is None:
            return None
        return value.to_uuid()

    def value_to_string(self, obj):
        """Serialise as the canonical 26-character form (``dumpdata``)."""
        value = self.value_from_object(obj)
        return "" if value is None else str(value)
