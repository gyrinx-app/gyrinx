"""Keep the per-template Alpine directive count from increasing.

Run with --update after a migration to lower the checked-in ceilings.
The baseline is an inventory of first-party templates, not vendored kit code.
"""

import argparse
import json
import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE = ROOT / "n26/frontend/tooling/alpine-baseline.json"
COMMENTS = re.compile(r"{% comment\b.*?{% endcomment %}|{#.*?#}|<!--.*?-->", re.S)
DIRECTIVE = re.compile(r"\s(?:x-[\w.:-]+|@[\w.:-]+)\b(?=\s|=|/?>)")


def inventory():
    counts = {}
    for path in sorted((ROOT / "n26").rglob("*.html")):
        count = len(DIRECTIVE.findall(COMMENTS.sub("", path.read_text())))
        if count:
            counts[str(path.relative_to(ROOT))] = count
    return counts


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--update", action="store_true")
    args = parser.parse_args()
    current = inventory()
    baseline = json.loads(BASELINE.read_text())
    increases = {
        path: count for path, count in current.items() if count > baseline.get(path, 0)
    }
    if increases:
        for path, count in increases.items():
            print(
                f"{path}: {count} Alpine directives (ceiling {baseline.get(path, 0)})"
            )
        raise SystemExit(
            "Use a React island for new N26 interactions. See docs/developing-gyrinx/react.md."
        )
    if args.update:
        BASELINE.write_text(json.dumps(current, indent=2) + "\n")
    print(
        f"N26 Alpine: {sum(current.values())} directives in {len(current)} templates; no increases."
    )


if __name__ == "__main__":
    main()
