#!/usr/bin/env python3
"""Annotate PR-comment JSON with reviews that are still in progress.

GitHub drops Copilot from ``reviewRequests`` while a lite review is running.
``gh pr view --json reviewRequests,reviews`` is then empty even though the
timeline shows a ``ReviewRequestedEvent`` for ``copilot-pull-request-reviewer``
and the sidebar says "Reviewing at lite effort". The in-progress signal is
that event with no later review from the same login.

A team request is fulfilled when a member reviews, which leaves no removal
event and no review by the team, so teams count only while they are still in
``reviewRequests``.
"""

from __future__ import annotations

import json
import sys
from typing import Any


def reviewer_login(reviewer: dict[str, Any] | None) -> str | None:
    if not reviewer:
        return None
    return reviewer.get("login") or reviewer.get("combinedSlug") or reviewer.get("name")


def reviews_in_progress(pr: dict[str, Any]) -> list[dict[str, Any]]:
    last_requested: dict[str, str] = {}
    last_removed: dict[str, str] = {}
    for event in pr.get("timelineItems", {}).get("nodes") or []:
        if not event:
            continue
        reviewer = event.get("requestedReviewer") or {}
        if reviewer.get("__typename") == "Team":
            continue
        login = reviewer_login(reviewer)
        if not login:
            continue
        created = event.get("createdAt") or ""
        typename = event.get("__typename")
        if typename == "ReviewRequestedEvent" and created >= last_requested.get(
            login, ""
        ):
            last_requested[login] = created
        elif typename == "ReviewRequestRemovedEvent" and created >= last_removed.get(
            login, ""
        ):
            last_removed[login] = created

    last_review: dict[str, str] = {}
    for review in pr.get("reviews", {}).get("nodes") or []:
        login = (review.get("author") or {}).get("login")
        if not login:
            continue
        submitted = review.get("submittedAt") or ""
        if submitted >= last_review.get(login, ""):
            last_review[login] = submitted

    outstanding: set[str] = set()
    for node in pr.get("reviewRequests", {}).get("nodes") or []:
        login = reviewer_login((node or {}).get("requestedReviewer"))
        if login:
            outstanding.add(login)

    in_progress: list[dict[str, Any]] = []
    for login in sorted(last_requested.keys() | outstanding):
        requested_at = last_requested.get(login)
        removed_at = last_removed.get(login)
        reviewed_at = last_review.get(login)
        still_requested = login in outstanding
        if (
            requested_at
            and removed_at
            and removed_at >= requested_at
            and not still_requested
        ):
            continue
        if (
            reviewed_at
            and requested_at
            and reviewed_at >= requested_at
            and not still_requested
        ):
            continue
        if not requested_at and not still_requested:
            continue
        in_progress.append(
            {
                "login": login,
                "requestedAt": requested_at,
                "lastReviewAt": reviewed_at,
            }
        )
    return in_progress


def _truncated(connection: dict[str, Any] | None, count_field: str) -> bool:
    if not connection:
        return False
    count = connection.get(count_field)
    return count is not None and count > len(connection.get("nodes") or [])


def reviews_in_progress_truncated(pr: dict[str, Any]) -> bool:
    return (
        _truncated(pr.get("reviews"), "totalCount")
        or _truncated(pr.get("reviewRequests"), "totalCount")
        or _truncated(pr.get("timelineItems"), "filteredCount")
    )


def annotate(pr: Any) -> Any:
    if not isinstance(pr, dict):
        return pr
    annotated = dict(pr)
    annotated["reviewsInProgress"] = reviews_in_progress(pr)
    annotated["reviewsInProgressTruncated"] = reviews_in_progress_truncated(pr)
    return annotated


def main() -> None:
    pr = json.load(sys.stdin)
    json.dump(annotate(pr), sys.stdout, indent=2)
    sys.stdout.write("\n")


if __name__ == "__main__":
    main()
