"""System check: every ``@task`` in a known module must be registered (#1947).

Declaring a background task takes two steps in the same file: ``@task`` on the
function, plus a ``TaskRoute`` entry in that module's ``task_routes`` list.
Only the **production** Pub/Sub backend enforces the second step (enqueue lookup
+ topic provisioning) — dev's ImmediateBackend never consults the registry and
tests call ``.func`` directly. Miss step two and everything is green locally
while the task is dead on arrival in prod.

This check turns that omission into a red error at check time — ``runserver``,
``migrate``, ``check --deploy``, CI — seconds after the mistake is made, in the
author's own terminal. It also flags entries that aren't actually
``@task``-decorated functions.
"""

import importlib

from django.core.checks import Error, register
from django.tasks import Task

from gyrinx.tasks.discovery import ROUTES_ATTR, first_party_task_modules
from gyrinx.tasks.registry import get_all_tasks

# Escape hatch for a task module NOT named ``<app>.tasks`` (an unconventional
# location discovery wouldn't find). Empty by default: every first-party
# ``<app>/tasks.py`` is discovered, as is any module that already owns a
# registered task, so listing those here would only duplicate the scan.
TASK_MODULES = ()


def _task_module_paths(routes):
    """Every module worth scanning for ``@task`` functions:

    - the explicit ``TASK_MODULES``;
    - every module that already owns a registered task (so a second task added
      beside a registered one is caught);
    - each first-party app's conventional ``<app>.tasks`` module, when it exists
      — this closes the "brand-new app's first task, never registered" gap.

    That third source is ``discovery.first_party_task_modules()``, the very list
    the registry collects routes from. Sharing it is the point: scanning a
    different set than discovery reads would leave the difference unpoliced.
    Deduplicated in first-seen order rather than through a set, so the errors
    this check emits come out in a stable order.
    """
    paths = list(TASK_MODULES)
    paths += [route.path.rsplit(".", 1)[0] for route in routes]
    paths += first_party_task_modules()
    return list(dict.fromkeys(paths))


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
                        f"Add `TaskRoute({name})` to the `{ROUTES_ATTR}` list in "
                        f"{mod_path.replace('.', '/')}.py (create the list if the "
                        f"module hasn't got one). Unregistered tasks pass locally "
                        f"(dev's ImmediateBackend and .func test calls skip the "
                        f"registry) but fail on enqueue in production."
                    ),
                    id="gyrinx.tasks.E001",
                )
            )

    # Reverse: a registry entry must wrap a real @task. A deleted function fails
    # at import of the declaring module already; this catches registering a
    # plain function.
    for route in routes:
        if not isinstance(route.func, Task):
            errors.append(
                Error(
                    f"Registry entry '{route.name}' is not a @task-decorated function.",
                    hint=(
                        f"Every TaskRoute in a `{ROUTES_ATTR}` list must wrap a "
                        f"function decorated with django.tasks @task."
                    ),
                    id="gyrinx.tasks.E002",
                )
            )
    return errors
