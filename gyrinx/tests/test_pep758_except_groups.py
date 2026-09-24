"""PEP 758 except groups are valid on this runtime, and ruff emits them.

Copilot has flagged `except E1, E2:` as Python 2 / invalid Python 3
(see `n26/core/action_initialisation.py`). Agents must not add parentheses
unless the clause binds with `as`. These tests pin that boundary so a
Copilot-driven rewrite fights the formatter in CI rather than silently
landing.
"""

import subprocess
import sys
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]


def _ruff() -> str:
    for candidate in (
        Path(sys.prefix) / "bin" / "ruff",
        Path(sys.executable).parent / "ruff",
    ):
        if candidate.is_file():
            return str(candidate)
    pytest.fail("ruff is not in the test interpreter's environment")


def test_except_groups_parse_without_parentheses():
    compile(
        "try:\n    raise ValueError\nexcept ValueError, TypeError:\n    pass\n",
        "<pep758>",
        "exec",
    )


def test_except_groups_still_need_parentheses_when_binding_as():
    with pytest.raises(SyntaxError):
        compile(
            "try:\n    raise ValueError\nexcept ValueError, TypeError as exc:\n    pass\n",
            "<pep758>",
            "exec",
        )


def test_ruff_format_strips_parentheses_from_except_groups_without_as(tmp_path):
    source = tmp_path / "sample.py"
    source.write_text("try:\n    pass\nexcept (ValueError, TypeError):\n    pass\n")
    subprocess.run(
        [_ruff(), "format", str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "except ValueError, TypeError:" in source.read_text()


def test_ruff_format_keeps_parentheses_on_except_groups_with_as(tmp_path):
    source = tmp_path / "sample.py"
    source.write_text(
        "try:\n    pass\nexcept (ValueError, TypeError) as exc:\n    _ = exc\n"
    )
    subprocess.run(
        [_ruff(), "format", str(source)],
        check=True,
        capture_output=True,
        text=True,
    )
    assert "except (ValueError, TypeError) as exc:" in source.read_text()


def test_copilot_python_instructions_state_the_pep758_boundary():
    text = (ROOT / ".github/instructions/python.instructions.md").read_text()
    assert "PEP 758" in text
    assert "except (ValueError, TypeError) as exc" in text
    assert "except ValueError, TypeError:" in text
