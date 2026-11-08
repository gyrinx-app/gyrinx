"""Stash menus preserve ordinary action order, then append danger actions with
separators when multiple actions exist.
"""

import pytest

from n26.core.listing import DANGER, LINK, SECONDARY, SUBMIT, Action
from n26.core.views.owned import stash_menu


def act(label, tone=SECONDARY):
    return Action(label, LINK, f"/at?{label.lower()}=1", tone)


class TestTheStashMenu:
    """Place danger actions last; omit the separator for a single action."""

    def test_the_others_come_first_and_each_danger_act_gets_a_separator(self):
        menu = stash_menu(
            [act("Reassign"), act("Sell", DANGER), act("Refund"), act("Delete", DANGER)]
        )
        assert [
            (entry["label"], entry["tone"], entry["separator_before"]) for entry in menu
        ] == [
            ("Reassign", "default", False),
            ("Refund", "default", False),
            ("Sell", "danger", True),
            ("Delete", "danger", True),
        ]
        assert menu[0]["href"] == "/at?reassign=1"

    def test_two_danger_acts_alone_each_still_get_a_separator(self):
        menu = stash_menu([act("Sell", DANGER), act("Delete", DANGER)])
        assert [entry["separator_before"] for entry in menu] == [True, True]

    def test_a_single_act_has_no_separator(self):
        (entry,) = stash_menu([act("Delete", DANGER)])
        assert entry["separator_before"] is False

    def test_a_submit_act_is_refused(self):
        with pytest.raises(ValueError):
            stash_menu([Action("Sell", SUBMIT, "/sell", DANGER)])
