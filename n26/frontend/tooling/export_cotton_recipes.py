"""Build React's presentation recipes from the Cotton templates Django uses.

Only static primitives cross this boundary. Behaviour belongs to React; Alpine
directives and user content are never compiled into the generated module.
"""

import json
import os
from html.parser import HTMLParser
from pathlib import Path

import django
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler


class Elements(HTMLParser):
    def __init__(self, source):
        super().__init__()
        self.elements = []
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        self.elements.append((tag, dict(attrs)))


def classes(source, *tags):
    """Fail the build if a primitive's extracted tag sequence changes."""
    rendered = Template(CottonCompiler().process(source)).render(Context())
    elements = Elements(rendered).elements
    found = [(tag, attrs) for tag, attrs in elements if tag in tags]
    if tuple(tag for tag, _ in found) != tags:
        raise ValueError(f"Cotton structure changed: {source}: {found}")
    return [" ".join(attrs.get("class", "").split()) for _, attrs in found]


def recipes():
    from n26.core.icons import resolve

    search = classes(
        '<c-n26.search-bar :live="True" model="query" />',
        "form",
        "div",
        "span",
        "label",
        "input",
        "button",
    )
    return {
        "button": {
            variant: classes(
                f'<c-ui.button variant="{variant}">Save</c-ui.button>', "button"
            )[0]
            for variant in ("default", "primary", "success", "danger")
        },
        "table": classes("<c-ui.table />", "div", "table"),
        "link": classes('<c-n26.link href="/">Name</c-n26.link>', "a", "span"),
        "stagedBadge": classes(
            '<c-ui.badge color="amber" size="sm">Staged</c-ui.badge>', "span"
        )[0],
        "actionBar": classes(
            '<c-n26.action-bar :surface="True"><c-slot name="trailing">Action</c-slot></c-n26.action-bar>',
            "div",
            "div",
        ),
        "search": dict(
            zip(
                ("root", "group", "icon", "label", "input", "clear"),
                search,
                strict=True,
            )
        ),
        "icons": {
            name: [
                {"tag": tag, "attrs": attrs}
                for tag, attrs in Elements(str(resolve(name).body)).elements
            ]
            for name in ("search", "x")
        },
    }


def main():
    os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gyrinx.settings")
    django.setup()
    target = Path(__file__).parents[1] / "generated" / "cotton.json"
    target.parent.mkdir(exist_ok=True)
    content = json.dumps(recipes(), indent=2) + "\n"
    if not target.exists() or target.read_text() != content:
        target.write_text(content)


if __name__ == "__main__":
    main()
