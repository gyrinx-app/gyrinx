"""The scenario tables: four tables, six entries each, keyed for links."""

from django.contrib.staticfiles import finders

from n26.library.scenario_tables import TABLES, ScenarioEntry, table


def test_every_table_has_one_entry_for_each_face_of_a_d6():
    assert [found.key for found in TABLES] == [
        "deployment",
        "objective",
        "side_job",
        "crew",
    ]
    for found in TABLES:
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
