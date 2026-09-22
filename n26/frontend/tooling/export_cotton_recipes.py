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


def input_recipe():
    root, control = classes('<c-ui.input type="text" />', "div", "input")
    return {"root": root, "control": control}


def switch_recipe():
    root, control, track, thumb = attributes(
        '<c-ui.switch name="example" />', "div", "input", "button", "span"
    )

    def states(attrs, prefix, expected):
        found = tuple(re.findall(r"'([^']+)'\s*:", attrs.get(":class", "")))
        if found != expected:
            raise ValueError(f"Cotton switch state classes changed: {found}")
        return dict(
            zip(
                (
                    f"{prefix}Transition",
                    f"{prefix}Checked",
                    f"{prefix}Unchecked",
                ),
                found,
                strict=True,
            )
        )

    track_states = states(
        track,
        "track",
        (
            "transition-colors",
            "bg-accent",
            "bg-ink-200 dark:bg-ink-700",
        ),
    )
    thumb_states = states(
        thumb,
        "thumb",
        (
            "transition-transform",
            "translate-x-[1.375rem]",
            "translate-x-0.5",
        ),
    )
    return {
        "root": class_name(root),
        "control": class_name(control),
        "track": class_name(track),
        "thumb": class_name(thumb),
        **track_states,
        **thumb_states,
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


def callout_recipe():
    """Extract the static, icon-free warning used beside selection controls."""
    root, content, body = classes(
        '<c-ui.alert variant="warning" :icon="False">Explanation.</c-ui.alert>',
        "div",
        "div",
        "div",
    )
    return {"root": root, "content": content, "body": body}


def filter_menu_recipe():
    """Extract the static presentation of the composed filter menu.

    Alpine supplies the Cotton component's state and positioning, so React owns
    those behaviours. The element sequence still comes from the real component:
    a structural change fails this build instead of silently drifting the
    adapter.
    """
    source = '<c-n26.filter-menu label="Filter" name="filter" :options="options" />'
    rendered = Template(CottonCompiler().process(source)).render(
        Context({"options": [{"value": "one", "label": "One"}]})
    )
    elements = Elements(rendered).elements
    expected = (
        "fieldset",
        "div",
        "div",
        "div",
        "div",
        "button",
        "span",
        "span",
        "svg",
        "path",
        "div",
        "div",
        "div",
        "button",
        "span",
        "button",
        "div",
        "div",
        "label",
        "input",
        "div",
        "div",
        "svg",
        "path",
        "div",
        "div",
        "span",
        "button",
        "div",
        "button",
        "button",
    )
    if tuple(tag for tag, _ in elements) != expected:
        raise ValueError(f"Cotton filter-menu structure changed: {elements}")

    def at(index):
        return " ".join(elements[index][1].get("class", "").split())

    def state_classes(index, attribute, expected):
        found = tuple(
            " ".join(value.split())
            for value in re.findall(r"'([^']+)'\s*:", elements[index][1][attribute])
        )
        if found != expected:
            raise ValueError(
                f"Cotton filter-menu state classes changed: {index}: {found}"
            )
        return found

    indicator_states = state_classes(
        21,
        ":class",
        (
            "border-accent bg-accent",
            "border-ink-300 dark:border-ink-600",
        ),
    )
    check_states = state_classes(
        22,
        ":class",
        ("scale-100", "scale-0", "text-accent-foreground"),
    )
    indicator_base = at(21).replace(indicator_states[1], "").strip()
    check_base = at(22).replace(check_states[1], "").strip()

    return {
        "root": at(3),
        "trigger": at(5),
        "triggerContent": at(6),
        "count": at(7),
        "panel": at(10),
        "body": at(11),
        "quickActions": at(12),
        "quickAction": at(13),
        "separator": at(14),
        "options": at(16),
        "option": at(17),
        "checkbox": at(18),
        "checkboxInput": at(19),
        "checkboxIndicatorWrap": at(20),
        "checkboxIndicator": indicator_base,
        "checkboxIndicatorChecked": indicator_states[0],
        "checkboxIndicatorUnchecked": indicator_states[1],
        "checkboxCheck": check_base,
        "checkboxCheckChecked": f"{check_states[0]} {check_states[2]}",
        "checkboxCheckUnchecked": check_states[1],
        "checkboxContent": at(24),
        "checkboxText": at(25),
        "only": at(27),
        "actions": at(28),
        "apply": at(29),
        "cancel": at(30),
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
        '<c-ui.field label="Name" description_trailing="Help" for="recipe-field">Control</c-ui.field>',
        "div",
        "label",
        "span",
        "div",
    )
    toggle_field = classes(
        '<c-ui.field variant="toggle" label="Name" description_trailing="Help" for="recipe-field">Control</c-ui.field>',
        "div",
        "div",
        "div",
        "label",
        "span",
        "div",
        "div",
    )
    (
        toggle_root,
        toggle_row,
        toggle_text,
        toggle_label,
        toggle_label_text,
        toggle_control,
        toggle_description,
    ) = toggle_field
    if (
        toggle_root,
        toggle_label,
        toggle_label_text,
        toggle_description,
    ) != tuple(field):
        raise ValueError("Cotton toggle field no longer reuses the block field recipe")
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
        "callout": callout_recipe(),
        "input": input_recipe(),
        "nativeSelect": native_select_recipe(),
        "field": {
            **dict(
                zip(
                    ("root", "label", "labelText", "description"),
                    field,
                    strict=True,
                )
            ),
            "toggleRow": toggle_row,
            "toggleText": toggle_text,
            "toggleControl": toggle_control,
            "error": classes('<c-ui.error message="Select a model." />', "div")[0],
        },
        "switch": switch_recipe(),
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
        "filterMenu": filter_menu_recipe(),
        "icons": {
            name: [
                {"tag": tag, "attrs": attrs}
                for tag, attrs in Elements(str(resolve(name).body)).elements
            ]
            for name in ("search", "x", "chevron-down")
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
