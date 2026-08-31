#!/usr/bin/env python3
"""Warn about off-style microcopy. Never blocks.

The full rules live in .agents/skills/microcopy/SKILL.md; this script catches
the greppable subset — banned words, "successfully", exclamation marks in
copy, Title Case button labels — and prints warnings so the writer can judge
each one. Warn-only by design: copy calls need human judgement, and a matched
word can be legitimate in context (a rulebook name, a test asserting the old
string).

    scripts/check_microcopy.py FILE [FILE...]   # scan named files
    scripts/check_microcopy.py --diff           # files changed vs main + untracked
    scripts/check_microcopy.py --hook           # PostToolUse hook: JSON on stdin

Exit codes: 0 always in CLI modes. In --hook mode, exit 2 when there are
findings so the agent that made the edit sees them as feedback (the edit
itself is not undone or blocked). Hook mode scans only the text the edit
introduced, so pre-existing warnings in a legacy file do not repeat on every
edit — existing copy is fix-on-touch, and sweeping it is the skill's call,
not this script's.

The word list is maintained by hand against the SKILL.md ban table; when a
ban is added there, add it here too. This file must stay parseable by old
Pythons (no 3.14-only syntax): the PostToolUse hook runs it with whatever
`python3` is on PATH, which outside the venv can be the system 3.9.
"""

import io
import json
import pathlib
import re
import subprocess  # nosec B404 — runs only fixed git commands to list changed files
import sys
import tokenize

ROOT = pathlib.Path(__file__).resolve().parent.parent

# (regex, hint). Case-insensitive. Applied to template lines and, in .py
# files, to string literals (docstrings included) via tokenize.
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
    (r"\bunlock(s|ed|ing)?\b", "marketing-speak — say what becomes available"),
    (r"\bdelve\b", "AI tell — use a plain verb"),
    (r"\bget started\b", "onboarding cliché — name the first action instead"),
    (r"\bready to\b", "hype heading — name the thing shown instead"),
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
# `font-bold!`); class attribute values are blanked before this runs, which
# also covers single-word utilities (`hidden!`).
BANG = re.compile(r"(?<![-\w])[A-Za-z]{2,}!(?=[\"'<\s]|$)")

# class="..." values carry no copy and are where Tailwind's `!` suffixes and
# utility words live — blank them before scanning a template line.
CLASS_ATTR = re.compile(r"""\bclass=("[^"]*"|'[^']*')""")

# Title Case after a leading verb in template text: ">Add Fighter<". Second
# capitalised word must not be a proper noun or an initialism.
TITLE_CASE = re.compile(
    r">\s*(Add|New|Create|Edit|Delete|Remove|Save|Copy|Update|Confirm|Change|"
    r"Select|Send|View|Manage|Assign|Archive|Upload|Record) ([A-Z][a-z]+)"
)
PROPER_NOUNS = {"Necromunda", "Gyrinx", "Patreon", "Discord", "Google", "Bootstrap"}

# Directory names whose subtrees hold no product copy, matched against path
# segments (never substrings). scripts/ and the agent trees quote the banned
# words on purpose.
EXCLUDE_DIRS = {
    "migrations",
    "tests",
    "node_modules",
    ".venv",
    "rule-reference",
    "static",
    "scripts",
    ".claude",
    ".agents",
}


def repo_relative_parts(path):
    """Path segments relative to the repo tree, wherever the file lives.

    A file under another checkout or worktree still gets sensible segments:
    everything up to and including `worktrees/<name>` is dropped, so the
    n26-only rules and the directory exclusions see `n26/...` either way.
    """
    resolved = path.resolve()
    try:
        return resolved.relative_to(ROOT).parts
    except ValueError:
        parts = resolved.parts
        if "worktrees" in parts:
            idx = parts.index("worktrees")
            return parts[idx + 2 :]
        return parts


def scan_text(text, label, parts, is_template):
    rules = list(WORD_RULES)
    if parts and parts[0] == "n26":
        rules += N26_WORD_RULES
    compiled = [(re.compile(rx, re.IGNORECASE), hint) for rx, hint in rules]

    findings = []
    for lineno, line in enumerate(text.splitlines(), start=1):
        scannable = CLASS_ATTR.sub('class=""', line) if is_template else line
        for rx, hint in compiled:
            m = rx.search(scannable)
            if m:
                word = m.group(0)
                findings.append(f"{label}:{lineno}: “{word}” — {hint}")
        if BANG.search(scannable) and "<!--" not in line:
            findings.append(
                f"{label}:{lineno}: exclamation mark in copy — end with a full stop"
            )
        if is_template:
            m = TITLE_CASE.search(line)
            if m and m.group(2) not in PROPER_NOUNS:
                verb, noun = m.group(1), m.group(2)
                findings.append(
                    f"{label}:{lineno}: “{verb} {noun}” — "
                    f"sentence case: “{verb} {noun.lower()}”"
                )
    return findings


def python_strings(text):
    """(start_line, string_source) for every string literal, docstrings and
    f-string text included. Comments and code never reach the word rules this
    way. f-strings tokenize as FSTRING_MIDDLE chunks on Python 3.12+; on
    older Pythons they arrive as plain STRING tokens."""
    string_types = {tokenize.STRING, getattr(tokenize, "FSTRING_MIDDLE", -1)}
    tokenize_errors = (tokenize.TokenError, IndentationError, SyntaxError)
    out = []
    try:
        for tok in tokenize.generate_tokens(io.StringIO(text).readline):
            if tok.type in string_types:
                out.append((tok.start[0], tok.string))
    except tokenize_errors:
        return None
    return out


def scan_file(path):
    parts = repo_relative_parts(path)
    if any(part in EXCLUDE_DIRS for part in parts):
        return []
    if any(part.startswith("test_") for part in parts):
        return []
    if path.suffix not in (".html", ".py", ".txt"):
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    except UnicodeDecodeError:
        return []

    label = "/".join(parts)
    if path.suffix in (".html", ".txt"):
        return scan_text(text, label, parts, is_template=True)

    strings = python_strings(text)
    if strings is None:
        return scan_text(text, label, parts, is_template=False)
    findings = []
    for start_line, source in strings:
        for f in scan_text(source, label, parts, is_template=False):
            _, lineno, rest = f.split(":", 2)
            real_line = start_line + int(lineno) - 1
            findings.append(f"{label}:{real_line}:{rest}")
    return findings


def hook_findings(payload):
    """Scan only the text this edit introduced, so warnings are about the
    change, never the file's backlog."""
    tool_input = payload.get("tool_input") or {}
    file_path = tool_input.get("file_path")
    if not file_path:
        return []
    path = pathlib.Path(file_path)
    if path.suffix not in (".html", ".py", ".txt"):
        return []
    parts = repo_relative_parts(path)
    if any(part in EXCLUDE_DIRS for part in parts):
        return []
    if any(part.startswith("test_") for part in parts):
        return []

    texts = []
    if "content" in tool_input:
        texts.append(tool_input["content"])
    if "new_string" in tool_input:
        texts.append(tool_input["new_string"])
    for edit in tool_input.get("edits") or []:
        if isinstance(edit, dict) and edit.get("new_string"):
            texts.append(edit["new_string"])

    label = "/".join(parts) + " (this edit)"
    is_template = path.suffix in (".html", ".txt")
    findings = []
    for text in texts:
        for f in scan_text(text, label, parts, is_template):
            findings.append(f)
    return findings


def changed_files():
    names = []
    for args in (
        ["git", "diff", "--name-only", "main...HEAD"],
        ["git", "diff", "--name-only", "HEAD"],
        ["git", "ls-files", "--others", "--exclude-standard"],
    ):
        result = subprocess.run(  # nosec B607 — fixed argv; git resolved from PATH like every repo tool
            args, capture_output=True, text=True, cwd=str(ROOT), check=False
        )
        names.extend(result.stdout.splitlines())
    seen = []
    for name in names:
        if name and name not in seen:
            seen.append(name)
    return [ROOT / name for name in seen]


def main():
    argv = sys.argv[1:]
    hook_mode = "--hook" in argv

    if hook_mode:
        try:
            payload = json.load(sys.stdin)
        except ValueError:
            return 0
        except OSError:
            return 0
        findings = hook_findings(payload)
    else:
        if "--diff" in argv:
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
        print("rules: .agents/skills/microcopy/SKILL.md):", file=out)
        for f in findings:
            print("  " + f, file=out)
        if hook_mode:
            return 2
    return 0


if __name__ == "__main__":
    sys.exit(main())
