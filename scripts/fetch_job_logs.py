#!/usr/bin/env python3
"""Fetch GitHub Actions job logs while a workflow run is still in progress.

``gh run view --log-failed`` waits until every job in the run has finished.
A completed job already exposes logs on ``GET .../actions/jobs/JOB_ID/logs``
while sibling jobs are still running. Filter for pytest ``FAILURES`` rather
than the Post job cleanup / container tail. An in-progress job's latest
chunk can lag several minutes.

    python scripts/fetch_job_logs.py
    python scripts/fetch_job_logs.py 2667
    python scripts/fetch_job_logs.py --run 36277763307
    python scripts/fetch_job_logs.py --job 108503680591
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Sequence
from dataclasses import dataclass
from typing import Protocol
from urllib.parse import urlparse

FAILED_CONCLUSIONS = frozenset({"failure", "cancelled", "timed_out", "startup_failure"})
FETCHABLE_STATUSES = frozenset({"completed", "in_progress"})
PREFERRED_WORKFLOW = "Tests"
TIMESTAMP_RE = re.compile(r"^\ufeff?\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d+)?Z ")
FAILURES_BANNER_RE = re.compile(r"^={3,}\s*FAILURES\s*={3,}\s*$")
CLEANUP_RE = re.compile(r"^(Post job cleanup\.?|Stop and remove container:)")
JOB_URL_RE = re.compile(
    r"/actions/runs/(?P<run>\d+)(?:/job/(?P<job>\d+))?",
)
PR_URL_RE = re.compile(r"/pull/(?P<pr>\d+)")
MAX_EXCERPT_LINES = 200
IN_PROGRESS_TAIL_LINES = 80


class JobLogsUnavailable(RuntimeError):
    """The REST jobs API had no log body for this job yet."""


class GitHub(Protocol):
    def repo_name(self) -> str: ...

    def current_branch(self) -> str: ...

    def pull_request(self, number: int | None) -> dict: ...

    def runs_for_sha(self, sha: str) -> list[dict]: ...

    def jobs_for_run(self, run_id: int) -> list[dict]: ...

    def job(self, job_id: int) -> dict: ...

    def job_logs(self, job_id: int) -> str: ...


@dataclass(frozen=True)
class Selection:
    """What the user asked to fetch."""

    pr: int | None = None
    run: int | None = None
    job: int | None = None
    include_all: bool = False


def strip_log_prefix(line: str) -> str:
    """Drop the Actions timestamp so FAILURES banners match as plain text."""
    return TIMESTAMP_RE.sub("", line.rstrip("\r\n"))


def cut_cleanup(lines: Sequence[str]) -> list[str]:
    """Drop Post job cleanup and container teardown from the end of a log."""
    kept: list[str] = []
    for line in lines:
        if CLEANUP_RE.match(line):
            break
        kept.append(line)
    return kept


def extract_failure_excerpt(
    log_text: str,
    *,
    job_status: str = "completed",
    max_lines: int = MAX_EXCERPT_LINES,
) -> str:
    """Return the pytest FAILURES block, or a lagged tail for a running job.

    Mid-run xdist ``FAILED`` progress lines are not the traceback. The
    banner at the end of the pytest session is. Cleanup and container
    teardown after ``##[error]Process completed`` are noise.
    """
    stripped = [strip_log_prefix(line) for line in log_text.splitlines()]
    useful = cut_cleanup(stripped)
    if job_status != "completed":
        tail = useful[-IN_PROGRESS_TAIL_LINES:]
        if not tail:
            return (
                "(no log lines yet; an in-progress job's REST log can lag "
                "several minutes)"
            )
        return "\n".join(tail)

    start = next(
        (index for index, line in enumerate(useful) if FAILURES_BANNER_RE.match(line)),
        None,
    )
    errors = [line for line in useful if line.startswith("##[error]")]
    if start is None:
        body = useful[-max_lines:] if useful else []
        excerpt = list(body)
        for line in errors:
            if line not in excerpt:
                excerpt.append(line)
        if not excerpt:
            return "(no FAILURES banner and no ##[error] lines in this log)"
        return "\n".join(excerpt)

    chunk = useful[start:]
    if len(chunk) > max_lines:
        omitted = len(chunk) - max_lines
        chunk = (
            chunk[: max_lines - 20]
            + [f"... ({omitted} lines omitted) ..."]
            + chunk[-19:]
        )
    for line in errors:
        if line not in chunk:
            chunk.append(line)
    return "\n".join(chunk)


def jobs_to_fetch(
    jobs: Sequence[dict],
    *,
    job_id: int | None = None,
    include_all: bool = False,
) -> list[dict]:
    """Choose which jobs to download logs for.

    Default: failed conclusions. If none have failed yet, in-progress jobs
    (their REST logs can lag). ``--all`` includes every job that can have
    logs. A ``--job`` id always wins.
    """
    if job_id is not None:
        matching = [job for job in jobs if int(job["id"]) == job_id]
        if matching:
            return matching
        return [{"id": job_id, "name": f"job {job_id}", "status": "unknown"}]

    fetchable = [job for job in jobs if job.get("status") in FETCHABLE_STATUSES]
    if include_all:
        return list(fetchable)
    failed = [job for job in fetchable if job.get("conclusion") in FAILED_CONCLUSIONS]
    if failed:
        return failed
    return [job for job in fetchable if job.get("status") == "in_progress"]


def prefer_tests_run(runs: Sequence[dict]) -> dict | None:
    """Pick the Tests workflow when several runs share a head SHA."""
    if not runs:
        return None
    for run in runs:
        if run.get("name") == PREFERRED_WORKFLOW:
            return run
    return runs[0]


def parse_github_url(value: str) -> Selection | None:
    """Read a PR, run, or job id out of a github.com URL."""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return None
    job_match = JOB_URL_RE.search(parsed.path)
    if job_match:
        job = job_match.group("job")
        run = job_match.group("run")
        if job:
            return Selection(job=int(job), run=int(run))
        return Selection(run=int(run))
    pr_match = PR_URL_RE.search(parsed.path)
    if pr_match:
        return Selection(pr=int(pr_match.group("pr")))
    return None


def parse_args(argv: Sequence[str] | None = None) -> Selection:
    parser = argparse.ArgumentParser(
        description=(
            "Fetch GitHub Actions job logs via the REST jobs API so a "
            "completed job can be read while sibling jobs are still running. "
            "Do not use `gh run view --log-failed` for that: it waits until "
            "the whole run ends."
        )
    )
    parser.add_argument(
        "target",
        nargs="?",
        help="PR number or GitHub PR/run/job URL. Default: the current branch's PR.",
    )
    parser.add_argument("--pr", type=int, help="Pull request number")
    parser.add_argument("--run", type=int, help="Workflow run id")
    parser.add_argument("--job", type=int, help="Job id")
    parser.add_argument(
        "--all",
        action="store_true",
        dest="include_all",
        help="Fetch every job that has logs, not only failures.",
    )
    ns = parser.parse_args(argv)
    selection = Selection(
        pr=ns.pr,
        run=ns.run,
        job=ns.job,
        include_all=ns.include_all,
    )
    if ns.target:
        from_url = parse_github_url(ns.target)
        if from_url is not None:
            selection = Selection(
                pr=selection.pr or from_url.pr,
                run=selection.run or from_url.run,
                job=selection.job or from_url.job,
                include_all=selection.include_all,
            )
        elif ns.target.isdigit():
            selection = Selection(
                pr=int(ns.target),
                run=selection.run,
                job=selection.job,
                include_all=selection.include_all,
            )
        else:
            parser.error(
                f"invalid target {ns.target!r}; expected a PR number or GitHub URL"
            )
    return selection


def format_job_line(job: dict) -> str:
    conclusion = job.get("conclusion") or "-"
    return (
        f"  job {job.get('id')}  {job.get('name', '?')}  "
        f"status={job.get('status', '?')}  conclusion={conclusion}"
    )


def run_html_url(run_id: int, jobs: Sequence[dict], repo: str) -> str:
    """Prefer the workflow run URL, not the first job's Checks tab URL."""
    if jobs:
        url = str(jobs[0].get("html_url") or "")
        if "/job/" in url:
            return url.split("/job/")[0]
        if "/actions/runs/" in url:
            return url
    return f"https://github.com/{repo}/actions/runs/{run_id}"


def resolve_run(github: GitHub, selection: Selection) -> tuple[dict, list[dict]]:
    """Return the workflow run and its jobs for this selection."""
    if selection.job is not None and selection.run is None:
        job = github.job(selection.job)
        run = {
            "id": job.get("run_id"),
            "status": job.get("status"),
            "conclusion": job.get("conclusion"),
            "html_url": job.get("html_url"),
            "name": job.get("workflow_name") or "job",
        }
        return run, [job]
    if selection.run is not None:
        jobs = github.jobs_for_run(selection.run)
        run = {
            "id": selection.run,
            "status": _run_status_from_jobs(jobs),
            "conclusion": _run_conclusion_from_jobs(jobs),
            "html_url": run_html_url(selection.run, jobs, github.repo_name()),
            "name": "run",
        }
        return run, jobs

    pull = github.pull_request(selection.pr)
    sha = pull["headRefOid"]
    runs = github.runs_for_sha(sha)
    run = prefer_tests_run(runs)
    if run is None:
        where = f"PR #{pull.get('number', selection.pr)}" if pull else "this SHA"
        raise RuntimeError(f"No GitHub Actions runs found for {where}.")
    jobs = github.jobs_for_run(int(run["id"]))
    return run, jobs


def _run_status_from_jobs(jobs: Sequence[dict]) -> str:
    if any(job.get("status") in {"in_progress", "queued", "waiting"} for job in jobs):
        return "in_progress"
    return "completed"


def _run_conclusion_from_jobs(jobs: Sequence[dict]) -> str | None:
    if _run_status_from_jobs(jobs) == "in_progress":
        return None
    if any(job.get("conclusion") in FAILED_CONCLUSIONS for job in jobs):
        return "failure"
    if jobs and all(job.get("conclusion") == "success" for job in jobs):
        return "success"
    return None


def render_report(
    github: GitHub,
    selection: Selection,
) -> tuple[str, int]:
    """Build the agent-facing report. Exit 0 even when no job has failed yet."""
    run, jobs = resolve_run(github, selection)
    lines: list[str] = []
    run_status = run.get("status") or "unknown"
    run_url = run.get("html_url") or ""
    lines.append(
        f"run {run.get('id')}  {run.get('name', '')}  "
        f"status={run_status}  conclusion={run.get('conclusion') or '-'}"
    )
    if run_url:
        lines.append(run_url)
    if run_status == "in_progress":
        lines.append(
            "This run is still in progress. Do not use "
            "`gh run view --log-failed`; it waits until every job finishes. "
            "Fetching completed (and lagged in-progress) job logs from "
            "GET .../actions/jobs/JOB_ID/logs."
        )
    for job in jobs:
        lines.append(format_job_line(job))

    chosen = jobs_to_fetch(
        jobs, job_id=selection.job, include_all=selection.include_all
    )
    if not chosen:
        lines.append(
            "No failed or in-progress jobs. Pass --all to fetch successful job logs."
        )
        return "\n".join(lines) + "\n", 0

    for job in chosen:
        job_id = int(job["id"])
        status = job.get("status") or "unknown"
        lines.append("")
        lines.append(
            f"## {job.get('name', job_id)} ({job_id})  "
            f"status={status}  conclusion={job.get('conclusion') or '-'}"
        )
        if status == "in_progress":
            lines.append(
                "Note: this job is still running. The REST log can lag "
                "several minutes behind the live tail."
            )
        elif status not in FETCHABLE_STATUSES:
            lines.append("Logs are not available until the job starts.")
            continue
        try:
            log_text = github.job_logs(job_id)
        except JobLogsUnavailable as exc:
            lines.append(str(exc) or "Logs are not available for this job yet.")
            continue
        lines.append(extract_failure_excerpt(log_text, job_status=status))
    return "\n".join(lines) + "\n", 0


class LiveGitHub:
    """GitHub CLI adapter. ``gh api --allow-escape-sequences`` follows the log redirect."""

    def __init__(self, repo: str | None = None):
        self._repo = repo

    def repo_name(self) -> str:
        if self._repo:
            return self._repo
        self._repo = self._gh_text(
            ["gh", "repo", "view", "--json", "nameWithOwner", "-q", ".nameWithOwner"]
        ).strip()
        return self._repo

    def current_branch(self) -> str:
        return self._gh_text(
            ["git", "branch", "--show-current"],
        ).strip()

    def pull_request(self, number: int | None) -> dict:
        args = [
            "gh",
            "pr",
            "view",
            "--json",
            "number,url,headRefOid,headRefName",
        ]
        if number is not None:
            args.insert(3, str(number))
        else:
            branch = self.current_branch()
            if not branch:
                raise RuntimeError("Could not determine the current branch.")
            args.insert(3, branch)
        return json.loads(self._gh_text(args))

    def runs_for_sha(self, sha: str) -> list[dict]:
        payload = json.loads(
            self._gh_text(
                [
                    "gh",
                    "api",
                    f"repos/{self.repo_name()}/actions/runs?head_sha={sha}&per_page=20",
                ]
            )
        )
        return list(payload.get("workflow_runs") or payload.get("runs") or [])

    def jobs_for_run(self, run_id: int) -> list[dict]:
        payload = json.loads(
            self._gh_text(
                ["gh", "api", f"repos/{self.repo_name()}/actions/runs/{run_id}/jobs"]
            )
        )
        return list(payload.get("jobs") or [])

    def job(self, job_id: int) -> dict:
        return json.loads(
            self._gh_text(
                ["gh", "api", f"repos/{self.repo_name()}/actions/jobs/{job_id}"]
            )
        )

    def job_logs(self, job_id: int) -> str:
        result = subprocess.run(
            [
                "gh",
                "api",
                "--allow-escape-sequences",
                f"repos/{self.repo_name()}/actions/jobs/{job_id}/logs",
            ],
            capture_output=True,
            text=True,
        )
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip() or (
                f"gh api exited {result.returncode}"
            )
            raise JobLogsUnavailable(
                f"No logs for job {job_id} yet ({detail}). "
                "Queued jobs have none; in-progress logs can lag several minutes."
            )
        return result.stdout

    def _gh_text(self, args: Sequence[str]) -> str:
        result = subprocess.run(args, capture_output=True, text=True)
        if result.returncode != 0:
            detail = (result.stderr or result.stdout or "").strip()
            raise RuntimeError(detail or f"{args[0]} exited {result.returncode}")
        return result.stdout


def main(argv: Sequence[str] | None = None, *, github: GitHub | None = None) -> int:
    try:
        selection = parse_args(argv)
        report, status = render_report(github or LiveGitHub(), selection)
    except SystemExit as exc:
        code = exc.code
        return code if isinstance(code, int) else 2
    except (RuntimeError, JobLogsUnavailable, json.JSONDecodeError, KeyError) as exc:
        print(str(exc), file=sys.stderr)
        return 1
    sys.stdout.write(report)
    return status


if __name__ == "__main__":
    raise SystemExit(main())
