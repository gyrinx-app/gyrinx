"""GitHub Actions job logs while a run is still in progress.

``gh run view --log-failed`` waits until every job finishes. Completed job
logs are already on ``GET .../actions/jobs/JOB_ID/logs`` (jay on #lessons,
25 Sep). These tests pin the FAILURES filter and the in-progress warning so
agents do not tail Post job cleanup or stall on the CLI waiter.
"""

from dataclasses import dataclass, field
from pathlib import Path

from scripts.fetch_job_logs import (
    JobLogsUnavailable,
    Selection,
    extract_failure_excerpt,
    jobs_to_fetch,
    main,
    parse_args,
    parse_github_url,
    prefer_tests_run,
    render_report,
)

ROOT = Path(__file__).resolve().parents[2]

LOG_WITH_FAILURES = """\
\ufeff2026-09-26T22:54:22.1145492Z Current runner version: '2.337.0'
2026-09-26T23:09:47.5405440Z [gw0] [ 43%] FAILED n26/tests/sandbox/test_authoring_views.py::TestFieldlessActionConfigurations::test_recruitment_rule
2026-09-26T23:27:42.5344848Z =================================== FAILURES ===================================
2026-09-26T23:27:42.5345728Z _ TestFieldlessActionConfigurations.test_recruitment_rule _
2026-09-26T23:27:42.5428393Z =========================== short test summary info ============================
2026-09-26T23:27:42.5429411Z FAILED n26/tests/sandbox/test_authoring_views.py::TestFieldlessActionConfigurations::test_recruitment_rule - assert 200 == 302
2026-09-26T23:27:42.5430984Z ===== 1 failed, 12599 passed, 13 skipped, 1 xfailed in 1957.02s (0:32:37) ======
2026-09-26T23:27:43.2070733Z ##[error]Process completed with exit code 1.
2026-09-26T23:27:43.2153532Z Post job cleanup.
2026-09-26T23:27:43.5302653Z Stop and remove container: f0f52ff94aa743c2b9282013df0b1f6b_postgres164_7cbce7
"""

LOG_WITHOUT_FAILURES = """\
2026-09-26T22:54:22.1145492Z ##[group]Runner Image
2026-09-26T22:54:23.0000000Z collecting ...
2026-09-26T22:54:24.0000000Z ##[error]The action is currently running
2026-09-26T22:54:25.0000000Z Post job cleanup.
"""


@dataclass
class FakeGitHub:
    pulls: dict[int | None, dict] = field(default_factory=dict)
    runs: dict[str, list[dict]] = field(default_factory=dict)
    jobs_by_run: dict[int, list[dict]] = field(default_factory=dict)
    job_records: dict[int, dict] = field(default_factory=dict)
    logs: dict[int, str] = field(default_factory=dict)

    def repo_name(self) -> str:
        return "gyrinx-app/gyrinx"

    def current_branch(self) -> str:
        return "cursor/lessons-board-improvements-652c"

    def pull_request(self, number: int | None) -> dict:
        if number in self.pulls:
            return self.pulls[number]
        if number is None and None in self.pulls:
            return self.pulls[None]
        raise RuntimeError(f"No PR {number}")

    def runs_for_sha(self, sha: str) -> list[dict]:
        return list(self.runs.get(sha, []))

    def jobs_for_run(self, run_id: int) -> list[dict]:
        return list(self.jobs_by_run.get(run_id, []))

    def job(self, job_id: int) -> dict:
        return dict(self.job_records[job_id])

    def job_logs(self, job_id: int) -> str:
        if job_id not in self.logs:
            raise JobLogsUnavailable(f"No logs for job {job_id} yet")
        return self.logs[job_id]


def _job(job_id, name, *, status="completed", conclusion="success", run_id=1):
    return {
        "id": job_id,
        "name": name,
        "status": status,
        "conclusion": conclusion,
        "run_id": run_id,
        "html_url": (
            f"https://github.com/gyrinx-app/gyrinx/actions/runs/{run_id}/job/{job_id}"
        ),
    }


def test_excerpt_keeps_failures_and_drops_cleanup_and_xdist_progress():
    excerpt = extract_failure_excerpt(LOG_WITH_FAILURES)

    assert (
        "=================================== FAILURES ==================================="
        in excerpt
    )
    assert "FAILED n26/tests/sandbox/test_authoring_views.py" in excerpt
    assert "assert 200 == 302" in excerpt
    assert "##[error]Process completed with exit code 1." in excerpt
    assert "Post job cleanup" not in excerpt
    assert "Stop and remove container" not in excerpt
    assert "[ 43%] FAILED" not in excerpt
    assert "Current runner version" not in excerpt


def test_excerpt_strips_actions_timestamps():
    excerpt = extract_failure_excerpt(LOG_WITH_FAILURES)

    assert "2026-09-26T" not in excerpt
    assert excerpt.startswith("====")


def test_in_progress_excerpt_is_a_tail_not_the_xdist_banner():
    excerpt = extract_failure_excerpt(LOG_WITHOUT_FAILURES, job_status="in_progress")

    assert "collecting ..." in excerpt
    assert "##[error]The action is currently running" in excerpt
    assert "Post job cleanup" not in excerpt
    assert "Runner Image" in excerpt


def test_completed_log_without_failures_keeps_error_lines():
    excerpt = extract_failure_excerpt(LOG_WITHOUT_FAILURES)

    assert "##[error]The action is currently running" in excerpt
    assert "Post job cleanup" not in excerpt


def test_long_failures_section_is_capped():
    body = "\n".join(
        f"2026-09-26T23:27:42.0000000Z traceback line {index}" for index in range(400)
    )
    log = (
        "2026-09-26T23:27:42.5344848Z =================================== FAILURES ===================================\n"
        + body
        + "\n2026-09-26T23:27:43.2070733Z ##[error]Process completed with exit code 1.\n"
        + "2026-09-26T23:27:43.2153532Z Post job cleanup.\n"
    )
    excerpt = extract_failure_excerpt(log, max_lines=50)
    lines = excerpt.splitlines()

    assert len(lines) <= 52
    assert "lines omitted" in excerpt
    assert "##[error]Process completed with exit code 1." in excerpt


def test_jobs_to_fetch_prefers_failed_jobs():
    jobs = [
        _job(1, "test", conclusion="success"),
        _job(2, "test-full", conclusion="failure"),
        _job(3, "fresh-database", status="in_progress", conclusion=None),
    ]

    chosen = jobs_to_fetch(jobs)

    assert [job["name"] for job in chosen] == ["test-full"]


def test_jobs_to_fetch_falls_back_to_in_progress_when_nothing_failed():
    jobs = [
        _job(1, "test", conclusion="success"),
        _job(2, "test-full", status="in_progress", conclusion=None),
    ]

    chosen = jobs_to_fetch(jobs)

    assert [job["name"] for job in chosen] == ["test-full"]


def test_jobs_to_fetch_all_includes_successes():
    jobs = [
        _job(1, "test", conclusion="success"),
        _job(2, "test-full", conclusion="failure"),
    ]

    chosen = jobs_to_fetch(jobs, include_all=True)

    assert [job["name"] for job in chosen] == ["test", "test-full"]


def test_jobs_to_fetch_job_id_wins():
    jobs = [_job(1, "test"), _job(2, "test-full", conclusion="failure")]

    chosen = jobs_to_fetch(jobs, job_id=1)

    assert [job["id"] for job in chosen] == [1]


def test_prefer_tests_workflow_when_several_runs_share_a_sha():
    runs = [
        {"id": 1, "name": "CI Checks"},
        {"id": 2, "name": "Tests"},
        {"id": 3, "name": "Migration watch"},
    ]

    assert prefer_tests_run(runs)["id"] == 2


def test_parse_job_and_run_urls():
    job = parse_github_url(
        "https://github.com/gyrinx-app/gyrinx/actions/runs/36277763307/job/108503680591"
    )
    run = parse_github_url(
        "https://github.com/gyrinx-app/gyrinx/actions/runs/36277763307"
    )
    pull = parse_github_url("https://github.com/gyrinx-app/gyrinx/pull/2667")

    assert job == Selection(run=36277763307, job=108503680591)
    assert run == Selection(run=36277763307)
    assert pull == Selection(pr=2667)


def test_parse_args_treats_a_bare_number_as_a_pr():
    assert parse_args(["2667"]) == Selection(pr=2667)


def test_run_report_links_the_workflow_run_not_the_first_job():
    github = FakeGitHub(
        jobs_by_run={
            99: [
                _job(10, "fresh-database", run_id=99),
                _job(11, "test-full", conclusion="failure", run_id=99),
            ]
        },
        logs={11: LOG_WITH_FAILURES},
    )

    report, status = render_report(github, Selection(run=99))

    assert status == 0
    assert "https://github.com/gyrinx-app/gyrinx/actions/runs/99\n" in report
    assert "runs/99/job/10" not in report.split("##", 1)[0]


def test_in_progress_run_warns_not_to_use_log_failed():
    github = FakeGitHub(
        pulls={
            2667: {
                "number": 2667,
                "headRefOid": "abc",
                "url": "https://github.com/gyrinx-app/gyrinx/pull/2667",
            }
        },
        runs={
            "abc": [
                {
                    "id": 99,
                    "name": "Tests",
                    "status": "in_progress",
                    "conclusion": None,
                    "html_url": "https://github.com/gyrinx-app/gyrinx/actions/runs/99",
                }
            ]
        },
        jobs_by_run={
            99: [
                _job(10, "test", conclusion="failure", run_id=99),
                _job(
                    11,
                    "test-full",
                    status="in_progress",
                    conclusion=None,
                    run_id=99,
                ),
            ]
        },
        logs={10: LOG_WITH_FAILURES},
    )

    report, status = render_report(github, Selection(pr=2667))

    assert status == 0
    assert "`gh run view --log-failed`" in report
    assert "GET .../actions/jobs/JOB_ID/logs" in report
    assert "assert 200 == 302" in report
    assert "Post job cleanup" not in report
    assert "test-full" in report
    assert "## test-full" not in report


def test_main_prints_the_excerpt_for_a_pr(capsys):
    github = FakeGitHub(
        pulls={
            2667: {"number": 2667, "headRefOid": "abc"},
        },
        runs={
            "abc": [{"id": 99, "name": "Tests", "status": "completed", "html_url": ""}]
        },
        jobs_by_run={99: [_job(10, "test-full", conclusion="failure", run_id=99)]},
        logs={10: LOG_WITH_FAILURES},
    )

    assert main(["2667"], github=github) == 0
    out = capsys.readouterr().out
    assert "FAILURES" in out
    assert "assert 200 == 302" in out


def test_missing_logs_are_a_skip_not_a_crash(capsys):
    github = FakeGitHub(
        job_records={
            10: _job(10, "test", status="in_progress", conclusion=None, run_id=99)
        },
        logs={},
    )

    assert main(["--job", "10"], github=github) == 0
    out = capsys.readouterr().out
    assert "No logs for job 10 yet" in out
    assert "lag several minutes" in out


def test_skill_and_docs_tell_agents_not_to_wait_on_log_failed():
    skill = (ROOT / ".agents/skills/ci-job-logs/SKILL.md").read_text()
    agents = (ROOT / "AGENTS.md").read_text()
    testing = (ROOT / "docs/developing-gyrinx/testing.md").read_text()

    for text in (skill, agents, testing):
        assert "fetch_job_logs.py" in text
        assert "log-failed" in text
        assert "actions/jobs" in text
