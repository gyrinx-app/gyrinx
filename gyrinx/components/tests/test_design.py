"""Tests for the design-system components."""

from __future__ import annotations

from gyrinx.components import render
from gyrinx.components.design import (
    Alert,
    Badge,
    Button,
    ButtonGroup,
    CapsLabel,
    CommaList,
    Container,
    Dot,
    EmptyState,
    Icon,
    InlineNone,
    NavTabs,
    SearchBar,
    SectionHeader,
    StateBadge,
    SubmitButton,
    Tab,
    Table,
)
from gyrinx.components.design.page import (
    ActionLink,
    BackLink,
    InfoColumn,
    InfoColumns,
    InlineActionMenu,
    MetaItem,
    MetaRow,
    PageHeader,
)


# --------------------------------------------------------------------------
# Icons
# --------------------------------------------------------------------------


def test_icon_raw_name():
    assert render(Icon("pencil")) == '<i class="bi-pencil"></i>'


def test_icon_semantic_name():
    assert render(Icon("edit")) == '<i class="bi-pencil"></i>'
    assert render(Icon("add")) == '<i class="bi-plus-lg"></i>'


def test_icon_strips_bi_prefix():
    assert render(Icon("bi-star")) == '<i class="bi-star"></i>'


def test_icon_extra_class():
    assert render(Icon("pencil", class_="fs-7")) == '<i class="bi-pencil fs-7"></i>'


# --------------------------------------------------------------------------
# Buttons
# --------------------------------------------------------------------------


def test_button_default():
    assert (
        render(Button("Save"))
        == '<button class="btn btn-primary btn-sm" type="button">Save</button>'
    )


def test_button_link_when_href():
    assert (
        render(Button("Edit", href="/x"))
        == '<a class="btn btn-primary btn-sm" href="/x">Edit</a>'
    )


def test_button_variant_and_size():
    assert (
        render(Button("Go", variant="success", size=None))
        == '<button class="btn btn-success" type="button">Go</button>'
    )


def test_button_outline():
    out = render(Button("x", outline=True, variant="light"))
    assert 'class="btn btn-outline-light btn-sm"' in out


def test_button_with_icon():
    out = render(Button("Edit", icon="pencil", href="/x"))
    assert (
        out
        == '<a class="btn btn-primary btn-sm" href="/x"><i class="bi-pencil"></i> Edit</a>'
    )


def test_submit_button_defaults_success():
    out = render(SubmitButton("Create"))
    assert out == '<button class="btn btn-success" type="submit">Create</button>'


def test_button_group_nav():
    out = render(ButtonGroup(Button("a"), nav=True))
    assert out.startswith('<nav class="nav btn-group flex-nowrap">')


# --------------------------------------------------------------------------
# Badges
# --------------------------------------------------------------------------


def test_badge():
    assert (
        render(Badge("5", variant="primary"))
        == '<span class="badge text-bg-primary">5</span>'
    )


def test_state_badge():
    assert (
        render(StateBadge("dead")) == '<span class="badge text-bg-danger">Dead</span>'
    )
    assert "text-bg-warning" in render(StateBadge("injured"))
    assert "text-bg-success" in render(StateBadge("active"))


# --------------------------------------------------------------------------
# Alerts
# --------------------------------------------------------------------------


def test_alert_default_info_icon():
    out = render(Alert("Note", variant="info"))
    assert out == (
        '<div class="alert alert-info alert-icon" role="alert">'
        '<i class="bi-info-circle"></i><div>Note</div></div>'
    )


def test_alert_danger_icon():
    out = render(Alert("Bad", variant="danger"))
    assert '<i class="bi-exclamation-triangle"></i>' in out
    assert "alert-danger" in out


def test_alert_dismissible_has_close_button():
    out = render(Alert("Hi", variant="success", dismissible=True))
    assert "alert-dismissible fade show" in out
    assert "btn-close" in out
    assert 'data-bs-dismiss="alert"' in out


def test_alert_no_icon():
    out = render(Alert("Plain", icon=False))
    assert "alert-icon" not in out
    assert "<i" not in out


# --------------------------------------------------------------------------
# Containers / cards
# --------------------------------------------------------------------------


def test_container_default():
    assert render(Container("x")) == '<div class="border rounded p-3">x</div>'


def test_container_compact():
    assert (
        render(Container("x", compact=True))
        == '<div class="border rounded p-2">x</div>'
    )


def test_section_header():
    out = render(
        SectionHeader(
            "Fighters", action_href="/add", action_text="Add", action_icon="add"
        )
    )
    assert "bg-body-secondary rounded px-2 py-1" in out
    assert '<h2 class="h5 mb-0">Fighters</h2>' in out
    assert (
        '<a class="fs-7 icon-link linked" href="/add"><i class="bi-plus-lg"></i>Add</a>'
        in out
    )


# --------------------------------------------------------------------------
# Typography
# --------------------------------------------------------------------------


def test_caps_label():
    assert render(CapsLabel("Status")) == '<div class="caps-label">Status</div>'


def test_dot():
    assert render(Dot()) == "&nbsp;·&nbsp;"


def test_comma_list():
    assert render(CommaList(["a", "b", "c"])) == (
        "<span>a</span><span>,&nbsp;</span><span>b</span><span>,&nbsp;</span><span>c</span>"
    )


def test_comma_list_single():
    assert render(CommaList(["only"])) == "<span>only</span>"


def test_empty_state():
    assert (
        render(EmptyState("No fighters yet."))
        == '<p class="text-secondary mb-0">No fighters yet.</p>'
    )


def test_inline_none():
    assert render(InlineNone()) == '<span class="text-secondary fst-italic">None</span>'


# --------------------------------------------------------------------------
# Nav / search
# --------------------------------------------------------------------------


def test_nav_tabs():
    out = render(NavTabs([Tab("One", href="/1", active=True), Tab("Two", href="/2")]))
    assert '<ul class="nav nav-tabs">' in out
    assert '<a class="nav-link active" href="/1">One</a>' in out
    assert '<a class="nav-link" href="/2">Two</a>' in out


def test_search_bar():
    out = render(SearchBar(value="orlock"))
    assert "input-group" in out
    assert '<i class="bi-search"></i>' in out
    assert 'value="orlock"' in out
    assert '<button class="btn btn-primary" type="submit">Search</button>' in out


# --------------------------------------------------------------------------
# Tables
# --------------------------------------------------------------------------


def test_table_headers():
    from gyrinx.components.design import TBody, Td, Tr

    out = render(Table(TBody(Tr[Td["a"]]), headers=["Name", "Cost"]))
    assert 'class="table table-sm table-borderless mb-0"' in out
    assert "<thead><tr><th>Name</th><th>Cost</th></tr></thead>" in out


def test_table_fixed_compact():
    out = render(Table(headers=["x"], fixed=True, compact=True))
    assert "table-fixed" in out
    assert "fs-7" in out


# --------------------------------------------------------------------------
# Page patterns
# --------------------------------------------------------------------------


def test_page_header():
    out = render(
        PageHeader(
            "Title",
            actions=Button("Edit", href="/e"),
            meta=MetaRow([MetaItem("Tom", icon="person")]),
        )
    )
    assert '<h1 class="mb-0">Title</h1>' in out
    assert "nav btn-group flex-nowrap ms-md-auto" in out
    assert "text-secondary fs-7" in out
    assert '<i class="bi-person"></i>' in out


def test_back_link():
    out = render(BackLink(url="/lists/", text="Back to gangs"))
    assert "breadcrumb" in out
    assert '<i class="bi-chevron-left"></i>' in out
    assert '<a href="/lists/">Back to gangs</a>' in out


def test_info_columns():
    out = render(
        InfoColumns(
            [InfoColumn("Status", "In Progress"), InfoColumn("Budget", "1500¢")]
        )
    )
    assert "border-bottom pb-3 mb-2" in out
    assert '<div class="caps-label">Status</div>' in out
    assert "flex-grow-1 col-md-3 flex-md-grow-0" in out


def test_inline_action_menu():
    out = render(
        InlineActionMenu(
            [
                ActionLink("Edit", href="/e"),
                ActionLink("Delete", href="/d", variant="danger"),
            ]
        )
    )
    assert '<i class="bi-arrow-90deg-up text-secondary me-1"></i>' in out
    assert '<a class="link-secondary" href="/e">Edit</a>' in out
    assert '<a class="link-danger" href="/d">Delete</a>' in out
    assert "&nbsp;·&nbsp;" in out


def test_inline_action_menu_row():
    out = render(
        InlineActionMenu([ActionLink("Edit", href="/e")], wrap="row", colspan=9)
    )
    assert out.startswith('<tr><td colspan="9" class="text-end">')
