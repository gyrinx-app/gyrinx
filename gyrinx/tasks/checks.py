"""Check that task declarations and registered routes agree.

Each background function needs @task and a TaskRoute in its module's
task_routes. The check reports unregistered declarations and routes that
wrap ordinary functions. Production needs routes for enqueue lookup and
topic provisioning.
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
    """Return modules to scan for task declarations.

    Include TASK_MODULES, registered-task modules and existing first-party
    app task modules. The last group catches an app's first unregistered task.
    """
    paths = list(TASK_MODULES)
    paths += [route.path.rsplit(".", 1)[0] for route in routes]
    paths += first_party_task_modules()
    return list(dict.fromkeys(paths))


def _declared_tasks(module_paths):
    """Map task names to their defining modules in the supplied module paths.

    Ignore imported tasks whose underlying function belongs to another module.
    """
    declared = {}
    for mod_path in module_paths:
        try:
            module = importlib.import_module(mod_path)
        except ModuleNotFoundError as exc:
            # Skip a missing target module, but propagate missing dependencies from a
            # module that exists so import failures remain visible.
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

    # Unregistered tasks cannot enqueue or provision topics in production.
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

    # Registered routes must wrap Django tasks, not ordinary functions.
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
