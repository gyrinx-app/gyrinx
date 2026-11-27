"""Export the real Cotton campaign sheet as a React-owned tree.

Presentation comes from upstream templates. Markers identify bounded interactive
regions; all user text is passed to React as text, never evaluated as HTML.
"""

import hashlib
import json
import re
from datetime import date
from html.parser import HTMLParser
from types import SimpleNamespace as N

from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler

VOID = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


class Tree(HTMLParser):
    def __init__(self, source):
        super().__init__(convert_charrefs=True)
        self.root = {"tag": "fragment", "attrs": {}, "children": []}
        self.stack = [self.root]
        self.feed(source)

    def handle_starttag(self, tag, attrs):
        node = {"tag": tag, "attrs": dict(attrs), "children": []}
        self.stack[-1]["children"].append(node)
        if tag not in VOID:
            self.stack.append(node)

    def handle_startendtag(self, tag, attrs):
        self.handle_starttag(tag, attrs)
        if tag not in VOID:
            self.stack.pop()

    def handle_endtag(self, tag):
        for i in range(len(self.stack) - 1, 0, -1):
            if self.stack[i]["tag"] == tag:
                self.stack = self.stack[:i]
                break

    def handle_data(self, text):
        if text.strip():
            self.stack[-1]["children"].append(text)


def render(source, **context):
    return Tree(
        Template(CottonCompiler().process(source)).render(Context(context))
    ).root


def slot(name):
    return {"tag": "span", "attrs": {"data-campaign-slot": name}, "children": []}


def walk(node):
    if isinstance(node, str):
        return
    yield node
    for child in node["children"]:
        yield from walk(child)


def find(node, predicate):
    return next(n for n in walk(node) if predicate(n))


def export_campaign_templates(here, upstream):
    sheet = N(
        name="__CAMPAIGN_NAME__",
        gang_count=3,
        battles_fought=2,
        campaign_type="Territory campaign",
        campaign_type_description="",
        arbitrator="louis",
        budget=1000,
        summary="<p>A territory campaign along the Ash Road. Rival gangs compete for control of the trade route.</p>",
        gangs=[],
        assets=[],
        tables_href="",
        add_asset_type_href="",
        counter_columns=["Reputation", "Income"],
    )
    source = """<c-n26.view.campaign-sheet :sheet="sheet">
      <c-slot name="breadcrumb"><span data-campaign-slot="breadcrumb"></span></c-slot>
      <c-slot name="arbitrator"><span data-campaign-slot="arbitrator"></span></c-slot>
      <c-slot name="trailing"><span data-campaign-slot="heading-switcher"></span></c-slot>
      <c-slot name="share"><span data-campaign-slot="share"></span></c-slot>
      <c-slot name="actions"><span data-campaign-slot="actions"></span></c-slot>
      <c-slot name="gangs_actions"><span data-campaign-slot="gangs-actions"></span></c-slot>
      <c-slot name="players_actions"><span data-campaign-slot="players-actions"></span></c-slot>
      <c-slot name="battles_actions"><span data-campaign-slot="battles-actions"></span></c-slot>
      <c-slot name="log_actions"><span data-campaign-slot="log-actions"></span></c-slot>
      <c-slot name="log"><span data-campaign-slot="activity"></span></c-slot>
      <c-slot name="battles"><span data-campaign-slot="battles"></span></c-slot>
      <c-slot name="players"><span data-campaign-slot="players"></span></c-slot>
    </c-n26.view.campaign-sheet>"""
    campaign = render(source, sheet=sheet)
    for node in walk(campaign):
        node["children"] = [
            "__GANG_COUNT__"
            if child == "3"
            else "__BATTLE_COUNT__"
            if child == "2"
            else child.replace("3 gangs", "__GANG_COUNT__ __GANG_NOUN__").replace(
                "2 recorded", "__BATTLE_COUNT__ recorded"
            )
            if isinstance(child, str)
            else child
            for child in node["children"]
        ]
    root = campaign["children"][0]
    root["attrs"]["class"] += " __CAMPAIGN_CLASS__"
    action_slot = find(
        campaign, lambda n: n["attrs"].get("data-campaign-slot") == "actions"
    )
    action_row = find(campaign, lambda n: action_slot in n["children"])
    action_row["attrs"]["class"] += " cp-campaign-action-row"
    action_row["children"].insert(0, slot("period"))
    find(campaign, lambda n: n["attrs"].get("id") == "n26-campaign-gangs")[
        "children"
    ] = [slot("gangs")]
    find(campaign, lambda n: n["attrs"].get("id") == "n26-campaign-assets")[
        "children"
    ] = [slot("assets")]
    overview = find(campaign, lambda n: n["attrs"].get("id") == "campaign-overview")
    metadata = find(overview, lambda n: n["tag"] == "dl")
    from copy import deepcopy

    duration_row = deepcopy(
        next(child for child in metadata["children"] if isinstance(child, dict))
    )
    find(duration_row, lambda n: n["tag"] == "dt")["children"] = ["Campaign duration"]
    find(duration_row, lambda n: n["tag"] == "dd")["children"] = [
        "__CAMPAIGN_DURATION__"
    ]
    metadata["children"] = [
        row
        for row in metadata["children"]
        if not isinstance(row, dict)
        or find(row, lambda n: n["tag"] == "dt")["children"] != ["Arbitrator"]
    ]
    metadata["children"].append(duration_row)
    # Reuse the Cotton metadata and description, with a compact unboxed layout.
    metadata["attrs"]["class"] = "cp-campaign-metadata"
    for row in metadata["children"]:
        if not isinstance(row, dict):
            continue
        row["attrs"]["class"] = "cp-campaign-metadata-row"
        term = find(row, lambda n: n["tag"] == "dt")
        term["attrs"]["class"] = "text-xs text-muted"
        if term["children"] == ["Gang budget"]:
            term["children"] = ["Founding budget"]
        find(row, lambda n: n["tag"] == "dd")["attrs"]["class"] = "text-xs font-medium"
    action_row["children"].insert(1, slot("metadata"))
    description = next(
        n
        for n in overview["children"]
        if isinstance(n, dict) and metadata not in list(walk(n))
    )
    description["attrs"]["class"] = "cp-campaign-description"
    description["children"] = [slot("description")]
    overview["attrs"]["class"] = "min-w-0"
    overview["children"] = [description]
    title = find(campaign, lambda n: n["tag"] == "h1")
    title["attrs"]["class"] += " cp-campaign-title __CAMPAIGN_NAME_CLASS__"
    title_row = find(campaign, lambda n: title in n["children"])
    title_block = find(campaign, lambda n: title_row in n["children"])
    title_block["children"].insert(
        title_block["children"].index(title_row) + 1, slot("arbitrator-line")
    )
    figures = find(campaign, lambda n: n["attrs"].get("id") == "n26-campaign-figures")
    find(campaign, lambda n: figures in n["children"])["attrs"]["class"] += (
        " cp-campaign-figures-host"
    )
    find(campaign, lambda n: figures in n["children"])["children"].append(
        slot("heading-actions")
    )
    figures_list = find(figures, lambda n: n["tag"] == "dl")
    cycle_figure = deepcopy(
        next(n for n in figures_list["children"] if isinstance(n, dict))
    )
    for node in walk(cycle_figure):
        node["attrs"] = {
            k: v.replace("Gangs in this campaign", "Cycles in this campaign").replace(
                "Gangs", "Cycles"
            )
            if isinstance(v, str)
            else v
            for k, v in node["attrs"].items()
        }
        node["children"] = [
            c.replace("Gangs in this campaign", "Cycles in this campaign")
            .replace("Gangs", "Cycles")
            .replace("__GANG_COUNT__", "__CYCLE_COUNT__")
            if isinstance(c, str)
            else c
            for c in node["children"]
        ]
    figures_list["children"].append(cycle_figure)
    section = render("""<c-n26.section :boxed="True" :flush="True" title="__SECTION_TITLE__" class="__SECTION_CLASS__">
      <c-slot name="actions"><span data-campaign-slot="actions"></span></c-slot>
      <span data-campaign-slot="content"></span>
    </c-n26.section>""")
    header = render("""<c-n26.page-header title="__PAGE_TITLE__">
       <c-slot name="breadcrumb"><span data-campaign-slot="breadcrumb"></span></c-slot>
       <c-slot name="actions"><span data-campaign-slot="actions"></span></c-slot>
    </c-n26.page-header>""")
    gang = N(
        name="__GANG_NAME__",
        gang_type="__GANG_TYPE__",
        owner=N(username="__OWNER__", pk=None, profile=None),
        href="/gang/",
        colour="violet",
        rating="__RATING__",
        credits="__CREDITS__",
        wealth="__WEALTH__",
        over_budget=False,
        credits_unlimited=False,
        credits_href="",
        remove_href="",
        counters=[N(value="__REPUTATION__", href=""), N(value="__INCOME__", href="")],
        detail_colspan=6,
        details=[
            N(label="Settlement", text="Settlement", rolls=[]),
            N(label="Territories", text="__TERRITORIES__", rolls=[]),
        ],
    )
    gangs = render(
        '<c-n26.campaign-gangs :sheet="sheet" />',
        sheet=N(gangs=[gang], counter_columns=["Reputation", "Income"]),
    )
    for node in walk(gangs):
        if "style" in node["attrs"]:
            node["attrs"]["style"] = node["attrs"]["style"].replace(
                "--color-violet-500", "--color-__GANG_COLOUR__-500"
            )
    gang_table = find(gangs, lambda n: n["tag"] == "table")
    gang_body = find(gangs, lambda n: n["tag"] == "tbody")
    gang_table["children"] = [
        n for n in gang_table["children"] if n is not gang_body
    ] + [slot("bodies")]
    asset_entry = N(
        name="__ASSET_NAME__",
        asset_name="",
        href="",
        income="__ASSET_INCOME__",
        boons=[],
        held=True,
        holder_href="/gang/",
        holder="__ASSET_HOLDER__",
        unassign_href="",
        transfer_href="",
        assign_href="",
        remove_href="",
    )
    assets = render(
        '<c-n26.campaign-assets :table="table" />',
        table=N(
            plural="Territories",
            label="Territory",
            held="__ASSET_HELD__",
            unclaimed="__ASSET_UNCLAIMED__",
            entries=[asset_entry],
            add_href="",
            create_href="",
            roll_href="",
        ),
    )
    asset_body = find(assets, lambda n: n["tag"] == "tbody")
    asset_row = asset_body["children"][0]
    asset_body["children"] = [slot("entries")]
    asset_entry.held = False
    asset_entry.income = 0
    unclaimed_assets = render(
        '<c-n26.campaign-assets :table="table" />',
        table=N(
            plural="Territories",
            label="Territory",
            held=0,
            unclaimed=1,
            entries=[asset_entry],
            add_href="",
            create_href="",
            roll_href="",
        ),
    )
    unclaimed_row = find(unclaimed_assets, lambda n: n["tag"] == "tbody")["children"][0]
    nav = render("""<c-n26.site.nav title="Gyrinx" href="/campaign/" sticky="1" class="dark">
       <c-slot name="logo"><img src="/static/history/logo.svg" width="24" height="24" alt="" /></c-slot>
       <c-slot name="switcher"><span data-campaign-slot="switcher"></span></c-slot>
       <c-slot name="actions"><span data-campaign-slot="actions"></span></c-slot>
    </c-n26.site.nav>""")
    nav_header = find(nav, lambda n: n["tag"] == "header")
    nav_header["children"] = [
        n
        for n in nav_header["children"]
        if not isinstance(n, dict) or n["tag"] != "noscript"
    ]
    nav_right = find(nav, lambda n: "ml-auto" in n["attrs"].get("class", "").split())
    nav_right["children"] = [slot("actions"), slot("navigation")]

    def template_path(relative):
        reference = here / "reference" / relative
        return (
            reference
            if reference.exists()
            else upstream / "n26/core/templates" / relative
        )

    files = [
        "cotton/n26/view/campaign_sheet.html",
        "cotton/n26/campaign_gangs.html",
        "cotton/n26/campaign_assets.html",
        "cotton/n26/section.html",
        "cotton/n26/site/nav/index.html",
        "n26/campaign.html",
    ]
    provenance = {
        str(template_path(p)): hashlib.sha256(template_path(p).read_bytes()).hexdigest()
        for p in files
    }
    base_path = template_path("n26/layouts/base.html")
    base = base_path.read_text()
    main_attrs = dict(
        re.findall(r'([\w-]+)="([^"]*)"', re.search(r"<main ([^>]+)>", base).group(1))
    )
    layout = {"tag": "main", "attrs": main_attrs, "children": [slot("content")]}
    width_style = next(
        value
        for value in re.findall(r"<style>(.*?)</style>", base, re.S)
        if "--n26-site-width" in value
    )
    owner = N(username="louis", pk=None, profile=None)
    breadcrumbs = render(
        """<c-ui.breadcrumbs>
      <c-ui.breadcrumbs.item><c-n26.user-link :user="owner" tone="current" /></c-ui.breadcrumbs.item>
      <c-ui.breadcrumbs.item href="/campaign/">Campaigns</c-ui.breadcrumbs.item>
      <c-ui.breadcrumbs.item :current="True">__CAMPAIGN_NAME__</c-ui.breadcrumbs.item>
    </c-ui.breadcrumbs>""",
        owner=owner,
    )
    edit_breadcrumbs = render(
        """<c-ui.breadcrumbs>
      <c-ui.breadcrumbs.item><c-n26.user-link :user="owner" tone="current" /></c-ui.breadcrumbs.item>
      <c-ui.breadcrumbs.item href="/campaign/">Campaigns</c-ui.breadcrumbs.item>
      <c-ui.breadcrumbs.item href="/campaign/">__CAMPAIGN_NAME__</c-ui.breadcrumbs.item>
      <c-ui.breadcrumbs.item :current="True">__PAGE_NAME__</c-ui.breadcrumbs.item>
    </c-ui.breadcrumbs>""",
        owner=owner,
    )
    badge = render('<c-ui.badge color="ink" size="sm">__BADGE_TEXT__</c-ui.badge>')
    active_badge = render(
        '<c-ui.badge color="orange" size="sm">__BADGE_TEXT__</c-ui.badge>'
    )
    accepted_badge = render('<c-ui.badge color="green" size="sm">Accepted</c-ui.badge>')
    table = render(
        '<c-ui.table><span data-campaign-slot="content"></span></c-ui.table>'
    )
    battle_source = (
        template_path("n26/campaign.html")
        .read_text()
        .split('<c-slot name="battles">', 1)[1]
        .split("</c-slot>", 1)[0]
    )
    battle_source = re.sub(r"{% url [^%]+%}", "/campaign/?view=battles", battle_source)
    battle = N(
        title="__BATTLE_TITLE__",
        date=date(2026, 10, 23),
        result_label="__BATTLE_RESULT__",
        gang_outcomes=[
            (N(name="__FIRST_GANG__", colour="violet"), True),
            (N(name="__SECOND_GANG__", colour="orange"), False),
        ],
    )
    battle_tree = render(battle_source, battles=[battle])
    battle_row = find(
        battle_tree,
        lambda n: (
            n["tag"] == "li" and "relative" in n["attrs"].get("class", "").split()
        ),
    )
    for node in walk(battle_row):
        if "style" in node["attrs"]:
            node["attrs"]["style"] = (
                node["attrs"]["style"]
                .replace("--color-violet-500", "--color-__FIRST_COLOUR__-500")
                .replace("--color-orange-500", "--color-__SECOND_COLOUR__-500")
            )
        if "datetime" in node["attrs"]:
            node["attrs"]["datetime"] = "__BATTLE_DATE__"
        node["children"] = [
            "__BATTLE_DATE_LABEL__" if child == "23 Oct 2026" else child
            for child in node["children"]
        ]
    trophy = find(battle_row, lambda n: n["attrs"].get("aria-label") == "Winner")
    for node in walk(battle_row):
        if trophy in node["children"]:
            node["children"] = [
                slot("winner") if child is trophy else child
                for child in node["children"]
            ]
            break
    battle_row["children"].append(slot("period"))
    for file in [
        "campaign_figures.html",
        "campaign_gangs.html",
        "campaign_assets_section.html",
    ]:
        fallback = template_path("n26/includes/" + file)
        provenance[str(fallback)] = hashlib.sha256(fallback.read_bytes()).hexdigest()
    provenance[str(base_path)] = hashlib.sha256(base_path.read_bytes()).hexdigest()
    from copy import deepcopy

    management_section = deepcopy(section)
    management_heading = find(management_section, lambda n: n["tag"] == "h2")
    management_heading["tag"] = "div"
    management_heading["attrs"] = {"data-campaign-slot": "heading-control"}
    management_heading["children"] = []
    status_dot = render(
        '<c-n26.color-swatch color="var(--cp-status-colour)" class="cp-campaign-status-dot" />'
    )
    data = {
        "statusDot": status_dot,
        "metadata": metadata,
        "badge": badge,
        "activeBadge": active_badge,
        "unclaimedAssetRow": unclaimed_row,
        "battleRow": battle_row,
        "trophy": trophy,
        "acceptedBadge": accepted_badge,
        "layout": layout,
        "layoutStyle": width_style,
        "breadcrumbs": breadcrumbs,
        "editBreadcrumbs": edit_breadcrumbs,
        "table": table,
        "campaign": campaign,
        "section": section,
        "managementSection": management_section,
        "header": header,
        "gangs": gangs,
        "gangBody": gang_body,
        "assets": assets,
        "assetRow": asset_row,
        "nav": nav,
        "provenance": provenance,
    }
    for name, tree in list(data.items()):
        if name in ("provenance", "layoutStyle"):
            continue
        for node in walk(tree):
            if node["tag"].startswith("c-"):
                raise ValueError(f"Cotton did not render {node['tag']} in {name}.")
    (here / "src/campaign-base.json").write_text(json.dumps(data, indent=2) + "\n")
    print(
        "Prepared campaign sheet, gangs, assets, sections and navigation from actual upstream Cotton templates."
    )
