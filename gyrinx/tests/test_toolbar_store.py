"""The lazy toolbar store gives readers exactly what the toolbar's MemoryStore would."""

import uuid

import pytest
from debug_toolbar.store import MemoryStore, get_store
from django.utils.safestring import mark_safe

from gyrinx.toolbar_store import LazyMemoryStore, Unserialized


class NotJSON:
    label = "not json"

    def __str__(self):
        return self.label


def sample_stats():
    return {
        "queries": [{"sql": "SELECT 1", "params": ("a", 1), "raw": b"\x00\x01"}],
        "html": mark_safe("<b>bold</b>"),
        "other": NotJSON(),
        "nothing": None,
    }


@pytest.fixture
def request_id():
    request_id = uuid.uuid4().hex
    yield request_id
    LazyMemoryStore.delete(request_id)
    MemoryStore.delete(request_id)


def test_development_uses_the_lazy_store():
    assert get_store() is LazyMemoryStore


def test_a_panel_reads_back_as_memory_store_gives_it(request_id):
    MemoryStore.save_panel(request_id, "SQLPanel", sample_stats())
    expected = MemoryStore.panel(request_id, "SQLPanel")
    MemoryStore.delete(request_id)

    LazyMemoryStore.save_panel(request_id, "SQLPanel", sample_stats())

    assert isinstance(
        LazyMemoryStore._request_store[request_id]["SQLPanel"], Unserialized
    )
    assert LazyMemoryStore.panel(request_id, "SQLPanel") == expected
    # The first read stored the JSON, so later reads decode the same string.
    assert isinstance(LazyMemoryStore._request_store[request_id]["SQLPanel"], str)
    assert LazyMemoryStore.panel(request_id, "SQLPanel") == expected


def test_the_last_recorded_stats_are_the_ones_read(request_id):
    stats = {"count": 1}
    LazyMemoryStore.save_panel(request_id, "SQLPanel", stats)
    stats.update(count=2)
    LazyMemoryStore.save_panel(request_id, "SQLPanel", stats)

    assert LazyMemoryStore.panel(request_id, "SQLPanel") == {"count": 2}


def test_a_change_after_saving_does_not_reach_the_reader(request_id):
    """The store keeps what was saved, as MemoryStore's save-time JSON does."""
    named = NotJSON()
    query = {"sql": "SELECT 1", "params": ["a"], "object": named}
    LazyMemoryStore.save_panel(request_id, "SQLPanel", {"queries": [query]})

    query["sql"] = "SELECT 2"
    query["params"].append("b")
    named.label = "changed"

    assert LazyMemoryStore.panel(request_id, "SQLPanel") == {
        "queries": [{"sql": "SELECT 1", "params": ["a"], "object": "not json"}]
    }


def test_all_panels_read_back_for_one_request(request_id):
    LazyMemoryStore.save_panel(request_id, "SQLPanel", {"a": 1})
    LazyMemoryStore.save_panel(request_id, "HistoryPanel", {"b": (2, 3)})

    assert dict(LazyMemoryStore.panels(request_id)) == {
        "SQLPanel": {"a": 1},
        "HistoryPanel": {"b": [2, 3]},
    }


def test_an_unknown_request_or_panel_reads_as_empty(request_id):
    assert LazyMemoryStore.panel(request_id, "SQLPanel") == {}
    assert dict(LazyMemoryStore.panels(request_id)) == {}

    LazyMemoryStore.save_panel(request_id, "SQLPanel", {"a": 1})

    assert LazyMemoryStore.panel(request_id, "TemplatesPanel") == {}
