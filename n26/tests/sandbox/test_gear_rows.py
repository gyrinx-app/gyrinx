"""Categories with draws_its_own_row display their equipment under a separate heading, such
as Gene-smithing. Grouping changes presentation while preserving assignment ratings and
removal behaviour.
"""

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from n26.core.card import build_card
from n26.core.printing import detail_groups
from n26.core.render import build_model_card, card_to_model_card
from n26.core.render_text import render_model_card
from n26.tests.sandbox.actions import (
    assign,
    create_category,
    create_wargear,
    found_gang,
    hire,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def player():
    return User.objects.create_user("player")


@pytest.fixture
def library(default_pack, person_type, gang_type, make_profile):
    """Ordinary gear and upgrades whose category requests a separate heading."""
    upgrades = create_category("Gene-smithing", "Gene-smithing", draws_its_own_row=True)
    return {
        "bruiser": make_profile("Goliath Bruiser", price=100),
        "respirator": create_wargear("Respirator", price=15),
        "iron_flesh": create_wargear("Iron flesh", price=30, category=upgrades),
        "dermal": create_wargear("Dermal hardening", price=10, category=upgrades),
    }


@pytest.fixture
def krath(gang_type, player, library):
    """A model holding one ordinary item and one grouped upgrade."""
    gang = found_gang("The Chain", gang_type, owner=player, budget=1000)
    mini = hire(gang, library["bruiser"], "Krath", paid=100)
    assign(library["respirator"], miniature=mini, paid=15)
    assign(library["iron_flesh"], miniature=mini, paid=30)
    return mini


def card_of(miniature):
    return build_model_card(miniature)


class TestACategoryThatAsksForItsOwnRow:
    def test_its_items_leave_the_gear_row(self, krath, library):
        card = card_of(krath)
        assert [line.name for line in card.equipment] == ["Respirator"]

    def test_they_arrive_under_the_category_name(self, krath):
        card = card_of(krath)
        assert [group.name for group in card.gear_groups] == ["Gene-smithing"]
        assert [line.name for line in card.gear_groups[0].lines] == ["Iron flesh"]

    def test_the_line_keeps_its_rating(self, krath):
        card = card_of(krath)
        assert card.gear_groups[0].lines[0].rating == 30

    def test_the_rating_still_counts_towards_the_model(self, krath):
        assert card_of(krath).rating == 145

    def test_a_group_with_nothing_in_it_is_not_drawn(self, krath, library):
        """Omit headings for categories with no equipment on this model."""
        card = card_of(krath)
        assert len(card.gear_groups) == 1

    def test_a_second_item_joins_the_same_group(self, krath, library):
        assign(library["dermal"], miniature=krath, paid=10)
        card = card_of(krath)
        assert [line.name for line in card.gear_groups[0].lines] == [
            "Dermal hardening",
            "Iron flesh",
        ]


class TestEverySurfaceDrawsIt:
    """Preserve separate gear groups in printed, text and captured model representations."""

    def test_the_printed_card_gives_it_a_heading(self, krath):
        groups = {group.label: group.text for group in detail_groups(card_of(krath))}
        assert groups["Gear"] == "Respirator"
        assert groups["Gene-smithing"] == "Iron flesh"

    def test_the_text_card_gives_it_a_line(self, krath):
        text = "\n".join(render_model_card(card_of(krath)))
        assert "Gear: Respirator" in text
        assert "Gene-smithing: Iron flesh" in text

    def test_the_captured_state_keeps_the_two_apart(self, krath):
        from n26.core.capture import gang_state

        state = gang_state(krath.membership.gang)
        model = next(iter(state["models"].values()))
        assert [name for name, _ in model["equipment"]] == ["Respirator"]
        assert model["gear_groups"] == [("Gene-smithing", [("Iron flesh", 30)])]


class TestTwoHeadingsOfOneName:
    """Keep same-named categories from different sections distinct in rendering and
    capture. Combining them would hide reassignment between categories during
    comparisons.
    """

    @pytest.fixture
    def twins(self, default_pack, library, gang_type, player):
        first = create_category("Ranged Weapons", "Salvage", draws_its_own_row=True)
        second = create_category("Close Combat", "Salvage", draws_its_own_row=True)
        left = create_wargear("Cutting torch", price=20, category=first)
        right = create_wargear("Bent rebar", price=5, category=second)
        gang = found_gang("Two Names", gang_type, owner=player, budget=1000)
        mini = hire(gang, library["bruiser"], "Sull", paid=100)
        assign(left, miniature=mini, paid=20)
        assign(right, miniature=mini, paid=5)
        return mini

    def test_both_headings_are_drawn(self, twins):
        card = card_of(twins)
        assert [group.name for group in card.gear_groups] == ["Salvage", "Salvage"]

    def test_each_keeps_its_own_things(self, twins):
        card = card_of(twins)
        held = [[line.name for line in group.lines] for group in card.gear_groups]
        assert sorted(held) == [["Bent rebar"], ["Cutting torch"]]

    def test_the_capture_does_not_fold_them_together(self, twins):
        from n26.core.capture import gang_state

        state = gang_state(twins.membership.gang)
        model = next(iter(state["models"].values()))
        assert len(model["gear_groups"]) == 2
        assert sorted(lines for _, lines in model["gear_groups"]) == [
            [("Bent rebar", 5)],
            [("Cutting torch", 20)],
        ]

    def test_drawing_them_asks_no_query_of_its_own(
        self, twins, django_assert_num_queries
    ):
        """Hydrate category sections with their assignments so tie-breaking adds no
        per-heading queries.
        """
        card = build_card(twins)
        with CaptureQueriesContext(connection) as counted:
            card_to_model_card(card, name="Sull")
        # Allow only the existing statline query, with no query added by grouping.
        assert len(counted.captured_queries) <= 1


class TestNothingElseChanges:
    def test_gear_with_no_category_stays_in_the_gear_row(
        self, gang_type, player, library
    ):
        gang = found_gang("The Other Chain", gang_type, owner=player, budget=1000)
        mini = hire(gang, library["bruiser"], "Vex", paid=100)
        assign(library["respirator"], miniature=mini, paid=15)
        card = card_of(mini)
        assert [line.name for line in card.equipment] == ["Respirator"]
        assert card.gear_groups == []

    def test_a_category_that_does_not_ask_leaves_its_items_in_gear(
        self, gang_type, player, library, default_pack
    ):
        ordinary = create_category("Personal Equipment", "Field Gear")
        lamp = create_wargear("Photo-goggles", price=35, category=ordinary)
        gang = found_gang("The Third Chain", gang_type, owner=player, budget=1000)
        mini = hire(gang, library["bruiser"], "Sull", paid=100)
        assign(lamp, miniature=mini, paid=35)
        card = card_of(mini)
        assert [line.name for line in card.equipment] == ["Photo-goggles"]
        assert card.gear_groups == []

    def test_a_grouped_line_asks_no_query_of_its_own(
        self, krath, library, gang_type, player, django_assert_num_queries
    ):
        """Grouped gear must add no render queries compared with ordinary equipment.
        Compare query counts so unrelated statline-query changes do not invalidate this
        constraint.
        """
        plain = found_gang("The Plain Chain", gang_type, owner=player, budget=1000)
        bare = hire(plain, library["bruiser"], "Yeng", paid=100)
        assign(library["respirator"], miniature=bare, paid=15)

        without = build_card(bare)
        with CaptureQueriesContext(connection) as counted:
            card_to_model_card(without, name="Yeng")

        assign(library["dermal"], miniature=krath, paid=10)
        with_groups = build_card(krath)
        with django_assert_num_queries(len(counted.captured_queries)):
            card_to_model_card(with_groups, name="Krath")
