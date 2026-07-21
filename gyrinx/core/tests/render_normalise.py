"""Comparison tiers for the golden-HTML harness.

The default is BYTE EQUALITY. Every normalisation below is a class of change
the harness can no longer detect, so each one is opt-in per golden and must be
justified in review. Two are unavoidable (CSRF), the rest are the known,
measured consequences of routing markup through a cotton component.

TIER 1  byte-exact, after scrubbing values that cannot be deterministic.
TIER 2  structural: (tag, sorted-attrs, sorted-class-set, text). Blind to
        attribute ORDER and to `&` -> `&amp;`. Opt in with ATTR_ORDER/ENTITIES.
TIER 3  inline-whitespace guard. Tier 2 discards the whitespace BETWEEN
        elements, which is exactly where the cotton trailing-newline bug lives
        (adjacent badges rendering with a space between them). Tier 3 runs
        WHENEVER Tier 2 runs, so relaxing attribute order never silently
        relaxes whitespace.
"""

import difflib
import re
from html.parser import HTMLParser

CSRF = re.compile(r'(name="csrfmiddlewaretoken"\s+value=")[^"]*(")')
CSRF_JS = re.compile(r'(csrfmiddlewaretoken["\']?\s*[:=]\s*["\'])[^"\']*(["\'])')

UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-"
    r"[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)

# User pks are sequence-allocated, not UUIDs, so they shift with however many
# users earlier tests in the same worker happened to create (/user/1 alone,
# /user/155 inside the full suite). Narrow on purpose: only this one URL shape.
# The link TEXT (the username) is not scrubbed, so a page linking to the wrong
# user still fails.
USER_URL = re.compile(r"/user/\d+")

# The print page's QR code ENCODES the page URL, so it bakes the list uuid into
# an svg path -- and a longer uuid changes the symbol version, so even the
# viewBox moves (33x33 -> 37x37). No amount of scrubbing the surrounding html
# reaches inside a bitmap-as-path. Replace the whole widget: that the QR is
# present and correctly placed is checked, its pixels are not.
QR_WIDGET = re.compile(r'(<div id="qr-code"[^>]*>).*?(</div>)', re.S)

# Goldens permitted to fall back to Tier 2, with the reason. Keep this list
# SHORT and shrinking: an entry here is a page whose byte diff nobody reads.
ACCEPTED = {
    # "list-edit": "attr-order: c-btn emits class before type",
}


def scrub(html):
    """Neutralise values that cannot be made deterministic at the source."""
    html = CSRF.sub(r"\1CSRF\2", html)
    html = CSRF_JS.sub(r"\1CSRF\2", html)
    html = scrub_uuids(html)
    html = USER_URL.sub("/user/UID", html)
    html = QR_WIDGET.sub(r"\1QR-CODE\2", html)
    return html


def scrub_uuids(html):
    """Replace every UUID with a placeholder numbered by first appearance.

    render_world.deterministic_uuids() pins pks at the source, which is the
    better mechanism -- but it works by mutating `field.default` on 100 model
    fields globally, so it only holds if nothing else in the worker has touched
    those fields first. Under the project's default `pytest -n auto` that is not
    guaranteed: the harness passes alone and fails inside the full suite, with
    real uuid4s rendered against pinned goldens.

    Positional scrubbing makes the comparison independent of that. It is safe
    precisely because a pk's VALUE is never a meaningful part of the markup --
    only its position and its reuse across the page are, and both survive. A
    page that drops a link, or points two links at the same object, still fails.
    """
    mapping = {}

    def repl(match):
        return mapping.setdefault(match.group(0), f"UUID-{len(mapping) + 1:04d}")

    return UUID_RE.sub(repl, html)


class Structural(HTMLParser):
    """Flatten to a comparable sequence, discarding attribute order."""

    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.out = []

    def handle_starttag(self, tag, attrs):
        norm = []
        for k, v in sorted(attrs):
            if k == "class" and v:
                v = " ".join(sorted(v.split()))
            norm.append((k, v))
        self.out.append(("<", tag, tuple(norm)))

    def handle_endtag(self, tag):
        self.out.append((">", tag))

    def handle_data(self, data):
        if data.strip():
            self.out.append(("t", data.strip()))


def structural(html):
    p = Structural()
    p.feed(html)
    return p.out


# Whitespace between two tags: `</span> <span` vs `</span><span`.
BETWEEN = re.compile(r">(\s*)<")


def inline_gaps(html):
    """The exact whitespace run between every adjacent pair of tags."""
    return [m.group(1) for m in BETWEEN.finditer(html)]


def unified(name, expected, actual, label):
    diff = "\n".join(
        difflib.unified_diff(
            expected.splitlines(),
            actual.splitlines(),
            fromfile=f"{name} (golden)",
            tofile=f"{name} (actual)",
            lineterm="",
            n=2,
        )
    )
    return f"{name}: {label}\n" + "\n".join(diff.splitlines()[:40])


def compare(name, expected, actual):
    """Return None when equivalent, else a human-readable failure string."""
    expected, actual = scrub(expected), scrub(actual)

    if expected == actual:
        return None

    if name not in ACCEPTED:
        return unified(name, expected, actual, "byte mismatch (TIER 1)")

    # TIER 3 first: whitespace is the failure Tier 2 cannot see.
    if inline_gaps(expected) != inline_gaps(actual):
        for i, (e, a) in enumerate(zip(inline_gaps(expected), inline_gaps(actual))):
            if e != a:
                return (
                    f"{name}: inline whitespace changed at gap {i} "
                    f"({e!r} -> {a!r}) [TIER 3]. Adjacent inline elements will "
                    f"render with different spacing."
                )
        return f"{name}: number of inter-tag gaps changed [TIER 3]"

    if structural(expected) != structural(actual):
        return unified(
            name, expected, actual, f"structural mismatch [TIER 2, {ACCEPTED[name]}]"
        )

    return None
