"""Keep the Alpine in each N26 template from increasing.

Each template has two ceilings in the baseline:

- direct: Alpine attributes written in the template itself.
- kit: Alpine that kit components (<c-ui.*>) put on the page. Each use of a
  kit tag is charged that component's weight: the Alpine in its template,
  including kit tags it nests, read from the installed django_cotton_ui
  package or the first-party override that replaces it.

The baseline also records each kit tag's weight. When a kit upgrade or an
override changes a weight, the check fails and names the change; review it,
then run with --update. --update also lowers the ceilings after a migration.
It still fails when a template has more direct Alpine or more kit tag uses.
An override is scanned as a template too, so Alpine added to one fails as
direct Alpine.

This script must not import Django: CI runs it without settings.
"""

import argparse
import importlib.util
import json
import re
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
BASELINE_PATH = "n26/frontend/tooling/alpine-baseline.json"
FORMAT = 2
SCAN_DIR = "n26"
KIT_PACKAGE = "django_cotton_ui"
KIT_PREFIX = "ui."
# Template roots searched before the kit's. Overrides live here only, inside
# SCAN_DIR, so their own Alpine also counts as direct. test_check_n26_alpine.py
# fails if Django's loader finds a kit tag anywhere else first.
OVERRIDE_ROOTS = ("n26/core/templates",)
# Page chrome that nearly every page uses. Charging it would fail the check for
# every new page. The number is a cap: a kit upgrade that adds Alpine past it
# fails the run.
UNCHARGED_TAGS = {"ui.breadcrumbs": 3, "ui.alert": 3, "ui.avatar": 2}
# The design-system gallery exists to show kit components. Its direct Alpine
# still counts.
UNCHARGED_PATHS = ("n26/designsystem/",)

COMMENTS = re.compile(r"{% comment\b.*?{% endcomment %}|{#[^\n]*?#}|<!--.*?-->", re.S)
TEMPLATE_SYNTAX = re.compile(r"{%.*?%}|{{.*?}}", re.S)
RAW_TEXT = re.compile(r"(<(script|style)\b[^>]*>)(.*?)(</\2\s*>)", re.S | re.I)
START_TAG = re.compile(r"<([a-zA-Z][\w.:-]*)((?:[^>\"']|\"[^\"]*\"|'[^']*')*)>", re.S)
ATTR = re.compile(r"([^\s\"'=<>/]+)(?:\s*=\s*(?:\"[^\"]*\"|'[^']*'|[^\s>]+))?")
BRANCH = re.compile(r"{%\s*(if|elif|else|endif)\b.*?%}", re.S)


def _blank(text):
    """Replace text with spaces, keeping newlines and offsets."""
    return re.sub(r"[^\n]", " ", text)


def is_alpine(attr, cotton):
    """Whether an attribute is Alpine syntax on the rendered page.

    On a <c-*> tag, :attr is a Cotton Python expression and ::attr renders as
    a literal :attr. On an HTML tag, :attr is Alpine's x-bind shorthand.
    x-* and @* are Alpine on both, since Cotton passes them through.
    """
    if attr.startswith(("x-", "@", "::")):
        return True
    return attr.startswith(":") and not cotton


def scan(text):
    """Return (Alpine attribute offsets, [(offset, component)], branch tags).

    Comments, template tags and script/style bodies are blanked first, so a
    directive glued to a template tag, such as x-cloak{% endif %}, still counts.
    Components are <c-*> names without the prefix, such as "ui.dropdown".
    Branch tags are (offset, "if" | "elif" | "else" | "endif").
    """
    text = COMMENTS.sub(lambda m: _blank(m.group(0)), text)
    branches = [(m.start(), m.group(1)) for m in BRANCH.finditer(text)]
    text = TEMPLATE_SYNTAX.sub(lambda m: _blank(m.group(0)), text)
    text = RAW_TEXT.sub(lambda m: m.group(1) + _blank(m.group(3)) + m.group(4), text)
    directives, components = [], []
    for tag in START_TAG.finditer(text):
        name = tag.group(1)
        cotton = name.startswith("c-")
        if cotton:
            components.append((tag.start(), name[2:]))
        for attr in ATTR.finditer(tag.group(2)):
            if is_alpine(attr.group(1), cotton):
                directives.append(tag.start(2) + attr.start(1))
    return directives, components, branches


def per_render(items, branches):
    """Sum (offset, weight) items, counting only the largest branch of each if.

    One render draws one branch. An if with no else counts as drawn.
    Unbalanced branch tags fall back to summing every branch.
    """
    events = sorted(
        [(pos, 1, weight) for pos, weight in items]
        + [(pos, 0, kind) for pos, kind in branches]
    )
    stack = [[0]]
    for _, is_item, value in events:
        if is_item:
            stack[-1][-1] += value
        elif value == "if":
            stack.append([0])
        elif value in ("elif", "else") and len(stack) > 1:
            stack[-1].append(0)
        elif value == "endif" and len(stack) > 1:
            done = stack.pop()
            stack[-1][-1] += max(done)
    while len(stack) > 1:
        done = stack.pop()
        stack[-1][-1] += sum(done)
    return stack[0][0]


def kit_templates_dir():
    spec = importlib.util.find_spec(KIT_PACKAGE)
    if spec is None or not spec.submodule_search_locations:
        raise SystemExit(f"{KIT_PACKAGE} is not installed. Run uv sync.")
    return Path(spec.submodule_search_locations[0]) / "templates"


class Kit:
    """Resolves kit tags to templates and works out their weights."""

    def __init__(self, root, kit_templates=None):
        kit_templates = Path(kit_templates or kit_templates_dir())
        self.roots = [root / r for r in OVERRIDE_ROOTS] + [kit_templates]
        self.weights = {}
        self.unresolved = set()

    def resolve(self, tag):
        """Return the template file Cotton renders for <c-tag>, or None.

        Cotton snake-cases names, so mode-toggle and mode_toggle are one tag.
        It looks for x.html in every root before it looks for x/index.html.
        """
        name = "cotton/" + tag.replace(".", "/").replace("-", "_")
        for candidate in (f"{name}.html", f"{name}/index.html"):
            for base in self.roots:
                path = base / candidate
                if path.is_file():
                    return path
        return None

    def weight(self, tag):
        """Alpine that one use of <c-tag> renders, including kit tags it nests.

        A tag nested inside itself counts once: the inner use is skipped.
        """
        return self._weight(tag, frozenset())[0]

    def _weight(self, tag, seen):
        """Return (weight, tags skipped at or below tag to break a cycle).

        A weight inside a cycle depends on which tag the walk started from,
        so only a weight with no skip below it is cached.
        """
        if tag in self.weights:
            return self.weights[tag], frozenset()
        path = self.resolve(tag)
        if path is None:
            self.unresolved.add(tag)
            self.weights[tag] = 0
            return 0, frozenset()
        seen = seen | {tag}
        directives, components, branches = scan(path.read_text())
        items = [(pos, 1) for pos in directives]
        skipped = set()
        for pos, child in components:
            if not child.startswith(KIT_PREFIX):
                continue
            if child in seen:
                skipped.add(child)
                continue
            child_weight, child_skipped = self._weight(child, seen)
            items.append((pos, child_weight))
            skipped |= child_skipped
        weight = per_render(items, branches)
        if not skipped:
            self.weights[tag] = weight
        return weight, frozenset(skipped)


def charged(path, tag):
    return (
        tag.startswith(KIT_PREFIX)
        and tag not in UNCHARGED_TAGS
        and not path.startswith(UNCHARGED_PATHS)
    )


def inventory(root, kit):
    """Return ({path: {"direct": n, "kit": m}}, {path: Counter of charged kit tags}).

    Counts list only templates with some Alpine. Uses list every template that
    uses a charged kit tag, even one that weighs 0 today. Every kit tag is
    resolved, charged or not, so a missing template fails the run.
    """
    counts, uses = {}, {}
    for file in sorted((root / SCAN_DIR).rglob("*.html")):
        path = file.relative_to(root).as_posix()
        directives, components, _ = scan(file.read_text())
        for _, tag in components:
            if tag.startswith(KIT_PREFIX):
                kit.weight(tag)
        tags = Counter(tag for _, tag in components if charged(path, tag))
        kit_count = sum(n * kit.weight(tag) for tag, n in tags.items())
        if directives or kit_count:
            counts[path] = {"direct": len(directives), "kit": kit_count}
        if tags:
            uses[path] = tags
    return counts, uses


def load_baseline(path):
    """Return the baseline, or None when it is missing or predates FORMAT."""
    if not path.exists():
        return None
    data = json.loads(path.read_text())
    if not isinstance(data, dict) or data.get("format") != FORMAT:
        return None
    return data


def compare(counts, uses, kit, baseline):
    """Return (refused, from_weights): templates over a ceiling.

    Each maps path -> {label: (count, ceiling)}. Kit uses are priced at the
    recorded weights, so a weight that fell cannot hide a new use. A kit rise
    that fits the ceiling at the recorded weights comes from a weight change.
    """
    ceilings = baseline["templates"]
    recorded = baseline["weights"]
    zero = {"direct": 0, "kit": 0}
    refused, from_weights = {}, {}
    for path in sorted(set(counts) | set(uses)):
        count = counts.get(path, zero)
        ceiling = {**zero, **ceilings.get(path, {})}
        at_recorded = sum(
            n * recorded.get(tag, kit.weight(tag))
            for tag, n in uses.get(path, {}).items()
        )
        over = {}
        if count["direct"] > ceiling["direct"]:
            over["direct Alpine"] = (count["direct"], ceiling["direct"])
        if at_recorded > ceiling["kit"]:
            over["kit Alpine at the recorded weights"] = (at_recorded, ceiling["kit"])
        if over:
            refused[path] = over
        elif count["kit"] > ceiling["kit"]:
            from_weights[path] = {"kit Alpine": (count["kit"], ceiling["kit"])}
    return refused, from_weights


def decreases(old, new):
    """Return lines naming each ceiling that new lowers."""
    zero = {"direct": 0, "kit": 0}
    lines = []
    for path in sorted(set(old) | set(new)):
        before, after = old.get(path, zero), new.get(path, zero)
        for column in ("direct", "kit"):
            if after[column] < before.get(column, 0):
                lines.append(f"{path} {column} {before[column]}→{after[column]}")
    return lines


def dump(weights, templates):
    """One line per entry, so a diff shows both columns of a template together."""

    def block(rows):
        return ",\n".join(
            f"    {json.dumps(k)}: {json.dumps(v)}" for k, v in rows.items()
        )

    return (
        f'{{\n  "format": {FORMAT},\n'
        f'  "weights": {{\n{block(weights)}\n  }},\n'
        f'  "templates": {{\n{block(templates)}\n  }}\n}}\n'
    )


def print_over(over_by_path):
    for path, over in over_by_path.items():
        for label, (count, ceiling) in over.items():
            print(f"{path}: {count} {label} (ceiling {ceiling})")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__.split("\n\n")[0])
    parser.add_argument(
        "--update",
        action="store_true",
        help="lower the ceilings and accept changed kit weights",
    )
    parser.add_argument("--root", type=Path, default=ROOT, help=argparse.SUPPRESS)
    parser.add_argument("--kit-templates", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--baseline", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)

    root = args.root.resolve()
    baseline_path = args.baseline or root / BASELINE_PATH
    kit = Kit(root, args.kit_templates)
    counts, uses = inventory(root, kit)
    for tag in UNCHARGED_TAGS:
        kit.weight(tag)
    if kit.unresolved:
        raise SystemExit(
            "No template found for kit tags: "
            + ", ".join(sorted(kit.unresolved))
            + ". Check whether a kit upgrade renamed them."
        )
    over_cap = {
        tag: (kit.weight(tag), cap)
        for tag, cap in UNCHARGED_TAGS.items()
        if kit.weight(tag) > cap
    }
    if over_cap:
        raise SystemExit(
            "Uncharged kit tags now carry more Alpine than their cap: "
            + ", ".join(f"{t} {w} (cap {c})" for t, (w, c) in over_cap.items())
            + ". Charge them, or raise the cap in UNCHARGED_TAGS."
        )
    weights = {
        tag: kit.weight(tag) for tag in sorted({t for u in uses.values() for t in u})
    }

    baseline = load_baseline(baseline_path)
    if baseline is None:
        if not args.update:
            raise SystemExit(
                f"{baseline_path} is missing or predates format {FORMAT}. "
                "Run with --update to write it."
            )
        print(
            f"Wrote a new format {FORMAT} baseline; it is not compared with the old one."
        )
    else:
        refused, from_weights = compare(counts, uses, kit, baseline)
        changed = {
            tag: (baseline["weights"][tag], weight)
            for tag, weight in weights.items()
            if tag in baseline["weights"] and baseline["weights"][tag] != weight
        }
        unrecorded = {
            tag: weight
            for tag, weight in weights.items()
            if tag not in baseline["weights"]
        }
        if refused:
            print_over(refused)
            raise SystemExit(
                "Use a React island for new N26 interactions. "
                "See docs/developing-gyrinx/react.md."
            )
        if changed and not args.update:
            print_over(from_weights)
            moved = ", ".join(f"{t} {a}→{b}" for t, (a, b) in changed.items())
            raise SystemExit(
                f"Kit component weights changed: {moved}. "
                "Review the kit upgrade or override, then run with --update."
            )
        if unrecorded and not args.update:
            new = ", ".join(f"{t} {w}" for t, w in unrecorded.items())
            raise SystemExit(
                f"Kit tags with no recorded weight: {new}. "
                "Run with --update to record them."
            )
        if args.update:
            for line in decreases(baseline["templates"], counts):
                print(line)
            for tag, (a, b) in changed.items():
                print(f"weight {tag} {a}→{b}")
            for tag, weight in unrecorded.items():
                print(f"weight {tag} recorded as {weight}")

    if args.update:
        baseline_path.write_text(dump(weights, counts))
    direct = sum(c["direct"] for c in counts.values())
    kit_total = sum(c["kit"] for c in counts.values())
    print(
        f"N26 Alpine: {direct} direct and {kit_total} from kit components "
        f"in {len(counts)} templates; no increases."
    )


if __name__ == "__main__":
    main()
