"""The switchers: what each one lists, and what it costs.

They are drawn on every screen that belongs to one gang, so both of those are
load-bearing — a list that included somebody else's gangs or somebody else's
fighters would be a leak, and a query that grew with the roster would grow on
every page.

Which siblings a switcher offers depends on what the control sits beside. The
bar names the gang and offers the reader's others; a heading naming a fighter
offers the gang's other fighters, because the useful move from the middle of
equipping one is to the next one.
"""

import pytest
from django.contrib.auth.models import User
from django.test import RequestFactory
from django.urls import reverse

from n26.core.models import Gang
from n26.core.navigation import (
    NAV_SIBLINGS,
    campaign_switcher,
    fighter_switcher,
    gang_switcher,
    owned_gangs,
    places_switcher,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """The signed-in person these tests look at the app as."""
    return User.objects.create_user("player")


@pytest.fixture
def stranger(db):
    return User.objects.create_user("someone-else")


@pytest.fixture
def author(db):
    """Staff, and so the one reader the authoring places are offered to."""
    return User.objects.create_user("author", is_staff=True)


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


class TestThePlaces:
    """The default bar switcher on a page that is not one of anything lists
    the app itself, so the keyboard way into the bar lands everywhere."""

    def test_it_lists_the_apps_places(self, author):
        switcher = places_switcher(request_for(author))
        assert [item.label for item in switcher.items] == [
            "Home",
            "Gangs",
            "Help",
            "Content library",
            "Modifiers",
            "Foundations",
            "Ingest",
        ]

    def test_the_guides_are_one_of_the_places(self, tester):
        """A written-out path rather than a reversed route: the guides are
        flatpages, addressed by the URL they are stored under."""
        switcher = places_switcher(request_for(tester))
        labels = [item.label for item in switcher.items]
        assert labels.index("Help") == labels.index("Gangs") + 1
        assert [item.href for item in switcher.items if item.label == "Help"] == [
            "/help/n26/"
        ]

    def test_authoring_is_not_offered_to_a_reader_who_does_not_write(self, stranger):
        """The drawer draws the authoring section for staff only, and a
        switcher that named those pages for everyone would be the drawer
        disagreeing with itself."""
        switcher = places_switcher(request_for(stranger))
        assert [item.label for item in switcher.items] == ["Home", "Gangs", "Help"]

    def test_naming_the_place_turns_the_leading_link_on(self, tester):
        """The linked shape: a page that is one of the places names itself
        as the way back to itself, exactly as a gang's screens do."""
        switcher = places_switcher(request_for(tester), here="home")
        assert switcher.label == "Home"
        assert switcher.href == reverse("n26-dashboard")
        assert [item.label for item in switcher.items if item.current] == ["Home"]

    def test_a_page_that_is_no_place_gets_the_chevron_alone(self, tester):
        switcher = places_switcher(request_for(tester))
        assert switcher.label == ""
        assert not any(item.current for item in switcher.items)


@pytest.fixture
def hire(tester, make_profile, make_statline):
    """Put a fighter on a gang's roster, by name.

    Free, so a test can fill a roster past the cap without the gang running
    out of credits half way.
    """
    from n26.core.operations import operation

    profile = make_profile("Ganger", price=0)
    make_statline(profile)

    def _hire(gang, name):
        with operation(gang, actor=tester) as op:
            return op.hire(profile, name)

    return _hire


class TestWhichFightersAreListed:
    """The heading on a fighter's screen switches fighters, and the set is
    the gang's roster — not the reader's, and not everyone's."""

    def test_it_lists_the_gangs_own_fighters(self, make_gang, hire):
        gang = make_gang("The Ashen Choir")
        here = hire(gang, "Vex")
        hire(gang, "Karn")
        switcher = fighter_switcher(gang, here)
        assert {item.label for item in switcher.items} == {"Vex", "Karn"}

    def test_another_gangs_fighters_are_not_in_it(
        self, tester, stranger, make_gang, hire
    ):
        """Including one would be a way of finding out that someone else's
        fighter exists, and what they called it."""
        gang = make_gang("The Ashen Choir")
        here = hire(gang, "Vex")
        hire(make_gang("Their Gang", owner=stranger), "Their Fighter")
        hire(make_gang("Pit of Teeth"), "My Other Fighter")
        switcher = fighter_switcher(gang, here)
        assert [item.label for item in switcher.items] == ["Vex"]

    def test_a_fighter_off_the_roster_is_not_offered(self, make_gang, hire):
        """Leaving the gang is the membership being archived, which is what
        the sheet reads too — so the switcher and the sheet agree on who is
        in the gang."""
        gang = make_gang("The Ashen Choir")
        here = hire(gang, "Vex")
        gone = hire(gang, "Karn")
        gone.membership.archive()
        switcher = fighter_switcher(gang, here)
        assert [item.label for item in switcher.items] == ["Vex"]

    def test_every_row_leads_to_the_screen_it_is_drawn_on(self, make_gang, hire):
        """Switching fighter keeps the job: from the skills screen the rows
        are skills screens, and a reader picking their way down the roster
        is not dropped into a different task halfway."""
        gang = make_gang("The Ashen Choir")
        here = hire(gang, "Vex")
        other = hire(gang, "Karn")
        switcher = fighter_switcher(gang, here, route="n26-select")
        assert {item.href for item in switcher.items} == {
            reverse("n26-select", args=[here.pk]),
            reverse("n26-select", args=[other.pk]),
        }
        assert switcher.menu_label == "Select skills for another fighter"

    def test_the_kit_screen_is_where_it_leads_by_default(self, make_gang, hire):
        gang = make_gang("The Ashen Choir")
        here = hire(gang, "Vex")
        switcher = fighter_switcher(gang, here)
        assert [item.href for item in switcher.items] == [
            reverse("n26-equip", args=[here.pk])
        ]
        assert switcher.menu_label == "Equip another fighter"

    def test_a_screen_with_no_address_of_its_own_leads_to_the_kit_screen(
        self, make_gang, hire
    ):
        """A choice slot names one card and one question, so there is no
        such page for anybody else. Rather than leave the control off those
        screens, the rows go to the page every fighter has."""
        gang = make_gang("The Ashen Choir")
        here = hire(gang, "Vex")
        switcher = fighter_switcher(gang, here, route="n26-choose")
        assert [item.href for item in switcher.items] == [
            reverse("n26-equip", args=[here.pk])
        ]
        assert switcher.menu_label == "Equip another fighter"

    def test_the_fighter_you_are_on_survives_the_cap(self, make_gang, hire):
        gang = make_gang("The Ashen Choir")
        for index in range(NAV_SIBLINGS + 2):
            hire(gang, f"Fighter {index:02d}")
        here = hire(gang, "Zzz, the last one")
        switcher = fighter_switcher(gang, here)
        assert switcher.items[0].label == "Zzz, the last one"
        assert switcher.items[0].current

    def test_the_query_does_not_grow_with_the_roster(
        self, make_gang, hire, django_assert_num_queries
    ):
        """One capped query, on a screen a player opens for every fighter in
        turn — so a big gang must cost it what a small one does."""
        gang = make_gang("The Ashen Choir")
        here = hire(gang, "Vex")
        with django_assert_num_queries(1):
            fighter_switcher(gang, here)
        for index in range(NAV_SIBLINGS * 2):
            hire(gang, f"Fighter {index:02d}")
        with django_assert_num_queries(1):
            fighter_switcher(gang, here)


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

    def test_a_page_that_is_not_one_of_a_gang_offers_the_apps_places(
        self, client, tester, make_gang
    ):
        """The gangs listing is no one gang, so the bar switches pages
        instead — named, because the listing is one of the app's places,
        with the same chord every bar switcher answers."""
        make_gang("The Ashen Choir")
        client.force_login(tester)
        body = client.get(reverse("n26-gangs")).content.decode()
        assert 'aria-label="Switch to another gang"' not in body
        assert 'aria-label="Go to another page"' in body
        assert reverse("n26-dashboard") in body
        assert "(⌥⇧F)" in body

    def test_the_dashboard_names_itself_in_the_bar(self, client, tester):
        client.force_login(tester)
        body = client.get(reverse("n26-dashboard")).content.decode()
        assert 'aria-label="Go to another page"' in body
        assert ">Home</span>" in body
        assert reverse("n26-gangs") in body

    def test_the_bar_and_the_heading_answer_different_chords(
        self, client, tester, make_gang
    ):
        """⌥⇧F is the bar's switcher and ⌥⇧R the heading's, on every screen
        that has both — two controls answering one chord would both open."""
        here = make_gang("The Ashen Choir")
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[here.pk])).content.decode()
        assert 'aria-keyshortcuts="Alt+Shift+F"' in body
        assert 'aria-keyshortcuts="Alt+Shift+R"' in body
        assert "(⌥⇧F)" in body
        assert "(⌥⇧R)" in body


class TestTheHeading:
    """A page's own name gets a switcher too, and it switches whatever the
    name is — which is not always what the bar is showing."""

    def test_the_gang_sheet_offers_the_others_beside_its_name(
        self, client, tester, make_gang
    ):
        """The same set as the bar, because the heading is the gang. Named
        differently, because two controls announced identically tell a reader
        who cannot see where they sit nothing about either."""
        here = make_gang("The Ashen Choir")
        client.force_login(tester)
        body = client.get(reverse("n26-gang", args=[here.pk])).content.decode()
        assert 'aria-label="Switch to another gang"' in body
        assert 'aria-label="Your other gangs"' in body

    def test_the_gangs_beside_the_heading_cost_nothing_extra(
        self, client, tester, make_gang
    ):
        """Both switchers and the drawer read the same memoised list, so
        drawing it a second time on the same page is free."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        here = make_gang("The Ashen Choir")
        for index in range(NAV_SIBLINGS):
            make_gang(f"Gang {index:02d}")
        client.force_login(tester)
        with CaptureQueriesContext(connection) as captured:
            assert client.get(reverse("n26-gang", args=[here.pk])).status_code == 200
        capped = [
            query
            for query in captured.captured_queries
            if f"LIMIT {NAV_SIBLINGS}" in query["sql"] and "n26_gang" in query["sql"]
        ]
        assert len(capped) == 1

    def test_the_equip_screen_offers_the_gangs_other_fighters(
        self, client, tester, make_gang, hire
    ):
        """The bar switches gangs and the heading switches fighters. Both are
        on the screen, and the one beside "Equip Vex" is the one that moves a
        player to the next fighter."""
        gang = make_gang("The Ashen Choir")
        here = hire(gang, "Vex")
        other = hire(gang, "Karn")
        client.force_login(tester)
        body = client.get(reverse("n26-equip", args=[here.pk])).content.decode()
        assert 'aria-label="Equip another fighter"' in body
        assert 'aria-label="Switch to another gang"' in body
        assert reverse("n26-equip", args=[other.pk]) in body

    def test_the_equip_screen_costs_the_same_whatever_the_roster(
        self, client, tester, make_gang, hire
    ):
        """A list of fighters on the screen of every fighter is exactly where
        a per-row query would hide: opened once per fighter, and worst on the
        gangs with the most of them."""
        from django.db import connection
        from django.test.utils import CaptureQueriesContext

        gang = make_gang("The Ashen Choir")
        here = hire(gang, "Vex")
        client.force_login(tester)
        url = reverse("n26-equip", args=[here.pk])
        # Once first: the session row is written on the first request of a
        # session and updated on the rest.
        client.get(url)

        with CaptureQueriesContext(connection) as alone:
            assert client.get(url).status_code == 200
        for index in range(NAV_SIBLINGS * 2):
            hire(gang, f"Fighter {index:02d}")
        with CaptureQueriesContext(connection) as crowded:
            assert client.get(url).status_code == 200

        assert len(crowded.captured_queries) == len(alone.captured_queries)


class TestTheColourScheme:
    """The control lives in the account menu; it still has to be there and
    still has to be able to set all three states."""

    def test_every_scheme_is_reachable_from_the_account_menu(
        self, client, tester, make_gang
    ):
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


class TestWhoseCampaignsAreListed:
    """The same rules a gang's switcher follows, on the screens that belong
    to one campaign."""

    @pytest.fixture
    def make_campaign(self, tester):
        def make(name, owner=None):
            from n26.core.models import Campaign

            return Campaign.objects.create(name=name, owner=owner or tester)

        return make

    def test_it_lists_the_viewers_campaigns(self, tester, make_campaign):
        make_campaign("Ashfall")
        make_campaign("Sump City")
        switcher = campaign_switcher(request_for(tester), make_campaign("Dust Falls"))
        assert {item.label for item in switcher.items} == {
            "Ashfall",
            "Sump City",
            "Dust Falls",
        }

    def test_someone_elses_campaigns_are_not_in_it(
        self, tester, stranger, make_campaign
    ):
        mine = make_campaign("Ashfall")
        make_campaign("Theirs", owner=stranger)
        switcher = campaign_switcher(request_for(tester), mine)
        assert [item.label for item in switcher.items] == ["Ashfall"]

    def test_an_archived_campaign_is_not_offered(self, tester, make_campaign):
        mine = make_campaign("Ashfall")
        make_campaign("Gone").archive()
        switcher = campaign_switcher(request_for(tester), mine)
        assert [item.label for item in switcher.items] == ["Ashfall"]

    def test_the_campaign_you_are_on_is_marked(self, tester, make_campaign):
        make_campaign("Sump City")
        here = make_campaign("Ashfall")
        switcher = campaign_switcher(request_for(tester), here)
        assert [item.label for item in switcher.items if item.current] == ["Ashfall"]
        assert switcher.label == "Ashfall"

    def test_the_campaign_you_are_on_survives_the_cap(self, tester, make_campaign):
        """Named last in the alphabet, so a capped query drops it — and a
        switcher that omits the page it is on says the reader is nowhere."""
        for index in range(NAV_SIBLINGS + 2):
            make_campaign(f"Campaign {index:02d}")
        here = make_campaign("Zzz, the last one")
        switcher = campaign_switcher(request_for(tester), here)
        assert switcher.items[0].label == "Zzz, the last one"
        assert switcher.items[0].current

    def test_the_list_is_read_once_however_often_it_is_drawn(
        self, tester, make_campaign, django_assert_num_queries
    ):
        """Memoised on the request: a page drawing the bar and the switcher
        beside a heading would otherwise fetch the same campaigns twice."""
        for index in range(5):
            make_campaign(f"Campaign {index}")
        here = make_campaign("Ashfall")
        request = request_for(tester)
        with django_assert_num_queries(1):
            campaign_switcher(request, here)
            campaign_switcher(request, here)
