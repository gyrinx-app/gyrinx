"""The scenario generator's tables, rolls, stamps and log notes."""

import random

from n26.core.scenarios import (
    TABLES,
    ScenarioEntry,
    choosable,
    describe,
    generator_query,
    history_note,
    is_stamped,
    read_history_note,
    results,
    roll,
    rolls_of,
    stamp,
    table,
)


def test_every_table_has_one_entry_for_each_face_of_a_d6():
    assert [found.key for found in TABLES] == [
        "deployment",
        "objective",
        "side_job",
        "crew",
    ]
    for found in TABLES:
        assert [entry.roll for entry in found.entries] == [1, 2, 3, 4, 5, 6]
    assert all(entry.image for entry in table("deployment").entries)
    assert table("nope") is None
    assert table("crew").entry(7) is None


def test_roll_rolls_only_the_tables_named_in_table_order():
    # A seeded game die for a repeatable test, not a secret.
    rolls = roll(["crew", "deployment"], rng=random.Random(1))  # nosec B311
    assert list(rolls) == ["deployment", "crew"]
    assert all(1 <= value <= 6 for value in rolls.values())


def test_results_skip_a_key_or_roll_that_is_not_on_a_table():
    found = results({"deployment": "3", "objective": "9", "crew": "x", "other": "2"})
    assert [(result.table.key, result.roll) for result in found] == [("deployment", 3)]
    assert found[0].entry == table("deployment").entry(3)
    assert found[0].face == "3"


def test_choosable_marks_the_entry_picked_on_each_table():
    tables = choosable({"objective": "4"})
    objective = next(each for each in tables if each.table.key == "objective")
    assert [option.picked for option in objective.entries] == [
        False,
        False,
        False,
        True,
        False,
        False,
    ]
    deployment = next(each for each in tables if each.table.key == "deployment")
    assert not any(option.picked for option in deployment.entries)


def test_a_stamp_proves_the_same_rolls_in_the_same_campaign_only():
    rolls = {"deployment": 6, "crew": 2}
    check = stamp("C1", rolls)
    assert is_stamped("C1", {"crew": 2, "deployment": 6}, check)
    assert not is_stamped("C1", {"deployment": 1, "crew": 2}, check)
    assert not is_stamped("C2", rolls, check)
    assert not is_stamped("C1", rolls, "")
    assert not is_stamped("C1", {}, stamp("C1", {}))


def test_a_history_note_round_trips():
    note = history_note(True, {"deployment": 6, "crew": 2}, "Dust-up at the sump")
    assert note == "rolled deployment=6,crew=2 Dust-up at the sump"
    assert read_history_note(note) == (
        True,
        {"deployment": "6", "crew": "2"},
        "Dust-up at the sump",
    )
    assert read_history_note("chose objective=1") == (False, {"objective": "1"}, "")
    assert read_history_note("") == (False, {}, "")


def test_generator_query_names_the_mode_that_made_the_result():
    every = {found.key: 1 for found in TABLES}
    assert generator_query("C1", True, every)["mode"] == "full"
    some = generator_query("C1", True, {"crew": 4})
    assert some["mode"] == "components"
    assert some["tables"] == ["crew"]
    assert some["check"] == stamp("C1", {"crew": 4})
    assert generator_query("C1", False, {"crew": 4}) == {"mode": "choose", "crew": 4}
    assert rolls_of(results({"crew": "4"})) == {"crew": 4}


def test_a_label_leaves_off_a_heading_colon_and_spaces():
    assert ScenarioEntry(roll=1, name=" Turf War: ", text="").label == "Turf War"
    assert ScenarioEntry(roll=1, name="Ambush!", text="").label == "Ambush!"


def test_describe_names_each_table_roll_and_entry():
    found = results({"deployment": "6", "crew": "2"})
    assert describe(found) == (
        f"Deployment 6 ({table('deployment').entry(6).label}), "
        f"Crew 2 ({table('crew').entry(2).label})"
    )
