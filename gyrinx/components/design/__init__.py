"""Gyrinx design-system components.

A component for every recurring pattern in ``docs/DESIGN-SYSTEM.md`` — so call
sites compose named components instead of hand-writing Bootstrap class strings.

    from gyrinx.components.design import Button, Alert, PageHeader, SectionHeader
"""

from __future__ import annotations

from .badges import Badge, StateBadge
from .buttons import Button, ButtonGroup, SubmitButton
from .containers import Card, CardBody, CardHeader, Container, SectionHeader
from .feedback import Alert, Messages
from .forms import CsrfInput, Form, FormField, FormFields
from .icons import ICONS, Icon
from .nav import NavTabs, SearchBar, Tab
from .page import (
    ActionLink,
    BackLink,
    InfoColumn,
    InfoColumns,
    InlineActionMenu,
    MetaItem,
    MetaRow,
    PageHeader,
    PageShell,
)
from .tables import Table, TBody, Td, Th, Tr
from .typography import CapsLabel, CommaList, Dot, EmptyState, InlineNone

__all__ = [
    # icons
    "Icon",
    "ICONS",
    # buttons
    "Button",
    "SubmitButton",
    "ButtonGroup",
    # badges
    "Badge",
    "StateBadge",
    # feedback
    "Alert",
    "Messages",
    # containers
    "Container",
    "SectionHeader",
    "Card",
    "CardHeader",
    "CardBody",
    # typography
    "CapsLabel",
    "CommaList",
    "Dot",
    "EmptyState",
    "InlineNone",
    # nav
    "NavTabs",
    "Tab",
    "SearchBar",
    # forms
    "Form",
    "FormField",
    "FormFields",
    "CsrfInput",
    # tables
    "Table",
    "TBody",
    "Tr",
    "Td",
    "Th",
    # page
    "PageHeader",
    "BackLink",
    "MetaItem",
    "MetaRow",
    "InfoColumn",
    "InfoColumns",
    "InlineActionMenu",
    "ActionLink",
    "PageShell",
]
