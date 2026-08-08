"""The gangs index: the bar's Gangs link, and where it lands.

The page draws the same table the dashboard's first tab does, so these
tests are about the wiring — whose gangs reach it, whose do not, that
the facets the filter needs come with them, and what ``?q=`` narrows.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Gang
from n26.library.models import GangType

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """Staff, because /n26/ is fenced to staff and testers."""
    return User.objects.create_user("player", is_staff=True)


@pytest.fixture
def make_gang(gang_type, tester):
    def _make(name, owner=None, type_=None):
        return Gang.objects.create(
            name=name,
            owner=owner or tester,
            gang_type=type_ or gang_type,
            starting_credits=1000,
            credits=1000,
        )

    return _make


def test_lists_the_gangs_you_own(client, tester, make_gang):
    make_gang("The Ashen Choir")
    make_gang("The Bad Girls")

    client.force_login(tester)
    response = client.get(reverse("n26-gangs"))
    assert response.status_code == 200
    body = response.content.decode()
    assert "The Ashen Choir" in body
    assert "The Bad Girls" in body


def test_a_strangers_gangs_are_not_yours(client, tester, make_gang):
    """Owner-scoped like the dashboard: which gangs exist is not
    something a signed-in stranger gets to read off a list page."""
    make_gang("The Ashen Choir")
    rival = User.objects.create_user("rival", is_staff=True)
    make_gang("Someone Else's Problem", owner=rival)

    client.force_login(rival)
    body = client.get(reverse("n26-gangs")).content.decode()
    assert "Someone Else" in body
    assert "The Ashen Choir" not in body


def test_an_archived_gang_is_gone_from_the_list(client, tester, make_gang):
    gang = make_gang("The Ashen Choir")
    gang.archived = True
    gang.save()

    client.force_login(tester)
    assert "The Ashen Choir" not in client.get(reverse("n26-gangs")).content.decode()


def test_the_rows_carry_the_facets_the_filter_reads(client, tester, make_gang):
    """The type filter is computed from the rows on the page, so the
    context the dashboard hands the table has to arrive here too."""
    make_gang("The Ashen Choir")

    client.force_login(tester)
    response = client.get(reverse("n26-gangs"))
    assert [option["label"] for option in response.context["gang_type_options"]] == [
        "Escher"
    ]


def test_each_row_links_to_its_sheet(client, tester, make_gang):
    gang = make_gang("The Ashen Choir")

    client.force_login(tester)
    body = client.get(reverse("n26-gangs")).content.decode()
    assert reverse("n26-gang", args=[gang.pk]) in body


def test_founding_is_offered_where_the_list_is(client, tester):
    """An empty list is the likeliest place for someone to want a gang,
    so the page carries the create action rather than pointing back at
    the dashboard for it."""
    client.force_login(tester)
    body = client.get(reverse("n26-gangs")).content.decode()
    assert reverse("n26-create-gang") in body
    assert "No gangs yet" in body


def test_the_index_does_not_swallow_founding(client, tester):
    """`gangs/` and `gangs/new/` are different pages, in that order."""
    client.force_login(tester)
    assert client.get(reverse("n26-create-gang")).status_code == 200


class TestSearchingForAGang:
    """`?q=` narrows the list on the server.

    The table's own box narrows the rows already drawn, which stops being
    enough the moment someone owns more gangs than a page carries. So the
    box also submits, and this is what it submits to: a query in the URL,
    a linkable page, and an answer that does not depend on a script
    having run.

    What matched is read off the context rather than the markup: a gang
    the reader owns is named in the bar's switcher too, so its absence
    from the list is not its absence from the page.
    """

    @staticmethod
    def _search(client, query):
        response = client.get(reverse("n26-gangs"), {"q": query})
        return [gang.name for gang in response.context["gangs"]]

    def test_a_substring_of_a_name_finds_the_gang(self, client, tester, make_gang):
        """Substrings, not whole words — the fallback in the platform's
        search is why "ashen" need not be typed out in full."""
        make_gang("The Ashen Choir")
        make_gang("The Bad Girls")

        client.force_login(tester)
        assert self._search(client, "ashe") == ["The Ashen Choir"]

    def test_the_gang_type_is_searched_as_well_as_the_name(
        self, client, tester, make_gang
    ):
        """The row prints both and the in-page filter reads both, so the
        submitted search has to as well, or the box changes its mind on
        the way to the server."""
        make_gang("The Ashen Choir")
        make_gang("Hammers", type_=GangType.objects.create(name="Goliath"))

        client.force_login(tester)
        assert self._search(client, "goli") == ["Hammers"]

    def test_a_query_matching_nothing_says_so(self, client, tester, make_gang):
        """Two different emptinesses: nothing matched, and nothing owned.
        Offering to found a gang is only right for the second."""
        make_gang("The Ashen Choir")

        client.force_login(tester)
        response = client.get(reverse("n26-gangs"), {"q": "helmawr"})
        assert list(response.context["gangs"]) == []
        body = response.content.decode()
        assert "No gangs match that" in body
        assert "No gangs yet" not in body

    def test_the_query_comes_back_in_the_box(self, client, tester, make_gang):
        make_gang("The Ashen Choir")

        client.force_login(tester)
        body = client.get(reverse("n26-gangs"), {"q": "ashe"}).content.decode()
        assert 'value="ashe"' in body

    def test_a_strangers_gang_never_matches_your_search(
        self, client, tester, make_gang
    ):
        """The search runs inside the owner scope, not beside it."""
        rival = User.objects.create_user("rival", is_staff=True)
        make_gang("The Ashen Choir")
        make_gang("The Ashen Rivals", owner=rival)

        client.force_login(tester)
        assert self._search(client, "ashen") == ["The Ashen Choir"]

    @pytest.mark.parametrize("params", [{}, {"q": ""}, {"q": "   "}])
    def test_no_query_lists_everything(self, client, tester, make_gang, params):
        """A blank box is not a search for nothing."""
        make_gang("The Ashen Choir")
        make_gang("The Bad Girls")

        client.force_login(tester)
        response = client.get(reverse("n26-gangs"), params)
        assert [gang.name for gang in response.context["gangs"]] == [
            "The Ashen Choir",
            "The Bad Girls",
        ]

    def test_the_dashboard_sends_its_search_here(self, client, tester, make_gang):
        """One search, wherever the box is drawn: the dashboard's tab
        cannot answer for gangs it did not carry, so it does not try."""
        make_gang("The Ashen Choir")

        client.force_login(tester)
        body = client.get(reverse("n26-dashboard")).content.decode()
        assert f'action="{reverse("n26-gangs")}"' in body
