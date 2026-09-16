import importlib
import threading

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, transaction
from django.http import HttpResponse
from django.test import RequestFactory, override_settings

from gyrinx.site.middleware import WritePauseMiddleware
from gyrinx.site.models import WritePause
from gyrinx.site.write_pause import (
    WritesPaused,
    bind_paused_consumer,
    exclusive_scope,
    pause_scope,
    register_write_scope,
    release_paused_consumer,
    resume_scope,
    task_delivery_gate,
    write_guard,
)
from gyrinx.tasks.route import PausedTaskConsumer, TaskRoute

pytestmark = [pytest.mark.core, pytest.mark.django_db(transaction=True)]


def _task(**kwargs):
    return kwargs


@pytest.fixture
def scope():
    slug = "test-pause"
    register_write_scope(slug, path_prefixes=("/test-pause/",))
    pause, _ = WritePause.objects.get_or_create(scope=slug)
    pause.state = WritePause.State.OPEN
    pause.generation = 0
    pause.reason = ""
    pause.permitted_task_name = ""
    pause.permitted_run_id = ""
    pause.save()
    return pause


def test_write_guard_fails_closed_for_missing_state():
    with transaction.atomic(), pytest.raises(ImproperlyConfigured):
        with write_guard("missing-pause-row"):
            pass


def test_task_delivery_defers_for_missing_state():
    route = TaskRoute(_task, write_scope="missing-task-pause-row")
    with task_delivery_gate(route, {}) as admission:
        assert not admission.allowed
        assert admission.pause is None


def test_pause_blocks_writes_and_requires_released_binding(scope):
    pause = pause_scope(scope.scope, actor=None, reason="Counter maintenance")
    with transaction.atomic(), pytest.raises(WritesPaused):
        with write_guard(scope.scope):
            pass

    bind_paused_consumer(
        scope.scope,
        generation=pause.generation,
        task_name=f"{__name__}._task",
        run_id="run-1",
    )
    with pytest.raises(WritesPaused, match="Release"):
        resume_scope(scope.scope, generation=pause.generation)

    release_paused_consumer(
        scope.scope,
        generation=pause.generation,
        task_name=f"{__name__}._task",
        run_id="run-1",
    )
    resume_scope(scope.scope, generation=pause.generation)
    with transaction.atomic(), write_guard(scope.scope):
        pass


def test_resume_rejects_a_stale_generation(scope):
    first = pause_scope(scope.scope, actor=None, reason="First pause")
    resume_scope(scope.scope, generation=first.generation)
    latest = pause_scope(scope.scope, actor=None, reason="Latest pause")

    with pytest.raises(WritesPaused, match="changed after the page loaded"):
        resume_scope(scope.scope, generation=first.generation)

    scope.refresh_from_db()
    assert scope.state == WritePause.State.PAUSED
    assert scope.generation == latest.generation


def test_exact_bound_task_is_admitted_and_stale_generation_is_deferred(scope):
    paused = pause_scope(scope.scope, actor=None, reason="Cutover")
    route = TaskRoute(
        _task,
        write_scope=scope.scope,
        paused_consumer=PausedTaskConsumer(),
    )
    bind_paused_consumer(
        scope.scope,
        generation=paused.generation,
        task_name=route.path,
        run_id="backfill-1",
    )

    kwargs = {"backfill_id": "backfill-1", "pause_generation": paused.generation}
    with task_delivery_gate(route, kwargs) as admission:
        assert admission.allowed
        with transaction.atomic(), write_guard(scope.scope):
            pass

    kwargs["pause_generation"] -= 1
    with task_delivery_gate(route, kwargs) as admission:
        assert not admission.allowed


def test_task_gate_releases_session_lock_when_body_raises(scope):
    route = TaskRoute(_task, write_scope=scope.scope)
    with pytest.raises(RuntimeError):
        with task_delivery_gate(route, {}):
            raise RuntimeError("delivery failed")
    # An exclusive control operation on the same connection would hang if the
    # session-scoped shared lock leaked from the exceptional delivery.
    pause_scope(scope.scope, actor=None, reason="Still drainable")


def test_admitted_delivery_can_take_transaction_guard_while_pause_waits(scope):
    """A queued exclusive pause must not deadlock a delivery already admitted."""
    delivery_admitted = threading.Event()
    pause_started = threading.Event()
    nested_guard_done = threading.Event()
    errors = []

    def delivery():
        from django.db import close_old_connections

        close_old_connections()
        try:
            route = TaskRoute(_task, write_scope=scope.scope)
            with task_delivery_gate(route, {}) as admission:
                assert admission.allowed
                delivery_admitted.set()
                assert pause_started.wait(2)
                with transaction.atomic(), write_guard(scope.scope):
                    nested_guard_done.set()
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            close_old_connections()

    def pauser():
        from django.db import close_old_connections

        close_old_connections()
        try:
            assert delivery_admitted.wait(2)
            pause_started.set()
            pause_scope(scope.scope, actor=None, reason="Drain")
        except Exception as exc:  # pragma: no cover - surfaced below
            errors.append(exc)
        finally:
            close_old_connections()

    delivery_thread = threading.Thread(target=delivery)
    pause_thread = threading.Thread(target=pauser)
    delivery_thread.start()
    pause_thread.start()
    delivery_thread.join(5)
    pause_thread.join(5)

    assert nested_guard_done.is_set()
    assert not delivery_thread.is_alive()
    assert not pause_thread.is_alive()
    assert errors == []
    scope.refresh_from_db()
    assert scope.state == WritePause.State.PAUSED


def test_reused_atomic_decorator_rechecks_pause_between_calls(scope):
    @transaction.atomic
    def guarded_call():
        with write_guard(scope.scope):
            return "written"

    assert guarded_call() == "written"
    pause_scope(scope.scope, actor=None, reason="Stop later calls")
    with pytest.raises(WritesPaused):
        guarded_call()


def test_guard_from_rolled_back_savepoint_is_not_cached_in_outer_transaction(scope):
    with transaction.atomic():
        try:
            with transaction.atomic():
                with write_guard(scope.scope):
                    raise RuntimeError("roll back the savepoint")
        except RuntimeError:
            pass

        WritePause.objects.filter(pk=scope.pk).update(
            state=WritePause.State.PAUSED, reason="Pause after rollback"
        )
        with pytest.raises(WritesPaused):
            with write_guard(scope.scope):
                pass


def test_htmx_write_pause_refreshes_to_safe_read_notice(scope):
    pause_scope(scope.scope, actor=None, reason="Safe maintenance <script>")
    middleware = WritePauseMiddleware(lambda request: HttpResponse("changed"))
    request = RequestFactory().post("/test-pause/change", HTTP_HX_REQUEST="true")

    response = middleware(request)

    assert response.status_code == 503
    assert response["Retry-After"] == "30"
    assert response["HX-Refresh"] == "true"
    assert b"&lt;script&gt;" in response.content


def test_view_improperly_configured_error_is_not_masked_or_retried(scope):
    calls = 0

    def broken_view(request):
        nonlocal calls
        calls += 1
        raise ImproperlyConfigured("The view is broken")

    middleware = WritePauseMiddleware(broken_view)
    request = RequestFactory().get("/test-pause/read")

    with pytest.raises(ImproperlyConfigured, match="The view is broken"):
        middleware(request)

    assert calls == 1


@override_settings(WRITE_PAUSE_DRAIN_TIMEOUT_SECONDS=0.02)
def test_pause_timeout_leaves_scope_open(scope):
    admitted = threading.Event()
    release = threading.Event()

    def active_request():
        from django.db import close_old_connections

        close_old_connections()
        route = TaskRoute(_task, write_scope=scope.scope)
        with task_delivery_gate(route, {}):
            admitted.set()
            release.wait(2)
        close_old_connections()

    thread = threading.Thread(target=active_request)
    thread.start()
    assert admitted.wait(2)
    try:
        with pytest.raises(WritesPaused, match="maintenance timeout"):
            pause_scope(scope.scope, actor=None, reason="Must drain")
    finally:
        release.set()
        thread.join(2)

    scope.refresh_from_db()
    assert scope.state == WritePause.State.OPEN


def test_unlock_failure_physically_closes_before_returning_connection_to_pool(
    monkeypatch,
):
    module = importlib.import_module("gyrinx.site.write_pause")

    class RawConnection:
        closed = False

        def cursor(self):
            return BrokenCursor()

        def close(self):
            self.closed = True

    class Pool:
        returned = []

        def putconn(self, raw):
            assert raw.closed, (
                "a lock-owning live session must never return to the pool"
            )
            self.returned.append(raw)

    class BrokenCursor:
        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, *_args):
            raise DatabaseError("connection failed during unlock")

    class Wrapper:
        def __init__(self):
            self.connection = RawConnection()
            self.pool = Pool()

        def ensure_connection(self):
            pass

        def cursor(self):
            return BrokenCursor()

        def close(self):
            self.pool.putconn(self.connection)
            self.connection = None

    wrapper = Wrapper()
    raw = wrapper.connection
    monkeypatch.setattr(module, "connection", wrapper)

    module._session_unlock("pg_advisory_unlock_shared", "test-scope", raw)

    assert raw.closed
    assert wrapper.pool.returned == [raw]
    assert wrapper.connection is None


def test_unlock_uses_the_physical_connection_that_acquired_the_lock(monkeypatch):
    module = importlib.import_module("gyrinx.site.write_pause")

    class Cursor:
        def __init__(self, calls):
            self.calls = calls

        def __enter__(self):
            return self

        def __exit__(self, *_args):
            return False

        def execute(self, sql, params):
            self.calls.append((sql, params))

        def fetchone(self):
            return (True,)

    class Raw:
        def __init__(self):
            self.calls = []

        def cursor(self):
            return Cursor(self.calls)

    acquired_on = Raw()
    replacement = Raw()
    wrapper = type("Wrapper", (), {"connection": replacement})()
    monkeypatch.setattr(module, "connection", wrapper)

    module._session_unlock("pg_advisory_unlock_shared", "test-scope", acquired_on)

    assert len(acquired_on.calls) == 1
    assert "pg_advisory_unlock_shared" in acquired_on.calls[0][0]
    assert replacement.calls == []


def test_exclusive_scope_restores_enclosing_transaction_lock_timeout(scope):
    from django.db import connection

    with transaction.atomic():
        with connection.cursor() as cursor:
            cursor.execute("SET LOCAL lock_timeout = '7s'")
        with exclusive_scope(scope.scope):
            with connection.cursor() as cursor:
                cursor.execute("SHOW lock_timeout")
                assert cursor.fetchone()[0] == "7s"
