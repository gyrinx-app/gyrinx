from types import SimpleNamespace

import pytest
from bs4 import BeautifulSoup
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler

from n26.core.flow import FlowStep
from n26.core.views.action_flows import _steps
from n26.library.models import ResolveAdvancement

pytestmark = pytest.mark.django_db


def advancement_record(*, target=None):
    return SimpleNamespace(
        outcome_id="outcome",
        outcome=SimpleNamespace(operation=ResolveAdvancement()),
        review={"target": target or {}},
        skill_selection=None,
    )


def shape(steps):
    return [(step.label, step.current, step.complete, step.skipped) for step in steps]


@pytest.fixture
def promotion(monkeypatch):
    monkeypatch.setattr(
        "n26.core.promotions.replaces_roll", lambda record, configured: True
    )


@pytest.fixture
def no_promotion(monkeypatch):
    monkeypatch.setattr(
        "n26.core.promotions.replaces_roll", lambda record, configured: False
    )


def test_a_promotion_skips_the_roll_and_review_keeps_its_number(promotion):
    steps = _steps(advancement_record(), stage="review")

    assert shape(steps) == [
        ("Choice", False, True, False),
        ("Roll", False, False, True),
        ("Promotion", False, True, False),
        ("Skill", False, False, True),
        ("Review", True, False, False),
        ("Completed", False, False, False),
    ]


def test_a_result_that_grants_a_skill_takes_the_skill_step(no_promotion):
    steps = _steps(advancement_record(target={"skill": "catfall"}), stage="review")

    assert [step.label for step in steps] == [
        "Choice",
        "Roll",
        "Advancement",
        "Skill",
        "Review",
        "Completed",
    ]
    assert not any(step.skipped for step in steps)
    assert [step.complete for step in steps] == [True, True, True, True, False, False]


def test_before_the_result_is_known_nothing_is_skipped(no_promotion):
    steps = _steps(advancement_record(), stage="roll")

    assert not any(step.skipped for step in steps)
    assert [step.current for step in steps].index(True) == 1


def test_a_page_outside_the_steps_marks_none_current(no_promotion):
    steps = _steps(advancement_record(), stage="cancel")

    assert not any(step.current or step.complete for step in steps)


def draw(steps):
    html = Template(
        CottonCompiler().process('<c-n26.flow-progress :steps="steps" />')
    ).render(Context({"steps": steps}))
    return BeautifulSoup(html, "html.parser")


def test_more_than_four_steps_always_stack():
    five = [FlowStep(str(n), current=n == 1) for n in range(1, 6)]
    four = five[:4]

    assert "md:flex-row" not in draw(five).find("ol")["class"]
    assert "md:flex-row" in draw(four).find("ol")["class"]


def test_a_skipped_step_keeps_its_number_and_says_so():
    drawn = draw(
        [
            FlowStep("Choice", complete=True),
            FlowStep("Roll", skipped=True),
            FlowStep("Review", current=True),
        ]
    )
    roll = drawn.find_all("li")[1]

    assert "2" in roll.get_text()
    assert "Roll (skipped)" in roll.get_text(" ", strip=True).replace("  ", " ")
    assert drawn.find_all("li")[2].get("aria-current") == "step"
