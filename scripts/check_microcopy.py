#!/usr/bin/env python3
"""Warn about off-style microcopy. Never blocks.

The full rules live in .claude/skills/microcopy/SKILL.md; this script catches
the greppable subset — banned words, "successfully", exclamation marks in
strings, Title Case button labels — and prints warnings so the writer can
judge each one. Warn-only by design: copy calls need human judgement, and a
matched word can be legitimate in context (a rulebook name, a test asserting
the old string).

    scripts/check_microcopy.py FILE [FILE...]   # scan named files
    scripts/check_microcopy.py --diff           # scan files changed vs main
    scripts/check_microcopy.py --hook           # PostToolUse hook: JSON on stdin

Exit codes: 0 always in CLI modes. In --hook mode, exit 2 when there are
findings so the agent that made the edit sees them as feedback (the edit
itself is not undone or blocked).
"""

import json
import pathlib
import re
import subprocess
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent

# (regex, hint). Case-insensitive. Applied to template lines, and to .py lines
# that contain a string literal.
WORD_RULES = [
    (r"\bsuccessfully\b", 'state the fact instead: "Battle recorded."'),
    (r"\bnought\b", 'quaint — write "0"'),
    (
        r"\bshel(f|ves)\b",
        "commerce metaphor — say section, category, or the relational name",
    ),
    (
        r"\bshops?\b",
        "commerce metaphor — say section, category, or the relational name",
    ),
    (r"\btill\b", 'banned — name the payment point; never "till" for "until"'),
    (r"\bsow(s|n|ing)?\b", 'say "create"'),
    (r"\bpressed\b", '"clicked", not "pressed"'),
    (r"\bobligations?\b", "banned — name the mechanism that tracks what is owed"),
    (r"\bdebts?\b", "banned — name the mechanism that tracks what is owed"),
    (r"\bsells\b", "a collection contains/includes things; it is not a merchant"),
    (
        r"\banswers?\b",
        'speech metaphor — use "pick" or "choose" (they differ; see the skill)',
    ),
    (r"\bSKU\b", 'say "assignable"'),
    (r"\bseamless(ly)?\b", "marketing-speak — describe, never sell"),
    (r"\bpowerful\b", "marketing-speak — describe, never sell"),
    (r"\brobust\b", "marketing-speak — describe, never sell"),
    (r"\bleverage\b", 'say "use"'),
    (r"\bdelve\b", "AI tell — use a plain verb"),
    (r"\bget started\b", "onboarding cliché — name the first action instead"),
    (r"\bwe are sorry\b|\bwe're sorry\b", "no apologies — state the rule or the fact"),
    (r"\boops\b", "no drama — state what happened"),
    (r"\bplease\b", 'drop "please" — instructions are imperative'),
]

# "cost" is price-vs-rating confusion; the ban is n26-wide (test_money_words
# enforces models — this catches copy).
N26_WORD_RULES = [
    (r"\bcosts?\b", "banned in n26 — price (asked now) or rating (added to worth)"),
]

# An exclamation mark ending a sentence in copy. Must not match `!=`,
# `!important`, `<!--`, or Tailwind important suffixes (`py-0!`,
# `bg-ink-200!`, `font-bold!` — a digit or a hyphenated utility before the
# mark).
BANG = re.compile(r"(?<![-\w])[A-Za-z]{2,}!(?=[\"'<\s]|$)")

# Title Case after a leading verb in template text: ">Add Fighter<". Second
# capitalised word must not be a proper noun or an initialism.
TITLE_CASE = re.compile(
    r">\s*(Add|New|Create|Edit|Delete|Remove|Save|Copy|Update|Confirm|Change|"
    r"Select|Send|View|Manage|Assign|Archive|Upload|Record) ([A-Z][a-z]+)"
)
PROPER_NOUNS = {"Necromunda", "Gyrinx", "Patreon", "Discord", "Google", "Bootstrap"}

EXCLUDE_PARTS = (
    "/migrations/",
    "/tests/",
    "/test_",
    "/node_modules/",
    "/.venv/",
    "/rule-reference/",
    "/static/",
    # This script and its docs quote the banned words on purpose.
    "/scripts/",
    "/.claude/",
)

PY_STRING_LINE = re.compile(r"""["']""")


def scan_file(path: pathlib.Path) -> list[str]:
    rel = path.resolve()
    try:
        rel = rel.relative_to(ROOT)
    except ValueError:
        pass
    rel_str = "/" + str(rel)
    if any(part in rel_str for part in EXCLUDE_PARTS):
        return []
    if path.suffix not in (".html", ".py", ".txt"):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError, UnicodeDecodeError:
        return []

    is_template = path.suffix in (".html", ".txt")
    rules = list(WORD_RULES)
    if str(rel).startswith("n26/"):
        rules += N26_WORD_RULES
    compiled = [(re.compile(rx, re.IGNORECASE), hint) for rx, hint in rules]

    findings = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        if not is_template and not PY_STRING_LINE.search(line):
            continue
        for rx, hint in compiled:
            m = rx.search(line)
            if m:
                findings.append(f"{rel}:{lineno}: “{m.group(0)}” — {hint}")
        if BANG.search(line) and "<!--" not in line:
            findings.append(
                f"{rel}:{lineno}: exclamation mark in copy — end with a full stop"
            )
        if is_template:
            m = TITLE_CASE.search(line)
            if m and m.group(2) not in PROPER_NOUNS:
                findings.append(
                    f"{rel}:{lineno}: “{m.group(1)} {m.group(2)}” — sentence case: “{m.group(1)} {m.group(2).lower()}”"
                )
    return findings


def changed_files() -> list[pathlib.Path]:
    out = subprocess.run(
        ["git", "diff", "--name-only", "main...HEAD"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    ).stdout
    out += subprocess.run(
        ["git", "diff", "--name-only", "HEAD"],
        capture_output=True,
        text=True,
        cwd=ROOT,
        check=False,
    ).stdout
    return [ROOT / line for line in dict.fromkeys(out.splitlines()) if line]


def main() -> int:
    argv = sys.argv[1:]
    hook_mode = "--hook" in argv

    if hook_mode:
        try:
            payload = json.load(sys.stdin)
        except json.JSONDecodeError, OSError:
            return 0
        file_path = (payload.get("tool_input") or {}).get("file_path")
        paths = [pathlib.Path(file_path)] if file_path else []
    elif "--diff" in argv:
        paths = changed_files()
    else:
        paths = [pathlib.Path(a) for a in argv]
        if not paths:
            print(__doc__)
            return 0

    findings = []
    for path in paths:
        if path.is_file():
            findings += scan_file(path)

    if findings:
        out = sys.stderr if hook_mode else sys.stdout
        print("Microcopy warnings (advisory — judge each in context;", file=out)
        print("rules: .claude/skills/microcopy/SKILL.md):", file=out)
        for f in findings:
            print(f"  {f}", file=out)
        if hook_mode:
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
