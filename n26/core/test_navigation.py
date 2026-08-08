"""The bar's gang switcher: whose gangs it lists, and what it costs.

The switcher is drawn on every screen that belongs to one gang, so both of
those are load-bearing — a list that included somebody else's gangs would be
a leak, and a query that grew with the roster would grow on every page.
"""

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.urls import reverse

from n26.core.models import Gang
from n26.core.navigation import NAV_SIBLINGS, gang_switcher, owned_gangs

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """Staff, because /n26/ is fenced to staff and testers."""
    return User.objects.create_user("player", is_staff=True)


@pytest.fixture
def stranger(db):
    return User.objects.create_user("someone-else")


@pytest.fixture
def make_gang(gang_type, tester):
    def make(name, owner=None):
        return Gang.objects.create(
            name=name,
            owner=owner or tester,
            gang_type=gang_type,
            starting_credits=1000,
            credits=1000,
        )

    return make


def request_for(user):
    request = RequestFactory().get("/n26/")
    request.user = user
    return request


class TestWhoseGangsAreListed:
    """The switcher is built from the viewer's own roster and nothing else."""

    def test_it_lists_the_viewers_gangs(self, tester, make_gang):
        make_gang("The Ashen Choir")
        make_gang("Pit of Teeth")
        switcher = gang_switcher(request_for(tester), make_gang("Salt and Iron"))
        assert {item.label for item in switcher.items} == {
            "The Ashen Choir",
            "Pit of Teeth",
            "Salt and Iron",
        }

    def test_someone_elses_gangs_are_not_in_it(self, tester, stranger, make_gang):
        mine = make_gang("The Ashen Choir")
        make_gang("Their Gang", owner=stranger)
        switcher = gang_switcher(request_for(tester), mine)
        assert [item.label for item in switcher.items] == ["The Ashen Choir"]

    def test_a_deleted_gang_is_not_offered(self, tester, make_gang):
        mine = make_gang("The Ashen Choir")
        make_gang("Gone").archive()
        switcher = gang_switcher(request_for(tester), mine)
        assert [item.label for item in switcher.items] == ["The Ashen Choir"]

    def test_the_gang_you_are_on_is_marked(self, tester, make_gang):
        make_gang("Pit of Teeth")
        here = make_gang("The Ashen Choir")
        switcher = gang_switcher(request_for(tester), here)
        marked = [item.label for item in switcher.items if item.current]
        assert marked == ["The Ashen Choir"]
        assert switcher.label == "The Ashen Choir"

    def test_the_gang_you_are_on_survives_the_cap(self, tester, make_gang):
        """Named last in the alphabet, so a capped query drops it — and a
        switcher that omits the page it is on says the reader is nowhere."""
        for index in range(NAV_SIBLINGS + 2):
            make_gang(f"Gang {index:02d}")
        here = make_gang("Zzz, the last one")
        switcher = gang_switcher(request_for(tester), here)
        assert switcher.items[0].label == "Zzz, the last one"
        assert switcher.items[0].current


class TestWhatItCosts:
    """One query for the drawer and the bar between them, and the same one
    however many gangs the reader has."""

    def test_the_list_is_read_once_per_request(
        self, tester, make_gang, django_assert_num_queries
    ):
        here = make_gang("The Ashen Choir")
        request = request_for(tester)
        with django_assert_num_queries(1):
            owned_gangs(request)
            gang_switcher(request, here)
            owned_gangs(request)

    def test_the_query_does_not_grow_with_the_roster(
        self, tester, make_gang, django_assert_num_queries
    ):
        here = make_gang("The Ashen Choir")
        with django_assert_num_queries(1):
            gang_switcher(request_for(tester), here)
        for index in range(NAV_SIBLINGS * 3):
            make_gang(f"Gang {index:02d}")
        with django_assert_num_queries(1):
            gang_switcher(request_for(tester), here)


class TestTheBar:
    """What a gang's screens actually put in the HTML."""

    def test_the_gang_sheet_names_its_gang_in_the_bar(self, client, tester, make_gang):
        here = make_gang("The Ashen Choir")
        other = make_gang("Pit of Teeth")
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[here.pk])).content.decode()
        assert 'aria-label="Switch to another gang"' in body
        # The other gang is a real link in the HTML, not something the panel
        # fetches when it opens.
        assert reverse("n26-gang", args=[other.pk]) in body
        assert 'aria-current="page"' in body

    def test_a_fighters_screen_names_the_gang(
        self, client, tester, make_gang, make_profile, make_statline
    ):
        """Equipping someone shows the gang in the bar: the fighter is named
        by the heading below it, and the way out a player wants is sideways
        to their other gang."""
        from n26.core.operations import operation

        here = make_gang("The Ashen Choir")
        make_gang("Pit of Teeth")
        profile = make_profile("Ganger", price=55)
        make_statline(profile)
        with operation(here, actor=tester) as op:
            fighter = op.hire(profile, "Vex")
        client.force_login(tester)
        body = client.get(reverse("n26-equip", args=[fighter.pk])).content.decode()
        assert 'aria-label="Switch to another gang"' in body
        assert "Pit of Teeth" in body

    def test_a_page_that_is_not_one_of_anything_has_no_switcher(
        self, client, tester, make_gang
    ):
        make_gang("The Ashen Choir")
        client.force_login(tester)
        body = client.get(reverse("n26-gangs")).content.decode()
        assert 'aria-label="Switch to another gang"' not in body


class TestTheColourScheme:
    """The control moved into the account menu; it still has to be there and
    still has to be able to set all three states."""

    def test_the_scheme_rows_are_in_the_account_menu(self, client, tester, make_gang):
        client.force_login(tester)
        body = client.get(reverse("n26-gangs")).content.decode()
        assert "set('light')" in body
        assert "set('dark')" in body
        assert "set('system')" in body

    def test_the_bar_no_longer_carries_a_toggle_for_a_signed_in_reader(
        self, client, tester
    ):
        """Its whole purpose in moving was the horizontal space, so a copy
        left behind in the bar would have bought nothing."""
        client.force_login(tester)
        body = client.get(reverse("n26-gangs")).content.decode()
        assert 'aria-label="Toggle dark mode"' not in body

    def test_a_visitor_with_no_account_menu_keeps_the_toggle(self, rf):
        """Signed out there is no menu to put the rows in, and a reader who
        cannot change the scheme at all is worse off than one with a button.

        The layout is rendered on its own: the edition's gate sends anonymous
        visitors to log in, so this branch has no page to be reached from and
        would otherwise be exercised by nothing.
        """
        from django.contrib.auth.models import AnonymousUser
        from django.template.loader import render_to_string

        request = rf.get("/n26/")
        request.user = AnonymousUser()
        body = render_to_string(
            "n26/layouts/base.html", {"user": AnonymousUser()}, request=request
        )
        assert 'aria-label="Toggle dark mode"' in body
