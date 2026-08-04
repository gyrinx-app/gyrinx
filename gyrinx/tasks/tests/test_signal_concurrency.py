"""Concurrency: two simultaneous deliveries hitting the lifecycle signals.

The signal handlers are check-then-act — they read the execution's status and
then transition on the strength of it. Every step they take is a legal
transition on its own, so the state machine's row lock cannot catch two
deliveries interleaving *here*; the handlers need their own lock.

The FAILED case is the one that bites. A redelivery of a FAILED execution is a
retry, so the handler resets the record to READY before marking it RUNNING. Two
concurrent retries could both read FAILED, both reset, and both mark RUNNING,
leaving two RUNNING transitions for one attempt. These tests run the handlers on
separate threads against a real (committed) database, as a concurrent Pub/Sub
redelivery would.
"""

import threading

import pytest
from django.db import connection
from django.utils import timezone

from gyrinx.tasks.models import TaskExecution
from gyrinx.tasks.signals import handle_task_started

TRANSITIONS = TaskExecution.states.transition_model


class _Delivery:
    """The only thing the lifecycle handlers read off a TaskResult."""

    def __init__(self, task_id):
        self.id = task_id


def _run_concurrently(target, *, n=2, timeout=15):
    """Run ``target`` on ``n`` threads and return whatever they raised."""
    errors = []

    def wrapped():
        try:
            target()
        except Exception as e:  # noqa: BLE001 - surface, don't swallow
            errors.append(e)
        finally:
            # Each thread has its own connection; leaving it open strands it.
            connection.close()

    threads = [threading.Thread(target=wrapped) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join(timeout=timeout)

    stuck = [t for t in threads if t.is_alive()]
    assert not stuck, (
        f"{len(stuck)} delivery thread(s) did not finish within {timeout}s (deadlock?)"
    )
    return errors


def _make_execution(task_id="dup"):
    return TaskExecution.objects.create(
        task_id=task_id,
        task_name="_concurrency_probe",
        args=[],
        kwargs={},
        enqueued_at=timezone.now(),
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_retries_of_a_failed_execution_start_once():
    """Two simultaneous retries of a FAILED execution produce one RUNNING."""
    execution = _make_execution()
    execution.mark_running()
    execution.mark_failed(error_message="transient boom")
    assert execution.status == "FAILED"

    # Clear the setup's transitions so the count below is only the race.
    TRANSITIONS.objects.all().delete()

    errors = _run_concurrently(
        lambda: handle_task_started(sender=None, task_result=_Delivery("dup"))
    )

    assert not errors, f"delivery thread(s) raised: {errors!r}"
    execution.refresh_from_db()
    assert execution.status == "RUNNING"
    assert TRANSITIONS.objects.count() == 1, (
        "the second retry should have seen the first's RUNNING and skipped"
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_deliveries_start_once():
    """The same guarantee from READY: a duplicate delivery of a fresh execution
    marks it RUNNING once rather than twice."""
    execution = _make_execution(task_id="fresh")
    assert execution.status == "READY"

    errors = _run_concurrently(
        lambda: handle_task_started(sender=None, task_result=_Delivery("fresh"))
    )

    assert not errors, f"delivery thread(s) raised: {errors!r}"
    execution.refresh_from_db()
    assert execution.status == "RUNNING"
    assert TRANSITIONS.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_missing_execution_is_logged_not_raised():
    """An unknown task_id stays a warning even with the handler now atomic —
    a raise here 500s the prod push handler into a redelivery storm."""
    handle_task_started(sender=None, task_result=_Delivery("never-enqueued"))

    assert not TaskExecution.objects.filter(task_id="never-enqueued").exists()
