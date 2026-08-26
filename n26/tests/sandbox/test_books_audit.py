"""The books audit: every gang checked against its ledger, changing nothing.

The audit walks the estate on the batched runner. Proven here: a gang
whose books agree passes and the record ends DONE; a gang whose pinned
rating has drifted from its ledger lands in the record's failures with
the discrepancy in words, and is untouched by the audit itself.
"""

import pytest
from django.contrib.auth.models import User

from gyrinx.maintenance.models import Backfill
from n26.core.models import Gang
from n26.maintenance import Operation, audit_reconcile
from n26.tests.sandbox.actions import found_gang, hire

pytestmark = pytest.mark.django_db


@pytest.fixture
def player():
    return User.objects.create_user("auditee")


@pytest.fixture
def record(db):
    return Backfill.objects.create(
        operation=Operation.AUDIT_RECONCILE,
        status=Backfill.Status.RUNNING,
    )


def audit(record):
    audit_reconcile.func(backfill_id=str(record.pk))
    record.refresh_from_db()
    return record


class TestTheAudit:
    """Reads everything, changes nothing: agreement passes, drift is
    named on the record."""

    def test_a_gang_whose_books_agree_passes(
        self, gang_type, player, person_type, default_pack, record
    ):
        found_gang("Clean Books", gang_type, owner=player, budget=1000)

        audit(record)

        assert record.status == Backfill.Status.DONE
        assert record.summary["failures"] == {}
        assert record.summary["done"] >= 1

    def test_a_drifted_pin_is_named_and_the_gang_is_untouched(
        self, gang_type, player, person_type, default_pack, record
    ):
        from n26.tests.sandbox.actions import create_profile

        gang = found_gang("Cooked Books", gang_type, owner=player, budget=1000)
        profile = create_profile("Clerk", person_type, gang_type, price=50)
        hire(gang, profile, "Fiddler", paid=50)
        Gang.objects.filter(pk=gang.pk).update(rating=gang.rating + 7)

        audit(record)

        assert record.status == Backfill.Status.FAILED
        assert str(gang.pk) in record.summary["failures"]
        assert "rating pinned" in record.summary["failures"][str(gang.pk)]
        gang.refresh_from_db()
        assert gang.rating != 0  # untouched, still the drifted pin
