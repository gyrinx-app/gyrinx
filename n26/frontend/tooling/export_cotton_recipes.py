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


def radio_cards_recipe():
    """Extract the wrapping group and the card states used by the composer."""
    fieldset, legend, grid = attributes(
        '<c-n26.radio-cards label="Kind" min="var(--radio-card-min)" />',
        "fieldset",
        "legend",
        "div",
    )
    style = grid.get("style", "").strip()
    match = re.fullmatch(r"grid-template-columns:\s*([^;]+);?", style)
    if not match or "var(--radio-card-min)" not in match[1]:
        raise ValueError(f"Radio-card grid style changed: {style}")

    enabled = attributes(
        '<c-n26.radio-cards.card name="kind" value="one" label="One" '
        'description="Description" example="Example" :wrap="True">'
        '<c-slot name="flair"><c-ui.badge color="amber" size="sm">'
        "Deprecated</c-ui.badge></c-slot></c-n26.radio-cards.card>",
        "label",
        "input",
        "span",
        "span",
        "span",
        "span",
        "span",
        "span",
        "span",
        "svg",
        "span",
    )
    disabled = attributes(
        '<c-n26.radio-cards.card name="kind" value="one" label="One" '
        'reason="Reason" :wrap="True" :disabled="True" />',
        "label",
        "input",
        "span",
        "span",
        "span",
        "span",
    )
    if enabled[1].get("type") != "radio" or "disabled" not in disabled[1]:
        raise ValueError("Radio-card controls changed")

    return {
        "group": {
            "root": class_name(fieldset),
            "legend": class_name(legend),
            "grid": class_name(grid),
            "gridTemplateColumns": match[1],
        },
        "card": {
            "enabled": class_name(enabled[0]),
            "disabled": class_name(disabled[0]),
            "input": class_name(enabled[1]),
            "content": class_name(enabled[2]),
            "label": class_name(enabled[3]),
            "flairText": class_name(enabled[4]),
            "flair": class_name(enabled[5]),
            "description": class_name(enabled[7]),
            "reason": class_name(disabled[5]),
            "example": class_name(enabled[8]),
            "exampleIcon": class_name(enabled[9]),
            "exampleText": class_name(enabled[10]),
        },
    }


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


def quick_switcher_recipe():
    """Extract the static presentation of the navigation quick switcher.

    Rendered with one current and one ordinary row, so the row states are
    read from the real item template rather than restated here.
    """
    source = (
        '<c-n26.quick-switcher label="Label" href="/" menu_label="Switch">'
        '<c-n26.quick-switcher.item label="Here" href="/here" :current="True" />'
        '<c-n26.quick-switcher.item label="There" href="/there" />'
        "</c-n26.quick-switcher>"
    )
    rendered = Template(CottonCompiler().process(source)).render(Context())
    elements = Elements(rendered.split("<noscript>")[0]).elements
    expected = (
        "div",
        "div",
        "a",
        "span",
        "span",
        "div",
        "div",
        "button",
        "span",
        "svg",
        "path",
        "div",
        "div",
        "div",
        "div",
        "div",
        "svg",
        "path",
        "circle",
        "input",
        "div",
        "a",
        "span",
        "svg",
        "path",
        "a",
        "span",
        "p",
    )
    if tuple(tag for tag, _ in elements) != expected:
        raise ValueError(f"Cotton quick-switcher structure changed: {elements}")

    def at(index):
        return " ".join(elements[index][1].get("class", "").split())

    current_state = (
        "bg-ink-100 font-medium text-ink-900 dark:bg-ink-800 dark:text-ink-100"
    )
    other_state = "text-ink-700 dark:text-ink-300"
    if not at(21).endswith(current_state) or not at(25).endswith(other_state):
        raise ValueError("Cotton quick-switcher row states changed")
    highlight = re.fullmatch(
        r"\{\s*'([^']+)'\s*:\s*active === id\s*\}", elements[25][1].get(":class", "")
    )
    if not highlight:
        raise ValueError("Cotton quick-switcher highlight changed")
    worded = Template(
        CottonCompiler().process(
            '<c-n26.quick-switcher menu_label="Add" trigger_words="Add a skill">'
            '<c-n26.quick-switcher.choice label="Here" />'
            "</c-n26.quick-switcher>"
        )
    ).render(Context())
    parts = Elements(worded.split("<noscript>")[0]).elements
    chevrons = [a for tag, a in parts if tag == "button" and a.get("aria-haspopup")]
    choices = [a for tag, a in parts if tag == "button" and a.get("role") == "menuitem"]
    words = [
        a for tag, a in parts if tag == "span" and class_name(a) == "text-xs text-muted"
    ]
    if len(chevrons) != 1 or len(choices) != 1 or len(words) != 1:
        raise ValueError("Cotton quick-switcher trigger words or choice changed")

    return {
        "root": at(0),
        "group": at(1),
        "label": at(2),
        "chevronWords": class_name(chevrons[0]),
        "triggerWords": class_name(words[0]),
        "choice": class_name(choices[0]),
        "labelContent": at(3),
        "labelText": at(4),
        "chevron": at(7),
        "chevronIcon": at(8),
        "chevronSvg": at(9),
        "panel": at(11),
        "body": at(12),
        "header": at(13),
        "inputGroup": at(14),
        "inputIcon": at(15),
        "input": at(19),
        "row": at(25).removesuffix(other_state).strip(),
        "rowCurrent": current_state,
        "rowOther": other_state,
        "rowHighlight": highlight[1],
        "rowLabel": at(22),
        "rowCheck": at(23),
        "empty": at(27),
    }


def pick_list_recipe():
    """Extract the pick list's boxes and group headings from their Cotton."""
    from types import SimpleNamespace

    def box(**fields):
        defaults = {"detail": "", "granted_by": "", "fixed_because": ""}
        option = SimpleNamespace(
            key="k", name="Name", is_current=False, **(defaults | fields)
        )
        rendered = Template(
            CottonCompiler().process('<c-n26.pick-list.box :option="option" />')
        ).render(Context({"option": option}))
        return Elements(rendered).elements

    free = box(detail="Detail")
    held = box(granted_by="Keen-eyed")
    if [tag for tag, _ in free] != ["label", "input", "span", "span", "span"]:
        raise ValueError(f"Cotton pick-list box structure changed: {free}")
    if held[0][0] != "label" or "disabled" not in held[1][1]:
        raise ValueError("Cotton pick-list box no longer disables a granted option")
    legend, caption = classes(
        '<c-n26.pick-list.legend name="Name" caption="Caption" />', "legend", "span"
    )
    return {
        "box": class_name(free[0][1]),
        "boxFixed": class_name(held[0][1]),
        "checkbox": class_name(free[1][1]),
        "text": class_name(free[2][1]),
        "name": class_name(free[3][1]),
        "remark": class_name(free[4][1]),
        "legend": legend,
        "caption": caption,
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
    button_variants = ("default", "primary", "success", "danger", "ghost", "subtle")
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
        "buttonSmall": {
            variant: classes(
                f'<c-ui.button variant="{variant}" size="sm">Save</c-ui.button>',
                "button",
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
        "radioCards": radio_cards_recipe(),
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
        "badge": classes(
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
        "quickSwitcher": quick_switcher_recipe(),
        "pickList": pick_list_recipe(),
        "icons": {
            name: [
                {"tag": tag, "attrs": attrs}
                for tag, attrs in Elements(str(resolve(name).body)).elements
            ]
            for name in ("search", "x", "chevron-down", "info", "check")
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
