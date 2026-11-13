"""Build this independent preview from the repository's Cotton components."""

import json
import os
import re
import sys
from pathlib import Path

import django
from django.conf import settings

HERE = Path(__file__).resolve().parent
UPSTREAM = Path(os.environ.get("GYRINX_SOURCE", HERE.parents[2])).resolve()
sys.path.insert(0, str(UPSTREAM))
settings.configure(
    INSTALLED_APPS=["django_cotton", "django_cotton_ui"],
    TEMPLATES=[
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [str(UPSTREAM / "n26/core/templates")],
            "APP_DIRS": True,
            "OPTIONS": {
                "libraries": {
                    "icons": "n26.core.templatetags.icons",
                    "theme": "n26.core.templatetags.theme",
                }
            },
        }
    ],
)
django.setup()
from django.template import Context, Template  # noqa: E402
from django_cotton.compiler_regex import CottonCompiler  # noqa: E402

from n26.core.colours import GANG_COLOURS  # noqa: E402
from n26.frontend.tooling.export_cotton_recipes import (  # noqa: E402
    Elements,
    classes,
    dialog_recipe,
    input_recipe,
    native_select_recipe,
)


def segmented_tabs_recipe():
    source = '<c-ui.tabs variant="segmented" size="sm" :fill="True"><c-ui.tabs.tab name="Card">Card</c-ui.tabs.tab></c-ui.tabs>'
    elements = Elements(
        Template(CottonCompiler().process(source)).render(Context())
    ).elements
    rail = next(
        attrs
        for tag, attrs in elements
        if tag == "div" and "no-scrollbar" in attrs.get("class", "")
    )
    button = next(
        attrs
        for tag, attrs in elements
        if tag == "button" and "isActive" in attrs.get(":class", "")
    )
    states = re.findall(r"'([^']+)':\s*(!?)isActive", button[":class"])
    return {
        "rail": " ".join(rail["class"].split()),
        "button": " ".join(button["class"].split()),
        "active": next(value for value, negated in states if not negated),
        "inactive": next(value for value, negated in states if negated),
    }


recipes = {
    "colours": [
        {"name": colour.capitalize(), "token": f"--color-{colour}-500"}
        for colour in GANG_COLOURS
    ],
    "button": {
        variant: classes(
            f'<c-ui.button variant="{variant}" size="sm">Action</c-ui.button>', "button"
        )[0]
        for variant in ("default", "primary", "success", "ghost", "subtle")
    },
    "input": input_recipe(),
    "select": native_select_recipe(),
    "dialog": dialog_recipe(),
    "card": classes('<c-ui.card padding="none">Card</c-ui.card>', "div")[0],
    "tabs": segmented_tabs_recipe(),
}
(HERE / "src/cotton.json").write_text(json.dumps(recipes, indent=2) + "\n")
source = (UPSTREAM / "n26/designsystem/assets/app.css").read_text()
relative = Path(
    os.path.relpath(UPSTREAM / "n26/designsystem/assets", HERE / "src")
).as_posix()
source = source.replace('@import "./', f'@import "{relative}/')
kit = (UPSTREAM / "n26/designsystem/assets/cotton-ui.sources.css").read_text()
(HERE / "src/cotton-ui.sources.css").write_text(
    kit.replace(":root", ":host").replace(".dark {", ":host(.dark), .dark {")
)
source = source.replace(
    f'@import "{relative}/cotton-ui.sources.css";', '@import "./cotton-ui.sources.css";'
)
source = (
    source.replace('@source "', f'@source "{relative}/')
    .replace(":root", ":host")
    .replace(".dark {", ":host(.dark), .dark {")
)
(HERE / "src/theme.css").write_text(
    source + '\n@source "./";\n@import "./card-manager.css";\n'
)
print("Prepared Cotton recipes and the shadow-scoped N26 theme.")
