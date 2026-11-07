"""Serialise Debug Toolbar panel snapshots when they are first read.

Detach mutable panel data when saved, converting unsupported values with the
toolbar encoder. Later reads use its serialise and deserialise functions. A
lock prevents an older encoding result from replacing a newer snapshot.
"""

import threading

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
    # Held while saving and while keeping a read's JSON, so a read that finishes
    # encoding after a newer save never replaces it. runserver is threaded.
    lock = threading.Lock()

    @classmethod
    def save_panel(cls, request_id, panel_id, data=None):
        snapshot = Unserialized(detach(data))
        with cls.lock:
            cls.set(request_id)
            cls._request_store[request_id][panel_id] = snapshot

    @classmethod
    def serialized(cls, request_id, panel_id):
        """The JSON for one panel, encoding it now if nothing has read it yet."""
        stored = cls._request_store[request_id][panel_id]
        if not isinstance(stored, Unserialized):
            return stored
        encoded = serialize(stored.data)
        # Encoding runs outside the lock. Keep the JSON only if nothing saved a
        # newer snapshot, or evicted the request, in the meantime.
        with cls.lock:
            panels = cls._request_store.get(request_id)
            if panels is not None and panels.get(panel_id) is stored:
                panels[panel_id] = encoded
        return encoded

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
