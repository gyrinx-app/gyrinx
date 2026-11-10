"""Read the upstream design library without modifying its source snapshot."""

import json
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
                    "theme": "n26.core.templatetags.theme",
                    "arith": "n26.core.templatetags.arith",
                    "react": "n26.core.templatetags.react",
                    "richtext": "n26.core.templatetags.richtext",
                }
            },
        }
    ],
)
django.setup()
# The template exporter needs the configured standalone Django environment.
from n26.core.colours import GANG_COLOURS  # noqa: E402
from n26.frontend.tooling.export_cotton_recipes import (  # noqa: E402
    Elements,
    classes,
    dialog_recipe,
    native_select_recipe,
)


def picture_crop_recipe():
    from django.template import Context, Template
    from django_cotton.compiler_regex import CottonCompiler

    source = '<c-n26.picture-input id="upload" />'
    elements = Elements(
        Template(CottonCompiler().process(source)).render(Context())
    ).elements
    divs = [attrs["class"] for tag, attrs in elements if tag == "div"]
    return {
        "root": next(attrs["class"] for tag, attrs in elements if tag == "dialog"),
        "body": divs[1],
        "title": next(attrs["class"] for tag, attrs in elements if tag == "h2"),
        "description": next(attrs["class"] for tag, attrs in elements if tag == "p"),
        "error": next(
            attrs["class"] for tag, attrs in elements if "data-crop-error" in attrs
        ),
        "actions": divs[-1],
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
        for variant in ("default", "primary", "success", "ghost")
    },
    "select": native_select_recipe(),
    "dialog": dialog_recipe(),
    "label": classes("<c-ui.label>Label</c-ui.label>", "label")[0],
    "pictureCrop": picture_crop_recipe(),
}
(HERE / "src/cotton.json").write_text(json.dumps(recipes, indent=2) + "\n")
# Keep imports relative to the upstream stylesheet, then add playground classes.
source = (UPSTREAM / "n26/designsystem/assets/app.css").read_text()
source = source.replace('@import "./', '@import "../../../../n26/designsystem/assets/')
kit_path = UPSTREAM / "n26/designsystem/assets/cotton-ui.sources.css"
(HERE / "src/cotton-ui.sources.css").write_text(
    kit_path.read_text()
    .replace(":root", ":host")
    .replace(".dark {", ":host(.dark), .dark {")
)
source = source.replace(
    '@import "../../../../n26/designsystem/assets/cotton-ui.sources.css";',
    '@import "./cotton-ui.sources.css";',
)
source = source.replace('@source "', '@source "../../../../n26/designsystem/assets/')
source = source.replace(":root", ":host")
source = source.replace(".dark {", ":host(.dark), .dark {")
(HERE / "src/theme.css").write_text(
    source
    + '\n@source "./";\n@import "./gallery.css";\n@import "./frame.css";\n@import "./card-content.css";\n@import "./card-layout.css";\n@import "./new-cards.css";\n'
)
print("Prepared model-card recipes and N26 shadow theme from this checkout.")
