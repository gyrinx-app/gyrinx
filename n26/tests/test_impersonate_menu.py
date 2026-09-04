"""The account menu's way into the account whose page is on screen.

Here rather than beside the views because the overlay is the platform's, not
the edition's, and only these tests may reach across to it.

A roster and a campaign are the two things that open for somebody other than
their owner, so they are the two pages that can name an account to go into.
Everything else in n26 is owner-scoped and 404s a stranger, which leaves
nobody to offer.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.models import Gang
from n26.flags import CAMPAIGNS
from n26.tests.sandbox.actions import found_campaign

pytestmark = [pytest.mark.django_db, pytest.mark.core]


@pytest.fixture
def overseer(client):
    """The superuser these tests read the app as. Staff too, because the
    menu group the way in sits in is the staff one."""
    person = User.objects.create_superuser("overseer", "overseer@example.com")
    client.force_login(person)
    return person


@pytest.fixture
def player():
    """Not named "player": the shared ``owner`` fixture takes that username,
    and a test asking for both would trip the unique constraint."""
    return User.objects.create_user("gang-owner")


@pytest.fixture
def make_gang(gang_type, player):
    def make(name, owner=None):
        return Gang.objects.create(
            name=name,
            owner=owner or player,
            gang_type=gang_type,
            starting_credits=1000,
            credits=1000,
        )

    return make


@pytest.fixture
def campaigns_open():
    """The flag rows are seeded by a data migration, which does not run
    under --nomigrations."""
    return FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )


def start_url(person):
    return reverse("core:impersonate-start", args=[person.pk])


class TestWhoIsOffered:
    def test_a_gang_somebody_else_owns_names_its_owner(
        self, client, overseer, player, make_gang
    ):
        gang = make_gang("The Ashen Choir")

        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert start_url(player) in body
        assert "Impersonate gang-owner" in body

    def test_your_own_gang_offers_nothing(self, client, overseer, make_gang):
        """You are already signed in as yourself."""
        gang = make_gang("The Ashen Choir", owner=overseer)

        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Impersonate" not in body

    def test_a_campaign_names_its_arbitrator(
        self, client, overseer, player, campaigns_open, campaign_type
    ):
        campaign = found_campaign(
            "Dust Falls", campaign_type, owner=player, budget=1000
        )

        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()

        assert start_url(player) in body
        assert "Impersonate gang-owner" in body

    def test_a_page_about_nobody_offers_nothing(self, client, overseer):
        """The gangs index is a list, not somebody's page."""
        body = client.get(reverse("n26-gangs")).content.decode()

        assert "Impersonate" not in body

    def test_staff_who_are_not_superusers_are_not_offered_it(
        self, client, player, make_gang
    ):
        """The row sits in the staff group, but the act is a superuser's."""
        author = User.objects.create_user("author", is_staff=True)
        client.force_login(author)
        gang = make_gang("The Ashen Choir")

        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Impersonate" not in body

    def test_an_owner_who_has_been_deactivated_is_not_offered(
        self, client, overseer, player, make_gang
    ):
        player.is_active = False
        player.save()
        gang = make_gang("The Ashen Choir")

        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Impersonate" not in body

    def test_a_reader_who_is_not_signed_in_is_offered_nothing(self, client, make_gang):
        """A roster opens for whoever holds its address, so this path runs
        with no user at all."""
        gang = make_gang("The Ashen Choir")

        response = client.get(reverse("n26-gang", args=[gang.pk]))

        assert response.status_code == 200
        assert "Impersonate" not in response.content.decode()


class TestWhatItDoes:
    def test_the_page_it_comes_back_to_is_the_one_you_were_on(
        self, client, overseer, player, make_gang
    ):
        """The way back rides on the form, not on the address of the act."""
        gang = make_gang("The Ashen Choir")
        page = reverse("n26-gang", args=[gang.pk])

        body = client.get(page).content.decode()

        assert f'name="next" value="{page}"' in body

    def test_it_starts_the_overlay_and_comes_back_to_the_page(
        self, client, overseer, player, make_gang
    ):
        gang = make_gang("The Ashen Choir")
        page = reverse("n26-gang", args=[gang.pk])

        response = client.post(start_url(player), {"next": page}, follow=True)

        assert response.status_code == 200
        assert response.redirect_chain[-1][0] == page
        assert "Impersonating" in response.content.decode()

    def test_nothing_is_offered_while_an_overlay_is_running(
        self, client, overseer, player, make_gang
    ):
        """Starting a second one is refused, so offering it would be a lie.

        The account gone into is itself a superuser, so the staff group is
        still drawn and the reader still passes every other check. What
        withholds the row is the running overlay and nothing else.
        """
        deputy = User.objects.create_superuser("deputy", "deputy@example.com")
        gang = make_gang("The Ashen Choir")
        page = reverse("n26-gang", args=[gang.pk])
        client.post(start_url(deputy), {"next": page})

        body = client.get(page).content.decode()

        assert "Staff only" in body
        assert "Impersonate" not in body
