"""The counter-change engine: entered changes, corrections and results."""

from types import SimpleNamespace
from uuid import uuid4

import pytest

from n26.core.counter_changes import (
    CounterChange,
    HeldCounter,
    changeable,
    entries,
    held_counters,
    plan_changes,
    read_changes,
)
from n26.library.models import Counter, Rule


def held(name="Reputation", reading=5, stored=None):
    return HeldCounter(
        assignment=SimpleNamespace(pk=uuid4()),
        name=name,
        reading=reading,
        stored=reading if stored is None else stored,
    )


def node(thing, *, value=0, assignment=True, broadcast=False, suppressed=False):
    return SimpleNamespace(
        assignable=thing,
        assignment=(
            SimpleNamespace(pk=uuid4(), counter_value=SimpleNamespace(value=value))
            if assignment
            else None
        ),
        broadcast=broadcast,
        suppressed=suppressed,
    )


class TestReadChanges:
    def test_signed_whole_numbers_are_kept_and_zeros_dropped(self):
        errors = []
        assert read_changes(
            {"a": "3", "b": "-2", "c": "", "d": "0", "e": 4}, errors
        ) == {"a": 3, "b": -2, "e": 4}
        assert errors == []

    def test_anything_else_is_reported_and_counts_as_no_change(self):
        errors = []
        assert read_changes({"a": "two", "b": "1001", "c": True}, errors) == {}
        assert len(errors) == 3

    def test_a_missing_value_is_no_change(self):
        errors = []
        assert read_changes(None, errors) == {}
        assert read_changes(["a"], errors) == {}
        assert errors == ["The counter changes are invalid."]


class TestPlanChanges:
    def test_a_new_change_moves_the_counter_by_the_entry(self):
        counter = held(reading=5)
        (change,), errors = plan_changes([counter], {counter.id: 2}, {})
        assert change == CounterChange(counter.id, "Reputation", 5, 2, 0, 7, 0)
        assert change.delta == 2
        assert errors == []

    def test_a_correction_applies_the_difference_from_the_recorded_change(self):
        # Recorded +3, a later tally of +4 made it 12; now correct to +1.
        counter = held(reading=12)
        (change,), _ = plan_changes([counter], {counter.id: 1}, {counter.id: 3})
        assert change.delta == -2
        assert change.after == 10

    def test_an_effect_is_shown_apart_and_counted_once(self):
        counter = held(reading=5)
        (change,), _ = plan_changes(
            [counter], {counter.id: 1}, {}, effects={counter.id: 2}
        )
        assert (change.manual, change.effect, change.after) == (1, 2, 8)
        assert change.delta == 1

    def test_a_counter_cannot_go_below_zero(self):
        counter = held(reading=2)
        _, errors = plan_changes([counter], {counter.id: -3}, {})
        assert errors == ["Reputation cannot go below 0."]

    def test_the_floor_is_the_stored_value_not_the_reading(self):
        # A contribution adds 4 to the reading; the stored value is 1.
        counter = held(reading=5, stored=1)
        _, errors = plan_changes([counter], {counter.id: -2}, {})
        assert errors == ["Reputation cannot go below 0."]

    def test_a_recorded_counter_that_has_gone_cannot_be_corrected(self):
        gone = str(uuid4())
        _, errors = plan_changes([], {gone: 1}, {gone: 3}, names={gone: "Favour"})
        assert errors == [
            "You cannot correct the change to Favour: it was removed or moved "
            "after this report was applied. Change Favour on the gang page."
        ]

    def test_a_model_counter_that_has_gone_points_at_the_model_card(self):
        gone = str(uuid4())
        _, errors = plan_changes(
            [], {gone: 1}, {gone: 3}, names={gone: "Favour"}, change_on="Cinder's card"
        )
        assert errors[0].endswith("Change Favour on Cinder's card.")

    def test_an_unchanged_entry_for_a_counter_that_has_gone_is_kept(self):
        gone = str(uuid4())
        changes, errors = plan_changes([], {gone: 3}, {gone: 3})
        assert errors == []
        assert entries(changes, {gone: 3}, {gone: 3}) == {gone: 3}

    def test_a_counter_that_has_gone_and_is_left_out_keeps_its_change(self):
        gone = str(uuid4())
        changes, errors = plan_changes([], {}, {gone: 2})
        assert errors == []
        assert entries(changes, {}, {gone: 2}) == {gone: 2}

    def test_an_entered_zero_for_a_counter_that_has_gone_is_refused(self):
        gone = str(uuid4())
        _, errors = plan_changes([], {gone: 0}, {gone: 2}, names={gone: "Favour"})
        assert len(errors) == 1

    def test_entries_keep_only_what_the_report_changes(self):
        kept, cleared = held(), held(name="Favour")
        changes, _ = plan_changes([kept, cleared], {kept.id: 2}, {cleared.id: 1})
        assert entries(changes, {kept.id: 2}, {cleared.id: 1}) == {kept.id: 2}


@pytest.mark.django_db
class TestHeldCounters:
    def test_only_stored_drawn_counters_other_than_xp_and_income(self):
        reputation = node(Counter(name="Reputation"), value=3)
        nodes = [
            reputation,
            node(Counter(name="XP"), value=10),
            node(Counter(name="Income"), value=0),
            node(Counter(name="Hidden", drawn=False)),
            node(Counter(name="Granted"), assignment=False),
            node(Counter(name="Shared"), broadcast=True),
            node(Counter(name="Suppressed"), suppressed=True),
        ]
        readings = [SimpleNamespace(value=value) for value in (7, 10, 20, 0, 1, 0, 0)]
        (counter,) = held_counters(nodes, readings)
        assert counter.id == str(reputation.assignment.pk)
        assert (counter.name, counter.reading, counter.stored) == (
            "Reputation",
            7,
            3,
        )

    def test_non_counters_do_not_shift_the_readings(self):
        nodes = [node(Rule(name="Tough")), node(Counter(name="Favour"), value=2)]
        (counter,) = held_counters(nodes, [SimpleNamespace(value=2)])
        assert counter.reading == 2

    def test_a_qualified_income_counter_is_an_ordinary_counter(self):
        assert changeable(node(Counter(name="Income", qualifier="Guild")))
