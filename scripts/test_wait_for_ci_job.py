"""A required CI gate accepts only its successful companion in the same attempt."""

import subprocess  # nosec B404 - Test constructs timeout exceptions; never runs commands.
from copy import deepcopy

import pytest

from scripts.wait_for_ci_job import CompanionJobError, wait_for_job

pytestmark = pytest.mark.core


def _job(**changes):
    return {
        "name": "test-full",
        "run_id": 123,
        "run_attempt": 2,
        "head_sha": "a" * 40,
        "status": "completed",
        "conclusion": "success",
        **changes,
    }


def _wait(responses, timeout=3):
    now = [0]
    responses = iter(responses)
    last = [[]]

    def read_jobs():
        last[0] = next(responses, last[0])
        if isinstance(last[0], Exception):
            raise last[0]
        return deepcopy(last[0])

    def sleep(seconds):
        now[0] += seconds

    return wait_for_job(
        read_jobs,
        job_name="test-full",
        run_id=123,
        run_attempt=2,
        head_sha="a" * 40,
        timeout_seconds=timeout,
        poll_seconds=1,
        clock=lambda: now[0],
        sleep=sleep,
        report=lambda _: None,
    )


def test_wait_accepts_only_completed_success_after_queue_and_execution():
    assert (
        _wait(
            [[], [_job(status="queued")], [_job(status="in_progress")], [_job()]],
            timeout=4,
        )
        == _job()
    )


@pytest.mark.parametrize(
    "conclusion", ["failure", "cancelled", "skipped", "timed_out", "neutral", None]
)
def test_unsuccessful_companion_cannot_satisfy_required_gate(conclusion):
    with pytest.raises(CompanionJobError, match="concluded"):
        _wait([[_job(conclusion=conclusion)]])


@pytest.mark.parametrize(
    "changes", [{"run_id": 124}, {"run_attempt": 1}, {"head_sha": "b" * 40}]
)
def test_result_from_another_revision_run_or_attempt_is_rejected(changes):
    with pytest.raises(CompanionJobError, match="mismatch"):
        _wait([[_job(**changes)]])


def test_duplicate_job_name_cannot_choose_a_successful_result():
    with pytest.raises(CompanionJobError, match="multiple companion"):
        _wait([[_job(), _job(conclusion="failure")]])


def test_missing_companion_fails_with_full_rerun_instruction():
    with pytest.raises(CompanionJobError, match="rerun all jobs"):
        _wait([[{**_job(), "name": "another-job"}]])


def test_transient_api_failure_can_recover_but_persistent_failure_is_bounded():
    unavailable = subprocess.TimeoutExpired("gh", 30)
    assert _wait([unavailable, [_job()]]) == _job()
    with pytest.raises(CompanionJobError, match="within 3s"):
        _wait([unavailable])
