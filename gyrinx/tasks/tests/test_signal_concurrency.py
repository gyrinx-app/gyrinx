"""Concurrent task lifecycle signals must record each transition once.

Hold the execution lock across status checks and transitions, including
the FAILED-to-READY reset before retries.
"""

import threading

import pytest
from django.db import connection
from django.tasks.base import TaskResultStatus
from django.utils import timezone

from gyrinx.tasks.models import TaskExecution
from gyrinx.tasks.signals import handle_task_finished, handle_task_started

pytestmark = pytest.mark.core

TRANSITIONS = TaskExecution.states.transition_model


class _Delivery:
    """The fields the lifecycle handlers read off a TaskResult."""

    def __init__(self, task_id, status=None, return_value=None, errors=()):
        self.id = task_id
        self.status = status
        self._return_value = return_value
        self.errors = list(errors)


class _Error:
    """Stands in for a TaskError; the handler reads the traceback off it."""

    def __init__(self, traceback):
        self.traceback = traceback


def _run_concurrently(target, *, n=2, timeout=15):
    """Release n delivery threads together and return their raised exceptions.

    The barrier increases the chance that delivery handlers overlap.
    """
    errors = []
    start = threading.Barrier(n, timeout=timeout)

    def wrapped():
        try:
            start.wait()
            target()
        except Exception as e:  # noqa: BLE001 - surface, don't swallow
            errors.append(e)
        finally:
            # Close each delivery thread's database connection when it finishes.
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

    execution = _make_execution()
    execution.mark_running()
    execution.mark_failed(error_message="transient boom")
    assert execution.status == "FAILED"
    before = TRANSITIONS.objects.filter(instance=execution).count()

    errors = _run_concurrently(
        lambda: handle_task_started(sender=None, task_result=_Delivery("dup"))
    )

    assert not errors, f"delivery thread(s) raised: {errors!r}"
    execution.refresh_from_db()
    assert execution.status == "RUNNING"
    started = TRANSITIONS.objects.filter(instance=execution).count() - before
    assert started == 1, (
        "the second retry should have seen the first's RUNNING and skipped"
    )


@pytest.mark.django_db(transaction=True)
def test_concurrent_first_deliveries_start_once():

    execution = _make_execution(task_id="fresh")
    assert execution.status == "READY"

    errors = _run_concurrently(
        lambda: handle_task_started(sender=None, task_result=_Delivery("fresh"))
    )

    assert not errors, f"delivery thread(s) raised: {errors!r}"
    execution.refresh_from_db()
    assert execution.status == "RUNNING"
    assert TRANSITIONS.objects.filter(instance=execution).count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_finishes_record_one_success():
    """Concurrent successful finishes must settle once without an invalid second transition."""
    execution = _make_execution(task_id="finish-ok")
    execution.mark_running()
    before = TRANSITIONS.objects.filter(instance=execution).count()

    delivery = _Delivery(
        "finish-ok",
        status=TaskResultStatus.SUCCESSFUL,
        return_value={"ok": True},
    )
    errors = _run_concurrently(
        lambda: handle_task_finished(sender=None, task_result=delivery)
    )

    assert not errors, f"delivery thread(s) raised: {errors!r}"
    execution.refresh_from_db()
    assert execution.status == "SUCCESSFUL"
    assert execution.return_value == {"ok": True}
    assert execution.finished_at is not None
    settled = TRANSITIONS.objects.filter(instance=execution).count() - before
    assert settled == 1, "the second finish should have seen the first and skipped"


@pytest.mark.django_db(transaction=True)
def test_concurrent_finishes_record_one_failure():

    execution = _make_execution(task_id="finish-bad")
    execution.mark_running()
    before = TRANSITIONS.objects.filter(instance=execution).count()

    delivery = _Delivery(
        "finish-bad",
        status=TaskResultStatus.FAILED,
        errors=[_Error('  File "t.py", line 1\nValueError: boom')],
    )
    errors = _run_concurrently(
        lambda: handle_task_finished(sender=None, task_result=delivery)
    )

    assert not errors, f"delivery thread(s) raised: {errors!r}"
    execution.refresh_from_db()
    assert execution.status == "FAILED"
    assert execution.error_message == "boom"
    settled = TRANSITIONS.objects.filter(instance=execution).count() - before
    assert settled == 1


@pytest.mark.django_db
def test_missing_execution_is_logged_not_raised():

    handle_task_started(sender=None, task_result=_Delivery("never-enqueued"))

    assert not TaskExecution.objects.filter(task_id="never-enqueued").exists()
