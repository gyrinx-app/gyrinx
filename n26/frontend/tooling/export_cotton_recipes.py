"""Build React's presentation recipes from the Cotton templates Django uses.

Only static primitives cross this boundary. Behaviour belongs to React; Alpine
directives and user content are never compiled into the generated module.
"""

import json
import os
import re
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


def attributes(source, *tags):
    """Fail the build if a primitive's extracted tag sequence changes."""
    rendered = Template(CottonCompiler().process(source)).render(Context())
    elements = Elements(rendered).elements
    found = [(tag, attrs) for tag, attrs in elements if tag in tags]
    if tuple(tag for tag, _ in found) != tags:
        raise ValueError(f"Cotton structure changed: {source}: {found}")
    return [attrs for _, attrs in found]


def class_name(attrs):
    return " ".join(attrs.get("class", "").split())


def classes(source, *tags):
    return [class_name(attrs) for attrs in attributes(source, *tags)]


def checked_classes(attrs):
    """Extract only the fixed class alternatives of the checkbox's picked state."""
    expression = attrs.get(":class", "")
    match = re.fullmatch(r"picked\s*\?\s*'([^']*)'\s*:\s*'([^']*)'", expression)
    if not match:
        raise ValueError(f"Checkbox class expression changed: {expression}")
    return {"checked": match[1], "unchecked": match[2]}


def native_select_recipe():
    (select,) = attributes('<c-ui.select.native placeholder="" />', "select")
    style = select.get("style", "").strip()
    match = re.fullmatch(
        r"background-image:\s*(url\('[^']*'\));\s*background-size:\s*([^;]+);?",
        style,
    )
    if not match:
        raise ValueError(f"Native select chevron style changed: {style}")
    return {
        "className": class_name(select),
        "style": {"backgroundImage": match[1], "backgroundSize": match[2]},
    }


def checkbox_card_recipe():
    parts = attributes(
        '<c-n26.checkbox-card label="Model" description="Profile">Controls</c-n26.checkbox-card>',
        "div",
        "label",
        "input",
        "span",
        "span",
        "span",
        "div",
    )
    root, _, checkbox, _, _, _, body = parts
    if checkbox.get("type") != "checkbox" or body.get(":inert") != "!picked":
        raise ValueError("Checkbox card control or nested inert state changed")
    return {
        **dict(
            zip(
                ("root", "header", "checkbox", "text", "label", "description", "body"),
                map(class_name, parts),
                strict=True,
            )
        ),
        "selection": checked_classes(root),
        "nested": checked_classes(body),
    }


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
    button_variants = ("default", "primary", "success", "danger", "ghost")
    field = classes(
        '<c-ui.field label="Name" for="recipe-field">Control</c-ui.field>',
        "div",
        "label",
        "span",
    )
    return {
        "button": {
            variant: classes(
                f'<c-ui.button variant="{variant}">Save</c-ui.button>', "button"
            )[0]
            for variant in button_variants
        },
        "buttonLink": {
            variant: classes(
                f'<c-ui.button href="/" variant="{variant}">Cancel</c-ui.button>',
                "a",
            )[0]
            for variant in button_variants
        },
        "checkboxCard": checkbox_card_recipe(),
        "nativeSelect": native_select_recipe(),
        "field": {
            **dict(zip(("root", "label", "labelText"), field, strict=True)),
            "error": classes('<c-ui.error message="Select a model." />', "div")[0],
        },
        "formActions": classes("<c-n26.form-actions />", "div")[0],
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
