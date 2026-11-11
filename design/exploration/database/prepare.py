"""Build this exploration's recipes from frozen Cotton inputs and N26 helpers."""

import argparse
import hashlib
import json
import os
import re
import shutil
import sys
from pathlib import Path
from types import SimpleNamespace as N

HERE = Path(__file__).resolve().parent
parser = argparse.ArgumentParser(description=__doc__)
parser.add_argument("--capture-reference", action="store_true")
args = parser.parse_args()
UPSTREAM = Path(os.environ.get("GYRINX_SOURCE", HERE.parents[2])).resolve()
FALLBACK = Path(os.environ.get("GYRINX_FALLBACK_SOURCE", UPSTREAM)).resolve()
sys.path.insert(0, str(UPSTREAM))
import django  # noqa: E402
from django.conf import settings  # noqa: E402

settings.configure(
    INSTALLED_APPS=["django_cotton", "django_cotton_ui"],
    TEMPLATES=[
        {
            "BACKEND": "django.template.backends.django.DjangoTemplates",
            "DIRS": [
                str(HERE / "reference/templates"),
                str(UPSTREAM / "n26/core/templates"),
                str(FALLBACK / "n26/core/templates"),
            ],
            "APP_DIRS": True,
            "OPTIONS": {
                "libraries": {
                    "icons": "n26.core.templatetags.icons",
                    "arith": "n26.core.templatetags.arith",
                    "theme": "n26.core.templatetags.theme",
                }
            },
        }
    ],
)
django.setup()
from cotton_templates import find, render, slot, walk  # noqa: E402
from django.template import Engine  # noqa: E402

from n26.frontend.tooling.export_cotton_recipes import classes, native_select_recipe  # noqa: E402

orig_find = Engine.find_template
origins = set()


def track(self, *pos, **kw):
    template, origin = orig_find(self, *pos, **kw)
    origins.add(Path(origin.name))
    return template, origin


Engine.find_template = track
header = render("""<c-n26.page-header title="Database" lead="Find profiles, weapons and more.">
<c-slot name="breadcrumb"><c-ui.breadcrumbs><c-ui.breadcrumbs.item href="/">Gyrinx</c-ui.breadcrumbs.item><c-ui.breadcrumbs.item :current="True">Database</c-ui.breadcrumbs.item></c-ui.breadcrumbs></c-slot>
<c-slot name="actions"><span data-cotton-slot="actions"></span></c-slot></c-n26.page-header>""")
section = render(
    """<c-n26.section title="__TITLE__" count="__COUNT__" id="__SECTION_ID__"><c-slot name="actions"><span data-cotton-slot="actions"></span></c-slot><span data-cotton-slot="content"></span></c-n26.section>"""
)
card = render(
    """<c-ui.card padding="none"><c-slot name="header"><span data-cotton-slot="header"></span></c-slot><span data-cotton-slot="content"></span></c-ui.card>"""
)
names = ["M", "WS", "BS", "S", "T", "W", "I", "A", "Ld", "Cl", "Wil", "Int"]
cells = [
    N(
        short_name=name,
        full_name=name,
        value=f"__STAT_{chr(65 + i)}__",
        first_of_group=i in (0, 3, 5, 8),
        highlighted=i >= 8,
        modified=False,
    )
    for i, name in enumerate(names)
]
model = N(
    statline=N(groups=[cells[:8], cells[8:]]),
    type_line="__TYPE__",
    xp="—",
    skills=[],
    equipment=[],
    counter_lines=[],
    weapons=[],
    powers=[],
    rows=[],
    choices=[],
)
body = render('<c-n26.model-card.body :card="card" mode="readonly" />', card=model)
details = find(body, lambda n: n["tag"] == "dl")
for i, term in enumerate(details["children"]):
    if isinstance(term, dict) and term["tag"] == "dt":
        text = "".join(c for c in term["children"] if isinstance(c, str)).strip()
        if text in ("Skills", "Gear"):
            details["children"][i + 1]["children"] = [slot(text.lower())]
body["children"].append(slot("details"))
weapon_cells = [
    N(
        short_name=name,
        full_name=name,
        first_of_group=False,
        highlighted=False,
        modified=False,
        value=f"__VALUE_{chr(65 + i)}__",
    )
    for i, name in enumerate(["SR", "LR", "Str", "AP", "L"])
]
weapon_header = render(
    '<tr><c-n26.statline.header :cells="cells"><c-slot name="leading"><th scope="col">Weapon / profile</th></c-slot></c-n26.statline.header></tr>',
    cells=weapon_cells,
)
weapon_row = render(
    '<tr><c-n26.statline.cells :cells="cells"><c-slot name="leading"><th scope="row"><span data-cotton-slot="profile-name"></span></th></c-slot></c-n26.statline.cells></tr>',
    cells=weapon_cells,
)
nav = render(
    """<c-n26.site.nav title="Gyrinx" href="/" sticky="1" class="dark"><c-slot name="logo"><img src="/logo.svg" width="24" height="24" alt="" /></c-slot><c-slot name="switcher"><span data-cotton-slot="switcher"></span></c-slot><c-slot name="actions"><span data-cotton-slot="actions"></span></c-slot></c-n26.site.nav>"""
)
nav_header = find(nav, lambda n: n["tag"] == "header")
nav_header["children"] = [
    n
    for n in nav_header["children"]
    if not isinstance(n, dict) or n["tag"] != "noscript"
]
find(nav, lambda n: "ml-auto" in n["attrs"].get("class", "").split())["children"] = [
    slot("actions"),
    slot("navigation"),
]
base_path = HERE / "reference/layout.html"
if not base_path.exists():
    original = (FALLBACK / "n26/core/templates/n26/layouts/base.html").read_text()
    layout_attrs = re.search(r"<main ([^>]+)>", original).group(1)
    layout_width = next(
        v
        for v in re.findall(r"<style>(.*?)</style>", original, re.S)
        if "--n26-site-width" in v
    )
    base_path.write_text(
        f"<style>{layout_width}</style>\n<main {layout_attrs}></main>\n"
    )
layout_text = base_path.read_text()
main_attrs = dict(
    re.findall(
        r'([\w-]+)="([^"]*)"', re.search(r"<main ([^>]+)>", layout_text).group(1)
    )
)
layout_style = next(
    v
    for v in re.findall(r"<style>(.*?)</style>", layout_text, re.S)
    if "--n26-site-width" in v
)

search = render('<c-n26.search-bar :nested="True" />')
search_field = find(search, lambda n: n["tag"] == "input")
all_divs = [n for n in walk(search) if n["tag"] == "div"]
search_recipe = {
    "root": all_divs[0]["attrs"]["class"],
    "field": all_divs[1]["attrs"]["class"],
    "icon": find(search, lambda n: n["tag"] == "span")["attrs"]["class"],
    "input": search_field["attrs"]["class"],
}
recipes = {
    "button": {
        variant: classes(
            f'<c-ui.button variant="{variant}" size="sm">Action</c-ui.button>', "button"
        )[0]
        for variant in ("default", "primary", "ghost", "text")
    },
    "badge": classes('<c-ui.badge variant="pill">Example</c-ui.badge>', "span")[0],
    "select": native_select_recipe(),
    "search": search_recipe,
}
if args.capture_reference:
    for path in origins:
        for root in (UPSTREAM, FALLBACK):
            try:
                relative = path.relative_to(root / "n26/core/templates")
            except ValueError:
                continue
            target = HERE / "reference/templates" / relative
            target.parent.mkdir(parents=True, exist_ok=True)
            if not target.exists():
                shutil.copy2(path, target)
            break
provenance = {
    str(path.relative_to(HERE)): hashlib.sha256(path.read_bytes()).hexdigest()
    for path in sorted((HERE / "reference/templates").rglob("*.html"))
}
provenance[str(base_path.relative_to(HERE))] = hashlib.sha256(
    base_path.read_bytes()
).hexdigest()
presentation = dict(
    header=header,
    section=section,
    card=card,
    modelBody=body,
    weaponHeader=weapon_header,
    weaponRow=weapon_row,
    results={
        "tag": "div",
        "attrs": {"class": "min-w-0"},
        "children": [slot("content")],
    },
    nav=nav,
    layout={"attrs": main_attrs},
    layoutStyle=layout_style,
    provenance=provenance,
)
(HERE / "src/presentation.json").write_text(json.dumps(presentation, indent=2) + "\n")
(HERE / "src/cotton.json").write_text(json.dumps(recipes, indent=2) + "\n")
print(
    f"Prepared Database Cotton presentation from {len(provenance)} reference templates."
)
