"""The 0172 backfill must copy ``was_random`` onto the *historical* rows too.

0173 drops ``was_random`` from ``historicalcrewmember`` as well as the live
table, so 0172 is the only chance to carry the value across. Miss it and every
historical row keeps the ``source`` field default — the change history then says
forever that fighters drawn at random were hand-picked.

The real migration can't be exercised against the current schema (``was_random``
is long gone from both models), so the backfill function is driven against a
stand-in registry. That is enough to pin the thing that was wrong: which models
the function touches.
"""

import pytest

migration = __import__(
    "n23.core.migrations.0172_backfill_crew_member_source",
    fromlist=["backfill_member_source", "unbackfill_member_source"],
)


class _FakeManager:
    """Just enough queryset for the backfill: ``filter``, ``update``,
    ``iterator``. Filtering returns the same row dicts, so updating a filtered
    subset writes through to the originals."""

    def __init__(self, rows):
        self.rows = rows

    def filter(self, **kwargs):
        return _FakeManager(
            [r for r in self.rows if all(r.get(k) == v for k, v in kwargs.items())]
        )

    def update(self, **kwargs):
        for row in self.rows:
            row.update(kwargs)
        return len(self.rows)

    def iterator(self):
        return iter(self.rows)

    def delete(self):
        for row in self.rows:
            row["_deleted"] = True


class _FakeApps:
    def __init__(self, **models):
        self._models = {
            name: type("FakeModel", (), {"objects": _FakeManager(rows)})
            for name, rows in models.items()
        }

    def get_model(self, app_label, model_name):
        return self._models[model_name]


def _rows():
    """A drawn member and a chosen one, in both tables, as they look straight
    after 0171 adds ``source`` with its default."""
    return [
        {"was_random": True, "source": "chosen"},
        {"was_random": False, "source": "chosen"},
    ]


def test_backfill_copies_was_random_onto_historical_rows():
    live, historical = _rows(), _rows()
    apps = _FakeApps(CrewMember=live, HistoricalCrewMember=historical, Crew=[])

    migration.backfill_member_source(apps, None)

    assert [r["source"] for r in historical] == ["random", "chosen"]
    assert [r["source"] for r in live] == ["random", "chosen"]


def test_reverse_restores_was_random_on_historical_rows():
    live = [
        {"was_random": False, "source": "random"},
        {"was_random": False, "source": "chosen"},
    ]
    historical = [
        {"was_random": False, "source": "random"},
        {"was_random": False, "source": "chosen"},
    ]
    apps = _FakeApps(CrewMember=live, HistoricalCrewMember=historical, Crew=[])

    migration.unbackfill_member_source(apps, None)

    assert [r["was_random"] for r in historical] == [True, False]
    assert [r["was_random"] for r in live] == [True, False]


@pytest.mark.parametrize("func", ["backfill_member_source", "unbackfill_member_source"])
def test_both_directions_touch_the_historical_model(func):
    """A guard against the original bug rather than its symptom: whichever way
    the migration runs, it must ask for HistoricalCrewMember at all."""
    asked = []

    class _Recorder(_FakeApps):
        def get_model(self, app_label, model_name):
            asked.append(model_name)
            return super().get_model(app_label, model_name)

    apps = _Recorder(CrewMember=_rows(), HistoricalCrewMember=_rows(), Crew=[])
    getattr(migration, func)(apps, None)

    assert "HistoricalCrewMember" in asked
