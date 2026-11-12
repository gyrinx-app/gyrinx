"""Campaign toolkit writes, inbox delivery and permission boundaries."""

import json
from datetime import date
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Notification
from n26.core import toolkit
from n26.core.campaigns import campaign_operation
from n26.core.models import (
    Assignment,
    CampaignParticipant,
    CounterValue,
    Miniature,
)
from n26.core.models.toolkit import (
    TAG_ICONS,
    CampaignTag,
    Intervention,
    InterventionReceipt,
    ToolkitAlert,
    ToolkitDelivery,
)
from n26.core.reconcile import check_gang
from n26.library.authoring import create_counter, create_weapon
from n26.tests.sandbox.actions import found_campaign, found_gang, join_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def demo(campaign_type, gang_type):
    arb = User.objects.create_user("toolkit-arbitrator")
    players = [User.objects.create_user(f"toolkit-player-{i}") for i in range(2)]
    campaign = found_campaign("Dust Falls", campaign_type, owner=arb)
    gangs = []
    for i, player in enumerate(players):
        CampaignParticipant.objects.create(
            campaign=campaign, user=player, state=CampaignParticipant.State.ACCEPTED
        )
        gang = found_gang(f"Gang {i}", gang_type, owner=player, budget=1000)
        join_campaign(gang, campaign)
        gangs.append(gang)
    return campaign, arb, players, gangs


def command(campaign, actor, action, payload, key=None):
    return toolkit.change(
        campaign,
        actor,
        action,
        {"request_key": str(key or uuid4()), "payload": json.dumps(payload)},
    )


def offer(gangs, **overrides):
    return {
        "title": "Supply drop",
        "narrative": "Recovered from the ash road.",
        "mode": "bundle",
        "choices": 1,
        "rewards": [{"kind": "credits", "amount": 30}],
        "recipients_mode": "selected",
        "gangs": [str(g.pk) for g in gangs],
        "inform_all": False,
        **overrides,
    }


def test_bundle_updates_every_gang_and_replays_without_duplicate_rewards(demo):
    campaign, arb, players, gangs = demo
    payload = offer(gangs)
    key = uuid4()
    for _ in range(2):
        form, url = command(campaign, arb, "intervention", payload, key)
        assert url, form.errors
    assert Intervention.objects.count() == 1
    for gang in gangs:
        gang.refresh_from_db()
        assert gang.credits == 1030
        assert check_gang(gang) == []
    form, url = command(
        campaign, arb, "intervention", offer(gangs, title="Different"), key
    )
    assert url is None
    assert form.errors


def test_each_gang_chooses_once_and_only_its_owner_can_choose(demo):
    campaign, arb, players, gangs = demo
    form, url = command(
        campaign,
        arb,
        "intervention",
        offer(
            gangs,
            mode="choice",
            rewards=[
                {"kind": "credits", "amount": 30},
                {"kind": "credits", "amount": 60},
            ],
        ),
    )
    assert url, form.errors
    receipt = InterventionReceipt.objects.get(gang=gangs[0])
    selection = {"receipt": str(receipt.pk), "selected": [1]}
    assert command(campaign, players[1], "choose", selection)[1] is None
    assert command(campaign, arb, "choose", selection)[1] is None
    assert (
        command(campaign, players[0], "choose", {**selection, "selected": [0, 1]})[1]
        is None
    )
    assert command(campaign, players[0], "choose", selection)[1]
    assert command(campaign, players[0], "choose", selection)[1]
    assert (
        command(campaign, players[0], "choose", {**selection, "selected": [0]})[1]
        is None
    )
    gangs[0].refresh_from_db()
    gangs[1].refresh_from_db()
    assert gangs[0].credits == 1060
    assert gangs[1].credits == 1000
    assert InterventionReceipt.objects.get(gang=gangs[1]).resolved_at is None
    assert check_gang(gangs[0]) == []


def test_equipment_resources_and_profiles_use_the_gang_ledger(demo, make_profile):
    campaign, arb, players, gangs = demo
    weapon = create_weapon("Supply shotgun", price=30)
    resource = create_counter("Supply crates")
    profile = make_profile("Reinforcement", price=50)
    rewards = [
        {"kind": "weapon", "id": str(weapon.pk), "amount": 2},
        {"kind": "resource", "id": str(resource.pk), "amount": 4},
        {"kind": "profile", "id": str(profile.pk), "amount": 1},
    ]
    form, url = command(
        campaign, arb, "intervention", offer(gangs[:1], rewards=rewards)
    )
    assert url, form.errors
    gang = gangs[0]
    gang.refresh_from_db()
    assert gang.credits == 1000
    assert Assignment.objects.filter(stash_root__gang=gang, weapon=weapon).count() == 2
    assert (
        CounterValue.objects.get(
            assignment__gang=gang, assignment__counter=resource
        ).value
        == 4
    )
    assert (
        Miniature.objects.filter(
            membership__gang=gang, membership__profile=profile
        ).count()
        == 1
    )
    assert check_gang(gang) == []


@pytest.mark.parametrize("target", ["gangs", "players"])
def test_tags_apply_to_gangs_or_players_and_can_be_removed(demo, target):
    campaign, arb, players, gangs = demo
    payload = offer(
        gangs[:1],
        target=target,
        players=[str(players[0].pk)],
        rewards=[
            {
                "kind": "tag",
                "name": "Most Wanted",
                "info": "Bounty issued: 50 credits.",
                "icon": "key-round",
                "amount": 1,
            }
        ],
    )
    form, url = command(campaign, arb, "intervention", payload)
    assert url, form.errors
    tag = CampaignTag.objects.get()
    assert (
        (tag.player_id == players[0].pk)
        if target == "players"
        else (tag.gang_id == gangs[0].pk)
    )
    assert command(campaign, players[0], "remove_tag", {"tag": str(tag.pk)})[1] is None
    form, url = command(campaign, arb, "remove_tag", {"tag": str(tag.pk)})
    assert url, form.errors
    tag.refresh_from_db()
    assert tag.removed_at is not None


def test_player_targets_cannot_receive_roster_or_credit_rewards(demo):
    campaign, arb, players, gangs = demo
    form, url = command(
        campaign,
        arb,
        "intervention",
        offer([], target="players", players=[str(players[0].pk)]),
    )
    assert url is None
    assert Intervention.objects.count() == 0


def test_notifications_include_campaign_link_and_announce_offer_and_choices(
    demo, django_capture_on_commit_callbacks
):
    campaign, arb, players, gangs = demo
    with django_capture_on_commit_callbacks(execute=True):
        form, url = command(
            campaign,
            arb,
            "intervention",
            offer(
                gangs[:1],
                mode="choice",
                inform_all=True,
                rewards=[
                    {"kind": "credits", "amount": 30},
                    {"kind": "credits", "amount": 60},
                ],
            ),
        )
    assert url, form.errors
    receipt = InterventionReceipt.objects.get()
    before = Notification.objects.filter(owner=players[1]).count()
    assert before == 1
    with django_capture_on_commit_callbacks(execute=True):
        assert command(
            campaign,
            players[0],
            "choose",
            {"receipt": str(receipt.pk), "selected": [0]},
        )[1]
    assert Notification.objects.filter(owner=players[1]).count() == before + 1
    for n in Notification.objects.all():
        assert campaign.name in n.subject
        assert toolkit.campaign_href(campaign) in n.content
        assert n.sender_id == arb.pk
        assert n.target_url
    from n26.notifications import retry_toolkit_notifications

    retry_toolkit_notifications.func()
    assert Notification.objects.count() == 7


def test_communications_consolidate_duplicate_gang_owners(
    demo, django_capture_on_commit_callbacks
):
    campaign, arb, players, gangs = demo
    other = found_gang(
        "Another gang", gangs[0].gang_type, owner=players[0], budget=1000
    )
    join_campaign(other, campaign)
    with django_capture_on_commit_callbacks(execute=True):
        form, url = command(
            campaign,
            arb,
            "communication",
            offer([gangs[0], other], title="Campaign night", body="Meet at seven."),
        )
    assert url, form.errors
    assert Notification.objects.filter(owner=players[0]).count() == 1
    assert Notification.objects.get().target_url == toolkit.campaign_href(campaign)


def test_alerts_fire_for_player_join_and_recorded_outcome(
    demo, django_capture_on_commit_callbacks
):
    campaign, arb, players, gangs = demo
    assert command(
        campaign, arb, "alerts", {"events": ["gang_added", "battle_outcome"]}
    )[1]
    other = found_gang(
        "New arrivals", gangs[0].gang_type, owner=players[0], budget=1000
    )
    with django_capture_on_commit_callbacks(execute=True):
        join_campaign(other, campaign, actor=players[0])
    assert Notification.objects.filter(owner=arb).count() == 1
    with django_capture_on_commit_callbacks(execute=True):
        with campaign_operation(campaign, actor=arb) as act:
            battle = act.record_battle(date.today(), gangs, scenario="Road crossing")
    assert Notification.objects.filter(owner=arb).count() == 1
    with django_capture_on_commit_callbacks(execute=True):
        with campaign_operation(campaign, actor=arb) as act:
            act.record_outcome(
                battle, result="draw", winners=[], revision=battle.revision
            )
    assert Notification.objects.filter(owner=arb).count() == 2
    assert command(campaign, arb, "alerts", {"events": []})[1]
    assert ToolkitAlert.objects.count() == 0


def test_non_arbitrators_cannot_open_or_post_toolkit_forms(client, demo):
    campaign, arb, players, gangs = demo
    client.force_login(players[0])
    assert client.get(reverse("n26-toolkit", args=[campaign.pk])).status_code == 404
    assert (
        client.post(
            reverse("n26-toolkit-command", args=[campaign.pk, "intervention"]),
            {"request_key": str(uuid4()), "payload": json.dumps(offer(gangs))},
        ).status_code
        == 404
    )
    assert Intervention.objects.count() == 0


def test_toolkit_and_dashboard_use_the_existing_n26_shell(client, demo):
    campaign, arb, players, gangs = demo
    client.force_login(arb)
    response = client.get(reverse("n26-toolkit", args=[campaign.pk]))
    assert response.status_code == 200
    assert b'data-react-name="arbitrator-toolkit"' in response.content
    dashboard = client.get(reverse("n26-campaign", args=[campaign.pk]))
    assert toolkit.toolkit_href(campaign) in dashboard.content.decode()
    client.force_login(players[0])
    assert (
        toolkit.toolkit_href(campaign)
        not in client.get(reverse("n26-campaign", args=[campaign.pk])).content.decode()
    )


def test_all_requested_icons_resolve_to_lucide():
    from n26.core.icons import resolve

    assert {"key-round", "paintbrush", "printer", "library-big"} <= set(TAG_ICONS)
    for name in TAG_ICONS:
        assert resolve(name).body


@pytest.mark.parametrize(
    "patch", [{"mode": []}, {"gangs": [{}]}, {"rewards": [{"kind": [], "amount": 1}]}]
)
def test_malformed_payloads_are_rejected_without_partial_rewards(demo, patch):
    campaign, arb, players, gangs = demo
    form, url = command(campaign, arb, "intervention", {**offer(gangs), **patch})
    assert url is None
    assert form.errors
    assert Intervention.objects.count() == 0


def test_home_query_count_stays_flat_as_interventions_and_tags_grow(client, demo):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    campaign, arb, players, gangs = demo
    client.force_login(arb)

    def count():
        with CaptureQueriesContext(connection) as queries:
            response = client.get(reverse("n26-toolkit", args=[campaign.pk]))
        assert response.status_code == 200
        return len(queries)

    command(campaign, arb, "intervention", offer(gangs[:1]))
    count()
    before = count()
    for i in range(5):
        command(
            campaign,
            arb,
            "intervention",
            offer(
                gangs,
                rewards=[
                    {
                        "kind": "tag",
                        "name": f"Status {i}",
                        "info": "Campaign status.",
                        "icon": "paintbrush",
                    }
                ],
            ),
        )
    assert count() == before


def test_native_and_json_adapters_apply_equivalent_commands(client, demo):
    campaign, arb, players, gangs = demo
    client.force_login(arb)
    native = client.post(
        reverse("n26-toolkit-form", args=[campaign.pk, "intervention"]),
        {"request_key": str(uuid4()), "payload": json.dumps(offer(gangs[:1]))},
    )
    api = client.post(
        reverse("n26-toolkit-command", args=[campaign.pk, "intervention"]),
        {"request_key": str(uuid4()), "payload": json.dumps(offer(gangs[1:]))},
    )
    assert native.status_code == 302
    assert api.status_code == 200
    for gang in gangs:
        gang.refresh_from_db()
        assert gang.credits == 1030
        assert check_gang(gang) == []


def test_notification_failure_keeps_the_reward_and_is_retryable(
    demo, monkeypatch, django_capture_on_commit_callbacks
):
    from n26 import notifications

    campaign, arb, players, gangs = demo
    original = notifications.tell
    monkeypatch.setattr(notifications, "tell", lambda *args, **kwargs: None)
    with django_capture_on_commit_callbacks(execute=True):
        form, url = command(campaign, arb, "intervention", offer(gangs[:1]))
    assert url, form.errors
    gangs[0].refresh_from_db()
    assert gangs[0].credits == 1030
    assert ToolkitDelivery.objects.get().delivered_at is None
    monkeypatch.setattr(notifications, "tell", original)
    notifications.retry_toolkit_notifications.func()
    notifications.retry_toolkit_notifications.func()
    assert Notification.objects.count() == 1
    assert check_gang(gangs[0]) == []


def test_invalid_child_identifiers_return_not_found(client, demo):
    campaign, arb, players, gangs = demo
    client.force_login(arb)
    for path in [
        reverse("n26-toolkit-form", args=[campaign.pk, "remove_tag"]) + "?tag=invalid",
        reverse("n26-toolkit-form", args=[campaign.pk, "choose"]) + "?receipt=invalid",
        reverse("n26-toolkit-intervention", args=[campaign.pk, "invalid"]),
    ]:
        assert client.get(path).status_code == 404
