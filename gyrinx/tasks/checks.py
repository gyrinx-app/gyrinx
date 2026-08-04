"""System check: every ``@task`` in a known module must be registered (#1947).

Declaring a background task is a two-step ritual split across two files with
nothing coupling them: ``@task`` in the task module, plus a ``TaskRoute`` entry
in ``gyrinx/tasks/registry.py``. Only the **production** Pub/Sub backend enforces
the second step (enqueue lookup + topic provisioning) — dev's ImmediateBackend
never consults the registry and tests call ``.func`` directly. Miss step two and
everything is green locally while the task is dead on arrival in prod.

This check turns that omission into a red error at check time — ``runserver``,
``migrate``, ``check --deploy``, CI — seconds after the mistake is made, in the
author's own terminal. It also flags registry entries that aren't actually
``@task``-decorated functions.
"""

import importlib
import importlib.util

from django.apps import apps as django_apps
from django.core.checks import Error, register
from django.tasks import Task

from gyrinx.tasks.registry import get_all_tasks

# Escape hatch for a task module NOT named ``<app>.tasks`` (an unconventional
# location auto-discovery in ``_task_module_paths`` wouldn't find). Empty by
# default: every first-party ``<app>/tasks.py`` is auto-discovered, as is any
# module that already owns a registered task, so listing those here would only
# duplicate the scan.
TASK_MODULES = ()

# Import prefixes we consider first-party. Auto-discovery is restricted to these
# so a third-party app's task module can't spuriously demand entries in *our*
# registry. ``n23.``/``n26.`` are the per-edition namespaces (#2093): the current
# edition moves from ``gyrinx.core``/``gyrinx.content`` to ``n23.*``, and n26
# lands alongside it. They are listed ahead of the move so the rename cannot
# silently narrow this scan — the failure mode would be a brand-new edition app's
# first task going unregistered, which only surfaces in production.
FIRST_PARTY_PREFIXES = ("gyrinx.", "n23.", "n26.")


def _task_module_paths(routes):
    """Every module worth scanning for ``@task`` functions:

    - the explicit ``TASK_MODULES``;
    - every module that already owns a registered task (so a second task added
      beside a registered one is caught);
    - each first-party app's conventional ``<app>.tasks`` module, when it exists
      — this closes the "brand-new app's first task, never registered" gap
      without waiting for declaration-owned registration (#1947 rec 2). See
      ``FIRST_PARTY_PREFIXES`` for what counts as first-party.
    """
    paths = set(TASK_MODULES)
    paths |= {route.path.rsplit(".", 1)[0] for route in routes}
    for app_config in django_apps.get_app_configs():
        if not app_config.name.startswith(FIRST_PARTY_PREFIXES):
            continue
        candidate = f"{app_config.name}.tasks"
        try:
            spec = importlib.util.find_spec(candidate)
        except (ImportError, AttributeError, ValueError):
            spec = None  # parent not importable / not a package — nothing to scan
        if spec is not None:
            paths.add(candidate)
    return paths


def _declared_tasks(module_paths):
    """Map ``{task_name: module_path}`` for every ``@task`` defined in the given
    modules. Tasks merely *imported* into a module (``func.__module__`` differs)
    are attributed to their own module, not double-counted here."""
    declared = {}
    for mod_path in module_paths:
        try:
            module = importlib.import_module(mod_path)
        except ModuleNotFoundError as exc:
            # Skip only when the target module itself is absent (a typo'd
            # TASK_MODULES entry, or a removed module) — nothing to scan. A
            # missing *dependency* of a real module (``exc.name`` is something
            # else) is genuine breakage and must not be hidden, so let it raise.
            if exc.name == mod_path or mod_path.startswith(f"{exc.name}."):
                continue
            raise
        for obj in vars(module).values():
            if isinstance(obj, Task) and obj.func.__module__ == mod_path:
                declared[obj.func.__name__] = mod_path
    return declared


@register()
def check_tasks_registered(app_configs, **kwargs):
    """Cross-check declared ``@task`` functions against the registry, both ways."""
    errors = []
    routes = get_all_tasks()
    registered = {route.name for route in routes}
    declared = _declared_tasks(_task_module_paths(routes))

    # Forward: a declared @task missing from the registry is dead on arrival in
    # production (the Pub/Sub backend rejects the enqueue and provisions no topic).
    for name, mod_path in sorted(declared.items()):
        if name not in registered:
            errors.append(
                Error(
                    f"Background task '{name}' ({mod_path}) is declared with @task "
                    f"but not registered.",
                    hint=(
                        f"In gyrinx/tasks/registry.py, import it "
                        f"(`from {mod_path} import {name}`) and add "
                        f"`TaskRoute({name})` to the list. Unregistered tasks pass "
                        f"locally (dev's ImmediateBackend and .func test calls skip "
                        f"the registry) but fail on enqueue in production."
                    ),
                    id="gyrinx.tasks.E001",
                )
            )

    # Reverse: a registry entry must wrap a real @task. A deleted function fails
    # at import of registry.py already; this catches registering a plain function.
    for route in routes:
        if not isinstance(route.func, Task):
            errors.append(
                Error(
                    f"Registry entry '{route.name}' is not a @task-decorated function.",
                    hint=(
                        "Every TaskRoute in gyrinx/tasks/registry.py must wrap a "
                        "function decorated with django.tasks @task."
                    ),
                    id="gyrinx.tasks.E002",
                )
            )
    return errors
