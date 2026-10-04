"""One deliberate campaign counter change, retaining existing tally permissions."""

import json

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core.campaigns import campaign_operation
from n26.core.models import Assignment, CampaignParticipant, LedgerEvent
from n26.core.render import render_gang
from n26.flags import CAMPAIGNS
from n26.tests.sandbox.actions import (
    assign,
    create_counter,
    ef_contributes_to_counter,
    found_campaign,
    found_gang,
    modifier,
    targets_gang_alone,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def setup(client, campaign_type, gang_type):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    arbitrator = User.objects.create_user("arbitrator")
    player = User.objects.create_user("player")
    campaign = found_campaign("Dust Falls", campaign_type, owner=arbitrator)
    CampaignParticipant.objects.create(
        campaign=campaign, user=player, state=CampaignParticipant.State.ACCEPTED
    )
    with campaign_operation(campaign, actor=arbitrator) as op:
        counter = op.add_counter("Meat", opening=2)
    modifier(
        "Rules add three Meat",
        targets_gang_alone(),
        ef_contributes_to_counter(counter, 3),
        carried_by=campaign.additions,
    )
    gang = found_gang("Rust Kings", gang_type, owner=player)
    with campaign_operation(campaign, actor=arbitrator) as op:
        op.add_gang(gang)
    held = Assignment.objects.get(gang_root=gang, counter=counter, archived=False)
    client.force_login(arbitrator)
    return arbitrator, player, campaign, gang, held


def address(held):
    return reverse("n26-tally", args=[held.pk])


def events(held):
    return LedgerEvent.objects.filter(assignment=held, kind=LedgerEvent.Kind.TALLIED)


def reading(gang):
    return next(
        line for line in render_gang(gang).campaign.counters if line.name == "Meat"
    )


def test_amount_form_is_read_only_and_separates_recorded_from_contributed_values(
    client, setup
):
    _, _, _, gang, held = setup
    before = events(held).count()
    response = client.get(address(held))
    assert response.status_code == 200
    html = response.content.decode()
    assert "Recorded Meat: 2" in html
    assert "Contributions from rules and assets are added separately" in html
    assert events(held).count() == before
    assert (reading(gang).value, reading(gang).tallied) == (5, 2)


@pytest.mark.parametrize("actor", ["arbitrator", "player"])
def test_one_amount_records_one_change_with_the_actor_and_preserves_contributions(
    client, setup, actor
):
    arbitrator, player, campaign, gang, held = setup
    person = arbitrator if actor == "arbitrator" else player
    client.force_login(person)
    before = events(held).count()
    back = reverse("n26-campaign", args=[campaign.pk]) + "#gangs"
    response = client.post(address(held), {"adjust": 1, "change": 15, "back": back})
    assert response.status_code == 302
    assert response.url == back
    assert events(held).count() == before + 1
    event = events(held).latest("created")
    assert event.actor == person
    assert event.note == "+15 → 17"
    assert (reading(gang).value, reading(gang).tallied) == (20, 17)


def test_removing_an_amount_floors_the_recorded_value_without_removing_contributions(
    client, setup
):
    _, _, _, gang, held = setup
    assert client.post(address(held), {"adjust": 1, "change": -15}).status_code == 302
    assert (reading(gang).value, reading(gang).tallied) == (3, 0)
    assert events(held).latest("created").note == "-2 → 0"


@pytest.mark.parametrize("value", ["", "0", "words", "1001", "-1001"])
def test_invalid_amount_redraws_errors_without_a_change(client, setup, value):
    _, _, _, _, held = setup
    before = events(held).count()
    response = client.post(address(held), {"adjust": 1, "change": value})
    assert response.status_code == 200
    assert response.context["form"].errors["change"]
    assert events(held).count() == before


def test_unrelated_readers_and_arbitrator_of_personal_counter_are_refused(
    client, setup
):
    arbitrator, _, _, gang, held = setup
    client.force_login(User.objects.create_user("stranger"))
    assert client.get(address(held)).status_code == 404
    assert client.post(address(held), {"adjust": 1, "change": 15}).status_code == 404
    client.force_login(arbitrator)
    personal = assign(create_counter("Personal counter"), gang=gang)
    assert client.get(address(personal)).status_code == 404
    assert (
        client.post(address(personal), {"adjust": 1, "change": 15}).status_code == 404
    )


def test_return_target_is_validated_for_cancel_and_submit(client, setup):
    _, _, _, gang, held = setup
    target = "https://example.com/outside"
    response = client.get(address(held), {"back": target})
    assert response.context["back"] == reverse("n26-gang", args=[gang.pk])
    assert target not in response.content.decode()
    assert client.post(
        address(held), {"adjust": 1, "change": 1, "back": target}
    ).url == reverse("n26-gang", args=[gang.pk])


def test_campaign_and_owner_roster_offer_amount_links_but_readers_do_not(client, setup):
    _, player, campaign, gang, held = setup
    page = reverse("n26-campaign", args=[campaign.pk])
    soup = BeautifulSoup(client.get(page).content, "html.parser")
    assert soup.find("a", {"aria-label": "Adjust Meat"})["href"].startswith(
        address(held)
    )
    client.force_login(player)
    assert (
        "Adjust Meat"
        in client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    )
    client.force_login(User.objects.create_user("reader"))
    assert "Adjust Meat" not in client.get(page).content.decode()
    assert (
        "Adjust Meat"
        not in client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
    )


def test_removing_from_zero_shows_an_error_without_recording_an_empty_change(
    client, setup
):
    _, _, _, gang, held = setup
    assert client.post(address(held), {"adjust": 1, "change": -2}).status_code == 302
    before = events(held).count()
    response = client.post(address(held), {"adjust": 1, "change": -5})
    assert response.status_code == 200
    assert "already 0" in response.context["form"].errors["change"][0]
    assert events(held).count() == before
    assert (reading(gang).value, reading(gang).tallied) == (3, 0)


@pytest.mark.parametrize("actor", ["arbitrator", "player"])
@pytest.mark.parametrize("origin", ["n26-campaign", "n26-gang"])
def test_one_point_updates_just_the_counter_and_sends_a_toast(
    client, setup, actor, origin
):
    arbitrator, player, campaign, gang, held = setup
    client.force_login(arbitrator if actor == "arbitrator" else player)
    back = reverse(origin, args=[campaign.pk if origin == "n26-campaign" else gang.pk])
    response = client.post(
        address(held), {"change": 1, "back": back}, HTTP_HX_REQUEST="true"
    )
    assert response.status_code == 200
    soup = BeautifulSoup(response.content, "html.parser")
    host = soup.find(id=f"n26-counter-{held.pk}")
    assert host["hx-swap-oob"] == "true"
    assert host.select_one("[data-counter-value]").get_text(strip=True) == "6"
    assert not soup.find("html")
    assert not soup.find(id="n26-campaign-gangs")
    assert "HX-Replace-Url" not in response
    assert (
        json.loads(response["HX-Trigger"])["n26-toasts"][0]["message"]
        == "Meat is now 6."
    )
    assert (reading(gang).value, reading(gang).tallied) == (6, 3)
    assert {form["hx-post"] for form in host.find_all("form")} == {address(held)}
    assert all(
        form.find("input", {"name": "back"})["value"] == back
        for form in host.find_all("form")
    )


def test_the_owner_sheets_use_async_counter_controls(client, setup):
    _, player, campaign, gang, held = setup
    client.force_login(player)
    for route, pk in [("n26-campaign", campaign.pk), ("n26-gang", gang.pk)]:
        soup = BeautifulSoup(
            client.get(reverse(route, args=[pk])).content, "html.parser"
        )
        host = soup.find(id=f"n26-counter-{held.pk}")
        assert host
        assert len(host.find_all("form", {"hx-post": address(held)})) == 2


def test_the_async_counter_update_does_not_load_other_campaign_gangs(
    client, setup, gang_type
):
    arbitrator, player, campaign, _, held = setup
    payload = {"change": 1, "back": reverse("n26-campaign", args=[campaign.pk])}
    client.post(address(held), payload, HTTP_HX_REQUEST="true")
    with CaptureQueriesContext(connection) as few:
        assert (
            client.post(address(held), payload, HTTP_HX_REQUEST="true").status_code
            == 200
        )
    for number in range(6):
        other = found_gang(f"Other gang {number}", gang_type, owner=player)
        with campaign_operation(campaign, actor=arbitrator) as op:
            op.add_gang(other)
    with CaptureQueriesContext(connection) as many:
        assert (
            client.post(address(held), payload, HTTP_HX_REQUEST="true").status_code
            == 200
        )
    assert len(many) <= len(few)
