"""The required CI job's core-suite size gate. See
scripts/check_core_suite_bounds.py."""

import pytest

from scripts.check_core_suite_bounds import (
    HEADROOM,
    check_core_suite_bounds,
    main,
)

pytestmark = pytest.mark.core


def test_a_count_inside_the_range_with_headroom_is_silent():
    result = check_core_suite_bounds(800, 300, 1400)
    assert result.ok
    assert result.messages == ("core suite: 800 tests (allowed 300..1400)",)


def test_a_count_at_the_minimum_is_ok():
    result = check_core_suite_bounds(300, 300, 1400)
    assert result.ok
    assert "::warning::" not in "\n".join(result.messages)
    assert "::error::" not in "\n".join(result.messages)


@pytest.mark.parametrize("count", [1350, 1399, 1400])
def test_a_count_within_headroom_of_the_max_warns_but_passes(count):
    result = check_core_suite_bounds(count, 300, 1400)
    assert result.ok
    joined = "\n".join(result.messages)
    assert "::warning::" in joined
    assert "CORE_SUITE_MAX=1400" in joined
    assert "test.yaml" in joined
    assert "::error::" not in joined


def test_a_count_just_outside_headroom_does_not_warn():
    result = check_core_suite_bounds(1400 - HEADROOM - 1, 300, 1400)
    assert result.ok
    assert "::warning::" not in "\n".join(result.messages)


@pytest.mark.parametrize("count", [299, 1401])
def test_a_count_outside_the_bounds_fails(count):
    result = check_core_suite_bounds(count, 300, 1400)
    assert not result.ok
    joined = "\n".join(result.messages)
    assert "::error::" in joined
    assert "test.yaml" in joined
    assert "::warning::" not in joined


def test_headroom_is_inclusive_of_the_threshold():
    result = check_core_suite_bounds(100, 0, 150, headroom=50)
    assert result.ok
    assert "::warning::" in "\n".join(result.messages)


def test_main_prints_the_warning_and_exits_zero(capsys):
    assert main(["check_core_suite_bounds.py", "1350", "300", "1400"]) == 0
    out = capsys.readouterr().out
    assert "core suite: 1350 tests (allowed 300..1400)" in out
    assert "::warning::" in out


def test_main_refuses_a_count_above_the_max(capsys):
    assert main(["check_core_suite_bounds.py", "1401", "300", "1400"]) == 1
    captured = capsys.readouterr()
    assert "::error::" in captured.out
    assert captured.err == ""


def test_main_rejects_non_integers(capsys):
    assert main(["check_core_suite_bounds.py", "many", "300", "1400"]) == 2
    assert "integers" in capsys.readouterr().err


def test_main_rejects_the_wrong_number_of_arguments(capsys):
    assert main(["check_core_suite_bounds.py", "1", "2"]) == 2
    assert "Usage:" in capsys.readouterr().err


def test_main_accepts_an_explicit_headroom(capsys):
    assert main(["check_core_suite_bounds.py", "90", "0", "100", "5"]) == 0
    assert "::warning::" not in capsys.readouterr().out
    assert main(["check_core_suite_bounds.py", "96", "0", "100", "5"]) == 0
    assert "::warning::" in capsys.readouterr().out
