"""Branch diffs compare origin/main, the last fetched upstream.

A local ``main`` that was never fast-forwarded makes ``git diff main...HEAD``
include weeks of already-merged files. Finch hit that on a 14-file pull
request that looked like 233 files. ``check_microcopy.py --diff`` and the
review instructions now use ``origin/main``.
"""

import subprocess
from pathlib import Path

import pytest

from scripts.check_microcopy import branch_diff_base, changed_files

pytestmark = pytest.mark.core

ROOT = Path(__file__).resolve().parents[2]


def test_branch_diff_base_prefers_origin_main():
    assert branch_diff_base(True) == "origin/main"
    assert branch_diff_base(False) == "main"


def test_changed_files_diffs_against_origin_main_when_present(monkeypatch):
    calls = []
    real_run = subprocess.run

    def spy(args, **kwargs):
        calls.append(list(args))
        return real_run(args, **kwargs)

    monkeypatch.setattr("scripts.check_microcopy.subprocess.run", spy)
    changed_files()
    three_dot = [
        call
        for call in calls
        if call[:3] == ["git", "diff", "--name-only"] and call[-1].endswith("...HEAD")
    ]
    assert three_dot == [["git", "diff", "--name-only", "origin/main...HEAD"]]


def test_changed_files_falls_back_to_main_without_origin(monkeypatch):
    calls = []

    def fake_run(args, **kwargs):
        calls.append(list(args))
        return subprocess.CompletedProcess(args, 0, stdout="", stderr="")

    monkeypatch.setattr("scripts.check_microcopy._ref_exists", lambda ref: False)
    monkeypatch.setattr("scripts.check_microcopy.subprocess.run", fake_run)
    changed_files()
    assert ["git", "diff", "--name-only", "main...HEAD"] in calls
    assert ["git", "diff", "--name-only", "origin/main...HEAD"] not in calls


def test_review_instructions_name_origin_main():
    agents = (ROOT / "AGENTS.md").read_text()
    copywriter = (ROOT / ".claude/agents/copywriter.md").read_text()
    plan = (ROOT / ".claude/commands/manual-test-plan.md").read_text()
    skill = (ROOT / ".agents/skills/microcopy/SKILL.md").read_text()
    script = (ROOT / "scripts/check_microcopy.py").read_text()

    assert "git diff origin/main...HEAD" in agents
    assert "git diff origin/main...HEAD" in copywriter
    assert "git diff main...HEAD" not in copywriter
    assert "git diff origin/main --name-only" in plan
    assert "git log origin/main..HEAD" in plan
    assert "git diff main --name-only" not in plan
    assert "git log main..HEAD" not in plan
    assert "origin/main...HEAD" in skill
    assert 'f"{base}...HEAD"' in script
    assert '"main...HEAD"' not in script
