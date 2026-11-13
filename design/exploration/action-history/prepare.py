"""Export prototype recipes and a shadow theme from this checkout’s N26 sources."""

import json
import re
import sys
from pathlib import Path

import django
from django.conf import settings

HERE = Path(__file__).resolve().parent
UPSTREAM = HERE.parents[2]
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
                    "react": "n26.core.templatetags.react",
                }
            },
        }
    ],
)
django.setup()
# Template exports need the standalone Django settings above.
from n26.frontend.tooling.export_cotton_recipes import (  # noqa: E402
    Elements,
    classes,
    dialog_recipe,
    input_recipe,
    native_select_recipe,
)


def history_recipes():
    from django.template import Context, Template
    from django_cotton.compiler_regex import CottonCompiler

    def rendered(source):
        return Elements(
            Template(CottonCompiler().process(source)).render(Context())
        ).elements

    header = rendered(
        '<c-n26.page-header title="History" lead="Activity"><c-slot name="breadcrumb">Trail</c-slot><c-slot name="actions">Actions</c-slot></c-n26.page-header>'
    )
    divs = [attrs.get("class", "") for tag, attrs in header if tag == "div"]
    if len(divs) != 6:
        raise ValueError(
            "Review the N26 page-header structure before exporting history recipes."
        )
    nav = rendered(
        '<c-n26.site.nav sticky="1" class="dark"><c-slot name="switcher">Gang</c-slot></c-n26.site.nav>'
    )
    search = rendered('<c-n26.search-bar :nested="True" />')
    return {
        "pageHeader": dict(
            zip(
                ("root", "breadcrumbRow", "breadcrumb", "row", "column", "actions"),
                divs,
                strict=True,
            )
        )
        | {
            "title": next(a["class"] for t, a in header if t == "h1"),
            "lead": next(a["class"] for t, a in header if t == "p"),
        },
        "nav": {
            "root": next(a["class"] for t, a in nav if t == "header"),
            "inner": next(a["class"] for t, a in nav if t == "div"),
            "brand": next(a["class"] for t, a in nav if t == "a"),
        },
        "search": {
            "root": [a["class"] for t, a in search if t == "div"][0],
            "field": [a["class"] for t, a in search if t == "div"][1],
            "icon": next(a["class"] for t, a in search if t == "span"),
            "input": next(a["class"] for t, a in search if t == "input"),
        },
    }


recipes = {
    "button": {
        variant: classes(
            f'<c-ui.button variant="{variant}" size="sm">Action</c-ui.button>', "button"
        )[0]
        for variant in ("default", "primary", "success", "ghost", "subtle")
    },
    "card": classes('<c-ui.card padding="none">Card</c-ui.card>', "div")[0],
    "badge": classes('<c-ui.badge variant="pill">Highlighted</c-ui.badge>', "span")[0],
    "history": history_recipes(),
    "input": input_recipe(),
    "select": native_select_recipe(),
    "dialog": dialog_recipe(),
    "label": classes("<c-ui.label>Address</c-ui.label>", "label")[0],
}
(HERE / "src/cotton.json").write_text(json.dumps(recipes, indent=2) + "\n")
# Generate the shadow stylesheet from this checkout's actual N26 sources.
assets = UPSTREAM / "n26/designsystem/assets"
source = (assets / "app.css").read_text()
source = re.sub(
    r'@import "\./([^";]+)";',
    lambda m: f'@import "../../../../n26/designsystem/assets/{m[1]}";',
    source,
)
source = source.replace(
    '@import "../../../../n26/designsystem/assets/cotton-ui.sources.css";',
    '@import "./cotton-ui.sources.css";',
)
source = source.replace('@source "', '@source "../../../../n26/designsystem/assets/')
source = source.replace(":root", ":host").replace(".dark {", ":host(.dark), .dark {")
kit = (assets / "cotton-ui.sources.css").read_text()
(HERE / "src/cotton-ui.sources.css").write_text(
    kit.replace(":root", ":host").replace(".dark {", ":host(.dark), .dark {")
)
(HERE / "src/theme.css").write_text(
    source + '\n@source "./";\n@import "./history.css";\n'
)
print("Prepared Cotton recipes and the N26 shadow theme.")
