import pytest

from n26.core import schedule as s
from n26.core.cycle_display import _phase_end


@pytest.mark.parametrize(
    "mode,counts,position,phase,expected",
    [
        ("fixed", [("a", 2), ("a", 3), ("b", 1)], 0, "a", (6, "b")),
        ("fixed", [("a", 2), ("a", 3), ("b", 1)], 2, "a", (6, "b")),
        ("fixed", [("a", 3)], 3, "a", (4, None)),
        ("fixed", [("a", 3)], 1, "a", (4, None)),
        ("fixed", [], 0, "a", (1, None)),
        ("repeating", [("a", 2), ("b", 1), ("a", 3)], 4, "a", (9, "b")),
        ("repeating", [("a", 2), ("a", 3)], 4, "a", (None, None)),
        ("repeating", [("b", 1), ("a", 3)], 0, "a", (1, "b")),
    ],
)
def test_phase_boundary_uses_steps_without_projecting_an_unbounded_timeline(
    mode, counts, position, phase, expected
):
    plan = s.Plan(
        "plan",
        mode,
        tuple(
            s.PlanStep(str(index), name, count)
            for index, (name, count) in enumerate(counts)
        ),
    )
    assert _phase_end(plan, position, phase) == expected


def test_a_credited_repeating_revision_keeps_its_order_boundary():
    plan = s.Plan(
        "plan",
        "repeating",
        (s.PlanStep("one", "a", 3), s.PlanStep("two", "b", 1)),
        starts_after_order=5,
        start_position=2,
    )
    assert _phase_end(plan, 2, "a") == (7, "b")
