"""Wait for a companion job in this workflow attempt; never reuse an earlier result."""

import argparse
import json
import re
import shutil
import subprocess  # nosec B404 - Fixed gh argv; no shell.
import sys
import time


class CompanionJobError(RuntimeError):
    pass


def fetch_jobs(repository, run_id, run_attempt):
    gh = shutil.which("gh")
    if gh is None:
        raise CompanionJobError("gh is required to read companion job status")
    result = subprocess.run(
        [
            gh,
            "api",
            "--paginate",
            "--slurp",
            f"repos/{repository}/actions/runs/{run_id}/attempts/{run_attempt}/jobs?per_page=100",
        ],
        check=True,
        capture_output=True,
        text=True,
        timeout=30,
    )
    return [job for page in json.loads(result.stdout) for job in page["jobs"]]


def wait_for_job(
    read_jobs,
    *,
    job_name,
    run_id,
    run_attempt,
    head_sha,
    timeout_seconds=900,
    poll_seconds=20,
    clock=time.monotonic,
    sleep=time.sleep,
    report=print,
):
    deadline = clock() + timeout_seconds
    previous = None
    while clock() < deadline:
        try:
            jobs = read_jobs()
        except (
            subprocess.CalledProcessError,
            subprocess.TimeoutExpired,
            ValueError,
            KeyError,
        ) as exc:
            state = f"API unavailable ({type(exc).__name__})"
            matching = []
        else:
            matching = [job for job in jobs if job["name"] == job_name]
            state = "not yet present"
        if len(matching) > 1:
            raise CompanionJobError(f"multiple companion jobs named {job_name}")
        if matching:
            job = matching[0]
            for key, expected in (
                ("run_id", run_id),
                ("run_attempt", run_attempt),
                ("head_sha", head_sha),
            ):
                if str(job.get(key)) != str(expected):
                    raise CompanionJobError(f"companion job {key} mismatch")
            state = job["status"]
            if state == "completed":
                if job.get("conclusion") != "success":
                    raise CompanionJobError(
                        f"companion job concluded {job.get('conclusion')}"
                    )
                report(f"Companion job {job_name} succeeded in attempt {run_attempt}")
                return job
            if state not in {
                "queued",
                "in_progress",
                "waiting",
                "pending",
                "requested",
            }:
                raise CompanionJobError(f"unexpected companion job status: {state}")
        if state != previous:
            report(f"Waiting for companion job {job_name}: {state}")
            previous = state
        sleep(min(poll_seconds, max(0, deadline - clock())))
    raise CompanionJobError(
        f"companion job {job_name} did not succeed within {timeout_seconds}s in "
        f"attempt {run_attempt}; rerun all jobs if this attempt omitted it"
    )


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repository", required=True)
    parser.add_argument("--run-id", required=True, type=int)
    parser.add_argument("--run-attempt", required=True, type=int)
    parser.add_argument("--job-name", required=True)
    parser.add_argument("--head-sha", required=True)
    parser.add_argument("--timeout-seconds", type=int, default=900)
    parser.add_argument("--poll-seconds", type=int, default=20)
    args = parser.parse_args(argv)
    if not re.fullmatch(r"[A-Za-z0-9_.-]+/[A-Za-z0-9_.-]+", args.repository):
        parser.error("--repository must be owner/repo")
    if not re.fullmatch(r"[0-9a-f]{40}", args.head_sha):
        parser.error("--head-sha must be a full Git SHA")
    if min(args.run_id, args.run_attempt, args.timeout_seconds, args.poll_seconds) < 1:
        parser.error("run IDs, attempts and wait durations must be positive")
    try:
        wait_for_job(
            lambda: fetch_jobs(args.repository, args.run_id, args.run_attempt),
            job_name=args.job_name,
            run_id=args.run_id,
            run_attempt=args.run_attempt,
            head_sha=args.head_sha,
            timeout_seconds=args.timeout_seconds,
            poll_seconds=args.poll_seconds,
        )
    except CompanionJobError as exc:
        print(f"Companion job verification failed: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
