"""The content library's menu, and the kinds it lists out in full.

Most kinds are a row that leads to a listing. A slot type is a place
other content is filed under, so what an author wants is one particular
one — and the menu names them rather than making that two hops.
"""

import pytest

from n26.library.authoring import (
    create_pickable,
    create_picklist,
    create_slot,
    create_slot_type,
)
from n26.library.models import SlotType, Subtype
from n26.library.views import INDEX_LISTS, _listed_beneath

pytestmark = pytest.mark.django_db


@pytest.fixture
def two_slot_types(default_pack):
    legacy = create_slot_type("Gang Legacy", plural_name="Gang Legacies")
    guild = create_slot_type("Guild")
    create_pickable("Cawdor", legacy)
    create_pickable("Van Saar", legacy)
    picklist = create_picklist("House Legacies", legacy)
    create_slot("Gang Legacy", legacy, picklist=picklist)
    return legacy, guild


class TestWhatTheMenuListsOut:
    def test_a_slot_type_row_carries_the_slot_types_themselves(self, two_slot_types):
        listed = _listed_beneath("slot-type", SlotType)

        assert [row["label"] for row in listed] == ["Gang Legacy", "Guild"]

    def test_each_one_links_to_its_own_page(self, two_slot_types):
        legacy, _ = two_slot_types

        listed = _listed_beneath("slot-type", SlotType)

        assert listed[0]["url"] == f"/n26/authoring/slot-type/{legacy.pk}/"

    def test_each_one_says_what_has_been_built_in_it(self, two_slot_types):
        listed = _listed_beneath("slot-type", SlotType)

        assert listed[0]["notes"][:3] == ["2 pickables", "1 picklist", "1 slot"]

    def test_it_counts_one_of_a_thing_as_one(self, two_slot_types):
        """A menu row read at a glance should not say "1 slots"."""
        listed = _listed_beneath("slot-type", SlotType)

        assert "1 picklists" not in listed[0]["notes"]
        assert "0 pickable" not in listed[1]["notes"]
        assert listed[1]["notes"][:3] == ["0 pickables", "0 picklists", "0 slots"]

    def test_a_kind_that_is_not_listed_out_carries_nothing(self, two_slot_types):
        """Every kind would bury the menu; only the ones named are listed."""
        assert "subtype" not in INDEX_LISTS
        assert _listed_beneath("subtype", Subtype) == []


class TestThePageItself:
    def test_the_slot_types_are_drawn_under_their_kind(
        self, admin_client, two_slot_types
    ):
        body = admin_client.get("/n26/authoring/").content.decode()
        table = body[body.find("<table") : body.find("</table>", body.find("<table"))]

        assert "Slot type" in table
        assert table.index("Slot type") < table.index("Gang Legacy")
        assert "2 pickables · 1 picklist · 1 slot" in table

    def test_they_are_indented_so_they_read_as_of_that_kind(
        self, admin_client, two_slot_types
    ):
        """The ! is load-bearing: the kit's own [&_td] padding rule
        out-specifies a plain utility on the cell."""
        body = admin_client.get("/n26/authoring/").content.decode()

        assert "pl-8!" in body
