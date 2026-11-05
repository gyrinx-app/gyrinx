"""Read the upstream design library without modifying its checkout."""

import json
import os
import re
import sys
from pathlib import Path


def prepare():
    HERE = Path(__file__).resolve().parent
    UPSTREAM = HERE.parents[2]
    sys.path.insert(0, str(UPSTREAM))
    from django.conf import settings

    settings.configure(
        INSTALLED_APPS=["django_cotton", "django_cotton_ui"],
        TEMPLATES=[
            {
                "BACKEND": "django.template.backends.django.DjangoTemplates",
                "DIRS": [str(UPSTREAM / "n26/core/templates")],
                "APP_DIRS": True,
            }
        ],
    )
    import django

    django.setup()
    from n26.core.colours import GANG_COLOURS
    from n26.frontend.tooling.export_cotton_recipes import (
        classes,
        dialog_recipe,
        input_recipe,
        native_select_recipe,
    )

    recipes = {
        "colours": [
            {"name": colour.capitalize(), "token": f"--color-{colour}-500"}
            for colour in GANG_COLOURS
        ],
        "button": {
            variant: classes(
                f'<c-ui.button variant="{variant}" size="sm">Action</c-ui.button>',
                "button",
            )[0]
            for variant in ("default", "primary", "success", "ghost", "subtle")
        },
        "input": input_recipe(),
        "select": native_select_recipe(),
        "dialog": dialog_recipe(),
        "label": classes("<c-ui.label>Address</c-ui.label>", "label")[0],
        "description": classes("<c-ui.description>Help</c-ui.description>", "div")[0],
        "error": classes('<c-ui.error message="Invalid address" />', "div")[0],
        "fileInput": classes('<c-n26.picture-input id="upload" />', "input")[0],
    }
    (HERE / "src/cotton.json").write_text(json.dumps(recipes, indent=2) + "\n")
    # Share the installed library's exact icon names with the editor and preview validator.
    icon_exports = (
        HERE / "node_modules/lucide-react/dist/esm/icons/index.mjs"
    ).read_text()
    icon_names = {
        name: export
        for export, name in re.findall(
            r"export \{ default as (\w+) \} from '\./([\w-]+)\.mjs';", icon_exports
        )
    }
    (HERE / "src/lucide-icons.json").write_text(json.dumps(icon_names, indent=2) + "\n")
    # Keep imports relative to the upstream stylesheet, then add playground classes.
    source = (UPSTREAM / "n26/designsystem/assets/app.css").read_text()
    assets = os.path.relpath(UPSTREAM / "n26/designsystem/assets", HERE / "src")
    source = source.replace('@import "./', f'@import "{assets}/')
    kit_path = UPSTREAM / "n26/designsystem/assets/cotton-ui.sources.css"
    (HERE / "src/cotton-ui.sources.css").write_text(
        kit_path.read_text()
        .replace(":root", ":host")
        .replace(".dark {", ":host(.dark), .dark {")
    )
    source = source.replace(
        f'@import "{assets}/cotton-ui.sources.css";',
        '@import "./cotton-ui.sources.css";',
    )
    source = source.replace('@source "', f'@source "{assets}/')
    source = source.replace(":root", ":host")
    source = source.replace(".dark {", ":host(.dark), .dark {")
    (HERE / "src/theme.css").write_text(
        source + '\n@source "./";\n@import "./editor.css";\n@import "./callouts.css";\n'
    )
    print("Prepared actual Cotton button/input recipes and upstream N26 theme.")


if __name__ == "__main__":
    prepare()
