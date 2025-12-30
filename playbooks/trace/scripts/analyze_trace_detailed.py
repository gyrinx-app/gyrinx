#!/usr/bin/env python3
"""
Detailed Trace Analysis - Call Tree and Deep Dive

Provides deeper analysis of specific slow operations and their call hierarchy.
"""

import json
import sys
from collections import defaultdict
from datetime import datetime


def parse_timestamp(ts: str) -> datetime:
    """Parse ISO timestamp from trace."""
    if "." in ts:
        base, frac = ts.replace("Z", "").split(".")
        frac = frac[:6].ljust(6, "0")
        ts = f"{base}.{frac}"
    else:
        ts = ts.replace("Z", "")
    return datetime.fromisoformat(ts)


def load_and_process(filepath: str) -> tuple[dict, dict, dict]:
    """Load trace and build lookup structures."""
    with open(filepath) as f:
        data = json.load(f)

    spans = {}
    children = defaultdict(list)
    roots = []

    for span in data.get("spans", []):
        start = parse_timestamp(span["startTime"])
        end = parse_timestamp(span["endTime"])
        duration_ms = (end - start).total_seconds() * 1000

        span_info = {
            "span_id": span["spanId"],
            "name": span["name"],
            "start_time": start,
            "end_time": end,
            "duration_ms": duration_ms,
            "parent_span_id": span.get("parentSpanId"),
            "labels": span.get("labels", {}),
        }
        spans[span["spanId"]] = span_info

        if span.get("parentSpanId"):
            children[span["parentSpanId"]].append(span["spanId"])
        else:
            roots.append(span["spanId"])

    # Find actual roots (spans whose parent isn't in our span set)
    all_span_ids = set(spans.keys())
    for span_id, span in spans.items():
        parent = span["parent_span_id"]
        if parent and parent not in all_span_ids:
            roots.append(span_id)

    return spans, children, roots


def print_call_tree(spans, children, span_id, indent=0, max_depth=10):
    """Print call tree recursively."""
    if indent > max_depth:
        return

    span = spans[span_id]
    prefix = "  " * indent
    print(f"{prefix}{span['name']}: {span['duration_ms']:.2f}ms")

    child_ids = children.get(span_id, [])
    # Sort children by start time
    child_ids = sorted(child_ids, key=lambda cid: spans[cid]["start_time"])

    for child_id in child_ids:
        print_call_tree(spans, children, child_id, indent + 1, max_depth)


def find_spans_by_name(spans, name):
    """Find all spans with a given name."""
    return [s for s in spans.values() if s["name"] == name]


def analyze_children_of_operation(spans, children, op_name):
    """Analyze what operations happen under a specific operation."""
    parent_spans = find_spans_by_name(spans, op_name)

    print(f"\n## Analysis of '{op_name}' ({len(parent_spans)} occurrences)")
    print("-" * 60)

    for i, parent in enumerate(parent_spans[:3]):  # First 3 for detail
        print(f"\n### Occurrence {i + 1}: {parent['duration_ms']:.2f}ms")

        # Get all descendant operations
        def get_descendants(span_id, depth=0):
            result = []
            for child_id in children.get(span_id, []):
                child = spans[child_id]
                result.append((child, depth))
                result.extend(get_descendants(child_id, depth + 1))
            return result

        descendants = get_descendants(parent["span_id"])

        if descendants:
            # Group by name
            by_name = defaultdict(list)
            for desc, depth in descendants:
                by_name[desc["name"]].append(desc["duration_ms"])

            print("Child operations breakdown:")
            for name, durations in sorted(by_name.items(), key=lambda x: -sum(x[1])):
                print(
                    f"  {name}: {sum(durations):.2f}ms total ({len(durations)} calls)"
                )
        else:
            print("  (no child operations traced)")


def analyze_time_gaps(spans, children, root_span_id):
    """Analyze gaps between child operations - time spent in parent but not in children."""
    root = spans[root_span_id]

    # Get direct children
    child_ids = children.get(root_span_id, [])
    if not child_ids:
        return

    child_spans = [spans[cid] for cid in child_ids]
    child_spans.sort(key=lambda x: x["start_time"])

    total_child_time = sum(c["duration_ms"] for c in child_spans)
    gap_time = root["duration_ms"] - total_child_time

    print(f"\n## Time Gap Analysis for '{root['name']}'")
    print(f"Total duration: {root['duration_ms']:.2f}ms")
    print(f"Time in children: {total_child_time:.2f}ms")
    print(
        f"Untraced time (gaps/overhead): {gap_time:.2f}ms ({gap_time / root['duration_ms'] * 100:.1f}%)"
    )


def analyze_sequential_vs_parallel(spans, children, parent_span_id):
    """Analyze if child operations run sequentially or in parallel."""
    child_ids = children.get(parent_span_id, [])
    if not child_ids:
        return

    parent = spans[parent_span_id]
    child_spans = [spans[cid] for cid in child_ids]

    # Check for overlaps
    child_spans.sort(key=lambda x: x["start_time"])

    overlaps = 0
    for i in range(len(child_spans) - 1):
        current_end = child_spans[i]["end_time"]
        next_start = child_spans[i + 1]["start_time"]
        if current_end > next_start:
            overlaps += 1

    print(f"\n## Sequential vs Parallel Analysis for '{parent['name']}'")
    print(f"Number of direct children: {len(child_spans)}")
    print(f"Overlapping pairs: {overlaps}")
    print(
        f"Pattern: {'Mostly parallel' if overlaps > len(child_spans) / 2 else 'Mostly sequential'}"
    )


def main():
    if len(sys.argv) < 2:
        print("Usage: python analyze_trace_detailed.py <trace_file.json>")
        sys.exit(1)

    filepath = sys.argv[1]
    spans, children, roots = load_and_process(filepath)

    print("=" * 80)
    print("DETAILED TRACE ANALYSIS")
    print("=" * 80)

    # Find the main request span
    request_spans = [s for s in spans.values() if s["name"].startswith("GET ")]
    if request_spans:
        main_span_id = request_spans[0]["span_id"]

        print("\n## Top-Level Call Tree (depth 3)")
        print("-" * 60)
        print_call_tree(spans, children, main_span_id, max_depth=3)

        analyze_time_gaps(spans, children, main_span_id)
        analyze_sequential_vs_parallel(spans, children, main_span_id)

    # Analyze the slowest operations
    analyze_children_of_operation(
        spans, children, "listfighter_house_additional_gearline_display"
    )
    analyze_children_of_operation(spans, children, "ListDetailView_get_object")
    analyze_children_of_operation(spans, children, "listfighter_statline")
    analyze_children_of_operation(
        spans, children, "listfighterequipmentassignment_equipment_cost_with_override"
    )

    # Time breakdown by major phase
    print("\n## Where Is Time Spent? (Rough Breakdown)")
    print("-" * 60)

    phases = {
        "View get_object": ["ListDetailView_get_object"],
        "View get_context_data": ["ListDetailView_get_context_data"],
        "House Additional Gear Display": [
            "listfighter_house_additional_gearline_display"
        ],
        "Fighter Statline": ["listfighter_statline"],
        "Equipment Cost Calculations": [
            "listfighterequipmentassignment_equipment_cost_with_override"
        ],
        "Archived Fighters": [
            "list_archived_fighters",
            "list_archived_fighters_cached",
        ],
        "Active Fighters": ["list_active_fighters", "list_fighters"],
    }

    total_traced = 0
    for phase_name, span_names in phases.items():
        phase_time = 0
        for span_name in span_names:
            matching = find_spans_by_name(spans, span_name)
            phase_time += sum(s["duration_ms"] for s in matching)
        if phase_time > 0:
            print(f"  {phase_name}: {phase_time:.2f}ms")
            total_traced += phase_time

    # Find root span duration
    if request_spans:
        root_duration = request_spans[0]["duration_ms"]
        print(f"\n  Total request time: {root_duration:.2f}ms")
        print(f"  Traced in major phases: {total_traced:.2f}ms")
        print(f"  Other/overhead: {root_duration - total_traced:.2f}ms")


if __name__ == "__main__":
    main()
