"""System checks for task declarations and registered routes."""

import pytest
from django.tasks import task

import gyrinx.tasks.checks as checks
from gyrinx.tasks.registry import get_all_tasks
from gyrinx.tasks.route import TaskRoute

pytestmark = pytest.mark.core


# Django tasks require module-level functions. These test declarations are
# outside discovered task modules and enter the check only through test fixtures.
@task
def sample_registered():
    pass


@task
def sample_unregistered():
    pass


def test_current_registry_passes_the_check():

    assert checks.check_tasks_registered(app_configs=None) == []


def test_unregistered_declared_task_is_flagged(monkeypatch):

    routes = [r for r in get_all_tasks() if r.name != "hello_world"]
    monkeypatch.setattr(checks, "get_all_tasks", lambda: routes)

    errors = checks.check_tasks_registered(app_configs=None)

    e001 = [e for e in errors if e.id == "gyrinx.tasks.E001"]
    assert len(e001) == 1
    assert "hello_world" in e001[0].msg
    # Point the registration hint at the task's declaring module.
    assert "task_routes" in e001[0].hint
    assert "n23/core/tasks.py" in e001[0].hint


def test_module_owning_a_registered_task_is_scanned(monkeypatch):

    monkeypatch.setattr(checks, "TASK_MODULES", ())
    monkeypatch.setattr(checks, "get_all_tasks", lambda: [TaskRoute(sample_registered)])

    errors = checks.check_tasks_registered(app_configs=None)

    e001 = [e for e in errors if e.id == "gyrinx.tasks.E001"]
    assert any("sample_unregistered" in e.msg for e in e001)
    assert not any("sample_registered" in e.msg for e in e001)


def test_app_discovery_reaches_conventional_task_modules(monkeypatch):

    monkeypatch.setattr(checks, "TASK_MODULES", ())

    paths = checks._task_module_paths([])

    assert "n23.core.tasks" in paths


# Prefix filtering is covered in test_discovery.py.


def test_registry_entry_that_isnt_a_task_is_flagged(monkeypatch):

    def not_a_task():
        pass

    # Disable declaration scanning to isolate invalid registry entries.
    monkeypatch.setattr(checks, "_task_module_paths", lambda routes: set())
    monkeypatch.setattr(checks, "get_all_tasks", lambda: [TaskRoute(not_a_task)])

    errors = checks.check_tasks_registered(app_configs=None)

    assert [e.id for e in errors] == ["gyrinx.tasks.E002"]
    assert "not_a_task" in errors[0].msg


def test_check_is_registered_with_django():

    from django.core.checks.registry import registry as check_registry

    assert checks.check_tasks_registered in check_registry.get_checks()


def test_declared_tasks_attributes_tasks_to_their_own_module():

    assert checks._declared_tasks(("gyrinx.tasks.checks",)) == {}
    declared = checks._declared_tasks(("n23.core.tasks",))
    assert "reconcile_all_lists" in declared
    assert declared["reconcile_all_lists"] == "n23.core.tasks"


def test_declared_tasks_skips_unimportable_module():

    assert checks._declared_tasks(("gyrinx.tasks.does_not_exist",)) == {}
