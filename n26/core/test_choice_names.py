"""How a several-pick slot writes what it holds.

No database — the line is a join of names, and a repeat is a count
beside the first of that name. The picks stay as they were written.
"""

from types import SimpleNamespace

from n26.core.effects import ChoiceSlot, stacked_names


def names(*held):
    return stacked_names(held)


class TestStackedNames:
    def test_nothing_is_empty(self):
        assert names() == ""

    def test_one_name_is_the_name(self):
        assert names("Enfeebled") == "Enfeebled"

    def test_the_same_name_twice_is_counted(self):
        assert names("Enfeebled", "Enfeebled") == "Enfeebled (2)"

    def test_five_of_one_is_counted(self):
        assert names(*["Enfeebled"] * 5) == "Enfeebled (5)"

    def test_distinct_names_stay_in_order(self):
        assert names("Eye Injury", "Out Cold") == "Eye Injury, Out Cold"

    def test_a_later_repeat_joins_the_first_of_its_name(self):
        assert names("Enfeebled", "Out Cold", "Enfeebled") == "Enfeebled (2), Out Cold"


def slot(*held):
    return ChoiceSlot(
        kind_label="Lasting Injuries",
        source="Ganger",
        source_kind="profile",
        anchor=None,
        picks=[SimpleNamespace(name=name) for name in held],
    )


class TestTheChosenLine:
    def test_no_picks_is_none(self):
        assert slot().chosen_name is None

    def test_repeats_read_as_a_count(self):
        assert (
            slot("Enfeebled", "Enfeebled", "Enfeebled").chosen_name == "Enfeebled (3)"
        )
