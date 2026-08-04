"""The #1947 system check: declared @task functions must be registered."""

from django.tasks import task

import gyrinx.tasks.checks as checks
from gyrinx.tasks.registry import get_all_tasks
from gyrinx.tasks.route import TaskRoute


# Module-level @task functions (Django requires module scope) for tests that
# need a task in a module OTHER than n23.core.tasks. Neither is in the real
# registry, TASK_MODULES, or a discovered <app>.tasks module, so the live check
# never scans this module — they're inert outside the tests that reference them.
@task
def sample_registered():
    pass


@task
def sample_unregistered():
    pass


def test_current_registry_passes_the_check():
    """Every @task the app currently declares is registered — no errors. This is
    the guard: if someone lands a new task without a TaskRoute, this goes red."""
    assert checks.check_tasks_registered(app_configs=None) == []


def test_unregistered_declared_task_is_flagged(monkeypatch):
    """Drop one real task from the registry view and the check reports E001 for
    it — the exact mistake #1947 is about (declared, forgotten in registry.py)."""
    routes = [r for r in get_all_tasks() if r.name != "hello_world"]
    monkeypatch.setattr(checks, "get_all_tasks", lambda: routes)

    errors = checks.check_tasks_registered(app_configs=None)

    e001 = [e for e in errors if e.id == "gyrinx.tasks.E001"]
    assert len(e001) == 1
    assert "hello_world" in e001[0].msg
    assert "registry.py" in e001[0].hint


def test_module_owning_a_registered_task_is_scanned(monkeypatch):
    """A second @task in a module reached ONLY via a registered task's own module
    (not TASK_MODULES) is still caught — guards the route-module derivation."""
    monkeypatch.setattr(checks, "TASK_MODULES", ())
    monkeypatch.setattr(checks, "get_all_tasks", lambda: [TaskRoute(sample_registered)])

    errors = checks.check_tasks_registered(app_configs=None)

    e001 = [e for e in errors if e.id == "gyrinx.tasks.E001"]
    assert any("sample_unregistered" in e.msg for e in e001)
    assert not any("sample_registered" in e.msg for e in e001)


def test_app_discovery_reaches_conventional_task_modules(monkeypatch):
    """With no explicit TASK_MODULES and no registered routes, the scan still
    reaches n23.core.tasks purely by discovering the n23.core app's
    conventional <app>.tasks module — this closes the new-app gap."""
    monkeypatch.setattr(checks, "TASK_MODULES", ())

    paths = checks._task_module_paths([])

    assert "n23.core.tasks" in paths


def test_app_discovery_covers_edition_namespaces(monkeypatch):
    """The per-edition namespaces are first-party too. The n23 rename (#2093)
    moved ``gyrinx.core`` to ``n23.core``; if the prefix filter still only
    accepted ``gyrinx.``, this scan would silently stop discovering the
    edition's task module and the #1947 guard would weaken to nothing —
    a gap that only shows up in production."""

    class _StubAppConfig:
        def __init__(self, name):
            self.name = name

    monkeypatch.setattr(checks, "TASK_MODULES", ())
    monkeypatch.setattr(
        checks.django_apps,
        "get_app_configs",
        lambda: [
            _StubAppConfig("n23.core"),
            _StubAppConfig("n26.content"),
            _StubAppConfig("thirdparty.app"),
        ],
    )
    # Pretend every candidate resolves, so this exercises the prefix filter
    # rather than module resolution.
    monkeypatch.setattr(checks.importlib.util, "find_spec", lambda name: object())

    paths = checks._task_module_paths([])

    assert "n23.core.tasks" in paths
    assert "n26.content.tasks" in paths
    assert "thirdparty.app.tasks" not in paths


def test_registry_entry_that_isnt_a_task_is_flagged(monkeypatch):
    """A TaskRoute wrapping a plain (non-@task) function reports E002."""

    def not_a_task():
        pass

    # Silence the forward scan so only the reverse check runs.
    monkeypatch.setattr(checks, "_task_module_paths", lambda routes: set())
    monkeypatch.setattr(checks, "get_all_tasks", lambda: [TaskRoute(not_a_task)])

    errors = checks.check_tasks_registered(app_configs=None)

    assert [e.id for e in errors] == ["gyrinx.tasks.E002"]
    assert "not_a_task" in errors[0].msg


def test_check_is_registered_with_django():
    """The check is wired into Django's system-check framework (not just defined),
    so it actually runs on manage check / runserver / CI."""
    from django.core.checks.registry import registry as check_registry

    assert checks.check_tasks_registered in check_registry.get_checks()


def test_declared_tasks_attributes_tasks_to_their_own_module():
    """_declared_tasks only surfaces tasks *defined* in a module — a module with
    no @task (e.g. checks.py) yields nothing, so re-exports elsewhere can't create
    phantom 'unregistered' entries."""
    assert checks._declared_tasks(("gyrinx.tasks.checks",)) == {}
    declared = checks._declared_tasks(("n23.core.tasks",))
    assert "reconcile_all_lists" in declared
    assert declared["reconcile_all_lists"] == "n23.core.tasks"


def test_declared_tasks_skips_unimportable_module():
    """A bad module path degrades gracefully (skipped) rather than crashing the
    whole system check with a traceback."""
    assert checks._declared_tasks(("gyrinx.tasks.does_not_exist",)) == {}
