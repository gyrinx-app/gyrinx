"""The pick list and the tab strip's overflow, as the islands receive them."""

import json

import pytest
from bs4 import BeautifulSoup
from django.template import Context, Template
from django_cotton.compiler_regex import CottonCompiler

from n26.core.render import ChoiceOffer, Choosable, ChoosableGroup
from n26.core.templatetags.navigation import tab_overflow_switcher
from n26.core.templatetags.pick_list import pick_list_props

pytestmark = [pytest.mark.django_db, pytest.mark.core]


@pytest.fixture
def offer():
    return ChoiceOffer(
        label="Skills",
        groups=[
            ChoosableGroup(
                name="Agility",
                options=[
                    Choosable(key="s:1", name="Catfall", is_current=True),
                    Choosable(key="s:2", name="Clamber", detail="usable by Walkers"),
                    Choosable(
                        key="s:3", name="Keen-eyed", is_current=True, granted_by="Scout"
                    ),
                ],
            )
        ],
    )


class TestThePickListsProps:
    def test_every_box_says_what_it_is_and_whether_it_is_ticked(self, offer):
        props = pick_list_props(offer, [], name="skills", save="Save skills")
        assert props["groups"] == [
            {
                "name": "Agility",
                "caption": "",
                "options": [
                    {
                        "key": "s:1",
                        "name": "Catfall",
                        "detail": "",
                        "grantedBy": "",
                        "fixedBecause": "",
                        "picked": True,
                    },
                    {
                        "key": "s:2",
                        "name": "Clamber",
                        "detail": "usable by Walkers",
                        "grantedBy": "",
                        "fixedBecause": "",
                        "picked": False,
                    },
                    {
                        "key": "s:3",
                        "name": "Keen-eyed",
                        "detail": "",
                        "grantedBy": "Scout",
                        "fixedBecause": "",
                        "picked": True,
                    },
                ],
            }
        ]
        assert props["save"] == "Save skills"
        assert props["resetForm"] == ""

    def test_the_rest_of_the_library_is_offered_by_key(self, offer):
        props = pick_list_props(offer, [Choosable(key="s:9", name="Iron Will")])
        assert [option["key"] for option in props["addable"]] == ["s:9"]

    def test_without_script_every_box_posts_including_the_addable_ones(
        self, offer, settings
    ):
        """Before the island mounts, and for a reader with no script, the
        page draws the boxes itself; the ones not on the list yet sit in
        noscript, so only a reader without script sees them."""
        from unittest import mock

        from n26.core.templatetags import react

        manifest = {"islands/pick-list/entry.tsx": {"file": "assets/pl-1.js"}}
        with mock.patch.object(react, "_manifest", lambda: manifest):
            html = Template(
                CottonCompiler().process(
                    '<c-n26.pick-list :offer="offer" :addable="addable" '
                    'name="skills" save="Save skills" />'
                )
            ).render(
                Context(
                    {
                        "offer": offer,
                        "addable": [Choosable(key="s:9", name="Iron Will")],
                    }
                )
            )
        soup = BeautifulSoup(html, "html.parser")
        host = soup.select_one("[data-react-module]")
        assert host.has_attr("data-react-fallback")
        drawn = [box["value"] for box in host.select("input[type=checkbox]")]
        assert drawn[:3] == ["s:1", "s:2", "s:3"]
        assert host.select_one("noscript input[value='s:9']") is not None
        assert json.loads(soup.find(id=host["data-react-props"]).string)["name"] == (
            "skills"
        )


class TestTheOverflowTabs:
    def test_the_tabs_off_the_strip_are_offered_as_links(self):
        switcher = tab_overflow_switcher(
            [
                {"label": "Kit", "href": "/kit/", "current": True},
                {"label": "Rules", "href": "/rules/", "title": "Rules"},
                {"label": "Notes", "href": "/notes/", "title": "Notes and lore"},
            ],
            "Model screens",
        )
        assert [(item.label, item.href, item.title) for item in switcher.items] == [
            ("Rules", "/rules/", ""),
            ("Notes", "/notes/", "Notes and lore"),
        ]
        assert switcher.menu_label == "Other tabs"
        assert switcher.heading == "Model screens"
