"""
A debug toolbar store that serializes each panel's data when it is read.

The toolbar's ``MemoryStore`` turns every panel's data into JSON as the request
ends, on every ``record_stats`` call, so that the History panel and the
on-demand panel views can read it back later. Most of that data is never read.
On a component-heavy page the Templates panel alone holds megabytes of
formatted context, and encoding it took longer than rendering the page.

This store takes a detached copy of the data when it is saved and serializes the
copy the first time anything reads it, through the toolbar's own ``serialize``
and ``deserialize``. The copy shares strings and numbers, which cannot change,
and turns anything else JSON cannot hold into what the toolbar's encoder would
have made of it at that moment, so every reader gets exactly what
``MemoryStore`` would have given it, even if the recorded objects change later.
Copying is cheap; encoding the long strings is what was slow. The page that was
just rendered never reads its own entry: the toolbar draws it from the stats it
holds in memory.

It is development-only, and ``settings_dev`` selects it through the toolbar's
``TOOLBAR_STORE_CLASS`` setting. It lives apart from ``gyrinx/toolbar_dev.py``
because ``debug_toolbar.store`` imports a model, so it cannot be imported while
apps are still loading.
"""

from debug_toolbar.store import (
    DebugToolbarJSONEncoder,
    MemoryStore,
    deserialize,
    serialize,
)

_ENCODER = DebugToolbarJSONEncoder()


def detach(value):
    """A copy of ``value`` that later changes to the original cannot reach.

    Mirrors what ``serialize`` does with each kind of value, so serializing the
    copy later gives the same JSON as serializing the original now.
    """
    if value is None or isinstance(value, (str, int, float)):
        return value
    if isinstance(value, dict):
        return {key: detach(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [detach(item) for item in value]
    return detach(_ENCODER.default(value))


class Unserialized:
    """Panel data that has been recorded but not yet turned into JSON."""

    __slots__ = ("data",)

    def __init__(self, data):
        self.data = data


class LazyMemoryStore(MemoryStore):
    @classmethod
    def save_panel(cls, request_id, panel_id, data=None):
        cls.set(request_id)
        cls._request_store[request_id][panel_id] = Unserialized(detach(data))

    @classmethod
    def serialized(cls, request_id, panel_id):
        """The JSON for one panel, encoding it now if nothing has read it yet."""
        stored = cls._request_store[request_id][panel_id]
        if isinstance(stored, Unserialized):
            stored = serialize(stored.data)
            # The entry may have been evicted while it was being encoded.
            if request_id in cls._request_store:
                cls._request_store[request_id][panel_id] = stored
        return stored

    @classmethod
    def panel(cls, request_id, panel_id):
        try:
            return deserialize(cls.serialized(request_id, panel_id))
        except KeyError:
            return {}

    @classmethod
    def panels(cls, request_id):
        try:
            panel_ids = list(cls._request_store[request_id])
        except KeyError:
            return
        for panel_id in panel_ids:
            try:
                data = cls.serialized(request_id, panel_id)
            except KeyError:
                continue
            yield panel_id, deserialize(data)
