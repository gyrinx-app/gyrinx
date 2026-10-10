from uuid import uuid4

import pytest

from n26.core.action_forms import AdvancementRollForm, SkillRollForm

pytestmark = pytest.mark.core


class _SkillSet:
    pk = "agility"

    def __str__(self):
        return "Agility"


AGILITY = _SkillSet()


def _skill_form(**data):
    return SkillRollForm(
        {"request_key": str(uuid4()), "skill_set_id": "agility", **data},
        groups={AGILITY: []},
    )


@pytest.mark.parametrize("rolled", ["1", "6"])
def test_a_skill_roll_records_a_d6_from_one_to_six(rolled):
    form = _skill_form(roll_mode="record", rolled=rolled)

    assert form.is_valid(), form.errors
    assert form.cleaned_data["rolled"] == int(rolled)


@pytest.mark.parametrize("rolled", ["0", "7", "not a number"])
def test_a_skill_roll_refuses_a_number_a_d6_cannot_make(rolled):
    form = _skill_form(roll_mode="record", rolled=rolled)

    assert not form.is_valid()
    assert "rolled" in form.errors


def test_recording_a_skill_roll_needs_the_number():
    form = _skill_form(roll_mode="record")

    assert not form.is_valid()
    assert form.errors["rolled"] == ["Enter the number on your die."]


def test_rolling_in_gyrinx_ignores_a_typed_skill_roll():
    form = _skill_form(roll_mode="roll", rolled="4")

    assert form.is_valid(), form.errors
    assert form.cleaned_data["rolled"] is None


def test_a_skill_roll_without_a_mode_is_rolled_in_gyrinx():
    form = _skill_form()

    assert form.is_valid(), form.errors
    assert form.cleaned_data["rolled"] is None


def test_the_skill_roll_field_is_disabled_unless_recording():
    assert _skill_form(roll_mode="roll").fields["rolled"].disabled
    assert not _skill_form(roll_mode="record").fields["rolled"].disabled


def test_the_2d6_roll_needs_a_mode_and_a_recorded_total():
    missing = AdvancementRollForm({"request_key": str(uuid4())})
    assert missing.errors["roll_mode"] == ["Choose how to roll."]

    blank = AdvancementRollForm({"request_key": str(uuid4()), "roll_mode": "record"})
    assert blank.errors["rolled"] == ["Enter the total of your two dice."]


@pytest.mark.parametrize("rolled", ["", "0", "1", "13", "not a number"])
def test_a_recorded_advancement_roll_refuses_totals_two_dice_cannot_make(rolled):
    form = AdvancementRollForm(
        {"request_key": str(uuid4()), "roll_mode": "record", "rolled": rolled}
    )

    assert not form.is_valid()
    assert "rolled" in form.errors


@pytest.mark.parametrize("rolled", ["2", "12"])
def test_a_recorded_advancement_roll_accepts_both_ends_of_2d6(rolled):
    form = AdvancementRollForm(
        {"request_key": str(uuid4()), "roll_mode": "record", "rolled": rolled}
    )

    assert form.is_valid(), form.errors
    assert form.cleaned_data["rolled"] == int(rolled)
