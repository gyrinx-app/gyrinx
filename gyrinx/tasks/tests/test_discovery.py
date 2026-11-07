"""Discover app task routes with stable ordering and unique task names."""

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

    monkeypatch.setattr(
        discovery.django_apps,
        "get_app_configs",
        lambda: [
            _StubAppConfig("n23.core"),
            _StubAppConfig("n26.content"),
            _StubAppConfig("thirdparty.app"),
        ],
    )
    # Treat all candidate modules as importable to isolate namespace filtering.
    monkeypatch.setattr(discovery.importlib.util, "find_spec", lambda name: object())

    modules = discovery.first_party_task_modules()

    assert "n23.core.tasks" in modules
    assert "n26.content.tasks" in modules
    assert "thirdparty.app.tasks" not in modules


def test_first_party_task_modules_skips_apps_without_one():

    modules = discovery.first_party_task_modules()

    assert "n23.core.tasks" in modules
    assert "gyrinx.api.tasks" in modules
    assert "n23.content.tasks" not in modules


def test_first_party_task_modules_is_ordered_and_stable():

    first = discovery.first_party_task_modules()

    assert isinstance(first, list)
    assert first == discovery.first_party_task_modules()


def test_discovery_finds_the_real_declarations():

    names = {route.name for route in get_all_tasks()}

    assert "hello_world" in names  # n23.core.tasks
    assert "trigger_discord_issue_action" in names  # gyrinx.api.tasks


def test_discovery_preserves_per_task_config():
    """Preserve the longer acknowledgement deadlines required by maintenance tasks."""
    routes = {route.name: route for route in get_all_tasks()}

    assert routes["backfill_pins"].ack_deadline == 600
    assert routes["reconcile_all_lists"].ack_deadline == 600
    assert routes["complete_campaign_list_clone"].ack_deadline == 600
    assert routes["hello_world"].ack_deadline == 300


def test_discovery_is_deterministically_ordered():

    assert [r.path for r in discovery.discover_task_routes()] == [
        r.path for r in discovery.discover_task_routes()
    ]


def test_topic_names_derive_from_the_declaring_module():
    """Derive topics from task function modules, independently of where routes are declared."""
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

    module = type("_M", (), {discovery.ROUTES_ATTR: [_discovery_sample_task]})

    monkeypatch.setattr(discovery, "first_party_task_modules", lambda: ["fake.tasks"])
    monkeypatch.setattr(discovery.importlib, "import_module", lambda path: module)

    with pytest.raises(ImproperlyConfigured, match="not a\\s+TaskRoute"):
        discovery.discover_task_routes()


def test_duplicate_task_name_across_apps_is_rejected(monkeypatch):
    """Reject duplicate names because enqueue resolves routes by bare function name."""
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

    module = type("_M", (), {})

    monkeypatch.setattr(discovery, "first_party_task_modules", lambda: ["fake.tasks"])
    monkeypatch.setattr(discovery.importlib, "import_module", lambda path: module)

    assert discovery.discover_task_routes() == []
