"""The scenario generator's tables, rolls, parsing and log notes."""

import random

import pytest

from n26.core.scenarios import (
    describe,
    history_note,
    parse,
    read_history_note,
    results,
    roll,
    rolls_of,
)
from n26.library.scenario_tables import table


def test_roll_rolls_only_the_tables_named_in_table_order():
    # A seeded game die for a repeatable test, not a secret.
    rolls = roll(["crew", "deployment"], rng=random.Random(1))  # nosec B311
    assert list(rolls) == ["deployment", "crew"]
    assert all(1 <= value <= 6 for value in rolls.values())


def test_parse_reads_each_named_table_in_table_order():
    found, wrong = parse({"crew": "2", "deployment": "3", "other": "4"})
    assert wrong == []
    assert [(result.table.key, result.roll) for result in found] == [
        ("deployment", 3),
        ("crew", 2),
    ]
    assert found[0].entry == table("deployment").entry(3)
    assert found[0].face == "3"


def test_parse_reports_every_value_that_is_not_on_its_table():
    found, wrong = parse({"deployment": "7", "objective": "2", "crew": "x"})
    assert [each.key for each in wrong] == ["deployment", "crew"]
    assert results({"deployment": "7", "objective": "2"}) == []


def test_a_table_left_out_is_not_an_error():
    found, wrong = parse({"objective": "2", "side_job": ""})
    assert wrong == []
    assert rolls_of(found) == {"objective": 2}


@pytest.mark.parametrize("value", [3.5, 3.0, True, [3], {}, "3.0", "nan"])
def test_a_component_must_be_an_integer_or_its_exact_form_value(value):
    found, wrong = parse({"deployment": value, "crew": "2"})
    assert [each.key for each in wrong] == ["deployment"]
    assert results({"deployment": value, "crew": "2"}) == []


def test_a_history_note_round_trips():
    note = history_note({"deployment": 6, "crew": 2}, "Dust-up at the sump")
    assert note == "deployment=6,crew=2 Dust-up at the sump"
    assert read_history_note(note) == (
        {"deployment": "6", "crew": "2"},
        "Dust-up at the sump",
    )
    assert read_history_note("objective=1") == ({"objective": "1"}, "")
    assert read_history_note("") == ({}, "")


def test_describe_names_each_table_roll_and_entry():
    found = results({"deployment": "6", "crew": "2"})
    assert describe(found) == (
        f"Deployment 6 ({table('deployment').entry(6).label}), "
        f"Crew 2 ({table('crew').entry(2).label})"
    )


def test_side_jobs_come_last_numbered_in_order_with_their_sets():
    found, wrong = parse(
        {"side_job_3": "goliath-1", "side_job": 2, "crew": "4", "side_job_2": ""}
    )
    assert wrong == []
    assert [result.heading for result in found] == [
        "Crew",
        "Side job 1 (General)",
        "Side job 2 (Goliath)",
    ]
    assert rolls_of(found) == {
        "crew": 4,
        "side_job": "general-2",
        "side_job_2": "goliath-1",
    }


@pytest.mark.parametrize("value", ["orlock-2", "escher-7", "escher-", "-3", 9, 2.0])
def test_a_side_job_off_its_set_is_wrong(value):
    found, wrong = parse({"side_job": value})
    assert [each.key for each in wrong] == ["side_job"]


def test_a_history_note_round_trips_side_jobs():
    rolls = {"crew": 2, "side_job": "escher-3"}
    saved, name = read_history_note(history_note(rolls, "Sump clash"))
    assert rolls_of(results(saved)) == rolls
    assert name == "Sump clash"


def test_reroll_side_job_rolls_only_that_side_job():
    from n26.core.scenarios import reroll_side_job

    found, _ = parse({"crew": "2", "side_job": "escher-3", "side_job_2": "goliath-1"})
    rolls = reroll_side_job(found, "side_job_2", "escher", random.Random(1))  # nosec B311
    assert rolls["crew"] == 2
    assert rolls["side_job"] == "escher-3"
    assert rolls["side_job_2"].startswith("escher-")
    assert rolls["side_job_2"] != "escher-3"
    assert reroll_side_job(found, "side_job_3", "escher") is None
    assert reroll_side_job(found, "side_job", "orlock") is None
