"""The gang sheet: the design system's view over real rows.

Everything the page draws comes from ``render_gang``, which has its own
tests — these are about the wiring: who may see a gang, what a bad URL
does, and that the dashboard's rows actually reach it.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Gang
from n26.core.operations import operation

pytestmark = pytest.mark.django_db


@pytest.fixture
def tester(db):
    """Staff, because /n26/ is fenced to staff and testers.

    Not a group member: staff is the shorter of the two ways through the
    gate, and which one a viewer used is not what these tests are about.
    """
    return User.objects.create_user("player", is_staff=True)


@pytest.fixture
def gang(gang_type, tester):
    return Gang.objects.create(
        name="The Ashen Choir",
        owner=tester,
        gang_type=gang_type,
        starting_credits=1000,
        credits=340,
    )


def test_draws_the_gang(client, tester, gang):
    client.force_login(tester)
    response = client.get(reverse("n26-gang", args=[gang.pk]))
    assert response.status_code == 200
    body = response.content.decode()
    assert gang.name in body
    assert str(gang.gang_type) in body


def test_draws_each_member(client, tester, gang, make_profile, make_statline):
    """A hired fighter reaches the page as a card of its own."""
    profile = make_profile("Ganger", price=55)
    make_statline(profile, movement=5, weapon_skill=4, toughness=3)
    with operation(gang, actor=tester) as op:
        op.hire(profile, "Vex")
        op.hire(profile, "Sull")

    client.force_login(tester)
    body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    assert "Vex" in body
    assert "Sull" in body


def test_draws_the_gangs_standing_facts(client, tester, gang):
    """A counter the gang keeps reaches the details list, name and value."""
    from n26.library.authoring import create_counter
    from n26.tests.sandbox.actions import assign, tally

    tally(assign(create_counter("Meat"), gang=gang, actor=tester), +3)

    client.force_login(tester)
    body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    assert "Meat" in body


def test_no_empty_details_list_when_there_is_nothing_to_list(client, tester, gang):
    """The sheet spaces its sections, so an empty <dl> costs a visible gap.

    Pinned because the fix is a conditional slot, and a slot that turns
    out always to be filled would look identical in every other test.
    """
    client.force_login(tester)
    before = (
        client.get(reverse("n26-gang", args=[gang.pk])).content.decode().count("<dl")
    )

    from n26.library.authoring import create_counter
    from n26.tests.sandbox.actions import assign, tally

    tally(assign(create_counter("Meat"), gang=gang, actor=tester), +3)
    after = (
        client.get(reverse("n26-gang", args=[gang.pk])).content.decode().count("<dl")
    )

    assert after == before + 1


def test_someone_elses_gang_is_not_found(client, gang):
    """404 rather than 403 — which gangs exist is not there to be probed."""
    stranger = User.objects.create_user("stranger", is_staff=True)
    client.force_login(stranger)
    assert client.get(reverse("n26-gang", args=[gang.pk])).status_code == 404


def test_an_archived_gang_is_not_found(client, tester, gang):
    gang.archived = True
    gang.save()
    client.force_login(tester)
    assert client.get(reverse("n26-gang", args=[gang.pk])).status_code == 404


def test_a_pk_that_is_not_a_ulid_is_not_found(client, tester):
    """The id reaches ULIDField, which raises rather than missing.

    Without the view catching that, a mistyped URL is a 500 and an
    error report, for what is only ever somebody's bad link.
    """
    client.force_login(tester)
    assert client.get("/n26/gangs/nonsense/").status_code == 404


def test_founding_still_wins_over_the_id_route(client, tester):
    """`gangs/new/` must not resolve "new" as a gang id."""
    client.force_login(tester)
    assert client.get(reverse("n26-create-gang")).status_code == 200


def test_the_dashboard_links_to_the_sheet(client, tester, gang):
    """The row's href is the whole point of the screen being reachable."""
    client.force_login(tester)
    body = client.get(reverse("n26-dashboard")).content.decode()
    assert reverse("n26-gang", args=[gang.pk]) in body
