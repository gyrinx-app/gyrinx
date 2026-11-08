#!/usr/bin/env python3
"""Enforce per-pattern limits on hand-written Bootstrap markup.

    scripts/check_raw_markup.py            # enforce limits
    scripts/check_raw_markup.py --update   # update the baseline
    scripts/check_raw_markup.py --list btn # list remaining calls

Exit 1 when a count exceeds its baseline or falls below an outdated baseline.
Update the baseline after removing raw markup to retain the stricter limit.
"""

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "raw_markup_baseline.json"

# Raw markup exemptions and their reasons.
EXCLUDE = (
    # Component internals: this is where the class strings are supposed to live.
    "gyrinx/templates/cotton/",
    # The design-system page documents the raw classes it renders.
    "n23/core/templates/core/debug/design_system.html",
    # Error pages must render even when component resolution fails.
    "gyrinx/templates/errors/",
    "gyrinx/templates/404.html",
    "gyrinx/templates/500.html",
    # Scratch templates written and deleted by the component test harnesses while
    # they run (uuid-named, so no prefix rule catches them). They deliberately
    # contain the shapes this counts, and they vanish mid-scan under pytest-xdist.
    "n23/core/templates/cotton_test/",
    "gyrinx/templates/_cotton_test_host/",
    # Django admin vocabulary (form-row/submit-row/default), not Bootstrap.
    "gyrinx/templates/admin/",
    "n23/core/templates/admin/",
    "n23/content/templates/content/",
    "gyrinx/maintenance/templates/admin/",
    "gyrinx/analytics/templates/analytics/admin/",
)

PATTERNS = {
    "btn": r'class="[^"]*\bbtn btn-',
    "badge": r'class="[^"]*\bbadge[^"]*\btext-bg-',
    "alert": r'class="[^"]*\balert alert-',
    "border-rounded": r'class="[^"]*\bborder rounded',
    "invalid-feedback": r"invalid-feedback",
    "include-form_field": r"includes/form_field\.html",
    "include-back": r"includes/back\.html",
    "include-cancel": r"includes/cancel\.html",
}


# Scan the platform and N23 templates that use Bootstrap.
TEMPLATE_ROOTS = ("gyrinx", "n23")


def templates():
    paths = []
    for root in TEMPLATE_ROOTS:
        paths.extend((ROOT / root).rglob("*.html"))
    for path in sorted(paths):
        rel = path.relative_to(ROOT).as_posix()
        if not any(rel.startswith(x) or rel == x.rstrip("/") for x in EXCLUDE):
            yield rel, path


def scan():
    counts = {k: 0 for k in PATTERNS}
    sites = {k: [] for k in PATTERNS}
    compiled = {k: re.compile(v) for k, v in PATTERNS.items()}
    for rel, path in templates():
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except FileNotFoundError:
            # A concurrent test deleted its scratch template between the glob and
            # this read. The exclusions above cover the known harnesses; this keeps
            # the walk from crashing on any future one.
            continue
        for i, line in enumerate(text.splitlines(), 1):
            for key, rx in compiled.items():
                n = len(rx.findall(line))
                if n:
                    counts[key] += n
                    sites[key].append(f"{rel}:{i}")
    return counts, sites


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--update", action="store_true")
    ap.add_argument("--list", metavar="PATTERN")
    args = ap.parse_args()

    counts, sites = scan()

    if args.list:
        for s in sites.get(args.list, []):
            print(s)
        return 0

    if args.update or not BASELINE.exists():
        BASELINE.write_text(json.dumps(counts, indent=2, sort_keys=True) + "\n")
        print(f"baseline written: {BASELINE.relative_to(ROOT)}")
        for k in sorted(counts):
            print(f"  {k:<20} {counts[k]}")
        return 0

    base = json.loads(BASELINE.read_text())
    bad = []
    slack = []
    for key in sorted(PATTERNS):
        now, was = counts[key], base.get(key, 0)
        if now > was:
            bad.append(
                f"  {key:<20} {was} -> {now}  (+{now - was})\n"
                f"      scripts/check_raw_markup.py --list {key}"
            )
        elif now < was:
            slack.append(f"  {key:<20} {was} -> {now}  (-{was - now})")

    if bad:
        print("RAW MARKUP RATCHET: new hand-written Bootstrap markup\n")
        print("\n".join(bad))
        print("\nUse the cotton component, or add a justified entry to EXCLUDE.")
        return 1

    if slack:
        print("RATCHET LOOSE: counts dropped but the baseline was not updated.\n")
        print("\n".join(slack))
        print(
            "\nRun: scripts/check_raw_markup.py --update && git add scripts/raw_markup_baseline.json"
        )
        return 1

    print(f"raw-markup ratchet OK ({sum(counts.values())} sites at baseline)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
