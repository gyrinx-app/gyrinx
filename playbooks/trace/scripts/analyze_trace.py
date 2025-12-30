#!/usr/bin/env python3
"""
Trace Analysis Script for Performance Optimization

Analyzes OpenTelemetry traces exported from Google Cloud Trace to identify
performance bottlenecks and optimization opportunities.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime
from dataclasses import dataclass


@dataclass
class SpanInfo:
    """Processed span information."""

    span_id: str
    name: str
    start_time: datetime
    end_time: datetime
    duration_ms: float
    parent_span_id: str | None
    labels: dict


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp from trace."""
    # Handle nanosecond precision
    if "." in ts:
        base, frac = ts.replace("Z", "").split(".")
        # Truncate to microseconds (6 digits)
        frac = frac[:6].ljust(6, "0")
        ts = f"{base}.{frac}"
    else:
        ts = ts.replace("Z", "")
    return datetime.fromisoformat(ts)


def load_trace(filepath: str) -> dict:
    """Load trace JSON file."""
    with open(filepath) as f:
        return json.load(f)


def process_spans(trace_data: dict) -> list[SpanInfo]:
    """Process raw spans into SpanInfo objects."""
    spans = []
    for span in trace_data.get("spans", []):
        start = parse_timestamp(span["startTime"])
        end = parse_timestamp(span["endTime"])
        duration_ms = (end - start).total_seconds() * 1000

        spans.append(
            SpanInfo(
                span_id=span["spanId"],
                name=span["name"],
                start_time=start,
                end_time=end,
                duration_ms=duration_ms,
                parent_span_id=span.get("parentSpanId"),
                labels=span.get("labels", {}),
            )
        )
    return spans


def analyze_frequency(spans: list[SpanInfo]) -> dict[str, int]:
    """Count occurrences of each span name."""
    freq = defaultdict(int)
    for span in spans:
        freq[span.name] += 1
    return dict(sorted(freq.items(), key=lambda x: -x[1]))


def analyze_duration_stats(spans: list[SpanInfo]) -> dict[str, dict]:
    """Calculate duration statistics by span name."""
    durations = defaultdict(list)
    for span in spans:
        durations[span.name].append(span.duration_ms)

    stats = {}
    for name, durs in durations.items():
        stats[name] = {
            "count": len(durs),
            "total_ms": sum(durs),
            "avg_ms": sum(durs) / len(durs),
            "min_ms": min(durs),
            "max_ms": max(durs),
        }
    return stats


def find_slowest_spans(spans: list[SpanInfo], top_n: int = 20) -> list[SpanInfo]:
    """Find the N slowest individual spans."""
    return sorted(spans, key=lambda x: -x.duration_ms)[:top_n]


def find_cumulative_time_leaders(stats: dict[str, dict], top_n: int = 20) -> list:
    """Find operations consuming the most cumulative time."""
    items = [(name, s["total_ms"], s["count"]) for name, s in stats.items()]
    return sorted(items, key=lambda x: -x[1])[:top_n]


def build_call_tree(spans: list[SpanInfo]) -> dict:
    """Build parent-child call tree."""
    span_map = {s.span_id: s for s in spans}
    children = defaultdict(list)

    for span in spans:
        if span.parent_span_id:
            children[span.parent_span_id].append(span.span_id)

    # Find root spans
    roots = [
        s for s in spans if not s.parent_span_id or s.parent_span_id not in span_map
    ]

    return {"span_map": span_map, "children": children, "roots": roots}


def detect_n_plus_one_patterns(stats: dict[str, dict], threshold: int = 10) -> list:
    """Detect potential N+1 query patterns (operations repeated many times)."""
    patterns = []
    for name, s in stats.items():
        if s["count"] >= threshold:
            patterns.append(
                {
                    "name": name,
                    "count": s["count"],
                    "total_ms": s["total_ms"],
                    "avg_ms": s["avg_ms"],
                    "potential_savings_ms": s["total_ms"] - s["avg_ms"],
                }
            )
    return sorted(patterns, key=lambda x: -x["total_ms"])


def analyze_phases(spans: list[SpanInfo]) -> dict:
    """Analyze major phases of the request."""
    phases = {}
    phase_names = [
        "ListDetailView_get_object",
        "ListDetailView_get_context_data",
        "list_fighters",
        "list_archived_fighters",
    ]

    for span in spans:
        if span.name in phase_names:
            if span.name not in phases:
                phases[span.name] = {"duration_ms": span.duration_ms, "count": 1}
            else:
                phases[span.name]["duration_ms"] += span.duration_ms
                phases[span.name]["count"] += 1

    return phases


def find_operations_by_prefix(stats: dict[str, dict], prefix: str) -> dict[str, dict]:
    """Group operations by prefix."""
    return {name: s for name, s in stats.items() if name.startswith(prefix)}


def calculate_critical_path(spans: list[SpanInfo]) -> list[SpanInfo]:
    """
    Find the critical path - the longest sequential chain of operations.
    This is simplified: we trace from root to deepest leaf.
    """
    if not spans:
        return []

    # Find root span (typically the HTTP request)
    root = min(spans, key=lambda x: x.start_time)

    # Build children map
    children = defaultdict(list)
    span_map = {s.span_id: s for s in spans}

    for span in spans:
        if span.parent_span_id and span.parent_span_id in span_map:
            children[span.parent_span_id].append(span)

    # Find path with maximum total duration
    def find_longest_path(span_id: str) -> list[SpanInfo]:
        span = span_map[span_id]
        child_spans = children[span_id]

        if not child_spans:
            return [span]

        # Find child with longest path
        best_path = []
        for child in child_spans:
            path = find_longest_path(child.span_id)
            if sum(s.duration_ms for s in path) > sum(s.duration_ms for s in best_path):
                best_path = path

        return [span] + best_path

    return find_longest_path(root.span_id)


def print_report(spans: list[SpanInfo]):
    """Print comprehensive analysis report."""
    print("=" * 80)
    print("TRACE PERFORMANCE ANALYSIS REPORT")
    print("=" * 80)

    # Overall stats
    if spans:
        total_request_time = max(s.end_time for s in spans) - min(
            s.start_time for s in spans
        )
        print("\n## Overall Statistics")
        print(f"Total spans: {len(spans)}")
        print(f"Total request time: {total_request_time.total_seconds() * 1000:.2f}ms")

    # Frequency analysis
    print("\n## Operation Frequency (Top 30)")
    print("-" * 60)
    freq = analyze_frequency(spans)
    for i, (name, count) in enumerate(list(freq.items())[:30]):
        print(f"{i + 1:3}. {name}: {count}")

    # Duration stats
    stats = analyze_duration_stats(spans)

    # Cumulative time leaders
    print("\n## Cumulative Time by Operation (Top 30)")
    print("-" * 60)
    leaders = find_cumulative_time_leaders(stats, 30)
    for i, (name, total_ms, count) in enumerate(leaders):
        print(
            f"{i + 1:3}. {name}: {total_ms:.2f}ms total ({count} calls, {total_ms / count:.2f}ms avg)"
        )

    # Slowest individual spans
    print("\n## Slowest Individual Spans (Top 20)")
    print("-" * 60)
    slowest = find_slowest_spans(spans, 20)
    for i, span in enumerate(slowest):
        print(f"{i + 1:3}. {span.name}: {span.duration_ms:.2f}ms")

    # N+1 pattern detection
    print("\n## Potential N+1 Patterns (>= 10 calls)")
    print("-" * 60)
    patterns = detect_n_plus_one_patterns(stats, 10)
    for p in patterns[:20]:
        print(f"  {p['name']}: {p['count']} calls, {p['total_ms']:.2f}ms total")
        if p["count"] > 1:
            print(f"     -> If batched: could save ~{p['potential_savings_ms']:.2f}ms")

    # Operations by category
    print("\n## Time by Operation Category")
    print("-" * 60)

    categories = {
        "listfighter_": "ListFighter operations",
        "listfighterequipmentassignment_": "Equipment assignment operations",
        "list_": "List-level operations",
        "ListDetailView_": "View operations",
    }

    for prefix, label in categories.items():
        ops = find_operations_by_prefix(stats, prefix)
        if ops:
            total = sum(s["total_ms"] for s in ops.values())
            count = sum(s["count"] for s in ops.values())
            print(f"  {label}: {total:.2f}ms total ({count} operations)")

    # Phases analysis
    print("\n## Major Request Phases")
    print("-" * 60)
    phases = analyze_phases(spans)
    for name, data in phases.items():
        print(f"  {name}: {data['duration_ms']:.2f}ms")


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_trace.py <trace_file.json>")
        sys.exit(1)

    filepath = sys.argv[1]
    trace_data = load_trace(filepath)
    spans = process_spans(trace_data)

    print_report(spans)


if __name__ == "__main__":
    main()
