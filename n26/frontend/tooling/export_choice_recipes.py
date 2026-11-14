"""Extract choice presentation from query-free Cotton examples.

Page shells are inspected without rendering the Django base: asset generation
must also work before the React manifest exists.
"""

from pathlib import Path
from types import SimpleNamespace as Display

from django.template import Context, Template
from django.template.loader import render_to_string
from django_cotton.compiler_regex import CottonCompiler


def choice_recipes(parser, class_name):
    def render(source, **context):
        html = Template(CottonCompiler().process(source)).render(Context(context))
        return parser(html).elements

    def find(elements, tag, *tokens, without=(), **attributes):
        matches = {
            class_name(attrs)
            for name, attrs in elements
            if name == tag
            and set(tokens) <= set(attrs.get("class", "").split())
            and not set(without) & set(attrs.get("class", "").split())
            and all(attrs.get(key) == value for key, value in attributes.items())
        }
        if len(matches) != 1:
            raise ValueError(
                f"Cotton choice structure changed: {tag}, {tokens}: {matches}"
            )
        return matches.pop()

    def shape(elements, *tags):
        found = tuple(tag for tag, _ in elements)
        if found != tags:
            raise ValueError(
                f"Cotton choice structure changed: {found}, expected {tags}"
            )

    option = Display(
        key="pick",
        name="Example",
        band="1–6",
        summary="Summary",
        rating=10,
        removal_rating=5,
        remark="Remark",
        control="both",
    )
    offer = Display(
        is_empty=False,
        takes_several=True,
        groups=[
            Display(name="Group", caption="Caption", options=[option], lifted=True)
        ],
    )
    picks = render('<c-n26.choice-picks :offer="offer" />', offer=offer)
    shape(
        picks,
        "div",
        "fieldset",
        "legend",
        "span",
        "ul",
        "li",
        *(["span"] * 7),
        "button",
        "button",
    )
    pick_spans = [attrs for tag, attrs in picks if tag == "span"]
    empty = render(
        '<c-n26.choice-picks :offer="offer" />', offer=Display(is_empty=True)
    )

    roll = Display(
        faces=["1", "6"],
        total=7,
        dice_label="2D6",
        is_spent=False,
        landed=["Example"],
        threshold=False,
        entered=True,
        add=Display(key="pick", name="Example"),
        applied="Example",
    )
    result = render('<c-n26.roll-result :roll="roll" />', roll=roll)
    numeric = render(
        '<c-n26.roll-result :roll="roll" />',
        roll=Display(**{**vars(roll), "faces": []}),
    )
    spent = render(
        '<c-n26.roll-result :roll="roll" />',
        roll=Display(**{**vars(roll), "is_spent": True}),
    )
    if any(tag == "button" for tag, _ in spent):
        raise ValueError("Cotton spent roll must not offer an action")
    if [attrs.get("value") for tag, attrs in result if tag == "button"] != [
        "pick",
        "roll",
    ]:
        raise ValueError("Cotton roll actions changed")

    table = render(
        '<c-n26.roll-table :table="table" />',
        table=Display(dice_label="D6", lowest=1, highest=6),
    )
    if [attrs.get("value") for tag, attrs in table if tag == "button"] != [
        "enter",
        "roll",
        "enter",
    ]:
        raise ValueError("Cotton manual roll default submit changed")
    divider = render('<c-n26.divider label="or" />')
    shape(divider, "div", "span", "span", "span")

    faces = {}
    die_root = pip = filled_pip = None
    for value in range(1, 7):
        die = render(f'<c-n26.die value="{value}" />')
        shape(die, *(["span"] * 10))
        die_root = find(die, "span", "grid", role="img")
        pip_classes = [class_name(attrs) for _, attrs in die[1:]]
        filled = ["bg-ink-900" in classes.split() for classes in pip_classes]
        if sum(filled) != value:
            raise ValueError(f"Cotton die {value} has the wrong pip count")
        faces[str(value)] = filled
        pip = next(
            classes
            for classes, active in zip(pip_classes, filled, strict=True)
            if not active
        )
        filled_pip = next(
            classes
            for classes, active in zip(pip_classes, filled, strict=True)
            if active
        )

    block = Display(heading="Heading", description="Description")
    arrival = render(
        '<c-n26.arrival-block :block="block">Questions</c-n26.arrival-block>',
        block=block,
    )
    question = Display(
        heading_id="question",
        label="Choice",
        bearer="Example",
        chosen="Example",
        settled=False,
        roll_href="/roll/",
        offer=offer,
        field_name="pick",
        remove_name="remove",
    )
    question_parts = render(
        '<c-n26.arrival-question :question="question" />', question=question
    )
    screen = Display(
        blocks=[], may_continue=False, skip_url="/skip/", outstanding_words="one choice"
    )
    footer = parser(
        render_to_string(
            "n26/includes/arrival_blocks.html",
            {"screen": screen},
        )
    ).elements
    shape(footer, "form", "div", "div", "button", "a", "p")
    next_source = (
        Path(__file__).parents[2] / "core/templates/n26/next.html"
    ).read_text()
    next_parts = parser(next_source).elements

    return {
        "picks": {
            "root": find(picks, "div", "space-y-8"),
            "empty": find(empty, "p", "text-muted"),
            "legend": find(picks, "legend"),
            "caption": class_name(pick_spans[0]),
            "list": find(picks, "ul"),
            "option": find(picks, "li"),
            "band": class_name(pick_spans[1]),
            "body": class_name(pick_spans[2]),
            "name": class_name(pick_spans[3]),
            "summary": class_name(pick_spans[4]),
            "rating": class_name(pick_spans[5]),
            "removalRating": class_name(pick_spans[6]),
            "remark": class_name(pick_spans[7]),
        },
        "rollResult": {
            "root": find(result, "section"),
            "result": find(result, "span", "flex", "gap-4"),
            "faces": find(result, "span", "flex", "gap-2", without=("items-center",)),
            "face": find(result, "span", "grid", "text-5xl"),
            "numeric": find(numeric, "span", "size-12"),
            "body": find(result, "span", "min-w-0", "flex-1", without=("flex",)),
            "heading": find(result, "span", "block", "text-lg"),
            "diceLabel": find(result, "span", "font-normal", "text-muted"),
            "description": find(result, "span", "block", "text-muted"),
            "landing": find(result, "strong"),
            "actions": find(result, "span", "flex", "items-center", "gap-2"),
            "add": " ".join(
                token
                for token in find(result, "button", value="pick").split()
                if token in {"flex-1", "sm:flex-none"}
            ),
        },
        "rollTable": {
            "root": find(table, "div", "flex-col"),
            "defaultSubmit": find(table, "button", "sr-only"),
            "divider": find(table, "div", role="separator"),
            "verticalDivider": find(table, "span", "w-px"),
            "manual": find(table, "div", "items-center", "gap-2"),
            "inputWrapper": find(table, "div", "w-56"),
        },
        "divider": {
            "root": find(divider, "div"),
            "line": find(divider, "span", "h-px"),
            "label": find(divider, "span", "text-sm"),
        },
        "die": {"root": die_root, "pip": pip, "filledPip": filled_pip, "faces": faces},
        "arrivalBlock": {
            "root": find(arrival, "section"),
            "header": find(arrival, "div", "space-y-2"),
            "heading": find(arrival, "h2"),
            "description": find(arrival, "div", "rich-text"),
        },
        "arrivalQuestion": {
            "root": find(question_parts, "div", "space-y-4"),
            "header": find(question_parts, "div", "space-y-1"),
            "heading": find(question_parts, "h3"),
            "caption": find(question_parts, "span", "ml-1"),
            "status": find(question_parts, "p", "text-muted"),
        },
        "nextPage": {
            "root": find(next_parts, "div", "max-w-3xl"),
            "form": find(footer, "form"),
            "footer": find(footer, "div", "border-t"),
            "actions": find(footer, "div", "flex-wrap"),
            "hint": find(footer, "p"),
        },
    }
