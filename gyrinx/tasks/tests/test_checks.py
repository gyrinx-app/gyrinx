"""The #1947 system check: declared @task functions must be registered."""

import gyrinx.tasks.checks as checks
from gyrinx.tasks.checks import check_tasks_registered
from gyrinx.tasks.registry import get_all_tasks
from gyrinx.tasks.route import TaskRoute


def test_current_registry_passes_the_check():
    """Every @task the app currently declares is registered — no errors. This is
    the guard: if someone lands a new task without a TaskRoute, this goes red."""
    assert check_tasks_registered(app_configs=None) == []


def test_unregistered_declared_task_is_flagged(monkeypatch):
    """Drop one real task from the registry view and the check reports E001 for
    it — the exact mistake #1947 is about (declared, forgotten in registry.py)."""
    routes = [r for r in get_all_tasks() if r.name != "hello_world"]
    monkeypatch.setattr(checks, "get_all_tasks", lambda: routes)

    errors = check_tasks_registered(app_configs=None)

    e001 = [e for e in errors if e.id == "gyrinx.tasks.E001"]
    assert len(e001) == 1
    assert "hello_world" in e001[0].msg
    assert "registry.py" in e001[0].hint


def test_registry_entry_that_isnt_a_task_is_flagged(monkeypatch):
    """A TaskRoute wrapping a plain (non-@task) function reports E002."""

    def not_a_task():
        pass

    monkeypatch.setattr(checks, "TASK_MODULES", ())  # isolate the reverse check
    monkeypatch.setattr(checks, "get_all_tasks", lambda: [TaskRoute(not_a_task)])

    errors = check_tasks_registered(app_configs=None)

    assert [e.id for e in errors] == ["gyrinx.tasks.E002"]
    assert "not_a_task" in errors[0].msg


def test_check_is_registered_with_django():
    """The check is wired into Django's system-check framework (not just defined),
    so it actually runs on manage check / runserver / CI."""
    from django.core.checks.registry import registry as check_registry

    assert check_tasks_registered in check_registry.get_checks()


def test_declared_tasks_attributes_tasks_to_their_own_module():
    """_declared_tasks only surfaces tasks *defined* in a module — a module with
    no @task (e.g. checks.py) yields nothing, so re-exports elsewhere can't create
    phantom 'unregistered' entries."""
    # checks.py declares no tasks.
    assert checks._declared_tasks(("gyrinx.tasks.checks",)) == {}
    # A real task module surfaces its own tasks, keyed to that module.
    declared = checks._declared_tasks(("gyrinx.core.tasks",))
    assert "reconcile_all_lists" in declared
    assert declared["reconcile_all_lists"] == "gyrinx.core.tasks"
