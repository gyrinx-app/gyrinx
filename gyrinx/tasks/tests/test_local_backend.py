"""
Tests for the local durable task backend (DatabaseBackend) and its testing layer.

These exercise the eager and manual modes end-to-end and, crucially, the
Pub/Sub-like adverse conditions the manual driver can script: duplicate delivery,
transient failure + retry, message drop, and self-re-enqueueing chains.
"""

import pytest
from django.tasks import task

from gyrinx.tasks import local_backend
from gyrinx.tasks.local_backend import DatabaseBackend
from gyrinx.tasks.models import QueuedTask, TaskExecution
from gyrinx.tasks.worker import Outcome, compute_backoff, deliver

# --- Test tasks. Registered lazily below so the registry lookup used by the
# worker/manual driver resolves them. ---

_side_effects: list = []


@task
def _record_task(value: str):
    _side_effects.append(value)
    return f"recorded {value}"


@task
def _boom_task():
    raise RuntimeError("boom")


_flaky_state = {"fail_until_attempt": 0, "attempts": 0}


@task
def _flaky_task():
    _flaky_state["attempts"] += 1
    if _flaky_state["attempts"] < _flaky_state["fail_until_attempt"]:
        raise RuntimeError(f"transient failure on attempt {_flaky_state['attempts']}")
    _side_effects.append(f"flaky-ok-{_flaky_state['attempts']}")
    return "ok"


@task
def _chain_task(n: int):
    """Self-re-enqueueing task — models the maintenance chains (backfill/reconcile)."""
    _side_effects.append(n)
    if n > 0:
        _chain_task.enqueue(n=n - 1)


@pytest.fixture(autouse=True)
def _register_test_tasks(monkeypatch):
    """Register the module's test tasks in the registry for the duration of a test
    and reset shared side-effect state."""
    from gyrinx.tasks import registry, route

    routes = [
        route.TaskRoute(_record_task, min_retry_delay=1, max_retry_delay=4),
        route.TaskRoute(_boom_task, min_retry_delay=1, max_retry_delay=4),
        route.TaskRoute(_flaky_task, min_retry_delay=1, max_retry_delay=4),
        route.TaskRoute(_chain_task, min_retry_delay=1, max_retry_delay=4),
    ]
    monkeypatch.setattr(registry, "_tasks", routes)
    _side_effects.clear()
    _flaky_state["fail_until_attempt"] = 0
    _flaky_state["attempts"] = 0
    yield


# =============================================================================
# Eager mode — drop-in for ImmediateBackend
# =============================================================================


@pytest.mark.django_db
def test_eager_runs_inline_on_enqueue():
    """Default eager mode runs the task synchronously inside enqueue()."""
    result = _record_task.enqueue("hello")

    assert _side_effects == ["hello"]
    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "SUCCESSFUL"
    # Eager never persists a queue row.
    assert QueuedTask.objects.count() == 0


@pytest.mark.django_db
def test_eager_records_failure_without_raising():
    """A failing task in eager mode is recorded FAILED, not propagated."""
    result = _boom_task.enqueue()

    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "FAILED"
    assert "boom" in execution.error_message


@pytest.mark.django_db
def test_redelivery_of_completed_task_does_not_raise():
    """Post-completion redelivery: task_started re-fires for an already-terminal
    execution (the Pub/Sub at-least-once case). handle_task_started must skip the
    illegal SUCCESSFUL->RUNNING transition rather than raise — a raise here
    propagates out of run_task and, via the prod push handler, 500s into a
    redelivery storm."""
    from gyrinx.tasks.executor import run_task

    result = _record_task.enqueue("once")  # eager: runs inline, records SUCCESSFUL
    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "SUCCESSFUL"
    finished_at = execution.finished_at

    # Redeliver the same completed message straight through the shared executor.
    ok, _rv, err = run_task(
        _record_task.func,
        task_name="_record_task",
        task_id=result.id,
        args=["once"],
        kwargs={},
    )

    assert ok is True and err is None  # did not raise
    assert _side_effects == ["once", "once"]  # business logic ran again
    execution.refresh_from_db()
    assert execution.status == "SUCCESSFUL"  # canonical record untouched
    assert execution.finished_at == finished_at


# =============================================================================
# Manual mode — the testing layer
# =============================================================================


@pytest.mark.django_db
def test_manual_defers_until_delivered(task_queue):
    """In manual mode enqueue only queues; nothing runs until deliver."""
    _record_task.enqueue("x")

    assert _side_effects == []
    assert task_queue.pending() == 1

    task_queue.deliver_all()
    assert _side_effects == ["x"]
    assert task_queue.pending() == 0


@pytest.mark.django_db
def test_manual_redelivery_reruns_function(task_queue):
    """At-least-once duplicate: the function runs twice, the record stays SUCCESSFUL."""
    result = _record_task.enqueue("dup")
    task_queue.deliver_all()
    assert _side_effects == ["dup"]

    task_queue.redeliver_last()

    # Business logic ran again (idempotency is the caller's job to prove)...
    assert _side_effects == ["dup", "dup"]
    # ...but the canonical outcome record is untouched (still one SUCCESSFUL row).
    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "SUCCESSFUL"


@pytest.mark.django_db
def test_manual_transient_failure_then_retry_succeeds(task_queue):
    """fail_next() nacks the first delivery; the retry runs and succeeds."""
    result = _flaky_task.enqueue()

    task_queue.fail_next(1)  # first *delivery* fails (injected, task not run)
    task_queue.deliver_all()

    # The injected failure means the real function only ran on the retry.
    assert _side_effects == ["flaky-ok-1"]
    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "SUCCESSFUL"
    assert task_queue.pending() == 0


@pytest.mark.django_db
def test_manual_real_exception_then_recovers(task_queue):
    """A task that raises on its first attempt but succeeds later ends SUCCESSFUL
    (the retry resets the observability record so the transition is valid)."""
    result = _flaky_task.enqueue()
    _flaky_state["fail_until_attempt"] = 2  # raise on attempt 1, succeed on attempt 2

    task_queue.deliver_all()

    assert _side_effects == ["flaky-ok-2"]
    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "SUCCESSFUL"


@pytest.mark.django_db
def test_manual_gives_up_after_max_attempts(task_queue):
    """A permanently failing task is retried up to max_attempts, then given up."""
    result = _boom_task.enqueue()

    task_queue.deliver_all()

    # Row is gone (given up), execution is FAILED.
    assert QueuedTask.objects.count() == 0
    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "FAILED"


@pytest.mark.django_db
def test_manual_drop_loses_delivery(task_queue):
    """drop_next() simulates a lost message: the task never runs and the row is gone."""
    _record_task.enqueue("gone")

    task_queue.drop_next(1)
    outcome = task_queue.deliver_next()

    assert outcome == Outcome.DROPPED
    assert _side_effects == []
    assert task_queue.pending() == 0


@pytest.mark.django_db
def test_manual_self_re_enqueue_chain(task_queue):
    """A task that enqueues a follow-up (like the maintenance chains) drains fully."""
    _chain_task.enqueue(n=3)
    delivered = task_queue.deliver_all()

    assert _side_effects == [3, 2, 1, 0]
    assert delivered == 4
    assert task_queue.pending() == 0


# =============================================================================
# Backoff + configuration
# =============================================================================


def test_compute_backoff_is_exponential_and_capped():
    from gyrinx.tasks.route import TaskRoute

    r = TaskRoute(_record_task, min_retry_delay=10, max_retry_delay=100)
    assert compute_backoff(r, 1).total_seconds() == 10
    assert compute_backoff(r, 2).total_seconds() == 20
    assert compute_backoff(r, 3).total_seconds() == 40
    # Capped at max_retry_delay.
    assert compute_backoff(r, 10).total_seconds() == 100


def test_backend_rejects_invalid_mode():
    with pytest.raises(ValueError):
        DatabaseBackend("default", {"OPTIONS": {"mode": "nonsense"}})


@pytest.mark.django_db
def test_mode_override_flips_backend(task_queue):
    """The fixture's manual override is what defers execution."""
    assert local_backend.get_mode_override() == "manual"
    _record_task.enqueue("y")
    assert task_queue.pending() == 1


@pytest.mark.django_db
def test_deliver_unknown_task_is_discarded():
    """A queue row for a task missing from the registry is dropped (not retried
    forever), and its enqueue-time observability record is marked FAILED rather
    than left pending forever."""
    from django.utils import timezone

    TaskExecution.objects.create(
        task_id="orphan",
        task_name="_no_such_task",
        args=[],
        kwargs={},
        enqueued_at=timezone.now(),
    )
    qt = QueuedTask.objects.create(
        task_id="orphan",
        task_name="_no_such_task",
        args=[],
        kwargs={},
        enqueued_at=timezone.now(),
        available_at=timezone.now(),
        attempts=1,
    )
    outcome = deliver(qt)
    assert outcome == Outcome.UNKNOWN_TASK
    assert QueuedTask.objects.count() == 0
    execution = TaskExecution.objects.get(task_id="orphan")
    assert execution.status == "FAILED"
    assert "_no_such_task" in execution.error_message


@pytest.mark.django_db
def test_reclaim_does_not_clobber_completed_execution():
    """Crash-after-success reclaim: a worker died after run_task succeeded but
    before deleting the queue row, so the lease lapsed and the row is reclaimed
    (attempts > 1). The SUCCESSFUL execution must survive — not be reset to READY
    and re-terminalised as a fresh execution."""
    from django.utils import timezone

    execution = TaskExecution.objects.create(
        task_id="reclaimed",
        task_name="_record_task",
        args=["r"],
        kwargs={},
        enqueued_at=timezone.now(),
    )
    execution.mark_running()
    execution.mark_successful(return_value="recorded r")
    finished_at = execution.finished_at

    qt = QueuedTask.objects.create(
        task_id="reclaimed",
        task_name="_record_task",
        args=["r"],
        kwargs={},
        enqueued_at=timezone.now(),
        available_at=timezone.now(),
        attempts=2,  # a reclaim
    )
    outcome = deliver(qt)

    assert outcome == Outcome.SUCCESS
    execution.refresh_from_db()
    assert execution.status == "SUCCESSFUL"  # not reset to READY / regenerated
    assert execution.finished_at == finished_at
    assert QueuedTask.objects.count() == 0
