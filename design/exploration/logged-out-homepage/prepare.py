"""Generate homepage recipes and styles from this checkout’s N26 library."""

import json
import os
import re
import shutil
import sys
from pathlib import Path

import django
from django.conf import settings
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler
from PIL import Image

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
                    "richtext": "n26.core.templatetags.richtext",
                }
            },
        }
    ],
)
django.setup()


def cotton_recipes():
    # The checkout path and template engine must be configured before importing.
    from n26.frontend.tooling.export_cotton_recipes import classes, input_recipe

    return classes, input_recipe


classes, input_recipe = cotton_recipes()


def render_component(source, context=None):
    markup = Template(CottonCompiler().process(source)).render(Context(context or {}))
    return re.sub(r">\s+<", "><", markup).strip()


def without_sources(stylesheet):
    return re.sub(r"^@source [^\n]+\n?", "", stylesheet, flags=re.MULTILINE)


homepage = {
    "button": {
        variant: classes(
            f'<c-ui.button variant="{variant}" size="sm">Action</c-ui.button>', "button"
        )[0]
        for variant in ("primary", "ghost")
    },
    "linkButton": {
        variant: classes(
            f'<c-ui.button href="/" variant="{variant}" size="sm">Action</c-ui.button>',
            "a",
        )[0]
        for variant in ("default", "primary")
    },
    "input": input_recipe(),
    "label": classes("<c-ui.label>Username</c-ui.label>", "label")[0],
    "footer": render_component((HERE / "homepage-footer.html").read_text()),
    "changelog": render_component(
        (HERE / "homepage-changelog.html").read_text(),
        json.loads((HERE / "homepage-changelog.json").read_text()),
    ),
}
(HERE / "src/homepage.json").write_text(json.dumps(homepage, indent=2) + "\n")
# Read current checkout components and tokens; generated paths stay local.
source = (UPSTREAM / "n26/designsystem/assets/app.css").read_text()
asset_root = (UPSTREAM / "n26/designsystem/assets").as_posix()
source = source.replace('@import "./', f'@import "{asset_root}/')
kit_source = (UPSTREAM / "n26/designsystem/assets/cotton-ui.sources.css").read_text()
kit_source = kit_source.replace(":root", ":host").replace(
    ".dark {", ":host(.dark), .dark {"
)
source = source.replace(
    f'@import "{asset_root}/cotton-ui.sources.css";',
    '@import "./cotton-ui.sources.css";',
)
source = source.replace(":root", ":host").replace(".dark {", ":host(.dark), .dark {")
# Keep the same upstream theme; generate only the utilities this page uses.
homepage_source = without_sources(source)
homepage_source = homepage_source.replace(
    "./cotton-ui.sources.css", "./homepage-cotton-ui.css"
)
(HERE / "src/homepage-cotton-ui.css").write_text(without_sources(kit_source))
layout = (UPSTREAM / "n26/core/templates/n26/layouts/base.html").read_text()
layout_styles = next(
    block
    for block in re.findall(r"<style>(.*?)</style>", layout, re.DOTALL)
    if "--n26-site-width:" in block
)
(HERE / "src/homepage-layout.css").write_text(
    layout_styles.replace(":root", ":host") + "\n"
)
(HERE / "src/homepage-theme.css").write_text(
    homepage_source
    + '\n@source "./homepage.jsx";\n@source "./homepage.json";\n@source inline("bg-gray-{50,100,200,300,400,500,600,700,800,900,950} bg-amber-{50,100,200,300,400,500,600,700,800,900,950}");\n@import "./homepage-layout.css";\n@import "./callout-card.css";\n@import "./homepage.css";\n'
)
assets = HERE / "public/homepage"
assets.mkdir(parents=True, exist_ok=True)
shutil.copyfile(
    UPSTREAM / "gyrinx/site/static/platform/img/brand/logo-gold-transparent-bg.svg",
    assets / "logo.svg",
)
shutil.copyfile(HERE / "assets/homepage/support.webp", assets / "support.webp")
with Image.open(
    UPSTREAM
    / "n23/core/static/core/img/content/93daeffd-9587-404a-b3e1-33eff4ce7398.jpg"
) as image:
    image.thumbnail((1440, 1440), Image.Resampling.LANCZOS)
    image.convert("RGB").save(assets / "hero.webp", "WEBP", quality=85, method=6)
for obsolete in ("hero.jpg", "patreon.png", "patreon.webp"):
    (assets / obsolete).unlink(missing_ok=True)
print("Prepared actual Cotton button/input recipes and upstream N26 theme.")
