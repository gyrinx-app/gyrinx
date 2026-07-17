"""A living gallery of the component library, rendered with the components.

Registered under ``core/debug/components.html`` and served at
``/_debug/components/`` (development only). Doubles as a visual smoke test.
"""

from __future__ import annotations

from typing import Any

from ..design import (
    ActionLink,
    Alert,
    Badge,
    Button,
    ButtonGroup,
    CapsLabel,
    CommaList,
    Container,
    EmptyState,
    Icon,
    InfoColumn,
    InfoColumns,
    InlineActionMenu,
    InlineNone,
    MetaItem,
    MetaRow,
    NavTabs,
    PageHeader,
    SearchBar,
    SectionHeader,
    StateBadge,
    Table,
    TBody,
    Tab,
    Td,
    Tr,
)
from ..elements import Node, fragment
from ..layout import Page
from ..registry import register_page
from ..tags import code, div, h2, p, strong
from ..design.containers import Card, CardBody, CardHeader


def _section(title: str, *examples: Node, note: str | None = None) -> Node:
    return div(class_="vstack gap-3")[
        div(class_="border-bottom pb-1")[h2(class_="h4 mb-0")[title]],
        p(class_="text-secondary mb-0")[note] if note else None,
        div(class_="d-flex flex-wrap gap-2 align-items-start")[examples],
    ]


def _swatch(label: str, node: Node) -> Node:
    return div(class_="border rounded p-2 vstack gap-1", style={"min-width": "8rem"})[
        div(class_="caps-label")[label],
        div[node],
    ]


@register_page("core/debug/components.html")
def gallery_page(context: dict[str, Any]) -> Page:
    buttons = _section(
        "Buttons",
        _swatch("primary", Button("Open", variant="primary")),
        _swatch("success", Button("Save", variant="success", size=None)),
        _swatch("danger", Button("Delete", variant="danger", icon="delete")),
        _swatch("secondary", Button("Cancel", variant="secondary")),
        _swatch("outline", Button("Sign In", variant="light", outline=True)),
        _swatch("link", Button("Edit", href="#", icon="edit")),
        _swatch(
            "group",
            ButtonGroup(
                Button("Edit", icon="edit"),
                Button("Add", variant="success", icon="add"),
                nav=True,
            ),
        ),
    )
    badges = _section(
        "Badges",
        _swatch("primary", Badge("120¢", variant="primary")),
        _swatch("secondary", Badge("5", variant="secondary")),
        _swatch("active", StateBadge("active")),
        _swatch("injured", StateBadge("injured")),
        _swatch("dead", StateBadge("dead")),
    )
    alerts = div(class_="vstack gap-3")[
        div(class_="border-bottom pb-1")[h2(class_="h4 mb-0")["Alerts"]],
        div(class_="vstack gap-2")[
            Alert("Action completed successfully.", variant="success"),
            Alert("Something went wrong with your request.", variant="danger"),
            Alert("This action cannot be undone.", variant="warning"),
            Alert("Changes here will be logged to the campaign.", variant="info"),
            Alert(
                fragment[
                    strong["Remove gang?"],
                    p(class_="mb-0")["The gang will be archived."],
                ],
                variant="warning",
            ),
            Alert("Dismissible flash message.", variant="success", dismissible=True),
        ],
    ]
    containers = _section(
        "Containers & cards",
        div(class_="w-100 vstack gap-3")[
            Container("Standard grouping container (border rounded p-3)."),
            Container("Compact container (border rounded p-2).", compact=True),
            SectionHeader(
                "Section title", action_href="#", action_text="Add", action_icon="add"
            ),
            Card(
                CardHeader("Card header"),
                CardBody("Card body — reserved for fighter grids."),
            ),
        ],
    )
    tables = div(class_="vstack gap-3")[
        div(class_="border-bottom pb-1")[h2(class_="h4 mb-0")["Table"]],
        Table(
            TBody(
                Tr[Td["Ganger"], Td["Lasgun"], Td[Badge("80¢", variant="primary")]],
                Tr[Td["Juve"], Td[InlineNone()], Td[Badge("40¢", variant="primary")]],
            ),
            headers=["Fighter", "Weapon", "Cost"],
        ),
    ]
    navs = div(class_="vstack gap-3")[
        div(class_="border-bottom pb-1")[h2(class_="h4 mb-0")["Nav & search"]],
        NavTabs(
            [
                Tab("Overview", href="#", active=True),
                Tab("Gear", href="#"),
                Tab("Skills", href="#"),
            ]
        ),
        div(style={"max-width": "24rem"})[SearchBar(value="")],
    ]
    typography = _section(
        "Typography",
        _swatch("caps label", CapsLabel("Status")),
        _swatch("comma list", CommaList(["Nerves of Steel", "Spring Up", "Berserker"])),
        _swatch("empty state", EmptyState("No fighters yet.")),
        _swatch("inline none", InlineNone()),
    )
    page_header = div(class_="vstack gap-3")[
        div(class_="border-bottom pb-1")[h2(class_="h4 mb-0")["Page header & meta"]],
        div(class_="border rounded p-3")[
            PageHeader(
                "Iron Skulls",
                actions=ButtonGroup(
                    Button("Edit", icon="edit"),
                    Button("Add Fighter", variant="success", icon="add"),
                    nav=True,
                ),
                meta=MetaRow(
                    [
                        MetaItem("Underhive Boss", icon="person"),
                        MetaItem("Public", icon="eye"),
                    ]
                ),
            ),
        ],
        InfoColumns(
            [
                InfoColumn("Status", "In Progress"),
                InfoColumn("Budget", "1500¢"),
                InfoColumn("Content packs", "Scavvy"),
            ]
        ),
    ]
    inline_menu = div(class_="vstack gap-3")[
        div(class_="border-bottom pb-1")[h2(class_="h4 mb-0")["Inline action menu"]],
        div(class_="border rounded p-3")[
            div["Lasgun"],
            InlineActionMenu(
                [
                    ActionLink("Edit", href="#"),
                    ActionLink("Accessories", href="#"),
                    ActionLink("Cost", href="#"),
                    ActionLink("Reassign", href="#"),
                    ActionLink("Delete", href="#", variant="danger"),
                ]
            ),
        ],
    ]
    icons = _section(
        "Semantic icons",
        *[
            _swatch(name, div(class_="fs-4")[Icon(name)])
            for name in [
                "add",
                "edit",
                "delete",
                "back",
                "search",
                "warning",
                "info",
                "confirm",
                "more",
                "pack",
                "archive",
                "clone",
            ]
        ],
    )

    content = div(class_="col-12 px-0 vstack gap-5 pb-5")[
        div[
            PageHeader("Component library", subtitle_level=True),
            p(class_="text-secondary")[
                "Living gallery of the ",
                code["gyrinx.components"],
                " design-system components. Every element on this page is rendered from Python components — see ",
                code["gyrinx/components/design/"],
                ".",
            ],
        ],
        buttons,
        badges,
        alerts,
        containers,
        tables,
        navs,
        typography,
        page_header,
        inline_menu,
        icons,
    ]
    return Page(title="Component library", content=content)
