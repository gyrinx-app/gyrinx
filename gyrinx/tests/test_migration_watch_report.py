"""What the migration watch tells a pull request.

These tests enforce one rule: the watch says a branch is clear only when every
check gave an answer and none of them found anything. A run that was cancelled,
or whose checks were skipped because something earlier broke, has not verified
the branch, and its result must not look as though it has.
"""

import importlib.util
import pathlib

import pytest

MODULE_PATH = (
    pathlib.Path(__file__).resolve().parents[2]
    / "scripts"
    / "migration_watch_report.py"
)

spec = importlib.util.spec_from_file_location("migration_watch_report", MODULE_PATH)
report = importlib.util.module_from_spec(spec)
spec.loader.exec_module(report)


ALL_RAN = {
    "FETCH": "success",
    "MERGE": "success",
    "REPLAY_MAIN": "success",
    "REPLAY": "success",
    "DRIFT": "success",
    "LEAVES": "success",
    "OVERLAP": "success",
}


@pytest.fixture
def run(monkeypatch, tmp_path):
    """Build a report from a set of step outcomes, as the workflow passes them."""

    def build(findings=None, **outcomes):
        for name in [
            "FETCH",
            "MERGE",
            "REPLAY_MAIN",
            "REPLAY",
            "DRIFT",
            "LEAVES",
            "OVERLAP",
        ]:
            monkeypatch.setenv(name, outcomes.get(name, "skipped"))
        if findings is not None:
            (tmp_path / "overlap.json").write_text(
                f'{{"base_migrations": [], "branch_migrations": [], "findings": {findings}}}',
                encoding="utf-8",
            )
        state, headline, problems, notes = report.build(tmp_path)
        return state, headline, problems, notes

    return build


def test_every_check_ran_and_found_nothing(run):
    state, headline, problems, _ = run(findings="[]", **ALL_RAN)
    assert state == "success"
    assert headline == "clear against current main"
    assert problems == []


def test_a_cancelled_run_says_it_checked_nothing(run):
    # Every check is skipped because a newer push cancelled the run.
    state, headline, _, notes = run(FETCH="success", MERGE="success")
    assert state == "pending"
    assert headline == "not checked"
    assert "nothing here was verified" in notes[0]


def test_a_skipped_check_is_not_a_pass(run):
    # Main did not migrate, so the deploy replay never ran; the rest did.
    state, headline, problems, notes = run(
        findings="[]",
        FETCH="success",
        MERGE="success",
        REPLAY_MAIN="failure",
        REPLAY="skipped",
        DRIFT="success",
        LEAVES="success",
        OVERLAP="success",
    )
    assert state != "success"
    assert "clear" not in headline
    assert problems == []
    assert any("the deploy replay" in note for note in notes)


def test_an_overlap_check_that_wrote_no_findings_is_not_a_pass(run):
    # The command exits non-zero both when it finds a clash and when it cannot
    # run, so a failure with no findings file means it checked nothing.
    state, headline, problems, notes = run(**{**ALL_RAN, "OVERLAP": "failure"})
    assert state != "success"
    assert "clear" not in headline
    assert problems == []
    assert any("main gained" in note for note in notes)


def test_an_overlap_check_that_passed_without_findings_is_not_a_pass(run):
    # A green step with no findings file has still read nothing.
    state, headline, _, _ = run(**ALL_RAN)
    assert state != "success"
    assert "clear" not in headline


def test_unreadable_overlap_findings_are_not_a_pass(run, tmp_path):
    (tmp_path / "overlap.json").write_text("{not json", encoding="utf-8")
    state, headline, _, notes = run(**ALL_RAN)
    assert state != "success"
    assert "clear" not in headline
    assert any("could not be read" in note for note in notes)


def test_a_failing_check_is_a_problem(run):
    state, headline, problems, _ = run(
        findings="[]",
        **{**ALL_RAN, "REPLAY": "failure"},
    )
    assert state == "failure"
    assert "problem" in headline
    assert "next deploy would fail" in problems[0]


def test_a_branch_that_does_not_merge_is_a_problem(run, monkeypatch):
    monkeypatch.setenv("PR_BASE", "main")
    state, headline, problems, _ = run(FETCH="success", MERGE="failure")
    assert state == "failure"
    assert headline == "conflicts with main"
    assert "Does not merge into main" in problems[0]


def test_a_stacked_branch_that_does_not_merge_is_only_a_note(run, monkeypatch):
    # Main holds a squashed ancestor this chain still carries unsquashed. That
    # clears when the branch below lands, so it is not this branch's problem.
    monkeypatch.setenv("PR_BASE", "codex/the-branch-below")
    state, headline, problems, notes = run(FETCH="success", MERGE="failure")
    assert state == "pending"
    assert "codex/the-branch-below" in headline
    assert problems == []
    assert any("codex/the-branch-below" in note for note in notes)


def test_a_branch_that_could_not_be_fetched_is_an_error(run):
    state, headline, _, notes = run(FETCH="failure")
    assert state == "error"
    assert headline == "could not fetch the branch"
    assert "nothing was checked" in notes[0]


def test_an_order_clash_blocks(run):
    findings = (
        '[{"severity": "blocks", "base": "library.0095_x", "branch": "library.0095_y",'
        ' "base_operation": "AddField on library.pickable.x",'
        ' "branch_operation": "RenameModel on library.pickable",'
        ' "reason": "one branch renames or deletes a model the other changes"}]'
    )
    state, _, problems, _ = run(findings=findings, **ALL_RAN)
    assert state == "failure"
    assert "touches what main changed" in problems[0]


def test_a_data_migration_is_only_a_note(run):
    findings = (
        '[{"severity": "review", "base": "library.0095_x", "branch": "library.0095_y",'
        ' "base_operation": "AddField on library.pickable.weight",'
        ' "branch_operation": "RunPython on library.pickable",'
        ' "reason": "a data migration runs against a model the other branch changes"}]'
    )
    state, headline, problems, notes = run(findings=findings, **ALL_RAN)
    assert state == "success"
    assert headline == "clear, with a note"
    assert problems == []
    assert any("order does not matter" in note for note in notes)


def test_the_log_excerpt_drops_the_application_chatter(tmp_path):
    log = tmp_path / "leaves.log"
    log.write_text(
        "DEBUG 2026-01-01 tracing started\n"
        "INFO 2026-01-01 tracing enabled\n"
        "WARNING 2026-01-01 something noisy\n"
        "CommandError: A branch may add one migration leaf per app.\n",
        encoding="utf-8",
    )
    excerpt = report.tail(log)
    assert excerpt == "CommandError: A branch may add one migration leaf per app."


def test_a_run_that_checked_nothing_does_not_claim_it_checked(run):
    state, headline, problems, notes = run(FETCH="success", MERGE="success")
    body = report.render(state, headline, problems, notes, "https://run", "abc1234567")
    assert "migrated a database to main" not in body
