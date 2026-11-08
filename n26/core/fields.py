"""ULID primary keys stored in PostgreSQL UUID columns.

ULIDs contain a 48-bit millisecond timestamp and 80 random bits. Their
128-bit representation fits the native UUID column; Python values display
as 26 Crockford Base32 characters. Lookups accept either Base32 or UUID
text, and database tools display the UUID representation.

Timestamp-leading bytes keep indexes ordered by creation millisecond. The
pinned python-ulid generator also orders IDs monotonically within one
process, including IDs generated in the same millisecond. Across processes,
only millisecond ordering is guaranteed. Exhausting the random component
within a millisecond raises an error.

This field inherits UUIDField, so serializers that infer types from that
base need explicit handling when their contract requires Base32 output.
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
        except ValueError, AttributeError, TypeError:
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
