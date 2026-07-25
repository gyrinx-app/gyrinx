"""Static safety gate for django-cotton call sites. See scripts/check_cotton.sh."""

import pathlib
import re
import sys

ROOT = pathlib.Path(__file__).resolve().parent.parent
TEMPLATE_ROOT = ROOT / "gyrinx"
COTTON_DIRS = [
    TEMPLATE_ROOT / "templates" / "cotton",
    TEMPLATE_ROOT / "core" / "templates" / "cotton",
]

COMMENT = re.compile(r"\{%\s*comment\s*%\}.*?\{%\s*endcomment\s*%\}", re.S)
TAG = re.compile(r"<c-([\w.-]+)((?:\"[^\"]*\"|'[^']*'|[^>\"'])*?)/?>", re.S)
DYN_ATTR = re.compile(r"(?:^|\s):([\w.-]+)=")
# `:attrs="attrs"` is cotton's own attribute-proxying idiom (merges a dict of
# attributes a parent component already received), not a call-site value.
PROXY_ATTRS = {"attrs"}
CVARS = re.compile(r"<c-vars\b(.*?)/?>", re.S)
VAR_NAME = re.compile(r"(?:^|\s):?([\w-]+)=")

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
    rel = component.replace(".", "/") + ".html"
    for base in COTTON_DIRS:
        path = base / rel
        if path.is_file():
            # blank_comments FIRST: every component's doc comment talks about
            # <c-vars>, and CVARS.search takes the first match, so without this it
            # parses prose and returns an empty set. That silently blinded the
            # undeclared-prop XSS check on back/badge/btn/cancel/icon/messages —
            # fail-closed, but it also means a doc comment spelling out
            # `<c-vars foo="">` as an example would mark foo "declared" and let a
            # real `:foo=` through to the mark_safe'd attrs. Fail-open, from prose.
            src = blank_comments(path.read_text(encoding="utf-8", errors="replace"))
            match = CVARS.search(src)
            return set(VAR_NAME.findall(match.group(1))) if match else set()
    return None


def line_of(src, pos):
    return src.count("\n", 0, pos) + 1


def main():
    problems = []
    cache = {}
    for path in sorted(TEMPLATE_ROOT.rglob("*.html")):
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

            # 1. any template tag ({% %} or {{ }}) in attribute position
            # Both forms are equally hazardous in attribute position, and the pytest
            # gate has always checked both — this half only checked {%, so a
            # `<c-btn {{ x }}>` passed the hook and failed only in CI.
            if "{%" in unquoted or "{{" in unquoted:
                problems.append(
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
                        problems.append(
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
                    problems.append(
                        f'{rel}:{line}: <c-{name} {prop}="…"> needs the COLON: '
                        f':{prop}="…". Without it the value stringifies to rendered '
                        f"HTML, every attribute lookup resolves to nothing, and the "
                        f"label, help text and ERRORS are silently dropped (#2001)."
                    )
                elif not re.search(rf"(?:^|\s):{prop}=", attrs):
                    problems.append(
                        f'{rel}:{line}: <c-{name}> is missing :{prop}="…". The '
                        f"<c-vars> default shadows any ambient `{prop}` from an "
                        f"enclosing loop, so this renders an EMPTY wrapper and the "
                        f"form ships with the control missing."
                    )

            # 4. a search control with no accessible name
            if name in NEEDS_LABEL and not re.search(r"(?:^|\s):?label=", attrs):
                problems.append(
                    f'{rel}:{line}: <c-{name}> needs label="…" — the specific '
                    f'accessible name ("Search campaigns"), not the generic '
                    f"placeholder. It falls back to the placeholder so a bar is "
                    f"never nameless, but the fallback is not how a call site ships."
                )

    if problems:
        print("cotton checks FAILED:\n")
        print("\n".join(problems))
        return 1
    print("cotton checks: OK")
    return 0


if __name__ == "__main__":
    sys.exit(main())
