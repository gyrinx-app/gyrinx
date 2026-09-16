"""Database-backed admission control for scoped platform writes.

Paused task deliveries keep the queue's existing policy. ``TaskRoute`` defaults
to a 10-second initial retry and a 600-second cap, both written to Pub/Sub by
``gyrinx.tasks.provisioning``. Provisioning does not set message retention or a
dead-letter policy: retention therefore remains the provider's default (currently
seven days) and must be verified before a planned cutover.
"""

from __future__ import annotations

import hashlib
import logging
from contextlib import contextmanager
from contextvars import ContextVar
from dataclasses import dataclass

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.db import DatabaseError, OperationalError, connection, transaction
from django.utils import timezone

from gyrinx.site.models import WritePause

logger = logging.getLogger(__name__)


class WritesPaused(Exception):
    """The requested domain is temporarily read-only."""


@dataclass(frozen=True)
class WriteScopeRegistration:
    slug: str
    path_prefixes: tuple[str, ...] = ()
    admin_app_labels: tuple[str, ...] = ()


@dataclass(frozen=True)
class WritePermit:
    scope: str
    generation: int
    task_name: str
    run_id: str


@dataclass(frozen=True)
class DeliveryAdmission:
    allowed: bool
    pause: WritePause | None = None


_scopes: dict[str, WriteScopeRegistration] = {}
_permit: ContextVar[WritePermit | None] = ContextVar("write_pause_permit", default=None)
_admissions: ContextVar[tuple[tuple[str, WritePermit | None, WritePause], ...]] = (
    ContextVar("write_pause_admissions", default=())
)


def register_write_scope(slug, *, path_prefixes=(), admin_app_labels=()):
    registration = WriteScopeRegistration(
        slug=slug,
        path_prefixes=tuple(path_prefixes),
        admin_app_labels=tuple(admin_app_labels),
    )
    existing = _scopes.get(slug)
    if existing is not None and existing != registration:
        raise ImproperlyConfigured(f"Write scope {slug!r} was registered differently")
    _scopes[slug] = registration
    return registration


def registered_write_scopes():
    return tuple(_scopes.values())


def ensure_registered_scopes(**_kwargs):
    if WritePause._meta.db_table not in connection.introspection.table_names():
        return
    for scope in _scopes:
        WritePause.objects.get_or_create(scope=scope)


def _lock_key(scope):
    raw = hashlib.sha256(f"gyrinx.write-pause:{scope}".encode()).digest()[:8]
    return int.from_bytes(raw, byteorder="big", signed=True)


def _advisory(function, scope):
    with connection.cursor() as cursor:
        cursor.execute(f"SELECT {function}(%s)", [_lock_key(scope)])
        row = cursor.fetchone()
    return row[0] if row else None


def _session_unlock(function, scope):
    connection.ensure_connection()
    raw_connection = connection.connection
    try:
        with connection.cursor() as cursor:
            cursor.execute(f"SELECT {function}(%s)", [_lock_key(scope)])
            cursor.fetchone()
    except DatabaseError:
        # Django returns connections to its psycopg pool from connection.close().
        # Close the physical session first so putconn() discards it instead of
        # recycling a session that may still own this advisory lock.
        try:
            raw_connection.close()
        except Exception:
            logger.exception("Failed to close a connection after advisory unlock error")
        if connection.connection is raw_connection:
            if getattr(raw_connection, "closed", False):
                try:
                    connection.close()
                except Exception:
                    logger.exception(
                        "Failed to discard a connection after unlock error"
                    )
            else:
                # Do not hand a session with an uncertain lock state back to the
                # pool. Dropping the wrapper's reference lets the raw connection
                # be finalized instead of reused by another request.
                connection.connection = None


def _get_pause(scope, *, for_update=False):
    queryset = WritePause.objects
    if for_update:
        queryset = queryset.select_for_update()
    try:
        return queryset.get(scope=scope)
    except WritePause.DoesNotExist as exc:
        raise ImproperlyConfigured(
            f"Registered write scope {scope!r} has no database state"
        ) from exc


def pause_status(scope):
    return _get_pause(scope)


def _permit_matches(pause):
    permit = _permit.get()
    return bool(
        permit
        and permit.scope == pause.scope
        and permit.generation == pause.generation
        and permit.task_name == pause.permitted_task_name
        and permit.run_id == pause.permitted_run_id
        and pause.permitted_task_name
        and pause.permitted_run_id
    )


@contextmanager
def write_guard(scope):
    """Admit a domain write inside its caller's outer transaction."""
    if not connection.in_atomic_block:
        raise RuntimeError("write_guard() requires an active transaction")
    permit = _permit.get()
    for admitted_scope, admitted_permit, admitted_pause in reversed(_admissions.get()):
        if admitted_scope == scope and admitted_permit == permit:
            yield admitted_pause
            return
    _advisory("pg_advisory_xact_lock_shared", scope)
    pause = _get_pause(scope)
    if pause.state == WritePause.State.PAUSED and not _permit_matches(pause):
        raise WritesPaused(pause.reason or "Changes are temporarily paused.")
    token = _admissions.set((*_admissions.get(), (scope, permit, pause)))
    try:
        yield pause
    finally:
        _admissions.reset(token)


def require_paused_consumer(scope, *, run_id, generation):
    """Assert that the current delivery owns this pause's narrow write permit."""
    if not connection.in_atomic_block:
        raise RuntimeError("require_paused_consumer() requires an active transaction")
    _advisory("pg_advisory_xact_lock_shared", scope)
    pause = _get_pause(scope)
    permit = _permit.get()
    if not (
        pause.state == WritePause.State.PAUSED
        and permit
        and _permit_matches(pause)
        and permit.run_id == str(run_id)
        and permit.generation == int(generation)
    ):
        raise WritesPaused("This task is not authorised for the current write pause.")
    return pause


@contextmanager
def request_gate(scope):
    """Hold shared admission for an entire unsafe HTTP request."""
    _advisory("pg_advisory_lock_shared", scope)
    try:
        pause = _get_pause(scope)
        yield DeliveryAdmission(
            pause.state == WritePause.State.OPEN or _permit_matches(pause), pause
        )
    finally:
        _session_unlock("pg_advisory_unlock_shared", scope)


@contextmanager
def task_delivery_gate(route, kwargs):
    """Hold shared admission for a whole task delivery, including commit gaps."""
    if not route.write_scope:
        yield DeliveryAdmission(True)
        return
    scope = route.write_scope
    _advisory("pg_advisory_lock_shared", scope)
    token = None
    try:
        try:
            pause = _get_pause(scope)
        except ImproperlyConfigured:
            logger.error(
                "Task delivery deferred because write-pause state is missing",
                extra={"write_scope": scope, "task_name": route.path},
            )
            yield DeliveryAdmission(False)
            return
        allowed = pause.state == WritePause.State.OPEN
        consumer = route.paused_consumer
        if not allowed and consumer is not None:
            run_id = str(kwargs.get(consumer.run_id_kwarg, ""))
            raw_generation = kwargs.get(consumer.generation_kwarg)
            try:
                generation = int(raw_generation)
            except TypeError, ValueError:
                generation = -1
            permit = WritePermit(scope, generation, route.path, run_id)
            if (
                generation == pause.generation
                and route.path == pause.permitted_task_name
                and run_id == pause.permitted_run_id
                and run_id
            ):
                token = _permit.set(permit)
                allowed = True
        yield DeliveryAdmission(allowed, pause)
        if not allowed:
            logger.info(
                "Task delivery deferred by write pause",
                extra={
                    "write_scope": scope,
                    "task_name": route.path,
                    "pause_generation": pause.generation,
                },
            )
    finally:
        if token is not None:
            _permit.reset(token)
        _session_unlock("pg_advisory_unlock_shared", scope)


@contextmanager
def exclusive_write_scope(scope):
    """Drain a scope, then yield its locked row in one caller-composable transaction."""
    try:
        with transaction.atomic():
            timeout_ms = int(settings.WRITE_PAUSE_DRAIN_TIMEOUT_SECONDS * 1000)
            with connection.cursor() as cursor:
                cursor.execute("SET LOCAL lock_timeout = %s", [f"{timeout_ms}ms"])
            # Transaction-scoped control lock cannot leak through a pooled connection.
            # It is acquired before the row lock, matching every pause transition.
            _advisory("pg_advisory_xact_lock", scope)
            yield _get_pause(scope, for_update=True)
    except OperationalError as exc:
        if getattr(exc.__cause__, "sqlstate", None) == "55P03":
            raise WritesPaused(
                "Active changes did not finish before the maintenance timeout. "
                "Try again after checking running requests and tasks."
            ) from exc
        raise


exclusive_scope = exclusive_write_scope


def pause_scope(scope, *, actor, reason, permitted_task_name="", permitted_run_id=""):
    if bool(permitted_task_name) != bool(permitted_run_id):
        raise ValueError("A paused consumer requires both task name and run ID")
    with exclusive_write_scope(scope) as pause:
        if pause.state == WritePause.State.PAUSED:
            raise WritesPaused(f"{scope} writes are already paused")
        pause.state = WritePause.State.PAUSED
        pause.generation += 1
        pause.reason = reason.strip()
        pause.paused_at = timezone.now()
        pause.paused_by = actor
        pause.permitted_task_name = permitted_task_name
        pause.permitted_run_id = str(permitted_run_id)
        pause.save()
        return pause


def _change_binding(scope, *, generation, task_name, run_id, expected=None):
    if bool(task_name) != bool(run_id):
        raise ValueError("A paused consumer requires both task name and run ID")
    with exclusive_write_scope(scope) as pause:
        if pause.state != WritePause.State.PAUSED or pause.generation != generation:
            raise WritesPaused(
                "The write pause changed before the task was authorised."
            )
        current = (pause.permitted_task_name, pause.permitted_run_id)
        if expected is not None and current != expected:
            raise WritesPaused("A different task is authorised for this write pause.")
        pause.permitted_task_name = task_name
        pause.permitted_run_id = str(run_id)
        pause.save(
            update_fields=["permitted_task_name", "permitted_run_id", "modified"]
        )
        return pause


def bind_paused_consumer(scope, *, generation, task_name, run_id):
    return _change_binding(
        scope,
        generation=generation,
        task_name=task_name,
        run_id=run_id,
        expected=("", ""),
    )


def rebind_paused_consumer(
    scope, *, generation, task_name, run_id, previous_task_name, previous_run_id
):
    return _change_binding(
        scope,
        generation=generation,
        task_name=task_name,
        run_id=run_id,
        expected=(previous_task_name, str(previous_run_id)),
    )


def release_paused_consumer(scope, *, generation, task_name, run_id):
    return _change_binding(
        scope,
        generation=generation,
        task_name="",
        run_id="",
        expected=(task_name, str(run_id)),
    )


def resume_scope(scope, *, actor=None):
    with exclusive_write_scope(scope) as pause:
        if pause.permitted_task_name or pause.permitted_run_id:
            raise WritesPaused(
                "Release the authorised maintenance task before resuming writes."
            )
        pause.state = WritePause.State.OPEN
        pause.reason = ""
        pause.paused_at = None
        pause.paused_by = None
        pause.save()
        return pause
