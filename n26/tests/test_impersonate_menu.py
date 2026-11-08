"""Verify account-menu impersonation actions on public gang and campaign pages. The
platform handles permission checks and session state.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Gang
from n26.tests.sandbox.actions import found_campaign

pytestmark = [pytest.mark.django_db, pytest.mark.core]


@pytest.fixture
def overseer(client):
    """Authenticated superuser for account-menu permission checks."""
    person = User.objects.create_superuser("overseer", "overseer@example.com")
    client.force_login(person)
    return person


@pytest.fixture
def player():
    """Use a distinct username because the shared owner fixture already creates player."""
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
        """Impersonation is unnecessary when the page owner is already the current user."""
        gang = make_gang("The Ashen Choir", owner=overseer)

        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()

        assert "Impersonate" not in body

    def test_a_campaign_names_its_arbitrator(
        self, client, overseer, player, campaign_type
    ):
        campaign = found_campaign(
            "Dust Falls", campaign_type, owner=player, budget=1000
        )

        body = client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()

        assert start_url(player) in body
        assert "Impersonate gang-owner" in body

    def test_a_page_about_nobody_offers_nothing(self, client, overseer):
        """The gang index has no individual page owner to impersonate."""
        body = client.get(reverse("n26-gangs")).content.decode()

        assert "Impersonate" not in body

    def test_staff_who_are_not_superusers_are_not_offered_it(
        self, client, player, make_gang
    ):
        """Staff status alone does not permit impersonation."""
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
        """Public gang access must remain safe without an authenticated user."""
        gang = make_gang("The Ashen Choir")

        response = client.get(reverse("n26-gang", args=[gang.pk]))

        assert response.status_code == 200
        assert "Impersonate" not in response.content.decode()


class TestWhatItDoes:
    def test_the_page_it_comes_back_to_is_the_one_you_were_on(
        self, client, overseer, player, make_gang
    ):
        """Submit the current page as a next field with the impersonation action."""
        gang = make_gang("The Ashen Choir")
        page = reverse("n26-gang", args=[gang.pk])

        import json

        from bs4 import BeautifulSoup

        soup = BeautifulSoup(client.get(page).content, "html.parser")
        host = soup.select_one('[data-react-name="account-menu"]')
        menu = json.loads(soup.find(id=host["data-react-props"]).string)
        (staff,) = [e for e in menu["items"] if e.get("label") == "Staff only"]
        (form,) = [e for e in staff["items"] if e["type"] == "form"]
        assert form["action"] == start_url(player)
        assert ["next", page] in form["fields"]

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
        """An active impersonation session must hide further impersonation actions. Use a
        superuser target so other menu permission checks remain satisfied.
        """
        deputy = User.objects.create_superuser("deputy", "deputy@example.com")
        gang = make_gang("The Ashen Choir")
        page = reverse("n26-gang", args=[gang.pk])
        client.post(start_url(deputy), {"next": page})

        body = client.get(page).content.decode()

        assert "Staff only" in body
        assert "Impersonate" not in body
