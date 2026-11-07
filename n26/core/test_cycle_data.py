"""Schedule values survive storage without accepting unknown structure."""

from datetime import date

import pytest

from n26.core import cycle_data as data
from n26.core import schedule as s


def test_template_storage_preserves_the_default_phase_and_step_definitions():
    assert (
        data.template_from_data(
            s.DEFAULT_TEMPLATE.name, data.template_data(s.DEFAULT_TEMPLATE)
        )
        == s.DEFAULT_TEMPLATE
    )


def test_cycle_values_round_trip_optional_names_dates_and_original_text():
    details = s.CycleDetails(
        "phase", starts_on=date(2026, 11, 7), description="An arbitrator's note."
    )
    assert data.cycle_details_from_data(data.cycle_details_data(details)) == details


@pytest.mark.parametrize(
    "ref",
    [
        s.SavedCycleRef("saved"),
        s.ProjectedCycleRef(s.PlannedPosition("plan", 4)),
    ],
)
def test_saved_and_projected_references_round_trip_without_conflating_them(ref):
    assert data.ref_from_data(data.ref_data(ref)) == ref


@pytest.mark.parametrize(
    "definition", [None, [], {"phases": [], "steps": [], "other": 1}]
)
def test_unsupported_template_shapes_are_rejected(definition):
    with pytest.raises(s.ScheduleError):
        data.template_from_data("Plan", definition)


@pytest.mark.parametrize("value", [False, 42, "not-a-date", "2026-02-30"])
def test_invalid_dates_are_refused_before_reaching_model_fields(value):
    with pytest.raises(s.ScheduleError, match="dates"):
        data.cycle_details_from_data({"phase_id": "phase", "starts_on": value})


def test_reward_storage_retains_dice_configuration_without_rolling_it():
    rewards = data.rewards_from_data(
        {
            "win": {
                "credits": {
                    "fixed": 10,
                    "dice": {"count": 2, "sides": 6, "multiplier": 10},
                },
                "reputation": 2,
            },
            "entry_credits": {"fixed": 100},
        }
    )
    assert rewards.win == s.Reward(s.CreditAmount(10, s.DiceAmount(2, 6, 10)), 2)
    assert rewards.entry_credits == s.CreditAmount(100)


def test_step_identities_are_valid_before_they_can_be_used_as_saved_provenance():
    with pytest.raises(s.ScheduleError, match="26 characters"):
        data.steps_from_data([{"id": "x" * 27, "phase_id": "phase", "count": 1}])
