"""Copilot lite reviews are invisible on reviewRequests while they run.

On #2641, `reviewRequests` and `reviews` were empty while the GitHub timeline
showed Copilot reviewing at lite effort. The in-progress signal is a
ReviewRequestedEvent for copilot-pull-request-reviewer with no later review
from that bot. These tests pin that derived field so agents do not treat an
empty GraphQL review list as "no active review".
"""

import importlib.util
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / ".agents/skills/pr-comments/scripts/annotate_reviews_in_progress.py"
FETCH = ROOT / ".agents/skills/pr-comments/scripts/fetch-pr-comments.sh"
SKILL = ROOT / ".agents/skills/pr-comments/SKILL.md"


def _annotate():
    spec = importlib.util.spec_from_file_location(
        "annotate_reviews_in_progress", SCRIPT
    )
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


def _pr(*, requests=(), reviews=(), events=()):
    return {
        "reviewRequests": {"nodes": list(requests)},
        "reviews": {"nodes": list(reviews)},
        "timelineItems": {"nodes": list(events)},
    }


def _bot_request(created_at):
    return {
        "__typename": "ReviewRequestedEvent",
        "createdAt": created_at,
        "requestedReviewer": {
            "__typename": "Bot",
            "login": "copilot-pull-request-reviewer",
        },
    }


def test_copilot_lite_in_progress_when_review_requests_and_reviews_are_empty():
    annotate = _annotate()
    pr = _pr(events=(_bot_request("2026-09-23T21:37:29Z"),))
    assert annotate.reviews_in_progress(pr) == [
        {
            "login": "copilot-pull-request-reviewer",
            "requestedAt": "2026-09-23T21:37:29Z",
            "lastReviewAt": None,
        }
    ]


def test_copilot_re_review_is_in_progress_after_an_earlier_commented_review():
    annotate = _annotate()
    pr = _pr(
        reviews=(
            {
                "author": {"login": "copilot-pull-request-reviewer"},
                "submittedAt": "2026-09-23T21:43:05Z",
                "state": "COMMENTED",
            },
        ),
        events=(
            _bot_request("2026-09-23T21:37:29Z"),
            _bot_request("2026-09-23T21:48:22Z"),
        ),
    )
    assert annotate.reviews_in_progress(pr) == [
        {
            "login": "copilot-pull-request-reviewer",
            "requestedAt": "2026-09-23T21:48:22Z",
            "lastReviewAt": "2026-09-23T21:43:05Z",
        }
    ]


def test_completed_copilot_review_is_not_in_progress():
    annotate = _annotate()
    pr = _pr(
        reviews=(
            {
                "author": {"login": "copilot-pull-request-reviewer"},
                "submittedAt": "2026-09-23T21:52:57Z",
                "state": "COMMENTED",
            },
        ),
        events=(
            _bot_request("2026-09-23T21:37:29Z"),
            _bot_request("2026-09-23T21:48:22Z"),
        ),
    )
    assert annotate.reviews_in_progress(pr) == []


def test_outstanding_human_review_request_is_in_progress():
    annotate = _annotate()
    pr = _pr(
        requests=({"requestedReviewer": {"__typename": "User", "login": "jay"}},),
    )
    assert annotate.reviews_in_progress(pr) == [
        {
            "login": "jay",
            "requestedAt": None,
            "lastReviewAt": None,
        }
    ]


def test_removed_review_request_is_not_in_progress():
    annotate = _annotate()
    pr = _pr(
        events=(
            _bot_request("2026-09-23T21:37:29Z"),
            {
                "__typename": "ReviewRequestRemovedEvent",
                "createdAt": "2026-09-23T21:40:00Z",
                "requestedReviewer": {
                    "__typename": "Bot",
                    "login": "copilot-pull-request-reviewer",
                },
            },
        ),
    )
    assert annotate.reviews_in_progress(pr) == []


def test_annotate_adds_reviews_in_progress_without_dropping_other_fields():
    annotate = _annotate()
    pr = _pr(events=(_bot_request("2026-09-23T21:37:29Z"),))
    out = annotate.annotate(pr)
    assert out["timelineItems"] == pr["timelineItems"]
    assert out["reviewsInProgress"][0]["login"] == "copilot-pull-request-reviewer"


def test_fetch_script_queries_review_request_timeline_and_annotates():
    text = FETCH.read_text()
    assert "reviewRequests" in text
    assert "REVIEW_REQUESTED_EVENT" in text
    assert "REVIEW_REQUEST_REMOVED_EVENT" in text
    assert "copilot-pull-request-reviewer" in text
    assert "annotate_reviews_in_progress.py" in text


def test_skill_tells_agents_empty_reviews_are_not_no_copilot_review():
    text = SKILL.read_text()
    assert "reviewsInProgress" in text
    assert "copilot-pull-request-reviewer" in text
    assert "#2641" in text
