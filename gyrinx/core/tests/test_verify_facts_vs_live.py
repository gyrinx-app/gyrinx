"""Tests for the `verify_facts_vs_live` read-only drift harness (#1860 Stage 0)."""

from io import StringIO

import pytest
from django.core.management import call_command
from django.core.management.base import CommandError

from gyrinx.core.models.list import List


def _run(**kwargs):
    """Run the harness, returning (stdout, raised_command_error_or_None)."""
    out = StringIO()
    error = None
    try:
        call_command("verify_facts_vs_live", stdout=out, **kwargs)
    except CommandError as exc:
        error = exc
    return out.getvalue(), error


@pytest.mark.django_db
def test_in_sync_list_reports_no_mismatch(
    make_list, make_list_fighter, content_fighter
):
    lst = make_list("In Sync")
    make_list_fighter(lst, "Ganger", content_fighter=content_fighter)
    # Reconcile the persisted facts cache so it matches the live recompute.
    lst.facts_from_db(update=True)

    output, error = _run(owner=lst.owner.username)

    assert error is None, output
    assert "0 mismatch(es)" in output
    assert "MISMATCH" not in output


@pytest.mark.django_db
def test_drifted_rating_is_detected(make_list, make_list_fighter, content_fighter):
    lst = make_list("Drifted")
    make_list_fighter(lst, "Ganger", content_fighter=content_fighter)
    # Start in sync...
    lst.facts_from_db(update=True)
    live_rating = lst.rating_current

    # ...then artificially drift the persisted rating_current WITHOUT marking
    # the list dirty (QuerySet.update bypasses signals), simulating real drift.
    wrong_rating = live_rating + 999
    List.objects.filter(pk=lst.pk).update(rating_current=wrong_rating, dirty=False)

    output, error = _run(owner=lst.owner.username)

    # Non-zero exit (CommandError) on any mismatch.
    assert error is not None
    assert "1 mismatch(es)" in output
    assert "MISMATCH" in output
    assert str(lst.pk) in output
    # The reported delta is persisted - live = +999.
    assert "delta=+999" in output


@pytest.mark.django_db
def test_harness_does_not_write(make_list, make_list_fighter, content_fighter):
    """The harness must never mutate persisted facts, even when drift exists."""
    lst = make_list("No Writes")
    make_list_fighter(lst, "Ganger", content_fighter=content_fighter)
    lst.facts_from_db(update=True)
    drifted = lst.rating_current + 500
    List.objects.filter(pk=lst.pk).update(rating_current=drifted, dirty=False)

    _run(owner=lst.owner.username)

    # The drifted value is still present and dirty is untouched — nothing was
    # repaired or recomputed into the DB by the read-only harness.
    fresh = List.objects.get(pk=lst.pk)
    assert fresh.rating_current == drifted
    assert fresh.dirty is False


@pytest.mark.django_db
def test_list_id_filter_unknown_id_errors():
    _, error = _run(list_id="00000000-0000-0000-0000-000000000000")
    assert error is not None
    assert "No list found" in str(error)
