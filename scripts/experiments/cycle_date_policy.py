"""EXPERIMENTAL date-policy model, independent of Django and application code.

Missing bounds are unknown: they do not extend to infinity or reserve days.
A partially dated entry asserts its one known day; a fully dated entry asserts
every day from its start through its end, inclusive. Validation reports only
conflicts established by those asserted dates.
"""

from collections.abc import Sequence
from dataclasses import dataclass, replace
from datetime import date
from itertools import combinations


@dataclass(frozen=True)
class Bounds:
    start: date | None = None
    end: date | None = None


@dataclass(frozen=True)
class Entry:
    key: str
    order: int
    bounds: Bounds
    archived: bool = False


@dataclass(frozen=True)
class Issue:
    code: str
    keys: tuple[str, ...]


@dataclass(frozen=True)
class ShiftProposal:
    mode: str
    days: int


def _asserted_span(bounds: Bounds) -> tuple[date, date] | None:
    if bounds.start is None:
        return (bounds.end, bounds.end) if bounds.end is not None else None
    if bounds.end is None:
        return (bounds.start, bounds.start)
    if bounds.end < bounds.start:
        return None
    return bounds.start, bounds.end


def validate(
    entries: Sequence[Entry],
    *,
    chronological: bool = True,
    future_start: date | None = None,
) -> tuple[Issue, ...]:
    """Report definite conflicts without changing caller order or missing dates.

    Archived entries impose no constraints. Entry issues follow caller order;
    pair issues follow a stable sort by ordinal. Overlap takes precedence over
    date order, so each pair produces at most one issue. Reversed entries are
    excluded from pair comparisons, but still checked against ``future_start``.

    ``chronological`` requires known, disjoint spans to follow ordinal order.
    ``future_start`` is the first projected cycle's start after the saved prefix;
    every saved known bound must precede it, under either chronology policy.
    """
    active = [entry for entry in entries if not entry.archived]
    issues = []

    for entry in active:
        start, end = entry.bounds.start, entry.bounds.end
        if start is not None and end is not None and end < start:
            issues.append(Issue("reversed", (entry.key,)))
        if future_start is not None and any(
            bound is not None and bound >= future_start for bound in (start, end)
        ):
            issues.append(Issue("projection_boundary", (entry.key,)))

    dated = [
        (entry, span)
        for entry in sorted(active, key=lambda entry: entry.order)
        if (span := _asserted_span(entry.bounds)) is not None
    ]
    for (earlier, earlier_span), (later, later_span) in combinations(dated, 2):
        earlier_start, earlier_end = earlier_span
        later_start, later_end = later_span
        if earlier_start <= later_end and later_start <= earlier_end:
            issues.append(Issue("overlap", (earlier.key, later.key)))
        elif chronological and earlier_start > later_end:
            issues.append(Issue("date_order", (earlier.key, later.key)))

    return tuple(issues)


def propose_shift(
    entries: Sequence[Entry],
    *,
    order: int,
    old_end: date | None,
    new_end: date | None,
    future_start: date | None = None,
) -> ShiftProposal | None:
    """Suggest an optional shift; callers apply accepted proposals and validate.

    Known end edits preserve their delta. A newly known end offers the smallest
    forward shift needed to clear every later asserted span and the projected
    start. Existing gaps stay unchanged.
    """
    if new_end is None:
        return None
    anchors = [
        span[0]
        for entry in entries
        if not entry.archived
        and entry.order > order
        and (span := _asserted_span(entry.bounds)) is not None
    ]
    if future_start is not None:
        anchors.append(future_start)
    if not anchors:
        return None
    anchor = min(anchors)
    if old_end is not None:
        days = (new_end - old_end).days
        return ShiftProposal("delta", days) if days else None
    if anchor <= new_end:
        return ShiftProposal("align", (new_end - anchor).days + 1)
    return None


def shift_later(
    entries: Sequence[Entry], *, after_order: int, days: int
) -> tuple[Entry, ...]:
    """Shift each known bound after an ordinal, preserving gaps and input order.

    Archived entries remain unchanged. Each missing bound stays missing, and a
    fully undated entry remains undated. Date overflow raises ``ValueError``;
    immutable input entries remain unchanged even if a later bound overflows.
    """

    def shifted(bound: date | None) -> date | None:
        if bound is None:
            return None
        try:
            return date.fromordinal(bound.toordinal() + days)
        except OverflowError as exc:
            raise ValueError("Shifted date exceeds the supported range") from exc

    return tuple(
        replace(
            entry,
            bounds=Bounds(shifted(entry.bounds.start), shifted(entry.bounds.end)),
        )
        if not entry.archived and entry.order > after_order
        else entry
        for entry in entries
    )
