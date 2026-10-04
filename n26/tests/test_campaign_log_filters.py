"""Campaign log filters keep complete acts, attribution and shareable URLs."""

from datetime import UTC, datetime
from unittest.mock import patch

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone

from gyrinx.site.models import Availability, FeatureFlag
from gyrinx.timezones import SESSION_TZ_KEY, SESSION_TZ_USER_KEY
from n26.core.campaigns import campaign_operation
from n26.core.models import Assignment, CampaignParticipant
from n26.core.operations import operation
from n26.flags import CAMPAIGNS
from n26.library.authoring import add_asset_type, create_asset
from n26.library.models import AssetType
from n26.tests.sandbox.actions import found_campaign, found_gang

pytestmark = pytest.mark.django_db


def at(day, hour=12):
    return patch(
        "django.utils.timezone.now",
        return_value=datetime(2026, 10, day, hour, tzinfo=UTC),
    )


@pytest.fixture
def setup(client, campaign_type, gang_type):
    FeatureFlag.objects.create(
        slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
    )
    arbitrator = User.objects.create_user("arbitrator")
    player = User.objects.create_user("player")
    kind = add_asset_type(campaign_type, "Territory", AssetType.Ownership.HOLDING)
    asset = create_asset("Old Ruins", kind)
    campaign = found_campaign("Dust Falls", campaign_type, owner=arbitrator)
    CampaignParticipant.objects.create(
        campaign=campaign, user=player, state=CampaignParticipant.State.ACCEPTED
    )
    one = found_gang("Rust Kings", gang_type, owner=player)
    two = found_gang("Ash Vipers", gang_type, owner=arbitrator)
    with campaign_operation(campaign, actor=arbitrator) as op:
        counter = op.add_counter("Meat")
        first = op.add_gang(one)
        second = op.add_gang(two)
        holding = op.add_asset(asset)
        op.assign(holding, first)
    held_one = Assignment.objects.get(gang_root=one, counter=counter, archived=False)
    held_two = Assignment.objects.get(gang_root=two, counter=counter, archived=False)
    with at(1), operation(one, actor=player) as op:
        op.tally(held_one, 7)
    with at(2), operation(two, actor=arbitrator) as op:
        op.tally(held_two, 11)
    with at(3), campaign_operation(campaign, actor=arbitrator) as op:
        op.transfer(holding, second)
    client.force_login(arbitrator)
    return arbitrator, player, campaign, first, second, held_one


def address(campaign):
    return reverse("n26-campaign-log", args=[campaign.pk])


def acts(response):
    return [act for day in response.context["days"] for act in day.acts]


def text(act):
    return "".join(span.text for span in act.spans)


def test_player_filter_matches_the_actor_including_the_readers_own_acts(client, setup):
    arbitrator, player, campaign, _, _, _ = setup
    response = client.get(address(campaign), {"player": player.pk})
    assert response.context["matched"] == 1
    assert "+7" in text(acts(response)[0])
    client.force_login(player)
    response = client.get(address(campaign), {"player": player.pk})
    assert acts(response)[0].actor == "You"
    assert response.context["matched"] == 1
    response = client.get(
        address(campaign),
        {
            "player": arbitrator.pk,
            "from_date": "2026-10-03",
            "to_date": "2026-10-03",
            "kind": "gang",
        },
    )
    assert any(
        "went from Rust Kings to Ash Vipers" in text(act) for act in acts(response)
    )


@pytest.mark.parametrize("side", ["first", "second"])
def test_gang_filter_keeps_both_sides_of_a_transfer_once(client, setup, side):
    _, _, campaign, first, second, _ = setup
    gang = first.gang if side == "first" else second.gang
    response = client.get(address(campaign), {"gang": gang.pk})
    transfer = [
        act
        for act in acts(response)
        if "went from Rust Kings to Ash Vipers" in text(act)
    ]
    assert len(transfer) == 1
    assert str(first.gang_id) in transfer[0].related_gang_pks
    assert str(second.gang_id) in transfer[0].related_gang_pks
    assert all(
        act.gang_pk == str(gang.pk) or str(gang.pk) in act.related_gang_pks
        for act in acts(response)
    )


def test_date_range_is_inclusive_and_uses_the_displayed_local_date(client, setup):
    _, player, campaign, first, _, held = setup
    with timezone.override("UTC"):
        response = client.get(
            address(campaign), {"from_date": "2026-10-02", "to_date": "2026-10-02"}
        )
        assert response.context["matched"] == 1
        assert "+11" in text(acts(response)[0])
    with (
        patch(
            "django.utils.timezone.now",
            return_value=datetime(2026, 10, 1, 23, 30, tzinfo=UTC),
        ),
        operation(first.gang, actor=player) as op,
    ):
        op.tally(held, 9)
    session = client.session
    session[SESSION_TZ_KEY] = "Europe/London"
    session[SESSION_TZ_USER_KEY] = setup[0].pk
    session.save()
    with timezone.override("Europe/London"):
        response = client.get(
            address(campaign),
            {"from_date": "2026-10-02", "to_date": "2026-10-02", "player": player.pk},
        )
    assert response.context["matched"] == 1
    assert "+9" in text(acts(response)[0])


def test_action_type_uses_existing_history_categories_and_filters_combine(
    client, setup
):
    _, _, campaign, first, _, _ = setup
    response = client.get(address(campaign), {"kind": "campaign"})
    assert acts(response) and all(act.category == "campaign" for act in acts(response))
    response = client.get(
        address(campaign), {"gang": first.gang.pk, "kind": "campaign"}
    )
    assert response.context["matched"] == 0
    assert "No activity matches these filters." in response.content.decode()


@pytest.mark.parametrize(
    "data",
    [
        {"from_date": "invalid"},
        {"from_date": "2026-10-03", "to_date": "2026-10-01"},
        {"player": "999999"},
        {"gang": "bad-key"},
        {"kind": "unknown"},
    ],
)
def test_invalid_filters_show_errors_and_never_default_to_unfiltered_results(
    client, setup, data
):
    _, _, campaign, _, _, _ = setup
    response = client.get(address(campaign), data)
    assert response.status_code == 200
    assert response.context["filters"].errors
    assert response.context["matched"] == 0


def test_filter_options_are_scoped_to_people_and_gangs_named_by_this_history(
    client, setup, gang_type
):
    _, _, campaign, _, _, _ = setup
    outsider = User.objects.create_user("private-outside-user")
    found_gang("Private outside gang", gang_type, owner=outsider)
    html = client.get(address(campaign)).content.decode()
    assert outsider.username not in html
    assert "Private outside gang" not in html


def test_pagination_preserves_filters_and_pages_complete_acts(client, setup):
    _, player, campaign, first, _, held = setup
    for _number in range(60):
        with operation(first.gang, actor=player) as op:
            op.tally(held, 1)
    response = client.get(address(campaign), {"player": player.pk})
    assert response.context["matched"] == 61
    assert len(acts(response)) == 50
    assert f"player={player.pk}" in response.context["pages"]["next"]
    page_two = client.get(address(campaign) + response.context["pages"]["next"])
    assert len(acts(page_two)) == 11
    assert page_two.context["filters"]["player"].value() == str(player.pk)


def test_more_matching_events_do_not_add_filter_queries(client, setup):
    _, player, campaign, first, _, held = setup
    path = address(campaign)
    data = {"player": player.pk}
    client.get(path, data)
    with CaptureQueriesContext(connection) as few:
        assert client.get(path, data).status_code == 200
    for _number in range(12):
        with operation(first.gang, actor=player) as op:
            op.tally(held, 1)
    with CaptureQueriesContext(connection) as many:
        assert client.get(path, data).status_code == 200
    assert len(many) <= len(few)
