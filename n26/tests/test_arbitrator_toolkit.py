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


def test_notifications_announce_offer_but_keep_selections_with_the_recipient(
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
    assert Notification.objects.filter(owner=players[1]).count() == before
    for n in Notification.objects.all():
        assert campaign.name in n.subject
        assert toolkit.campaign_href(campaign) in n.content
        assert n.sender_id == arb.pk
        assert n.target_url
    from n26.notifications import retry_toolkit_notifications

    retry_toolkit_notifications.func()
    assert Notification.objects.count() == 5


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


@pytest.mark.parametrize("method", ["remove", "refund"])
def test_fighter_departures_trigger_alerts_once(demo, make_profile, method):
    from n26.core.models.toolkit import ToolkitAlertEvent
    from n26.core.operations import operation

    campaign, arb, players, gangs = demo
    command(campaign, arb, "alerts", {"events": ["fighter_deleted"]})
    profile = make_profile("Lookout", price=50)
    with operation(gangs[0], actor=players[0]) as op:
        fighter = op.hire(profile, "Scout")
    with operation(gangs[0], actor=players[0]) as op:
        getattr(op, method)(fighter.membership)
    with operation(gangs[0], actor=players[0]) as op:
        getattr(op, method)(fighter.membership)
    assert ToolkitAlertEvent.objects.filter(event="fighter_deleted").count() == 1
    assert "Scout" in ToolkitAlertEvent.objects.get().text
    assert check_gang(gangs[0]) == []


def test_battle_creation_and_player_gang_removal_are_alertable(demo):
    from n26.core.models.toolkit import ToolkitAlertEvent

    campaign, arb, players, gangs = demo
    command(campaign, arb, "alerts", {"events": ["battle_created", "gang_removed"]})
    with campaign_operation(campaign, actor=players[0]) as act:
        act.record_battle(date.today(), gangs, scenario="Supply road")
    membership = campaign.memberships.get(gang=gangs[0], left__isnull=True)
    with campaign_operation(campaign, actor=players[0]) as act:
        act.remove_gang(membership)
    assert set(ToolkitAlertEvent.objects.values_list("event", flat=True)) == {
        "battle_created",
        "gang_removed",
    }


def test_offer_selection_can_alert_the_arbitrator_without_a_public_broadcast(
    demo, django_capture_on_commit_callbacks
):
    campaign, arb, players, gangs = demo
    command(campaign, arb, "alerts", {"events": ["offer_selected"]})
    with django_capture_on_commit_callbacks(execute=True):
        command(
            campaign,
            arb,
            "intervention",
            offer(gangs[:1], mode="choice", inform_all=True),
        )
    receipt = InterventionReceipt.objects.get()
    before = Notification.objects.filter(owner=players[1]).count()
    with django_capture_on_commit_callbacks(execute=True):
        command(
            campaign,
            players[0],
            "choose",
            {"receipt": str(receipt.pk), "selected": [0]},
        )
    assert Notification.objects.filter(owner=players[1]).count() == before
    assert (
        Notification.objects.filter(
            owner=arb, subject__contains="selects an intervention"
        ).count()
        == 1
    )


def test_asset_assign_transfer_and_release_capture_one_event_per_change(demo):
    from n26.core.models.toolkit import ToolkitAlertEvent
    from n26.library.authoring import add_asset_type, create_asset

    campaign, arb, players, gangs = demo
    command(campaign, arb, "alerts", {"events": ["asset_owner_changed"]})
    kind = add_asset_type(campaign.additions, "Workshop", "pooled")
    asset = create_asset("Repair shed", kind, pack=campaign.pack)
    memberships = list(campaign.memberships.select_related("gang").order_by("gang_id"))
    with campaign_operation(campaign, actor=arb) as act:
        held = act.add_asset(asset)
        act.assign(held, memberships[0])
        act.transfer(held, memberships[1])
        act.unassign(held)
        act.unassign(held)
    assert ToolkitAlertEvent.objects.filter(event="asset_owner_changed").count() == 3


def test_tags_have_a_separate_workflow_and_do_not_appear_as_interventions(client, demo):
    campaign, arb, players, gangs = demo
    client.force_login(arb)
    payload = offer(
        gangs[:1],
        rewards=[
            {
                "kind": "tag",
                "name": "Most Wanted",
                "icon": "crosshair",
                "info": "Bounty issued.",
            }
        ],
    )
    form, url = command(campaign, arb, "tags", payload)
    assert url.endswith("?tab=tags"), form.errors
    assert Intervention.objects.get().purpose == "tags"
    response = client.get(reverse("n26-toolkit", args=[campaign.pk]))
    assert response.context["toolkit_props"]["interventions"] == []
    assert response.context["toolkit_props"]["tags"][0]["name"] == "Most Wanted"


def test_inbox_attribution_uses_the_current_sender_name_and_badge(
    client, demo, django_capture_on_commit_callbacks
):
    campaign, arb, players, gangs = demo
    from gyrinx.accounts.models import UserProfile

    arb.is_staff = True
    arb.save(update_fields=["is_staff"])
    UserProfile.objects.get_or_create(user=arb)
    with django_capture_on_commit_callbacks(execute=True):
        command(
            campaign,
            arb,
            "communication",
            offer(gangs[:1], title="Update", body="A message."),
        )
    notification = Notification.objects.get(owner=players[0])
    notification.content = (
        "<p>Legacy attribution</p><p>Choose exactly 1 rewards from the offer.</p>"
    )
    notification.save(update_fields=["content"])
    client.force_login(players[0])
    response = client.get(reverse("core:notifications"), HTTP_ACCEPT="application/json")
    assert response.status_code == 200
    assert "1 rewards" not in json.dumps(response.json())
    assert "1 reward from" in json.dumps(response.json())
    context = response.json()["rows"][0]["context"]
    assert context["sender"]["name"] == arb.username
    assert context["sender"]["badge"]["svg"]
    assert context["campaignHref"] == toolkit.campaign_href(campaign)


def test_report_only_alerts_capture_actions_without_immediate_notifications(
    demo, django_capture_on_commit_callbacks
):
    from n26.core.models.toolkit import ToolkitAlertEvent, ToolkitAlertSettings
    from n26.core.toolkit_alerts import deliver_due_reports

    campaign, arb, players, gangs = demo
    form, url = command(
        campaign,
        arb,
        "alerts",
        {
            "events": ["battle_created"],
            "immediate": False,
            "report_enabled": True,
            "report_days": 2,
        },
    )
    assert url, form.errors
    settings = ToolkitAlertSettings.objects.get()
    with django_capture_on_commit_callbacks(execute=True):
        with campaign_operation(campaign, actor=arb) as act:
            act.record_battle(date.today(), gangs, scenario="Two-day patrol")
    assert Notification.objects.count() == 0
    assert ToolkitAlertEvent.objects.count() == 1
    with django_capture_on_commit_callbacks(execute=True):
        assert deliver_due_reports(now=settings.next_report_at) == 1
        assert deliver_due_reports(now=settings.next_report_at) == 0
    report = Notification.objects.get()
    assert "Two-day patrol" in report.content
    assert "No alerted actions" not in report.content
    assert "Campaign wrap-up" in report.subject


def test_quiet_reports_arrive_for_every_due_window_and_never_duplicate(
    demo, django_capture_on_commit_callbacks
):
    from datetime import timedelta

    from n26.core.models.toolkit import ToolkitAlertSettings
    from n26.core.toolkit_alerts import deliver_due_reports

    campaign, arb, players, gangs = demo
    command(
        campaign,
        arb,
        "alerts",
        {
            "events": ["battle_created"],
            "immediate": False,
            "report_enabled": True,
            "report_days": 1,
        },
    )
    settings = ToolkitAlertSettings.objects.get()
    assert deliver_due_reports(now=settings.next_report_at - timedelta(seconds=1)) == 0
    with django_capture_on_commit_callbacks(execute=True):
        assert deliver_due_reports(now=settings.next_report_at + timedelta(days=1)) == 2
        assert deliver_due_reports(now=settings.next_report_at + timedelta(days=1)) == 0
    reports = list(Notification.objects.filter(owner=arb))
    assert len(reports) == 2
    assert all(
        "None of the selected actions took place from " in r.content
        and " to " in r.content
        for r in reports
    )
    settings.refresh_from_db()
    assert settings.window_start == settings.next_report_at - timedelta(days=1)


def test_immediate_and_reports_can_both_be_enabled_and_changed_without_losing_the_window(
    demo, django_capture_on_commit_callbacks
):
    from n26.core.models.toolkit import ToolkitAlertSettings
    from n26.core.toolkit_alerts import deliver_due_reports

    campaign, arb, players, gangs = demo
    values = {
        "events": ["battle_created"],
        "immediate": True,
        "report_enabled": True,
        "report_days": 3,
    }
    command(campaign, arb, "alerts", values)
    settings = ToolkitAlertSettings.objects.get()
    start = settings.window_start
    with django_capture_on_commit_callbacks(execute=True):
        with campaign_operation(campaign, actor=arb) as act:
            act.record_battle(date.today(), gangs, scenario="Patrol")
    assert Notification.objects.count() == 1
    command(campaign, arb, "alerts", {**values, "immediate": False, "report_days": 2})
    settings.refresh_from_db()
    assert settings.window_start == start
    with django_capture_on_commit_callbacks(execute=True):
        assert deliver_due_reports(now=settings.next_report_at) == 1
    assert Notification.objects.count() == 2
    command(campaign, arb, "alerts", {**values, "report_enabled": False})
    assert ToolkitAlertSettings.objects.get().next_report_at is None


@pytest.mark.parametrize("days", [0, -1, 366, 1.5, True])
def test_report_intervals_are_validated_on_the_server(demo, days):
    campaign, arb, players, gangs = demo
    form, url = command(
        campaign,
        arb,
        "alerts",
        {"events": [], "immediate": False, "report_enabled": True, "report_days": days},
    )
    assert url is None
    assert form.errors


def test_toolkit_inbox_queries_do_not_grow_with_deliveries(
    client, demo, django_capture_on_commit_callbacks
):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from gyrinx.accounts.models import UserProfile

    campaign, arb, players, gangs = demo
    UserProfile.objects.get_or_create(user=arb)
    client.force_login(players[0])

    def send(title):
        with django_capture_on_commit_callbacks(execute=True):
            command(campaign, arb, "communication", offer(gangs[:1], title=title))

    def measure():
        client.get(reverse("core:notifications"), HTTP_ACCEPT="application/json")
        with CaptureQueriesContext(connection) as queries:
            response = client.get(
                reverse("core:notifications"), HTTP_ACCEPT="application/json"
            )
            assert all(
                row["context"]["sender"]["name"] == arb.username
                for row in response.json()["rows"]
            )
        return len(queries)

    send("First")
    small = measure()
    for i in range(4):
        send(f"Message {i}")
    assert measure() <= small


def test_rich_toolkit_messages_keep_images_and_formatting_without_executable_html(
    client, demo, django_capture_on_commit_callbacks
):
    campaign, arb, players, gangs = demo
    body = '<p>A <strong>guild message</strong>.</p><img src="https://example.test/map.png" alt="Route map" onerror="alert(1)"><script>badScript()</script><a href="javascript:badLink()">link</a>'
    with django_capture_on_commit_callbacks(execute=True):
        form, destination = command(
            campaign, arb, "communication", offer(gangs[:1], body=body)
        )
    assert destination, form.errors
    notification = Notification.objects.get(owner=players[0])
    assert "<strong>guild message</strong>" in notification.content
    assert 'alt="Route map"' in notification.content
    assert "onerror" not in notification.content
    assert "badScript" not in notification.content
    assert "javascript:" not in notification.content
    client.force_login(arb)
    response = client.get(reverse("n26-toolkit", args=[campaign.pk]))
    nodes = json.dumps(
        response.context["toolkit_props"]["communications"][0]["bodyNodes"]
    )
    assert '"tag": "strong"' in nodes and '"tag": "img"' in nodes
    assert "badScript" not in nodes
    client.force_login(players[0])
    response = client.get(reverse("core:notifications"), HTTP_ACCEPT="application/json")
    assert '"tag": "img"' in json.dumps(response.json()["rows"][0]["content"])


def test_rich_intervention_text_is_rendered_on_offer_and_recipient_pages(
    client, demo, django_capture_on_commit_callbacks
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
                choices=1,
                narrative='<p><strong>Choose support</strong></p><img src="https://example.test/map.png" alt="Map">',
            ),
        )
    assert url, form.errors
    client.force_login(players[0])
    response = client.get(url)
    assert '"tag": "strong"' in json.dumps(
        response.context["toolkit_props"]["narrativeNodes"]
    )
    receipt = InterventionReceipt.objects.get()
    response = client.get(
        reverse("n26-toolkit-form", args=[campaign.pk, "choose"]),
        {"receipt": str(receipt.pk)},
    )
    assert '"tag": "img"' in json.dumps(
        response.context["toolkit_props"]["receipt"]["narrativeNodes"]
    )
    client.force_login(arb)
    response = client.get(
        reverse("n26-toolkit-form", args=[campaign.pk, "intervention"])
    )
    editor = response.context["toolkit_props"]["editor"]
    assert (
        "image" in editor["config"]["toolbar"]
        and editor["uploadUrl"] == "/tinymce/upload/"
    )


def test_tag_assignment_refuses_more_than_one_tag(demo):
    campaign, arb, players, gangs = demo
    tag = {"kind": "tag", "name": "Painter", "icon": "paintbrush", "amount": 1}
    form, url = command(campaign, arb, "tags", offer(gangs[:1], rewards=[tag, tag]))
    assert url is None and "one tag at a time" in str(form.errors)
    assert not Intervention.objects.exists()


def test_only_the_recipient_sees_an_inline_offer_and_confirmation_uses_the_shared_command(
    client, demo, django_capture_on_commit_callbacks
):
    campaign, arb, players, gangs = demo
    with django_capture_on_commit_callbacks(execute=True):
        command(
            campaign,
            arb,
            "intervention",
            offer(gangs[:1], mode="choice", choices=1, inform_all=True),
        )
    client.force_login(players[0])
    inbox = client.get(
        reverse("core:notifications"), HTTP_ACCEPT="application/json"
    ).json()
    offered = [row["offer"] for row in inbox["rows"] if row["offer"]]
    assert len(offered) == 1
    inline = offered[0]
    assert not inline["resolved"] and inline["gang"] == gangs[0].name
    data = {
        "request_key": inline["values"]["request_key"],
        "payload": json.dumps({"receipt": inline["id"], "selected": [0]}),
    }
    client.force_login(players[1])
    assert all(
        not row["offer"]
        for row in client.get(
            reverse("core:notifications"), HTTP_ACCEPT="application/json"
        ).json()["rows"]
    )
    assert client.post(inline["commandHref"], data).status_code == 422
    client.force_login(players[0])
    with django_capture_on_commit_callbacks(execute=True):
        assert client.post(inline["commandHref"], data).status_code == 200
        assert client.post(inline["commandHref"], data).status_code == 200
    gangs[0].refresh_from_db()
    assert gangs[0].credits == 1030
    rows = client.get(
        reverse("core:notifications"), HTTP_ACCEPT="application/json"
    ).json()["rows"]
    assert next(row["offer"] for row in rows if row["offer"])["resolved"]
    assert not check_gang(gangs[0])


def test_inline_offer_query_count_does_not_grow_with_offers(
    client, demo, django_capture_on_commit_callbacks
):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    campaign, arb, players, gangs = demo
    client.force_login(players[0])

    def send(title):
        with django_capture_on_commit_callbacks(execute=True):
            command(
                campaign,
                arb,
                "intervention",
                offer(gangs[:1], mode="choice", choices=1, title=title),
            )

    def measure(expected):
        client.get(reverse("core:notifications"), HTTP_ACCEPT="application/json")
        with CaptureQueriesContext(connection) as queries:
            rows = client.get(
                reverse("core:notifications"), HTTP_ACCEPT="application/json"
            ).json()["rows"]
            assert len([row for row in rows if row["offer"]]) == expected
        return len(queries)

    send("First offer")
    small = measure(1)
    for i in range(3):
        send(f"Offer {i}")
    assert measure(4) <= small


def test_wrap_up_line_breaks_render_as_elements(demo):
    from n26.rich_text import rich_text_nodes

    campaign, arb, players, gangs = demo
    content = toolkit.content_for(
        campaign,
        "Alerted actions this week:\n• A battle was created.\n• A player chose a reward.",
    )
    assert "&lt;br&gt;" not in content
    nodes = json.dumps(rich_text_nodes(content))
    assert '"tag": "br"' in nodes
    assert "A battle was created." in nodes


@pytest.mark.parametrize("choices", [-1, 0, 1.5, True])
def test_intervention_choice_count_requires_a_positive_integer(demo, choices):
    campaign, arb, players, gangs = demo
    form, url = command(
        campaign, arb, "intervention", offer(gangs[:1], mode="choice", choices=choices)
    )
    assert url is None and form.errors
    assert not Intervention.objects.exists()


def edit_values(client, campaign, arb, action, **query):
    client.force_login(arb)
    response = client.get(
        reverse("n26-toolkit-form", args=[campaign.pk, action]), query
    )
    assert response.status_code == 200
    return json.loads(response.context["toolkit_props"]["values"]["payload"])


def test_message_edits_update_existing_notifications_and_preserve_the_original(
    client, demo, django_capture_on_commit_callbacks
):
    from n26.core.models.toolkit import ToolkitCommand, ToolkitCommunicationRevision

    campaign, arb, players, gangs = demo
    with django_capture_on_commit_callbacks(execute=True):
        command(
            campaign,
            arb,
            "communication",
            offer(gangs, title="Original title", body="<p>Original message.</p>"),
        )
    source = ToolkitCommand.objects.get(action="communication")
    notification = Notification.objects.get(owner=players[0])
    notification.is_read = True
    notification.save(update_fields=["is_read"])
    payload = edit_values(
        client, campaign, arb, "edit_communication", communication=str(source.pk)
    )
    payload.update(title="Revised title", body="<p><strong>New details.</strong></p>")
    key = uuid4()
    with django_capture_on_commit_callbacks(execute=True):
        form, url = command(campaign, arb, "edit_communication", payload, key=key)
        assert url, form.errors
        assert command(campaign, arb, "edit_communication", payload, key=key)[1] == url
    assert Notification.objects.count() == 2
    assert ToolkitCommunicationRevision.objects.count() == 1
    notification.refresh_from_db()
    assert notification.is_read
    assert (
        notification.subject.endswith("Revised title")
        and "New details." in notification.content
    )
    source.refresh_from_db()
    assert source.payload["body"] == "<p>Original message.</p>"
    client.force_login(players[0])
    row = client.get(
        reverse("core:notifications"), HTTP_ACCEPT="application/json"
    ).json()["rows"][0]
    assert row["edited"]["originalSubject"].endswith("Original title")
    assert "Original message." in json.dumps(row["edited"]["originalContent"])
    payload = edit_values(
        client, campaign, arb, "edit_communication", communication=str(source.pk)
    )
    payload.update(body="<p>Third version.</p>")
    with django_capture_on_commit_callbacks(execute=True):
        assert command(campaign, arb, "edit_communication", payload)[1]
    assert ToolkitDelivery.objects.first().original_content.endswith(
        "<p>Original message.</p>"
    )
    assert Notification.objects.count() == 2


def test_stale_message_edits_require_review_and_other_players_cannot_edit(
    client, demo, django_capture_on_commit_callbacks
):
    from n26.core.models.toolkit import ToolkitCommand, ToolkitCommunicationRevision

    campaign, arb, players, gangs = demo
    with django_capture_on_commit_callbacks(execute=True):
        command(campaign, arb, "communication", offer(gangs, body="Original."))
    source = ToolkitCommand.objects.get(action="communication")
    draft = edit_values(
        client, campaign, arb, "edit_communication", communication=str(source.pk)
    )
    with django_capture_on_commit_callbacks(execute=True):
        assert command(
            campaign, arb, "edit_communication", {**draft, "body": "First edit."}
        )[1]
    url = reverse("n26-toolkit-command", args=[campaign.pk, "edit_communication"])
    response = client.post(
        url,
        {
            "request_key": str(uuid4()),
            "payload": json.dumps({**draft, "body": "Stale edit."}),
        },
    )
    assert (
        response.status_code == 409 and response.json()["code"] == "revision_conflict"
    )
    assert ToolkitCommunicationRevision.objects.count() == 1
    assert command(campaign, players[0], "edit_communication", draft)[1] is None
    assert Notification.objects.count() == 2


def test_message_update_delivery_is_retryable_and_does_not_recreate_notifications(
    client, demo, django_capture_on_commit_callbacks, monkeypatch
):
    from n26.core.models.toolkit import ToolkitCommand
    from n26.notifications import deliver_toolkit_notification

    campaign, arb, players, gangs = demo
    with django_capture_on_commit_callbacks(execute=True):
        command(campaign, arb, "communication", offer(gangs[:1], body="Original."))
    source = ToolkitCommand.objects.get(action="communication")
    draft = edit_values(
        client, campaign, arb, "edit_communication", communication=str(source.pk)
    )
    draft["body"] = "Changed."
    monkeypatch.setattr("n26.notifications.enqueue_toolkit_delivery", lambda *_: None)
    with django_capture_on_commit_callbacks(execute=True):
        assert command(campaign, arb, "edit_communication", draft)[1]
    delivery = ToolkitDelivery.objects.get()
    assert delivery.needs_sync
    assert "Original." in Notification.objects.get().content
    assert deliver_toolkit_notification.func(str(delivery.pk))
    assert not deliver_toolkit_notification.func(str(delivery.pk))
    assert "Changed." in Notification.objects.get().content
    assert Notification.objects.count() == 1
    delivery.refresh_from_db()
    assert not delivery.needs_sync


def test_tag_edits_notify_new_recipients_only_and_preserve_existing_assignments(
    client, demo, django_capture_on_commit_callbacks
):
    campaign, arb, players, gangs = demo
    with django_capture_on_commit_callbacks(execute=True):
        command(
            campaign,
            arb,
            "tags",
            offer(
                gangs[:1],
                rewards=[
                    {"kind": "tag", "name": "Guide", "icon": "snail", "amount": 1}
                ],
            ),
        )
    anchor = CampaignTag.objects.get()
    draft = edit_values(client, campaign, arb, "edit_tag", tag=str(anchor.pk))
    draft["rewards"][0].update(
        name="Road guide", icon="trophy", info="Contact this gang."
    )
    draft["gangs"] = [str(g.pk) for g in gangs]
    with django_capture_on_commit_callbacks(execute=True):
        form, url = command(campaign, arb, "edit_tag", draft)
        assert url, form.errors
    anchor.refresh_from_db()
    assert anchor.name == "Road guide" and anchor.removed_at is None
    tags = list(CampaignTag.objects.filter(removed_at__isnull=True))
    assert len(tags) == 2
    assert len({t.assignment_key for t in tags}) == 1
    assert Notification.objects.filter(owner=players[0]).count() == 1
    assert Notification.objects.filter(owner=players[1]).count() == 1
    draft = edit_values(client, campaign, arb, "edit_tag", tag=str(anchor.pk))
    with django_capture_on_commit_callbacks(execute=True):
        assert command(campaign, arb, "edit_tag", draft)[1]
    assert Notification.objects.count() == 2
    draft["gangs"] = [str(gangs[1].pk)]
    with django_capture_on_commit_callbacks(execute=True):
        assert command(campaign, arb, "edit_tag", draft)[1]
    anchor.refresh_from_db()
    assert anchor.removed_at is not None
    assert Notification.objects.count() == 2
    for gang in gangs:
        assert not check_gang(gang)


def test_player_tags_can_be_edited_without_notifying_retained_players(
    client, demo, django_capture_on_commit_callbacks
):
    campaign, arb, players, gangs = demo
    with django_capture_on_commit_callbacks(execute=True):
        command(
            campaign,
            arb,
            "tags",
            offer(
                [],
                target="players",
                players=[str(players[0].pk)],
                rewards=[
                    {
                        "kind": "tag",
                        "name": "Painter",
                        "icon": "paintbrush",
                        "amount": 1,
                    }
                ],
            ),
        )
    tag = CampaignTag.objects.get()
    draft = edit_values(client, campaign, arb, "edit_tag", tag=str(tag.pk))
    draft["players"] = [str(p.pk) for p in players]
    draft["rewards"][0]["info"] = "Coordinates painting."
    with django_capture_on_commit_callbacks(execute=True):
        form, url = command(campaign, arb, "edit_tag", draft)
        assert url, form.errors
    assert CampaignTag.objects.filter(removed_at__isnull=True).count() == 2
    assert Notification.objects.filter(owner=players[0]).count() == 1
    assert Notification.objects.filter(owner=players[1]).count() == 1


def test_reports_group_actions_by_type_and_skip_empty_sections():
    from types import SimpleNamespace

    from django.utils import timezone

    from n26.core.toolkit_alerts import report_content

    now = timezone.now()
    text, message = report_content(
        now,
        now,
        [
            SimpleNamespace(event="battle_created", text="Battle two."),
            SimpleNamespace(event="offer_selected", text="A reward was chosen."),
            SimpleNamespace(event="battle_created", text="Battle one."),
        ],
    )
    assert message.count("<h3>") == 2
    assert message.count("<li>") == 3
    assert (
        message.index("Battle two.")
        < message.index("Battle one.")
        < message.index("A reward was chosen.")
    )
    assert "fighter" not in message and "A player removes a gang" not in message
    assert "Selected actions from" in text


def test_existing_tag_groups_survive_the_edit_migration(demo):
    from importlib import import_module
    from uuid import uuid4

    from django.apps import apps

    from n26.write_pause import write_guard

    campaign, arb, players, gangs = demo
    assert command(
        campaign,
        arb,
        "tags",
        offer(
            gangs,
            rewards=[{"kind": "tag", "name": "Guide", "icon": "snail", "amount": 1}],
        ),
    )[1]
    with write_guard():
        for tag in CampaignTag.objects.all():
            CampaignTag.objects.filter(pk=tag.pk).update(assignment_key=uuid4())
        import_module("n26.core.migrations.0091_toolkit_edits").group_existing_tags(
            apps, None
        )
    assert CampaignTag.objects.values("assignment_key").distinct().count() == 1
    assert list(CampaignTag.objects.values_list("name", flat=True)) == [
        "Guide",
        "Guide",
    ]


def test_edited_message_listing_has_flat_query_growth(
    client, demo, django_capture_on_commit_callbacks
):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from n26.core.models.toolkit import ToolkitCommand

    campaign, arb, players, gangs = demo
    client.force_login(arb)

    def send_and_edit(index):
        with django_capture_on_commit_callbacks(execute=True):
            command(
                campaign,
                arb,
                "communication",
                offer(gangs, title=f"Message {index}", body="Original."),
            )
        source = ToolkitCommand.objects.filter(action="communication").latest("created")
        draft = edit_values(
            client, campaign, arb, "edit_communication", communication=str(source.pk)
        )
        draft["body"] = f"Changed {index}."
        with django_capture_on_commit_callbacks(execute=True):
            assert command(campaign, arb, "edit_communication", draft)[1]

    def measure(expected):
        url = reverse("n26-toolkit", args=[campaign.pk])
        client.get(url)
        with CaptureQueriesContext(connection) as queries:
            response = client.get(url)
            assert len(response.context["toolkit_props"]["communications"]) == expected
        return len(queries)

    send_and_edit(0)
    small = measure(1)
    for index in range(1, 4):
        send_and_edit(index)
    assert measure(4) <= small


def test_intervention_purpose_cannot_be_overridden_by_payload(demo):
    campaign, arb, players, gangs = demo
    form, url = command(
        campaign, arb, "intervention", {**offer(gangs), "_purpose": "tags"}
    )
    assert url, form.errors
    assert Intervention.objects.get().purpose == "intervention"


def test_malformed_recipient_mode_is_a_refusal(demo):
    campaign, arb, players, gangs = demo
    form, url = command(
        campaign, arb, "intervention", {**offer(gangs), "recipients_mode": []}
    )
    assert url is None
    assert form.errors
    assert not Intervention.objects.exists()
