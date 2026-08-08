"""The gangs index: the bar's Gangs link, and where it lands.

The page draws the same table the dashboard's first tab does, so these
tests are about the wiring — whose gangs reach it, whose do not, and
that the facets the filter needs come with them.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Gang

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """Staff, because /n26/ is fenced to staff and testers."""
    return User.objects.create_user("player", is_staff=True)


@pytest.fixture
def make_gang(gang_type, tester):
    def _make(name, owner=None):
        return Gang.objects.create(
            name=name,
            owner=owner or tester,
            gang_type=gang_type,
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
