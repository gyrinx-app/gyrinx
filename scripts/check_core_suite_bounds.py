#!/usr/bin/env python3
"""Check that a collected core-suite count sits inside the CI bounds.

The required `test` job counts the tests marked core on the branch and
refuses a count outside CORE_SUITE_MIN..CORE_SUITE_MAX in
`.github/workflows/test.yaml`. When main sits on the max, the next pull
request that marks another test core fails the required job, so this
script also warns when the count is within HEADROOM of the max.

    scripts/check_core_suite_bounds.py COUNT MIN MAX
    scripts/check_core_suite_bounds.py COUNT MIN MAX HEADROOM

Prints a one-line summary, then GitHub Actions annotations. Exit 1 when the
count is outside the bounds; exit 0 when it only needs a warning.
"""

import dataclasses
import sys

HEADROOM = 50


@dataclasses.dataclass(frozen=True)
class BoundsResult:
    """Outcome of one bounds check, ready to print."""

    ok: bool
    messages: tuple[str, ...]


def check_core_suite_bounds(
    count: int,
    minimum: int,
    maximum: int,
    headroom: int = HEADROOM,
) -> BoundsResult:
    """Return whether COUNT is inside [MIN, MAX], and any annotations.

    A count inside the range but at least as large as MAX - HEADROOM is
    still ok: the job must not fail until the cap is actually crossed.
    It does warn, because the next core-marked test would cross it.
    """
    if headroom < 0:
        raise ValueError("headroom must be >= 0")
    summary = f"core suite: {count} tests (allowed {minimum}..{maximum})"
    if count < minimum or count > maximum:
        return BoundsResult(
            ok=False,
            messages=(
                summary,
                "::error::the core suite has "
                f"{count} tests; adjust the marks or the bounds in test.yaml",
            ),
        )
    remaining = maximum - count
    if remaining <= headroom:
        return BoundsResult(
            ok=True,
            messages=(
                summary,
                "::warning::the core suite has "
                f"{count} tests, {remaining} below CORE_SUITE_MAX={maximum}. "
                "A main suite this close to the cap fails the next pull "
                "request that marks another test core. Raise CORE_SUITE_MAX in "
                ".github/workflows/test.yaml, or unmark tests that are not "
                "fundamental behaviour.",
            ),
        )
    return BoundsResult(ok=True, messages=(summary,))


def main(argv: list[str]) -> int:
    if len(argv) not in (4, 5):
        print(
            "Usage: check_core_suite_bounds.py COUNT MIN MAX [HEADROOM]",
            file=sys.stderr,
        )
        return 2
    try:
        count = int(argv[1])
        minimum = int(argv[2])
        maximum = int(argv[3])
        headroom = int(argv[4]) if len(argv) == 5 else HEADROOM
    except ValueError:
        print(
            "COUNT, MIN, MAX, and HEADROOM must be integers.",
            file=sys.stderr,
        )
        return 2
    try:
        result = check_core_suite_bounds(count, minimum, maximum, headroom)
    except ValueError as error:
        print(str(error), file=sys.stderr)
        return 2
    for line in result.messages:
        print(line)
    return 0 if result.ok else 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
