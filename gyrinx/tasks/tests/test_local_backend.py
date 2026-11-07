"""Local task delivery in eager and manual modes, including failures and redelivery."""

import pytest
from django.tasks import task

from gyrinx.tasks import local_backend
from gyrinx.tasks.local_backend import DatabaseBackend
from gyrinx.tasks.models import QueuedTask, TaskExecution
from gyrinx.tasks.worker import Outcome, compute_backoff, deliver

pytestmark = pytest.mark.core

# Register test tasks through the fixture so local delivery can resolve them.

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
    """Enqueue a follow-up task until n reaches zero."""
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


@pytest.mark.django_db
def test_eager_runs_inline_on_enqueue():

    result = _record_task.enqueue("hello")

    assert _side_effects == ["hello"]
    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "SUCCESSFUL"
    assert QueuedTask.objects.count() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("exclusive_write", [False, True])
def test_eager_retains_a_scoped_task_while_writes_are_paused(
    monkeypatch, exclusive_write
):
    from gyrinx.site.models import WritePause
    from gyrinx.site.write_pause import pause_scope
    from gyrinx.tasks import registry, route

    WritePause.objects.create(scope="test-eager-pause")
    monkeypatch.setattr(
        registry,
        "_tasks",
        [
            route.TaskRoute(
                _record_task,
                write_scope="test-eager-pause",
                exclusive_write=exclusive_write,
            )
        ],
    )
    pause_scope("test-eager-pause", actor=None, reason="Maintenance")

    result = _record_task.enqueue("later")

    assert _side_effects == []
    queued = QueuedTask.objects.get(task_id=result.id)
    assert queued.attempts == 0
    assert TaskExecution.objects.get(task_id=result.id).status == "READY"


@pytest.mark.django_db
def test_eager_records_failure_without_raising():

    result = _boom_task.enqueue()

    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "FAILED"
    assert "boom" in execution.error_message


@pytest.mark.django_db
def test_redelivery_of_completed_task_does_not_raise():
    """Rerun business logic while preserving the successful execution and its finish time."""
    from gyrinx.tasks.executor import run_task

    result = _record_task.enqueue("once")  # eager: runs inline, records SUCCESSFUL
    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "SUCCESSFUL"
    finished_at = execution.finished_at

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


@pytest.mark.django_db
def test_retry_after_failure_records_eventual_success():
    """Reset a failed execution for retry so the new attempt can record success."""
    from django.utils import timezone

    from gyrinx.tasks.executor import run_task

    execution = TaskExecution.objects.create(
        task_id="retry-me",
        task_name="_record_task",
        args=["r"],
        kwargs={},
        enqueued_at=timezone.now(),
    )
    execution.mark_running()
    execution.mark_failed(error_message="transient boom")
    assert execution.status == "FAILED"

    ok, _rv, err = run_task(
        _record_task.func,
        task_name="_record_task",
        task_id="retry-me",
        args=["r"],
        kwargs={},
    )

    assert ok is True and err is None
    assert _side_effects == ["r"]
    execution.refresh_from_db()
    assert execution.status == "SUCCESSFUL"  # reflects the successful retry
    assert execution.error_message == ""  # prior failure cleared


@pytest.mark.django_db
def test_manual_defers_until_delivered(task_queue):

    _record_task.enqueue("x")

    assert _side_effects == []
    assert task_queue.pending() == 1

    task_queue.deliver_all()
    assert _side_effects == ["x"]
    assert task_queue.pending() == 0


@pytest.mark.django_db
@pytest.mark.parametrize("exclusive_write", [False, True])
def test_manual_pause_deferral_does_not_spend_attempt_or_start_execution(
    task_queue, monkeypatch, exclusive_write
):
    from gyrinx.site.models import WritePause
    from gyrinx.site.write_pause import pause_scope
    from gyrinx.tasks import registry, route

    WritePause.objects.create(scope="test-task-scope")
    scoped_route = route.TaskRoute(
        _record_task, write_scope="test-task-scope", exclusive_write=exclusive_write
    )
    monkeypatch.setattr(registry, "_tasks", [scoped_route])
    result = _record_task.enqueue("later")
    pause_scope("test-task-scope", actor=None, reason="Maintenance")

    assert task_queue.deliver_next() == Outcome.DEFERRED
    queued = QueuedTask.objects.get(task_id=result.id)
    assert queued.attempts == 0
    assert queued.locked_until is None
    assert TaskExecution.objects.get(task_id=result.id).status == "READY"
    assert _side_effects == []

    assert task_queue.deliver_all() == 1
    assert task_queue.pending() == 1
    queued.refresh_from_db()
    assert queued.attempts == 0
    assert _side_effects == []


@pytest.mark.django_db
def test_manual_duplicate_redelivery_obeys_pause(task_queue, monkeypatch):
    from gyrinx.site.models import WritePause
    from gyrinx.site.write_pause import pause_scope
    from gyrinx.tasks import registry, route

    WritePause.objects.create(scope="test-redelivery-scope")
    monkeypatch.setattr(
        registry,
        "_tasks",
        [route.TaskRoute(_record_task, write_scope="test-redelivery-scope")],
    )
    _record_task.enqueue("once")
    assert task_queue.deliver_next() == Outcome.SUCCESS
    pause_scope("test-redelivery-scope", actor=None, reason="Maintenance")

    assert task_queue.redeliver_last() == Outcome.DEFERRED
    assert _side_effects == ["once"]


@pytest.mark.django_db
def test_manual_redelivery_reruns_function(task_queue):

    result = _record_task.enqueue("dup")
    task_queue.deliver_all()
    assert _side_effects == ["dup"]

    task_queue.redeliver_last()

    assert _side_effects == ["dup", "dup"]
    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "SUCCESSFUL"


@pytest.mark.django_db
def test_manual_transient_failure_then_retry_succeeds(task_queue):

    result = _flaky_task.enqueue()

    task_queue.fail_next(1)  # first *delivery* fails (injected, task not run)
    task_queue.deliver_all()

    # The injected failure consumes a delivery without calling the task function.
    assert _side_effects == ["flaky-ok-1"]
    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "SUCCESSFUL"
    assert task_queue.pending() == 0


@pytest.mark.django_db
def test_manual_real_exception_then_recovers(task_queue):

    result = _flaky_task.enqueue()
    _flaky_state["fail_until_attempt"] = 2  # raise on attempt 1, succeed on attempt 2

    task_queue.deliver_all()

    assert _side_effects == ["flaky-ok-2"]
    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "SUCCESSFUL"


@pytest.mark.django_db
def test_manual_gives_up_after_max_attempts(task_queue):

    result = _boom_task.enqueue()

    task_queue.deliver_all()

    assert QueuedTask.objects.count() == 0
    execution = TaskExecution.objects.get(task_id=result.id)
    assert execution.status == "FAILED"


@pytest.mark.django_db
def test_manual_drop_loses_delivery(task_queue):

    _record_task.enqueue("gone")

    task_queue.drop_next(1)
    outcome = task_queue.deliver_next()

    assert outcome == Outcome.DROPPED
    assert _side_effects == []
    assert task_queue.pending() == 0


@pytest.mark.django_db
def test_manual_self_re_enqueue_chain(task_queue):

    _chain_task.enqueue(n=3)
    delivered = task_queue.deliver_all()

    assert _side_effects == [3, 2, 1, 0]
    assert delivered == 4
    assert task_queue.pending() == 0


def test_compute_backoff_is_exponential_and_capped():
    from gyrinx.tasks.route import TaskRoute

    r = TaskRoute(_record_task, min_retry_delay=10, max_retry_delay=100)
    assert compute_backoff(r, 1).total_seconds() == 10
    assert compute_backoff(r, 2).total_seconds() == 20
    assert compute_backoff(r, 3).total_seconds() == 40
    assert compute_backoff(r, 10).total_seconds() == 100


def test_backend_rejects_invalid_mode():
    with pytest.raises(ValueError):
        DatabaseBackend("default", {"OPTIONS": {"mode": "nonsense"}})


def test_worker_pool_stop_leaves_instance_restartable():
    """Clear stop and wake events so restarted threads can process work."""
    from gyrinx.tasks.worker import TaskWorkerPool

    pool = TaskWorkerPool(num_workers=1)
    pool.stop()  # exercises the event reset directly, without starting threads

    assert not pool._stop.is_set()
    assert not pool._wake.is_set()
    assert pool._started is False


@pytest.mark.django_db
def test_mode_override_flips_backend(task_queue):

    assert local_backend.get_mode_override() == "manual"
    _record_task.enqueue("y")
    assert task_queue.pending() == 1


@pytest.mark.django_db
def test_deliver_unknown_task_is_discarded():

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
    """Preserve success when reclaiming a queue record left behind after task completion."""
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
