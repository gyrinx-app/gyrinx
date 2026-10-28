"""The scenario tables and side job sets: six entries each, keyed for links."""

from django.contrib.staticfiles import finders

from n26.library.scenario_tables import (
    SIDE_JOB_KEYS,
    SIDE_JOB_SETS,
    TABLES,
    ScenarioEntry,
    side_job_set,
    table,
)


def test_every_table_has_one_entry_for_each_face_of_a_d6():
    assert [found.key for found in TABLES] == ["deployment", "objective", "crew"]
    for found in TABLES + SIDE_JOB_SETS:
        assert [entry.roll for entry in found.entries] == [1, 2, 3, 4, 5, 6]
        assert all(entry.name.strip() and entry.text.strip() for entry in found.entries)


def test_every_deployment_has_a_map_that_ships():
    for entry in table("deployment").entries:
        assert finders.find(entry.image), entry.image


def test_a_table_is_found_by_key_and_an_entry_by_roll():
    assert table("nope") is None
    assert table("crew").entry(7) is None
    assert table("crew").entry(3).roll == 3


def test_a_label_leaves_off_a_heading_colon_and_spaces():
    assert ScenarioEntry(roll=1, name=" Turf War: ", text="").label == "Turf War"
    assert ScenarioEntry(roll=1, name="Ambush!", text="").label == "Ambush!"


def test_side_job_sets_are_listed_general_first_and_found_by_key():
    assert [found.key for found in SIDE_JOB_SETS] == ["general", "escher", "goliath"]
    assert side_job_set("escher").label == "Escher side jobs"
    assert side_job_set("orlock") is None
    assert SIDE_JOB_KEYS[:3] == ("side_job", "side_job_2", "side_job_3")


def test_text_between_asterisks_is_bold():
    entry = ScenarioEntry(roll=1, name="Pit Fight", text="Use *only* a *Melee* one.")
    assert entry.parts() == [
        ("Use ", False),
        ("only", True),
        (" a ", False),
        ("Melee", True),
        (" one.", False),
    ]
    assert entry.plain == "Use only a Melee one."
    for found in SIDE_JOB_SETS:
        assert all(entry.text.count("*") % 2 == 0 for entry in found.entries)
