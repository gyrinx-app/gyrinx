"""Unit tests for ULIDField, independent of any content model."""

import uuid as uuid_module

import pytest
from django.core.exceptions import ValidationError
from ulid import ULID

from n26.core.fields import ULIDField, to_ulid


class TestToULID:
    def test_accepts_a_ulid(self):
        value = ULID()
        assert to_ulid(value) is value

    @pytest.mark.parametrize(
        "convert",
        [
            pytest.param(str, id="base32-str"),
            pytest.param(lambda u: u.to_uuid(), id="uuid-object"),
            pytest.param(lambda u: str(u.to_uuid()), id="uuid-str"),
            pytest.param(lambda u: u.to_uuid().hex, id="uuid-hex"),
            pytest.param(lambda u: u.bytes, id="raw-bytes"),
        ],
    )
    def test_round_trips_every_accepted_form(self, convert):
        value = ULID()
        assert to_ulid(convert(value)) == value

    @pytest.mark.parametrize("bad", ["", "nonsense", "!!!", 12345, None])
    def test_rejects_junk(self, bad):
        with pytest.raises(ValueError):
            to_ulid(bad)


class TestULIDFieldConversion:
    def test_to_python_rejects_junk_as_a_validation_error(self):
        with pytest.raises(ValidationError):
            ULIDField().to_python("nonsense")

    def test_to_python_passes_through_empty(self):
        assert ULIDField().to_python(None) is None
        assert ULIDField().to_python("") is None

    def test_db_value_is_a_plain_uuid(self):
        value = ULID()
        prepped = ULIDField().get_db_prep_value(value, connection=None)
        assert isinstance(prepped, uuid_module.UUID)
        assert prepped == value.to_uuid()

    def test_deconstruct_round_trips(self):
        name, path, args, kwargs = ULIDField(primary_key=True).deconstruct()
        assert ULIDField(*args, **kwargs).primary_key is True


class TestMonotonicity:
    """python-ulid 4.x defaults to StrictMonotonicPolicy under a lock.

    This matters: it means ``ORDER BY id`` is exact creation order within a
    process, not merely millisecond-resolution. If a future release changes
    the default policy, this test is the tripwire.
    """

    def test_strictly_increasing_within_a_single_millisecond(self):
        batch = [ULID() for _ in range(5000)]
        same_ms = max(
            (
                [u for u in batch if u.timestamp == ts]
                for ts in {u.timestamp for u in batch}
            ),
            key=len,
        )
        assert len(same_ms) > 100, "test needs a decent same-millisecond run"
        rendered = [str(u) for u in same_ms]
        assert rendered == sorted(rendered)

    def test_uuid_conversion_preserves_sort_order(self):
        """Postgres compares `uuid` bytewise — this is what orders the index."""
        batch = [ULID() for _ in range(1000)]
        assert [str(u) for u in batch] == sorted(str(u) for u in batch)
        assert [u.to_uuid().bytes for u in batch] == sorted(
            u.to_uuid().bytes for u in batch
        )
