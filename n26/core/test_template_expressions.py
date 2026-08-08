"""Every Alpine directive in the edition must be an expression.

Alpine compiles a directive's value into expression position — roughly
``result = <what you wrote>``. Only two statement forms are special-cased
and wrapped in a function first: one starting ``if (…)``, and one starting
``let`` or ``const``. Anything else that opens with a statement keyword is
a syntax error at compile time.

That failure is silent everywhere a test can see. Alpine catches it,
writes it to the browser console, and skips the directive — so the page
still renders, the server still serves 200, and the behaviour the
directive was carrying simply never happens. A dialog stays unpromoted, a
row never registers, a watcher never runs, and nothing in the HTML says
why.

So it is checked here instead. A directive needing statements puts them in
a method on ``x-data`` and calls it; that body is inside an object literal,
which is an expression, and may contain anything.
"""

import re
from pathlib import Path

import n26

# Alpine's own directive spellings, plus the shorthands. `:` is x-bind and
# `@` is x-on; neither ever legitimately opens with a statement either.
DIRECTIVE = re.compile(r"""(?:^|\s)(x-[a-z:.-]+|[:@][\w:.-]+)=["']([^"']*)["']""")

# Statement keywords Alpine does not wrap. `if`, `let` and `const` are
# absent because Alpine handles those; the rest are syntax errors.
STATEMENT = re.compile(
    r"^\s*(try|for|while|do|switch|throw|return|var|function|class|with)\b"
)

TEMPLATES = sorted(Path(n26.__file__).parent.rglob("*.html"))


def alpine_directives():
    """Every (template, directive, value) triple the edition writes."""
    for template in TEMPLATES:
        text = template.read_text()
        for name, value in DIRECTIVE.findall(text):
            yield template, name, value


def test_there_are_directives_to_check():
    """A guard that discovers nothing passes for the wrong reason."""
    assert len(list(alpine_directives())) > 50


def test_no_directive_opens_with_a_statement_alpine_cannot_compile():
    offenders = [
        f'{template.relative_to(Path(n26.__file__).parent)}: {name}="{value[:60]}…"'
        for template, name, value in alpine_directives()
        if STATEMENT.match(value)
    ]
    assert not offenders, (
        "These Alpine directives open with a statement, which Alpine cannot "
        "compile — it logs a SyntaxError to the console and skips the "
        "directive, so whatever they do will silently not happen:\n  "
        + "\n  ".join(offenders)
        + "\nPut the statements in a method on x-data and call it from here."
    )
