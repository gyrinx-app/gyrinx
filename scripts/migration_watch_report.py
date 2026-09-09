#!/usr/bin/env python3
"""Write the migration-watch result onto a pull request.

Reads the step outcomes and logs the workflow left in ``REPORT_DIR``, then
keeps one comment on the pull request up to date (found by a marker, edited in
place) and sets a non-required status on the head commit. A pull request that
is clean and has never been commented on is left alone; one that was flagged
before is told it is clear now.

Standard library only; the workflow runs it on the runner's Python with the
``gh`` CLI on the path.
"""

import json
import os
import pathlib
import subprocess  # nosec B404 — calls the gh CLI with fixed arguments
import sys

MARKER = "<!-- migration-watch -->"
CONTEXT = "migration-watch"
LOG_TAIL = 30


def gh(*args, input_text=None):
    result = subprocess.run(  # nosec B603 B607 — fixed argv, no shell
        ["gh", *args], capture_output=True, text=True, input=input_text
    )
    if result.returncode:
        print(
            f"gh {' '.join(args[:3])}… failed: {result.stderr.strip()}", file=sys.stderr
        )
        return None
    return result.stdout


def tail(path):
    try:
        lines = path.read_text(encoding="utf-8").splitlines()
    except OSError:
        return ""
    lines = [
        line
        for line in lines
        if not line.startswith("DEBUG ") and "pkg_resources" not in line
    ]
    return "\n".join(lines[-LOG_TAIL:])


def outcome(name):
    return os.environ.get(name, "skipped")


def build(report_dir):
    """Return (state, headline, problems, notes); state is a commit-status state."""
    problems = []
    notes = []

    if outcome("FETCH") != "success":
        notes.append(
            "The branch could not be fetched, so nothing was checked.\n\n"
            f"```\n{tail(report_dir / 'fetch.log')}\n```"
        )
        return "error", "could not fetch the branch", problems, notes

    if outcome("MERGE") != "success":
        problems.append(
            "**Does not merge into main.** Git reports a conflict; the checks below need a merge to run.\n\n"
            f"```\n{tail(report_dir / 'merge.log')}\n```"
        )
        return "failure", "conflicts with main", problems, notes

    if outcome("REPLAY_MAIN") == "skipped":
        notes.append(
            "The environment or the database could not be set up, so the deploy replay did not run. "
            "That is the runner's problem, not this pull request's."
        )
    elif outcome("REPLAY_MAIN") != "success":
        notes.append(
            "Main itself did not migrate on an empty database, so the deploy replay could not run. "
            f"That is main's problem, not this pull request's.\n\n```\n{tail(report_dir / 'replay-main.log')}\n```"
        )
    elif outcome("REPLAY") != "success":
        problems.append(
            "**The next deploy would fail.** A database holding main did not accept this pull request's "
            f"migrations on top.\n\n```\n{tail(report_dir / 'replay.log')}\n```"
        )

    if outcome("DRIFT") != "success":
        problems.append(
            "**The merged models and migrations disagree.** `makemigrations --check` on the merge:\n\n"
            f"```\n{tail(report_dir / 'drift.log')}\n```"
        )

    if outcome("LEAVES") != "success":
        problems.append(
            "**This branch adds more than one migration leaf to an app.**\n\n"
            f"```\n{tail(report_dir / 'leaves.log')}\n```"
        )

    overlap_path = report_dir / "overlap.json"
    if overlap_path.exists():
        overlap = json.loads(overlap_path.read_text(encoding="utf-8"))
        blocks = [f for f in overlap["findings"] if f["severity"] == "blocks"]
        review = [f for f in overlap["findings"] if f["severity"] != "blocks"]
        if blocks or review:
            rows = ["| | Main gained | This branch | Why |", "|---|---|---|---|"]
            for f in [*blocks, *review]:
                flag = "❌" if f["severity"] == "blocks" else "⚠️"
                rows.append(
                    f"| {flag} | `{f['base']}`<br>{f['base_operation']} "
                    f"| `{f['branch']}`<br>{f['branch_operation']} | {f['reason']} |"
                )
            text = "\n".join(rows)
            if blocks:
                problems.append(
                    "**A migration here touches what main changed since this branch forked.** "
                    "Neither migration knows about the other, so the order they apply in is whichever "
                    "merges first.\n\n" + text
                )
            else:
                notes.append(
                    "A data migration here runs against something main changed since this branch "
                    "forked. Check that the order does not matter.\n\n" + text
                )
    elif outcome("OVERLAP") != "success":
        notes.append(
            f"The overlap check did not run:\n\n```\n{tail(report_dir / 'overlap.log')}\n```"
        )

    if problems:
        return (
            "failure",
            f"{len(problems)} problem(s) against current main",
            problems,
            notes,
        )
    if notes:
        return "success", "clear, with a note", problems, notes
    return "success", "clear against current main", problems, notes


def render(state, headline, problems, notes, run_url, main_sha):
    lines = [MARKER, f"### Migration watch: {headline}", ""]
    if state == "error":
        lines.append(f"[Run]({run_url}).")
    else:
        lines.append(
            f"Checked against main at `{main_sha[:10]}`: merged this branch into main, migrated a database to "
            "main and then to the merge, compared models with migrations, and read this branch's migrations "
            f"against the ones main gained since it forked. [Run]({run_url})."
        )
    lines.append("")
    if problems:
        lines.append("\n\n".join(problems))
        lines.append("")
        lines.append(
            "How to fix: regenerate the migration on a checkout that includes current main "
            "(`manage makemigrations <app> -n <name>`), or add main's leaf to its `dependencies` "
            "so it applies after what it relies on. No renaming is needed."
        )
    if notes:
        lines.append("")
        lines.append("\n\n".join(notes))
    if not problems and not notes:
        lines.append("Nothing here collides with main any more.")
    lines.append("")
    lines.append(
        "_Re-run automatically when main gains a migration or this branch changes._"
    )
    return "\n".join(lines)


def existing_comment(repo, pr_number):
    page = 1
    while True:
        out = gh(
            "api", f"repos/{repo}/issues/{pr_number}/comments?per_page=100&page={page}"
        )
        if not out:
            return None
        comments = json.loads(out)
        for comment in comments:
            if MARKER in (comment.get("body") or ""):
                return comment["id"]
        if len(comments) < 100:
            return None
        page += 1


def main():
    repo = os.environ["GITHUB_REPOSITORY"]
    pr_number = os.environ["PR_NUMBER"]
    sha = os.environ["PR_SHA"]
    run_url = os.environ.get("RUN_URL", "")
    report_dir = pathlib.Path(os.environ.get("REPORT_DIR", ".migration-watch"))
    main_sha = (
        subprocess.run(  # nosec B603 B607 — fixed argv, no shell
            ["git", "rev-parse", "origin/main"], capture_output=True, text=True
        ).stdout.strip()
        or "main"
    )

    state, headline, problems, notes = build(report_dir)
    body = render(state, headline, problems, notes, run_url, main_sha)
    print(body)

    comment_id = existing_comment(repo, pr_number)
    if comment_id:
        gh(
            "api",
            "--method",
            "PATCH",
            f"repos/{repo}/issues/comments/{comment_id}",
            "-f",
            f"body={body}",
        )
    elif problems or notes:
        gh(
            "api",
            "--method",
            "POST",
            f"repos/{repo}/issues/{pr_number}/comments",
            "-f",
            f"body={body}",
        )

    gh(
        "api",
        "--method",
        "POST",
        f"repos/{repo}/statuses/{sha}",
        "-f",
        f"state={state}",
        "-f",
        f"context={CONTEXT}",
        "-f",
        f"description={headline[:140]}",
        "-f",
        f"target_url={run_url}",
    )


if __name__ == "__main__":
    main()
