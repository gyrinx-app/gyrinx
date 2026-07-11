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

from django.core.checks import Error, register
from django.tasks import Task

from gyrinx.tasks.registry import get_all_tasks

# Modules that declare ``@task`` functions. Forgetting to register a task added
# to one of these is the common trap this check closes. We also scan every
# module that already owns a registered task (see ``check_tasks_registered``),
# so a second task added beside a registered one is caught even if the module
# isn't listed here. A brand-new module with *no* registered task is the rarer
# case that recommendation 2 in #1947 (declaration-owned registration) closes
# structurally — add such modules here until then.
TASK_MODULES = ("gyrinx.core.tasks",)


def _declared_tasks(module_paths):
    """Map ``{task_name: module_path}`` for every ``@task`` defined in the given
    modules. Tasks merely *imported* into a module (``func.__module__`` differs)
    are attributed to their own module, not double-counted here."""
    declared = {}
    for mod_path in module_paths:
        module = importlib.import_module(mod_path)
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

    # Scan the configured modules plus any module already owning a registered
    # task, so "added a second task next to a registered one" is always caught.
    module_paths = set(TASK_MODULES) | {
        route._underlying_func.__module__ for route in routes
    }
    declared = _declared_tasks(module_paths)

    # Forward: a declared @task missing from the registry is dead on arrival in
    # production (the Pub/Sub backend rejects the enqueue and provisions no topic).
    for name, mod_path in sorted(declared.items()):
        if name not in registered:
            errors.append(
                Error(
                    f"Background task '{name}' ({mod_path}) is declared with @task "
                    f"but not registered.",
                    hint=(
                        f"Add `TaskRoute({name})` to the list in "
                        f"gyrinx/tasks/registry.py. Unregistered tasks pass locally "
                        f"(dev's ImmediateBackend and .func test calls skip the "
                        f"registry) but fail on enqueue in production."
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
