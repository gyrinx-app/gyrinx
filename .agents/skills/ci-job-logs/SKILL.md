---
name: ci-job-logs
description: >
  Fetch GitHub Actions job logs while a workflow run is still in progress.
  Use when a CI check fails, when `gh run view --log-failed` waits or hangs,
  when you need a pytest FAILURES excerpt from a completed job while sibling
  jobs are still running, or when debugging the required `test` job before
  `test-full` finishes.
---

# CI job logs

`gh run view --log-failed` waits until **every** job in the workflow run has
finished. A completed job already exposes logs on the REST jobs API:

```
GET /repos/{owner}/{repo}/actions/jobs/{job_id}/logs
```

That works while sibling jobs (often `test-full`) are still running. An
in-progress job can return a partial log; the latest chunk may lag several
minutes.

Do not tail the Post job cleanup or "Stop and remove container" lines. Filter
for pytest `FAILURES` (the banner at the end of the session, not mid-run xdist
`[ 43%] FAILED` progress).

## Fetch

```bash
python scripts/fetch_job_logs.py
python scripts/fetch_job_logs.py 2667
python scripts/fetch_job_logs.py --job 108503680591
python scripts/fetch_job_logs.py --run 36277763307
# Codex:
.codex/run.sh python scripts/fetch_job_logs.py
```

With no argument, the helper uses the current branch's pull request and prefers
the `Tests` workflow. A bare number is a PR. `--all` includes successful jobs.

The helper calls `gh api --allow-escape-sequences repos/.../actions/jobs/JOB_ID/logs`
and prints the FAILURES excerpt. It will not run `gh run view --log-failed`.

## Direct REST (when the helper is the wrong shape)

```bash
gh api --allow-escape-sequences repos/gyrinx-app/gyrinx/actions/jobs/JOB_ID/logs
```

List jobs for a run with `gh api repos/gyrinx-app/gyrinx/actions/runs/RUN_ID/jobs`.
Job ids are also on the Checks tab URL (`.../actions/runs/RUN_ID/job/JOB_ID`).
