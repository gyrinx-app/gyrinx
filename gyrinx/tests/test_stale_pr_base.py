"""A stale pull request base.sha dismisses a fresh approval.

GitHub can report "The merge-base changed after approval" while the head
commit is unchanged. The stored base.sha is then older than the base branch,
and compare already uses that branch tip as the merge base. These tests pin
that distinction so a later agent does not PATCH a pull request that merely
lags its base branch.
"""

import importlib.util
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".agents/skills/pr-comments/scripts/stale_pr_base.py"
SKILL = ROOT / ".agents/skills/pr-comments/SKILL.md"
AGENTS = ROOT / "AGENTS.md"


def _script():
    spec = importlib.util.spec_from_file_location("stale_pr_base", SCRIPT)
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def test_recorded_base_is_stale_when_the_merge_base_is_already_the_tip():
    mod = _script()
    assert mod.is_stale_recorded_base(
        base_sha="afbdbdb",
        base_tip="0b807e8d1",
        merge_base="0b807e8d1",
    )


def test_current_base_sha_is_not_stale():
    mod = _script()
    assert not mod.is_stale_recorded_base(
        base_sha="0b807e8d1",
        base_tip="0b807e8d1",
        merge_base="0b807e8d1",
    )


def test_pull_request_behind_its_base_branch_is_not_stale():
    mod = _script()
    assert not mod.is_stale_recorded_base(
        base_sha="afbdbdb",
        base_tip="0b807e8d1",
        merge_base="afbdbdb",
    )


def test_missing_shas_are_not_stale():
    mod = _script()
    assert not mod.is_stale_recorded_base(base_sha="", base_tip="abc", merge_base="abc")


def test_describe_prints_the_same_base_refresh_command():
    mod = _script()
    code, message = mod.describe(
        base_sha="afbdbdb",
        base_tip="0b807e8d1",
        merge_base="0b807e8d1",
        repo="gyrinx-app/gyrinx",
        number=2903,
        base_ref="main",
    )
    assert code == 2
    assert (
        "gh api --method PATCH repos/gyrinx-app/gyrinx/pulls/2903 -f base=main"
        in message
    )


def test_describe_leaves_a_real_merge_base_change_alone():
    mod = _script()
    code, message = mod.describe(
        base_sha="afbdbdb",
        base_tip="0b807e8d1",
        merge_base="afbdbdb",
        repo="gyrinx-app/gyrinx",
        number=2903,
        base_ref="main",
    )
    assert code == 0
    assert "real merge-base change" in message


def test_refresh_command_keeps_a_stacked_base_ref():
    mod = _script()
    assert mod.refresh_command("gyrinx-app/gyrinx", 12, "feature/stacked") == (
        "gh api --method PATCH repos/gyrinx-app/gyrinx/pulls/12 -f base=feature/stacked"
    )


def test_refresh_command_rejects_a_base_ref_that_would_change_the_shell():
    mod = _script()
    with pytest.raises(ValueError):
        mod.refresh_command("gyrinx-app/gyrinx", 2903, "main;touch")


def test_base_ref_path_encodes_a_slash():
    mod = _script()
    assert mod.base_ref_api_path("gyrinx-app/gyrinx", "feature/stacked") == (
        "repos/gyrinx-app/gyrinx/git/ref/heads/feature%2Fstacked"
    )


def test_docs_name_the_stale_base_sha_check():
    for path in (SKILL, AGENTS):
        text = " ".join(path.read_text().split())
        assert "The merge-base changed after approval" in text
        assert "stale_pr_base.py" in text
        assert "--apply" in text
        assert "base.sha" in text
