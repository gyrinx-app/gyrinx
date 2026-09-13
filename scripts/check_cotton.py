"""Static safety gate for django-cotton call sites. See scripts/check_cotton.sh."""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
# Trees holding first-party templates: the platform shell and each edition
# package. Both are scanned for call sites; omitting one makes this gate pass
# while silently ignoring everything in it.
TEMPLATE_ROOTS = [ROOT / "gyrinx", ROOT / "n23", ROOT / "n26"]
# Where components are defined: the platform's and n26's. A component found in
# neither has no <c-vars> to read, and the undeclared-prop check is skipped for
# it, so an edition that ships components must be listed here or its call
# sites are only half-checked. Listing a directory that does not exist would
# be quietly meaningless in a file whose whole point is that an empty scan
# root passes vacuously, so add an entry only for a tree that really exists.
COTTON_DIRS = [
    ROOT / "gyrinx" / "templates" / "cotton",
    ROOT / "n26" / "core" / "templates" / "cotton",
]
# What a PRE_EXISTING entry is known to fail on: the words that check's
# message carries and no other check's does.
IN_ATTRIBUTE_POSITION = "template tag in attribute position"

# Calls the gate would fail that predate the n26 root joining the scan: n26
# component sources putting cotton's own attrs passthrough, or an if block, in
# attribute position on a nested component call. Each is pinned to the exact
# source of the call (whitespace collapsed) and to the one violation it is
# known to carry, so the entry stops matching the moment the call is edited,
# a second violation on the same call is reported, and everything else in the
# file is checked as normal; an entry that matches no failing call fails the
# gate, so a fixed call must take its entry with it. Fix them (or prove them
# harmless) and delete.
PRE_EXISTING = {
    (
        "n26/core/templates/cotton/n26/quick_switcher/of.html",
        '<c-n26.quick-switcher label="{{ switcher.label }}" href="{{ switcher.href }}" '
        'icon="{{ switcher.icon }}" heading="{{ switcher.heading }}" '
        'menu_label="{{ switcher.menu_label }}" placeholder="{{ switcher.placeholder }}" '
        'empty="{{ switcher.empty }}" align="{{ align }}" min_width="{{ min_width }}" '
        'hotkey="{{ hotkey }}" class="{{ class }}" {{ attrs }}>',
    ): IN_ATTRIBUTE_POSITION,
    (
        "n26/core/templates/cotton/n26/view/create_gang.html",
        '<c-n26.form-page action="{{ action }}" :form="form" {{ attrs }} '
        'title="{{ heading }}" lead="Required fields are marked with an asterisk (*)." '
        'submit_label="{{ submit_label }}" class="{{ class }}">',
    ): IN_ATTRIBUTE_POSITION,
    (
        "n26/core/templates/cotton/n26/view/fighter_hire.html",
        '<c-n26.form-page action="{{ action }}" :form="form" {{ attrs }} '
        'title="{{ heading }}" lead="Pick a profile and click Hire, then name the '
        "fighter. The options under each one change what you get and what you pay, "
        'and you can hire as many as you like without leaving this page." '
        'class="{{ class }}">',
    ): IN_ATTRIBUTE_POSITION,
}

COMMENT = re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.S)
TAG = re.compile(r"<c-([\w.-]+)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*?)/?>", re.S)
DYN_ATTR = re.compile(r"(?:^|\s):([\w.-]+)=")
# `:attrs="attrs"` is cotton's own attribute-proxying idiom (merges a dict of
# attributes a parent component already received), not a call-site value.
PROXY_ATTRS = {"attrs"}
CVARS = re.compile(r"<c-vars\b(.*?)/?>", re.S)
# A <c-vars> entry is `name="default"`, `:name="expr"`, or a bare `name` with
# no default at all (n26's ui/error.html declares `name form message` that
# way); the bare form is a declaration too, or every call passing it reads as
# an undeclared prop.
VAR_NAME = re.compile(r"(?:^|\s):?([\w-]+)(?==|\s|$)")

# Components that take a Django object (BoundField / Form) as a prop. Passing
# one WITHOUT the colon stringifies it: `field="{{ form.name }}"` renders the
# widget to HTML, after which every `field.*` lookup resolves to nothing and the
# component emits a wrapper with no label, no help text and NO ERRORS. The page
# still shows an input, so it looks right. That is the #2001 hidden-form-errors
# bug, reintroduced by one missing character, at a scale of ~120 call sites.
#
# Omitting the prop entirely is the same failure with a different cause: the
# `<c-vars>` default SHADOWS any ambient `field` from an enclosing {% for %}, so
# the component renders an empty wrapper and the form ships with fields missing.
OBJECT_PROPS = {
    "form.field": "field",
    "form.cell": "field",
    "form.choices": "field",
    "form.stepper": "field",
    "form.errors": "form",
    "errors": "form",
    # A username link stringified has no `.username` for the url tag to read,
    # and the badge tag then looks up a profile on a string.
    "user-link": "user",
    "n26.user-link": "user",
}

# Controls whose accessible name is not derivable from anything else on the
# page. The estate deliberately pairs a generic placeholder ("Search") with a
# specific aria-label ("Search campaigns"), and core/index.html renders two
# search bars on one page.
NEEDS_LABEL = {"filter.query", "form.search"}


def blank_comments(src):
    """Replace {% comment %} blocks with same-length whitespace (keeps line numbers)."""
    return COMMENT.sub(lambda m: re.sub(r"[^\n]", " ", m.group(0)), src)


def declared_props(component):
    """Prop names declared in <c-vars> of cotton/<component>.html, or None if absent."""
    # A hyphen in the tag is an underscore in the file: <c-n26.user-link> is
    # cotton/n26/user_link.html. Left as hyphens, every such component read as
    # undefined and its call sites were never checked for undeclared props.
    # A component may also be a directory with an index: <c-n26.quick-switcher>
    # is cotton/n26/quick_switcher/index.html, the shape every n26 root
    # component with parts takes. The direct file wins over the index, and
    # the platform's tree over an edition's, so a name means one file.
    rel = component.replace(".", "/").replace("-", "_")
    for base in COTTON_DIRS:
        for path in (base / f"{rel}.html", base / rel / "index.html"):
            if not path.is_file():
                continue
            # blank_comments FIRST: every component's doc comment talks about
            # <c-vars>, and CVARS.search takes the first match, so without this
            # it parses prose and returns an empty set. That silently blinded
            # the undeclared-prop XSS check on back/badge/btn/cancel/icon/
            # messages — fail-closed, but it also means a doc comment spelling
            # out `<c-vars foo="">` as an example would mark foo "declared" and
            # let a real `:foo=` through to the mark_safe'd attrs. Fail-open,
            # from prose.
            src = blank_comments(path.read_text(encoding="utf-8", errors="replace"))
            match = CVARS.search(src)
            if not match:
                return set()
            # Quoted defaults first: a bare word inside one is a value, not a
            # name — `class="a b"` declares class, not b.
            names = re.sub(r"\"[^\"]*\"|'[^']*'", '""', match.group(1))
            return set(VAR_NAME.findall(names))
    return None


def line_of(src, pos):
    return src.count("\n", 0, pos) + 1


def main():
    problems = []
    used = set()
    cache = {}
    for path in sorted(p for root in TEMPLATE_ROOTS for p in root.rglob("*.html")):
        # The component test harness writes uuid-named host templates into
        # gyrinx/templates/_cotton_test_host/ and deletes them again. They
        # deliberately contain the broken shapes these rules exist to forbid,
        # and under pytest-xdist they appear and vanish mid-scan.
        if "_cotton_test_host" in path.parts or path.name.startswith("_cotton_test"):
            continue
        try:
            raw = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            # A concurrently-created-and-deleted probe template (the component
            # test fixture writes one per test). Nothing to check.
            continue
        src = blank_comments(raw)
        rel = path.relative_to(ROOT)

        for match in TAG.finditer(src):
            name, attrs = match.group(1), match.group(2)
            line = line_of(src, match.start())
            unquoted = re.sub(r"\"[^\"]*\"|'[^']*'", "", attrs)
            # What this one call fails on; kept apart from the page's problems
            # until the call has been checked against PRE_EXISTING.
            found = []

            # 1. any template tag ({% %} or {{ }}) in attribute position
            # Both forms are equally hazardous in attribute position, and the pytest
            # gate has always checked both — this half only checked {%, so a
            # `<c-btn {{ x }}>` passed the hook and failed only in CI.
            if "{%" in unquoted or "{{" in unquoted:
                found.append(
                    f"{rel}:{line}: template tag in attribute position inside "
                    f"<c-{name}> -- cotton emits the raw source and the attribute "
                    f"is lost.\n"
                    # Plain strings, not f-strings: the example contains {% %}.
                    "    Fix: move it inside a quoted value "
                    '(attr="{% if cond %}...{% endif %}" / attr="{{ value }}"), or '
                    'pass a declared prop as a BARE dotted path (:field="form.x") '
                    "-- an expression in a :prop resolves to nothing. Otherwise "
                    "leave the element raw HTML."
                )

            # 2. dynamic attr that the component does not declare
            if name not in cache:
                cache[name] = declared_props(name)
            declared = cache[name]
            if declared is not None:
                for prop in DYN_ATTR.findall(attrs):
                    if prop in PROXY_ATTRS:
                        continue
                    if prop.replace("-", "_") not in declared and prop not in declared:
                        found.append(
                            f"{rel}:{line}: <c-{name} :{prop}=...> is not declared in that "
                            f"component's <c-vars>, so it renders through {{{{ attrs }}}}, which "
                            f"is NOT html-escaped.\n"
                            f'    Fix: use {prop}="{{{{ value }}}}" (autoescaped), or declare '
                            f"the prop in <c-vars>."
                        )

            # 3. an object prop (BoundField / Form) passed without the colon,
            #    or not passed at all.
            prop = OBJECT_PROPS.get(name)
            if prop is not None:
                if re.search(rf"(?:^|\s){prop}=", attrs):
                    found.append(
                        f'{rel}:{line}: <c-{name} {prop}="…"> needs the COLON: '
                        f':{prop}="…". Without it the value stringifies to rendered '
                        f"HTML, every attribute lookup resolves to nothing, and the "
                        f"label, help text and ERRORS are silently dropped (#2001)."
                    )
                elif not re.search(rf"(?:^|\s):{prop}=", attrs):
                    found.append(
                        f'{rel}:{line}: <c-{name}> is missing :{prop}="…". The '
                        f"<c-vars> default shadows any ambient `{prop}` from an "
                        f"enclosing loop, so this renders an EMPTY wrapper and the "
                        f"form ships with the control missing."
                    )

            # 4. a search control with no accessible name
            if name in NEEDS_LABEL and not re.search(r"(?:^|\s):?label=", attrs):
                found.append(
                    f'{rel}:{line}: <c-{name}> needs label="…" — the specific '
                    f'accessible name ("Search campaigns"), not the generic '
                    f"placeholder. It falls back to the placeholder so a bar is "
                    f"never nameless, but the fallback is not how a call site ships."
                )

            if found:
                key = (rel.as_posix(), " ".join(match.group(0).split()))
                expected = PRE_EXISTING.get(key)
                if expected is not None and any(expected in f for f in found):
                    used.add(key)
                # The entry covers the one violation it names; anything else
                # the same call fails on is as new as it would be anywhere.
                problems.extend(
                    f for f in found if expected is None or expected not in f
                )

    # A suppression that matches nothing is either a call somebody fixed, or a
    # call somebody edited: either way the entry is stale, and leaving it
    # would let the next bad call in that file through.
    for rel, call in sorted(set(PRE_EXISTING) - used):
        problems.append(
            f"{rel}: PRE_EXISTING entry no longer matches a failing call "
            f"({call[:60]}...). Delete the entry, or re-pin it to the call's "
            f"current source if the call is still knowingly wrong."
        )

    if problems:
        print("cotton checks FAILED:\n")
        print("\n".join(problems))
        return 1
    print("cotton checks: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
