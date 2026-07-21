#!/usr/bin/env python3
"""Monotonic ratchet on hand-written Bootstrap markup.

The cotton migration replaces raw class strings with components. Nothing stops
someone re-introducing `class="btn btn-primary"` in a new template afterwards,
and by the time anyone notices there are forty of them again. This script pins
a per-pattern ceiling that may only ever go DOWN.

    scripts/check_raw_markup.py            # enforce (CI + pre-commit)
    scripts/check_raw_markup.py --update   # re-baseline after a migration batch
    scripts/check_raw_markup.py --list btn # show the remaining call sites

Exit 1 when any count EXCEEDS its baseline, or when a baseline is stale (count
dropped and was not re-baselined) -- the second case keeps the ceiling tight
instead of letting slack accumulate.
"""

import argparse
import json
import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
BASELINE = ROOT / "scripts" / "raw_markup_baseline.json"

# Files that are ALLOWED to contain raw markup, with the reason.
EXCLUDE = (
    # Component internals: this is where the class strings are supposed to live.
    "gyrinx/templates/cotton/",
    # The living design-system showcase: its raw class strings ARE the
    # documentation, and the page renders a table naming them.
    "gyrinx/core/templates/core/debug/design_system.html",
    # Rendered by handler500 in a degraded process; a component-resolution
    # failure here would 500 the 500 page.
    "gyrinx/templates/errors/",
    "gyrinx/templates/404.html",
    "gyrinx/templates/500.html",
    # Golden snapshots are RENDERED OUTPUT. They contain the raw markup the
    # components emit, by definition, and counting them would make the ratchet
    # move every time a golden is recaptured.
    "gyrinx/core/tests/goldens/",
    # Django admin vocabulary (form-row/submit-row/default), not Bootstrap.
    "gyrinx/templates/admin/",
    "gyrinx/core/templates/admin/",
    "gyrinx/content/templates/content/",
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


def templates():
    for path in sorted((ROOT / "gyrinx").rglob("*.html")):
        rel = path.relative_to(ROOT).as_posix()
        if not any(rel.startswith(x) or rel == x.rstrip("/") for x in EXCLUDE):
            yield rel, path


def scan():
    counts = {k: 0 for k in PATTERNS}
    sites = {k: [] for k in PATTERNS}
    compiled = {k: re.compile(v) for k, v in PATTERNS.items()}
    for rel, path in templates():
        text = path.read_text(encoding="utf-8", errors="replace")
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
