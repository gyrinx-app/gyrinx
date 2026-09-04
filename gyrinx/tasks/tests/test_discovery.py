"""Autodiscovery of per-app ``task_routes`` (#2093).

The platform no longer names the edition's tasks; it collects what each app
declares. These pin the properties that makes that safe: the right modules are
scanned, ordering is stable, per-task config survives, and the two ways this can
be got wrong are loud rather than silent.
"""

import pytest
from django.core.exceptions import ImproperlyConfigured
from django.tasks import task

from gyrinx.tasks import discovery
from gyrinx.tasks.registry import get_all_tasks
from gyrinx.tasks.route import TaskRoute

pytestmark = pytest.mark.core


class _StubAppConfig:
    def __init__(self, name):
        self.name = name


@task
def _discovery_sample_task():
    pass


def test_first_party_task_modules_covers_edition_namespaces(monkeypatch):
    """The per-edition namespaces are first-party too. The n23 rename (#2093)
    moved ``gyrinx.core`` to ``n23.core``; if the prefix filter still only
    accepted ``gyrinx.``, discovery would silently stop collecting the edition's
    routes and every one of its tasks would be unroutable in production."""
    monkeypatch.setattr(
        discovery.django_apps,
        "get_app_configs",
        lambda: [
            _StubAppConfig("n23.core"),
            _StubAppConfig("n26.content"),
            _StubAppConfig("thirdparty.app"),
        ],
    )
    # Pretend every candidate resolves, so this exercises the prefix filter
    # rather than module resolution.
    monkeypatch.setattr(discovery.importlib.util, "find_spec", lambda name: object())

    modules = discovery.first_party_task_modules()

    assert "n23.core.tasks" in modules
    assert "n26.content.tasks" in modules
    assert "thirdparty.app.tasks" not in modules


def test_first_party_task_modules_skips_apps_without_one():
    """Only modules that actually exist are returned — most apps have no tasks.py."""
    modules = discovery.first_party_task_modules()

    assert "n23.core.tasks" in modules
    assert "gyrinx.api.tasks" in modules
    assert "n23.content.tasks" not in modules


def test_first_party_task_modules_is_ordered_and_stable():
    """Ordering reaches topic provisioning, so it must not come from a set."""
    first = discovery.first_party_task_modules()

    assert isinstance(first, list)
    assert first == discovery.first_party_task_modules()


def test_discovery_finds_the_real_declarations():
    """Every app's declared routes end up in the registry, from both the edition
    and the platform's own api app."""
    names = {route.name for route in get_all_tasks()}

    assert "hello_world" in names  # n23.core.tasks
    assert "trigger_discord_issue_action" in names  # gyrinx.api.tasks


def test_discovery_preserves_per_task_config():
    """ack_deadline=600 is load-bearing for the long-running maintenance tasks;
    autodiscovery must carry each route's own config, not flatten to defaults."""
    routes = {route.name: route for route in get_all_tasks()}

    assert routes["backfill_pins"].ack_deadline == 600
    assert routes["reconcile_all_lists"].ack_deadline == 600
    assert routes["complete_campaign_list_clone"].ack_deadline == 600
    assert routes["hello_world"].ack_deadline == 300


def test_discovery_is_deterministically_ordered():
    """Topic provisioning iterates this list; set-ordered discovery would make
    provisioning and these tests flaky."""
    assert [r.path for r in discovery.discover_task_routes()] == [
        r.path for r in discovery.discover_task_routes()
    ]


def test_topic_names_derive_from_the_declaring_module():
    """A task's Pub/Sub topic is its module path. Discovery moved the *route*
    declarations, never the functions — so the topics are unchanged. Renaming a
    topic orphans the old one and needs a redeploy to recreate it."""
    routes = {route.name: route for route in get_all_tasks()}

    assert routes["hello_world"].path == "n23.core.tasks.hello_world"
    assert (
        routes["trigger_discord_issue_action"].path
        == "gyrinx.api.tasks.trigger_discord_issue_action"
    )
    assert routes["hello_world"].topic_name.endswith(
        "gyrinx.tasks--n23.core.tasks.hello_world"
    )


def test_non_taskroute_entry_is_rejected(monkeypatch):
    """A bare function in task_routes fails loudly at discovery rather than
    blowing up later inside the backend."""
    module = type("_M", (), {discovery.ROUTES_ATTR: [_discovery_sample_task]})

    monkeypatch.setattr(discovery, "first_party_task_modules", lambda: ["fake.tasks"])
    monkeypatch.setattr(discovery.importlib, "import_module", lambda path: module)

    with pytest.raises(ImproperlyConfigured, match="not a\\s+TaskRoute"):
        discovery.discover_task_routes()


def test_duplicate_task_name_across_apps_is_rejected(monkeypatch):
    """Two apps declaring the same task name would silently route one app's task
    to the other's topic — enqueue resolves by bare function name."""
    module = type(
        "_M", (), {discovery.ROUTES_ATTR: [TaskRoute(_discovery_sample_task)]}
    )

    monkeypatch.setattr(
        discovery, "first_party_task_modules", lambda: ["a.tasks", "b.tasks"]
    )
    monkeypatch.setattr(discovery.importlib, "import_module", lambda path: module)

    with pytest.raises(ImproperlyConfigured, match="Duplicate task name"):
        discovery.discover_task_routes()


def test_module_without_declarations_is_skipped(monkeypatch):
    """A tasks.py with no task_routes contributes nothing — no crash."""
    module = type("_M", (), {})

    monkeypatch.setattr(discovery, "first_party_task_modules", lambda: ["fake.tasks"])
    monkeypatch.setattr(discovery.importlib, "import_module", lambda path: module)

    assert discovery.discover_task_routes() == []
