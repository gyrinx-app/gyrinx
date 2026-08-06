"""Autodiscovery of per-app task routes.

Modelled on ``django.contrib.admin.autodiscover()``: the platform walks the
installed apps, imports each one's conventional module, and lets the app itself
say what it wants registered. Here the module is ``<app>/tasks.py`` — where the
task functions already live — and the declaration is a module-level
``task_routes`` list, the same shape as a URLconf's ``urlpatterns``:

    from django.tasks import task
    from gyrinx.tasks import TaskRoute

    @task
    def send_welcome_email(user_id: int): ...

    task_routes = [
        TaskRoute(send_welcome_email),
    ]

**Declarations are discovered, not tasks.** We deliberately do not scan for
``@task``-decorated functions and register everything we find. A route carries
per-task configuration (ack deadline, retry backoff, cron schedule) and is the
surface that provisions a Pub/Sub topic — infrastructure with a cost and an IAM
footprint. Creating one as an implicit side effect of "somebody imported a
module" is the wrong trade; the app states its intent explicitly, and the
platform only collects it. (``.claude/notes/task-registry-footgun.md``, option
D.) ``gyrinx.tasks.checks`` polices the gap this leaves — a ``@task`` declared
and then left out of ``task_routes``.

Why this exists: ``gyrinx/tasks/registry.py`` used to import eight tasks from
``n23.core.tasks`` by name, so the platform depended on the edition it is meant
to be independent of (#2093). Inverting it means a new edition — or any new app
— registers its own tasks without the platform being edited at all.
"""

import importlib
import importlib.util

from django.apps import apps as django_apps
from django.core.exceptions import ImproperlyConfigured

from gyrinx.tasks.route import TaskRoute

# The conventional per-app module that declares background tasks.
TASK_MODULE_NAME = "tasks"

# The module-level name that module uses to declare its routes.
ROUTES_ATTR = "task_routes"

# Import prefixes we consider first-party. Discovery is restricted to these so a
# third-party app's ``tasks`` module is never imported on our behalf, and so
# nothing outside the project can put a route into our registry. ``n23.``/``n26.``
# are the per-edition namespaces (#2093): the current edition moved out of
# ``gyrinx.core``/``gyrinx.content`` to ``n23.*``, and n26 will land alongside
# it. ``gyrinx.`` stays because the platform packages (tasks, api, pages,
# analytics, maintenance) still live there.
#
# This is also the single definition of "first-party" shared with
# ``gyrinx.tasks.checks``. That matters: the check's job is "every declared
# @task is registered", so if it scanned a different set of modules than
# discovery collected from, the difference would be an unpoliced hole. Losing a
# prefix here silently narrows both at once rather than erroring — a brand-new
# edition app's first task would go unregistered, which only surfaces in
# production.
FIRST_PARTY_PREFIXES = ("gyrinx.", "n23.", "n26.")


def first_party_task_modules() -> list[str]:
    """Every first-party ``<app>.tasks`` module that actually exists.

    Ordered by ``INSTALLED_APPS`` (which ``get_app_configs()`` preserves) and
    returned as a list rather than a set: this ordering reaches topic
    provisioning and the tests, and set iteration order would make both flaky.
    """
    modules = []
    for app_config in django_apps.get_app_configs():
        if not app_config.name.startswith(FIRST_PARTY_PREFIXES):
            continue
        candidate = f"{app_config.name}.{TASK_MODULE_NAME}"
        try:
            spec = importlib.util.find_spec(candidate)
        except (ImportError, AttributeError, ValueError):
            spec = None  # parent not importable / not a package — nothing there
        if spec is not None:
            modules.append(candidate)
    return modules


def discover_task_routes() -> list[TaskRoute]:
    """Import every first-party task module and collect its declared routes.

    Ordering is deterministic: apps in ``INSTALLED_APPS`` order, and within an
    app the order the module lists them in.

    Raises:
        ImproperlyConfigured: if a ``task_routes`` entry isn't a ``TaskRoute``,
            or if two apps declare the same task name.
    """
    routes: list[TaskRoute] = []
    seen: dict[str, str] = {}  # task name -> the module that declared it

    for mod_path in first_party_task_modules():
        module = importlib.import_module(mod_path)
        declared = getattr(module, ROUTES_ATTR, None)
        if declared is None:
            continue

        for route in declared:
            if not isinstance(route, TaskRoute):
                raise ImproperlyConfigured(
                    f"{mod_path}.{ROUTES_ATTR} contains {route!r}, which is not a "
                    f"TaskRoute. Wrap the task: TaskRoute(my_task)."
                )
            # Names must be unique: enqueue and the push handler both resolve a
            # task by bare function name, so a collision would silently route
            # one app's task to the other app's topic.
            if route.name in seen:
                raise ImproperlyConfigured(
                    f"Duplicate task name '{route.name}' declared in both "
                    f"{seen[route.name]}.{ROUTES_ATTR} and {mod_path}.{ROUTES_ATTR}. "
                    f"Task names must be unique across the project."
                )
            seen[route.name] = mod_path
            routes.append(route)

    return routes
