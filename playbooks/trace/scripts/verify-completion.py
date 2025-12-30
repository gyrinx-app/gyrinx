#!/usr/bin/env python3
"""
Playbook Completion Verification Script

Validates that all required analysis outputs exist and meet quality thresholds.

Usage:
    python verify-completion.py [--stage N] [--verbose]

Options:
    --stage N    Check specific stage only (0-4)
    --verbose    Show detailed output
"""

import argparse
import sys
from pathlib import Path

# Minimum file size to be considered non-trivial
MIN_FILE_SIZE = 500  # bytes


def check_file(path: Path, min_size: int = MIN_FILE_SIZE) -> tuple[bool, str]:
    """Check if file exists and meets size threshold."""
    if not path.exists():
        return False, f"MISSING: {path}"
    size = path.stat().st_size
    if size < min_size:
        return False, f"TOO SMALL ({size} bytes): {path}"
    return True, f"OK ({size} bytes): {path}"


def check_directory(path: Path) -> tuple[bool, str]:
    """Check if directory exists."""
    if not path.exists():
        return False, f"MISSING DIR: {path}"
    if not path.is_dir():
        return False, f"NOT A DIR: {path}"
    return True, f"OK: {path}"


def verify_stage_0(analysis_dir: Path, verbose: bool) -> list[tuple[bool, str]]:
    """Verify Stage 0 outputs."""
    results = []

    required = [
        analysis_dir / "scope.md",
        analysis_dir / "trace-summary.md",
        analysis_dir / "operation-index.md",
    ]

    for f in required:
        ok, msg = check_file(f)
        results.append((ok, msg))
        if verbose or not ok:
            print(f"  Stage 0: {msg}")

    return results


def verify_stage_1(analysis_dir: Path, verbose: bool) -> list[tuple[bool, str]]:
    """Verify Stage 1 outputs."""
    results = []
    groups_dir = analysis_dir / "groups"

    ok, msg = check_directory(groups_dir)
    results.append((ok, msg))

    if not ok:
        print(f"  Stage 1: {msg}")
        return results

    # Check each group has required files
    for group_dir in groups_dir.iterdir():
        if group_dir.is_dir():
            for filename in ["profile.md", "bottlenecks.md"]:
                ok, msg = check_file(group_dir / filename)
                results.append((ok, msg))
                if verbose or not ok:
                    print(f"  Stage 1: {msg}")

    return results


def verify_stage_2(analysis_dir: Path, verbose: bool) -> list[tuple[bool, str]]:
    """Verify Stage 2 outputs."""
    results = []
    agg_dir = analysis_dir / "aggregation"

    ok, msg = check_directory(agg_dir)
    results.append((ok, msg))

    if not ok:
        print(f"  Stage 2: {msg}")
        return results

    required = [
        "issue-clusters.md",
        "time-attribution.md",
        "n-plus-one-summary.md",
        "prefetch-gaps.md",
        "critical-path.md",
    ]

    for filename in required:
        ok, msg = check_file(agg_dir / filename)
        results.append((ok, msg))
        if verbose or not ok:
            print(f"  Stage 2: {msg}")

    return results


def verify_stage_3(analysis_dir: Path, verbose: bool) -> list[tuple[bool, str]]:
    """Verify Stage 3 outputs."""
    results = []
    synth_dir = analysis_dir / "synthesis"
    opp_dir = analysis_dir / "opportunities"

    for d in [synth_dir, opp_dir]:
        ok, msg = check_directory(d)
        results.append((ok, msg))
        if not ok:
            print(f"  Stage 3: {msg}")

    required_synth = [
        "impact-estimates.md",
        "priority-matrix.md",
        "roadmap.md",
        "code-locations.md",
    ]

    for filename in required_synth:
        ok, msg = check_file(synth_dir / filename)
        results.append((ok, msg))
        if verbose or not ok:
            print(f"  Stage 3: {msg}")

    # Check at least one opportunity exists
    if opp_dir.exists():
        opp_files = list(opp_dir.glob("*.md"))
        if not opp_files:
            results.append((False, "No opportunity files in opportunities/"))
            print("  Stage 3: No opportunity files found")

    return results


def verify_stage_4(analysis_dir: Path, verbose: bool) -> list[tuple[bool, str]]:
    """Verify Stage 4 outputs."""
    results = []
    rec_dir = analysis_dir / "recommendations"

    required = [
        analysis_dir / "SUMMARY.md",
        analysis_dir / "baseline.md",
        analysis_dir / "learnings.md",
        analysis_dir / "verification-checklist.md",
    ]

    for f in required:
        ok, msg = check_file(f)
        results.append((ok, msg))
        if verbose or not ok:
            print(f"  Stage 4: {msg}")

    # Check recommendations directory
    ok, msg = check_directory(rec_dir)
    results.append((ok, msg))

    if rec_dir.exists():
        rec_files = list(rec_dir.glob("*.md"))
        if not rec_files:
            results.append((False, "No recommendation files"))
            print("  Stage 4: No recommendation files found")

    return results


def main():
    parser = argparse.ArgumentParser(description="Verify playbook completion")
    parser.add_argument(
        "--stage", type=int, choices=[0, 1, 2, 3, 4], help="Check specific stage"
    )
    parser.add_argument("--verbose", "-v", action="store_true", help="Verbose output")
    parser.add_argument("--analysis-dir", default="analysis", help="Analysis directory")
    args = parser.parse_args()

    analysis_dir = Path(args.analysis_dir)

    if not analysis_dir.exists():
        print(f"ERROR: Analysis directory not found: {analysis_dir}")
        sys.exit(1)

    verifiers = {
        0: verify_stage_0,
        1: verify_stage_1,
        2: verify_stage_2,
        3: verify_stage_3,
        4: verify_stage_4,
    }

    all_results = []
    stages_to_check = [args.stage] if args.stage is not None else range(5)

    for stage in stages_to_check:
        print(f"\nStage {stage}:")
        results = verifiers[stage](analysis_dir, args.verbose)
        all_results.extend(results)

    # Summary
    passed = sum(1 for ok, _ in all_results if ok)
    total = len(all_results)
    failed = total - passed

    print(f"\n{'=' * 50}")
    print(f"Results: {passed}/{total} checks passed")

    if failed > 0:
        print(f"INCOMPLETE: {failed} issues found")
        sys.exit(1)
    else:
        print("COMPLETE: All checks passed")
        sys.exit(0)


if __name__ == "__main__":
    main()
