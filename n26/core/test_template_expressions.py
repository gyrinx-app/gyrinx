"""Reject directive values that begin with unsupported statement keywords.

Django can render these attributes while the browser rejects their expressions.
Place statement bodies in x-data methods and call those methods from directives.
"""

import re
from pathlib import Path

import n26

# Recognise x- directives and the : and @ shorthand attributes.
DIRECTIVE = re.compile(r"""(?:^|\s)(x-[a-z:.-]+|[:@][\w:.-]+)=["']([^"']*)["']""")

# Exclude the if, let and const forms from the statement prefixes rejected by this
# guard.
STATEMENT = re.compile(
    r"^\s*(try|for|while|do|switch|throw|return|var|function|class|with)\b"
)

TEMPLATES = sorted(Path(n26.__file__).parent.rglob("*.html"))


def alpine_directives():
    """Yield template, directive and value triples matching recognised directive
    attributes.
    """
    for template in TEMPLATES:
        text = template.read_text()
        for name, value in DIRECTIVE.findall(text):
            yield template, name, value


def test_there_are_directives_to_check():
    """Discover enough directives to prevent an empty scan from passing the guard."""
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
