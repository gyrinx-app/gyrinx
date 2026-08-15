"""
Tests for task provisioning and where it is (and is not) allowed to run.

The cold-start regression these guard against: provisioning used to run inline in
`TasksConfig.ready()`, so it executed in every management command and every
gunicorn worker, blocking ~120s of a ~160s Cloud Run cold start.
"""

import inspect
from unittest.mock import MagicMock, patch

import pytest
from google.api_core.exceptions import AlreadyExists, Conflict

from gyrinx.tasks import provisioning
from gyrinx.tasks.apps import TasksConfig
from gyrinx.tasks.route import TaskRoute


def _route(name="a_task"):
    """A TaskRoute whose function is irrelevant — only its config is read here."""

    def fn():  # pragma: no cover - never called
        pass

    fn.__name__ = name
    return TaskRoute(fn)


def test_ready_does_not_provision():
    """
    `ready()` must not reach provisioning.

    This is the whole cold-start fix: `ready()` runs in every Django process, and
    provisioning is a run of blocking Pub/Sub admin calls. Asserted against the
    source rather than by calling `ready()`, so it fails loudly if someone
    reintroduces the call behind an environment check that happens to be off here.
    """
    source = inspect.getsource(TasksConfig.ready)
    assert "provision_task_infrastructure" not in source
    assert "K_SERVICE" not in source


def test_provision_tasks_command_is_a_noop_outside_cloud_run(monkeypatch):
    """The entrypoint calls this unconditionally, so it must be safe locally."""
    from django.core.management import call_command

    monkeypatch.delenv("K_SERVICE", raising=False)
    with patch.object(provisioning, "provision_task_infrastructure") as provision:
        call_command("provision_tasks")
    provision.assert_not_called()


def test_provision_tasks_command_provisions_in_cloud_run(monkeypatch):
    from django.core.management import call_command

    monkeypatch.setenv("K_SERVICE", "gyrinx")
    with patch(
        "gyrinx.tasks.management.commands.provision_tasks.provision_task_infrastructure"
    ) as provision:
        call_command("provision_tasks")
    provision.assert_called_once()


def test_update_subscription_retries_then_warns_on_conflict(caplog):
    """
    A 409 from a concurrent writer is benign and must not be logged as a failure.

    Two containers cold-starting together both write byte-identical config; the
    loser used to produce an ERROR with a traceback for every task on every boot.
    """
    subscriber = MagicMock()
    subscriber.update_subscription.side_effect = Conflict("raced with another request")

    with caplog.at_level("WARNING"):
        provisioning._update_subscription_tolerating_conflict(
            subscriber=subscriber,
            subscription_path="projects/p/subscriptions/s",
            subscription_name="s",
            push_config=MagicMock(),
            route=_route(),
        )

    assert (
        subscriber.update_subscription.call_count == provisioning.CONFLICT_RETRIES + 1
    )
    assert not [r for r in caplog.records if r.levelname == "ERROR"]
    assert any(r.levelname == "WARNING" for r in caplog.records)


def test_update_subscription_succeeds_after_a_transient_conflict():
    subscriber = MagicMock()
    subscriber.update_subscription.side_effect = [Conflict("raced"), None]

    provisioning._update_subscription_tolerating_conflict(
        subscriber=subscriber,
        subscription_path="projects/p/subscriptions/s",
        subscription_name="s",
        push_config=MagicMock(),
        route=_route(),
    )

    assert subscriber.update_subscription.call_count == 2


def test_existing_subscription_is_updated_not_reported_as_an_error():
    """AlreadyExists is the normal steady state — it must fall through to update."""
    publisher, subscriber = MagicMock(), MagicMock()
    publisher.create_topic.side_effect = AlreadyExists("topic exists")
    subscriber.create_subscription.side_effect = AlreadyExists("sub exists")

    provisioning._provision_task(
        publisher=publisher,
        subscriber=subscriber,
        project_id="p",
        route=_route(),
        push_endpoint="https://example.test/tasks/pubsub/",
        service_url="https://example.test",
        service_account="sa@example.test",
    )

    subscriber.update_subscription.assert_called_once()


def test_one_failing_task_does_not_stop_the_others(settings, caplog):
    """
    The pool must drain even when a task blows up.

    Provisioning is now concurrent; a raising worker that escaped the per-task
    try/except would take the whole run down with it.
    """
    settings.GCP_PROJECT_ID = "p"
    routes = [_route("first"), _route("second"), _route("third")]
    calls = []

    def fake_provision(*, route, **kwargs):
        calls.append(route.name)
        if route.name == "second":
            raise RuntimeError("boom")

    with (
        patch.object(provisioning, "get_all_tasks", return_value=routes),
        patch.object(provisioning, "_provision_task", side_effect=fake_provision),
        patch.object(provisioning, "_provision_scheduled_tasks"),
        patch.object(provisioning.pubsub_v1, "PublisherClient"),
        patch.object(provisioning.pubsub_v1, "SubscriberClient"),
    ):
        provisioning.provision_task_infrastructure()

    assert sorted(calls) == ["first", "second", "third"]


@pytest.mark.parametrize("path", ["/healthz"])
def test_healthz_is_served_without_django_routing(path):
    """
    The readiness probe must be answered above Django.

    Cloud Run probes the container by IP, which ALLOWED_HOSTS cannot list, so a
    probe routed through Django would 400. The inner app must never be reached.
    """
    from gyrinx.wsgi import make_application

    inner = MagicMock()
    app = make_application(inner)
    start_response = MagicMock()

    body = app({"PATH_INFO": path, "REQUEST_METHOD": "GET"}, start_response)

    assert b"".join(body) == b"ok\n"
    inner.assert_not_called()
    status = start_response.call_args[0][0]
    assert status.startswith("200")


def test_non_healthz_requests_reach_django():
    from gyrinx.wsgi import make_application

    inner = MagicMock(return_value=[b"page"])
    app = make_application(inner)

    body = app({"PATH_INFO": "/n23/lists/", "REQUEST_METHOD": "GET"}, MagicMock())

    assert b"".join(body) == b"page"
    inner.assert_called_once()
