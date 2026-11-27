"""Read the upstream design library without modifying its source snapshot."""

import json
import os
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
            "DIRS": [str(HERE / "reference"), str(UPSTREAM / "n26/core/templates")],
            "APP_DIRS": True,
            "OPTIONS": {
                "libraries": {
                    "icons": "n26.core.templatetags.icons",
                    "theme": "n26.core.templatetags.theme",
                    "richtext": "n26.core.templatetags.richtext",
                    "platform_tags": "campaign_template_tags",
                    "action_menu": "campaign_template_tags",
                    "badge_tags": "gyrinx.site.templatetags.badge_tags",
                }
            },
        }
    ],
)
django.setup()
from campaign_templates import export_campaign_templates  # noqa: E402

from n26.frontend.tooling.export_cotton_recipes import (  # noqa: E402
    classes,
    dialog_recipe,
    input_recipe,
    native_select_recipe,
)

export_campaign_templates(HERE, UPSTREAM)

recipes = {
    "button": {
        variant: classes(
            f'<c-ui.button variant="{variant}" size="sm">Action</c-ui.button>', "button"
        )[0]
        for variant in ("default", "primary", "success", "ghost", "subtle", "text")
    },
    "input": input_recipe(),
    "select": native_select_recipe(),
    "textarea": classes('<c-ui.textarea size="sm" height="sm" />', "textarea")[0],
    "dialog": dialog_recipe(),
    "label": classes("<c-ui.label>Address</c-ui.label>", "label")[0],
}
(HERE / "src/cotton.json").write_text(json.dumps(recipes, indent=2) + "\n")
# Keep imports relative to the upstream stylesheet, then add playground classes.
source = (UPSTREAM / "n26/designsystem/assets/app.css").read_text()
relative = Path(
    os.path.relpath(UPSTREAM / "n26/designsystem/assets", HERE / "src")
).as_posix()
source = source.replace('@import "./', f'@import "{relative}/')
kit_path = UPSTREAM / "n26/designsystem/assets/cotton-ui.sources.css"
(HERE / "src/cotton-ui.sources.css").write_text(
    kit_path.read_text()
    .replace(":root", ":host")
    .replace(".dark {", ":host(.dark), .dark {")
)
source = source.replace(
    f'@import "{relative}/cotton-ui.sources.css";', '@import "./cotton-ui.sources.css";'
)
source = source.replace('@source "', f'@source "{relative}/')
source = source.replace(":root", ":host")
source = source.replace(".dark {", ":host(.dark), .dark {")
(HERE / "src/theme.css").write_text(
    source + '\n@source "./";\n@import "./surface.css";\n@import "./campaign.css";\n'
)
print("Prepared campaign Cotton trees, recipes and shadow theme.")
