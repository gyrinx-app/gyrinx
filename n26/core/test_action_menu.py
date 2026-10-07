"""What a menu of links hands its React island, and what it draws first.

No database: the props and the wrapper are decided from the items and the
call site alone. The props are read back from the host's JSON script, the way
the island reads them.
"""

import json
import re
from pathlib import Path

import pytest
from bs4 import BeautifulSoup
from django import template
from django.template import Context, Template
from django.utils.html import escape
from django_cotton.compiler_regex import CottonCompiler

from n26.core.listing import DANGER, LINK, PRIMARY, SECONDARY, SUBMIT, Action
from n26.core.templatetags.action_menu import action_menu_props, link_actions


def render(source: str, **context) -> str:
    """Compile a call site the way the template loader would, then render it."""
    return Template(CottonCompiler().process(source)).render(Context(context))


def hosts(html):
    soup = BeautifulSoup(html, "html.parser")
    return soup, soup.select('[data-react-name="action-menu"]')


def props_of(html):
    soup, (host,) = hosts(html)
    return json.loads(soup.find(id=host["data-react-props"]).string)


def link(label, target, tone=SECONDARY):
    return Action(label=label, kind=LINK, target=target, tone=tone)


class TestTheProps:
    def test_actions_become_links_in_the_order_given(self):
        props = action_menu_props(
            [link("Sell", "/sell", DANGER), link("Refund", "/refund")],
            "Actions for Respirator",
        )
        assert props["items"] == [
            {
                "label": "Sell",
                "href": "/sell",
                "tone": "danger",
                "separatorBefore": False,
            },
            {
                "label": "Refund",
                "href": "/refund",
                "tone": "default",
                "separatorBefore": False,
            },
        ]

    def test_only_danger_is_drawn_as_danger(self):
        props = action_menu_props(
            [link("Buy", "/b", PRIMARY), link("Fit", "/f", SECONDARY)], "Actions"
        )
        assert [item["tone"] for item in props["items"]] == ["default", "default"]

    def test_an_action_that_submits_raises(self):
        with pytest.raises(ValueError, match="links only"):
            action_menu_props(
                [Action(label="Buy", kind=SUBMIT, target="x", tone=PRIMARY)], "Actions"
            )

    def test_an_item_with_no_address_is_left_out(self):
        props = action_menu_props(
            [
                {"label": "View gang", "href": "/g"},
                {"label": "Print", "href": ""},
                link("Edit", ""),
            ],
            "Actions",
        )
        assert [item["label"] for item in props["items"]] == ["View gang"]

    def test_separators_come_from_the_items(self):
        props = action_menu_props(
            [
                {"label": "Reassign", "href": "/r"},
                {
                    "label": "Sell",
                    "href": "/s",
                    "tone": "danger",
                    "separator_before": True,
                },
                {
                    "label": "Delete",
                    "href": "/d",
                    "tone": "danger",
                    "separator_before": True,
                },
            ],
            "Actions",
        )
        assert [item["separatorBefore"] for item in props["items"]] == [
            False,
            True,
            True,
        ]

    @pytest.mark.parametrize(
        "option",
        [{"trigger": "dots"}, {"variant": "primary"}, {"align": "center"}],
    )
    def test_an_unknown_option_raises(self, option):
        with pytest.raises(ValueError):
            action_menu_props([], "Actions", **option)

    def test_the_options_pass_through(self):
        props = action_menu_props(
            [],
            "Actions",
            trigger="chevron",
            variant="ghost",
            align="end",
            min_width="10rem",
        )
        assert {k: props[k] for k in ("trigger", "variant", "align", "minWidth")} == {
            "trigger": "chevron",
            "variant": "ghost",
            "align": "end",
            "minWidth": "10rem",
        }

    def test_escaped_template_text_is_decoded_once(self):
        """A Cotton attribute arrives escaped. React escapes again, so the
        props must carry the plain text."""
        props = action_menu_props(
            [{"label": escape("Tom & Co"), "href": escape("/g?a=1&b=2")}],
            escape("Actions for O'Brien & Sons"),
        )
        assert props["label"] == "Actions for O'Brien & Sons"
        assert props["items"][0]["label"] == "Tom & Co"
        assert props["items"][0]["href"] == "/g?a=1&b=2"

    def test_plain_python_text_is_left_alone(self):
        props = action_menu_props([link("Fish &amp; chips", "/f")], "A &amp; B")
        assert props["label"] == "A &amp; B"
        assert props["items"][0]["label"] == "Fish &amp; chips"

    def test_the_props_never_carry_an_aria_label(self):
        """Pages count the button's aria-label. A second copy in the JSON
        would double it."""
        props = action_menu_props([link("Sell", "/s")], "Actions for Respirator")
        assert "aria-label" not in json.dumps(props)


class TestLinkActions:
    def test_pairs_become_links_in_order(self):
        assert link_actions("View gang", "/g", "Edit gang settings", "/e") == [
            {
                "label": "View gang",
                "href": "/g",
                "tone": "default",
                "separator_before": False,
            },
            {
                "label": "Edit gang settings",
                "href": "/e",
                "tone": "default",
                "separator_before": False,
            },
        ]

    def test_an_odd_count_raises(self):
        with pytest.raises(template.TemplateSyntaxError):
            link_actions("View gang", "/g", "Edit gang settings")

    def test_the_danger_link_goes_last_without_a_separator(self):
        entries = link_actions("View", "/v", danger_label="Remove", danger_href="/r")
        assert entries[-1] == {
            "label": "Remove",
            "href": "/r",
            "tone": "danger",
            "separator_before": False,
        }

    def test_the_danger_link_takes_a_separator_when_asked(self):
        entries = link_actions(
            "View", "/v", danger_label="Remove", danger_href="/r", danger_separator=True
        )
        assert entries[-1]["separator_before"] is True

    def test_a_danger_label_without_an_address_is_left_out(self):
        assert link_actions("View", "/v", danger_label="Remove", danger_href="") == [
            {
                "label": "View",
                "href": "/v",
                "tone": "default",
                "separator_before": False,
            }
        ]


class TestTheWrapper:
    def test_it_hands_the_island_an_action_list(self):
        html = render(
            '<c-n26.action-menu :items="items" label="Actions for Respirator" '
            'trigger="chevron" align="end" min_width="10rem" />',
            items=[link("Reassign", "/r"), link("Sell", "/s", DANGER)],
        )
        assert props_of(html) == {
            "label": "Actions for Respirator",
            "trigger": "chevron",
            "variant": "default",
            "align": "end",
            "minWidth": "10rem",
            "items": [
                {
                    "label": "Reassign",
                    "href": "/r",
                    "tone": "default",
                    "separatorBefore": False,
                },
                {
                    "label": "Sell",
                    "href": "/s",
                    "tone": "danger",
                    "separatorBefore": False,
                },
            ],
        }

    def test_it_hands_the_island_a_danger_link_from_link_actions(self):
        html = render(
            "{% load action_menu %}"
            '{% link_actions danger_label="Remove from campaign" danger_href=href as menu_ %}'
            '<c-n26.action-menu :items="menu_" label="Actions for The Ashen Choir" variant="ghost" />',
            href="/campaign/1/remove?gang=2&next=/x",
        )
        props = props_of(html)
        assert props["items"] == [
            {
                "label": "Remove from campaign",
                "href": "/campaign/1/remove?gang=2&next=/x",
                "tone": "danger",
                "separatorBefore": False,
            }
        ]
        assert props["variant"] == "ghost"

    def test_the_fallback_is_the_islands_button(self):
        html = render(
            '<c-n26.action-menu :items="items" label="Actions for Respirator" variant="ghost" />',
            items=[link("Sell", "/s")],
        )
        _, (host,) = hosts(html)
        assert host.has_attr("data-react-fallback")
        (button,) = host.find_all("button")
        assert button["aria-label"] == "Actions for Respirator"
        assert button["title"] == "Actions for Respirator"
        assert button["aria-haspopup"] == "menu"
        assert button["aria-expanded"] == "false"
        # Dots and a chevron, as the island draws them.
        assert len(button.find_all("svg")) == 2
        assert html.count('aria-label="Actions for Respirator"') == 1

    def test_the_chevron_fallback_draws_the_chevron_alone(self):
        html = render(
            '<c-n26.action-menu :items="items" label="Actions" trigger="chevron" />',
            items=[link("Sell", "/s")],
        )
        _, (host,) = hosts(html)
        button = host.find("button")
        assert len(button.find_all("svg")) == 1
        assert "px-1.5!" in button["class"]

    def test_a_label_is_escaped_once_in_the_fallback(self):
        html = render(
            '<c-n26.action-menu :items="items" label="Actions for {{ name }}" />',
            items=[link("View", "/v")],
            name="O'Brien & Sons",
        )
        assert 'aria-label="Actions for O&#x27;Brien &amp; Sons"' in html
        assert "&amp;amp;" not in html
        assert props_of(html)["label"] == "Actions for O'Brien & Sons"

    def test_with_no_items_nothing_is_drawn(self):
        html = render(
            '<c-n26.action-menu :items="items" label="Actions" />',
            items=[link("View", "")],
        )
        assert html.strip() == ""

    def test_one_outer_element_holds_the_scripts(self):
        """In a button group the wrapper is the group's child, so the
        preloads and scripts must sit inside it."""
        html = render(
            '<c-n26.action-menu :items="items" label="Actions" />',
            items=[link("View", "/v")],
        )
        soup = BeautifulSoup(html, "html.parser")
        (outer,) = soup.find_all(recursive=False)
        assert outer.name == "div"
        assert outer.find("script", type="application/json")
        assert outer.find("link", rel="modulepreload")

    def test_the_links_are_listed_without_javascript_only_when_asked(self):
        items = [link("Notes", "/n"), link("Delete gang", "/d", DANGER)]
        plain = render(
            '<c-n26.action-menu :items="items" label="More actions" />', items=items
        )
        assert "<noscript>" not in plain
        assert "data-action-menu-scriptless" not in plain

        listed = render(
            '<c-n26.action-menu :items="items" label="More actions" :scriptless="True" />',
            items=items,
        )
        soup = BeautifulSoup(listed, "html.parser")
        assert soup.select_one("[data-action-menu-scriptless]")
        noscript = BeautifulSoup(soup.find("noscript").decode_contents(), "html.parser")
        links = noscript.select("[data-action-menu-list] li > a")
        assert [(a.get_text(strip=True), a["href"]) for a in links] == [
            ("Notes", "/n"),
            ("Delete gang", "/d"),
        ]
        assert "text-red-600" in links[1]["class"]
        assert not noscript.select("[aria-hidden]")

    def test_the_scriptless_links_stay_in_the_tab_order(self):
        """With no script nothing handles a menu's keys, so the list is
        plain links: no menu roles, and none taken out of the tab order."""
        html = render(
            '<c-n26.action-menu :items="items" label="More actions" :scriptless="True" />',
            items=[link("Notes", "/n"), link("Delete gang", "/d", DANGER)],
        )
        soup = BeautifulSoup(html, "html.parser")
        noscript = BeautifulSoup(soup.find("noscript").decode_contents(), "html.parser")
        assert noscript.find_all("a")
        assert not noscript.select("[tabindex]")
        assert not noscript.select("[role]")

    def test_the_scriptless_list_draws_the_items_separators(self):
        html = render(
            "{% load action_menu %}"
            '{% link_actions "View" "/v" danger_label="Delete" danger_href="/d" danger_separator=True as menu_ %}'
            '<c-n26.action-menu :items="menu_" label="Actions" :scriptless="True" />'
        )
        soup = BeautifulSoup(html, "html.parser")
        noscript = BeautifulSoup(soup.find("noscript").decode_contents(), "html.parser")
        (separator,) = noscript.select('li[aria-hidden="true"]')
        assert separator.find_next_sibling("li").get_text(strip=True) == "Delete"

    def test_the_scriptless_list_looks_like_the_island(self):
        """The list copies the classes the island takes from the kit
        dropdown. This keeps the two from drifting apart."""
        from n26.frontend.tooling.export_cotton_recipes import action_menu_recipe

        recipe = action_menu_recipe()
        html = render(
            "{% load action_menu %}"
            '{% link_actions "View" "/v" danger_label="Delete" danger_href="/d" danger_separator=True as menu_ %}'
            '<c-n26.action-menu :items="menu_" label="Actions" :scriptless="True" />'
        )
        soup = BeautifulSoup(html, "html.parser")
        noscript = BeautifulSoup(soup.find("noscript").decode_contents(), "html.parser")
        view, delete = noscript.select("li > a")
        (separator,) = noscript.select('li[aria-hidden="true"]')
        assert view["class"] == recipe["item"].split()
        assert delete["class"] == recipe["itemDanger"].split()
        assert separator["class"] == recipe["separator"].split()
        assert view.span["class"] == recipe["itemLabel"].split()


def test_a_button_group_keeps_props_scripts_hidden():
    """The group's equal-height rule sets display on its wrappers' children.
    A props script is one of those children, and without the exclusion the
    page would show its JSON as text."""
    css = (Path(__file__).parents[2] / "n26/designsystem/assets/app.css").read_text()
    css = " ".join(css.split())
    assert (
        '.n26-button-group > *:not(button):not(a) > *:not([role="menu"]):not(script):not(link)'
        in css
    )


def test_a_button_group_leaves_the_scriptless_list_alone():
    """The group squares and rounds the corners of its buttons and links.
    The scriptless list's links are not the group's, so every corner rule
    skips them, as it skips a dropdown's open menu."""
    css = (Path(__file__).parents[2] / "n26/designsystem/assets/app.css").read_text()
    # Prettier may break a long :not( ) across lines.
    css = re.sub(r"\(\s+", "(", re.sub(r"\s+\)", ")", " ".join(css.split())))
    # One :not() with both, so the exclusion adds no specificity: the reset
    # must not outrank the rounding on a group's first and last child.
    exempt = ':not([role="menu"] *, [data-action-menu-list] *)'
    for rule in (
        ".n26-button-group :is(button, a)" + exempt + " {",
        ".n26-button-group > :first-child :is(button, a)" + exempt + ",",
        ".n26-button-group > :last-child :is(button, a)" + exempt + ",",
        ".n26-button-group :is(button, a):hover" + exempt + ",",
        ".n26-button-group :is(button, a):focus-visible" + exempt + " {",
    ):
        assert rule in css
    assert ':not([role="menu"] *)' not in css
