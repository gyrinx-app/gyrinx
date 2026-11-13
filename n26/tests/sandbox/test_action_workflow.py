"""Native and JSON action commands share exact receipts and locked authority."""

from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from n26.core.action_workflow import ActionTarget, change
from n26.core.models import ActionRecord, Assignment, LedgerEvent, ModelChoiceReceipt
from n26.core.operations import Refusal
from n26.tests.sandbox import test_advancement_action_flows as earned_flows
from n26.tests.sandbox import test_fighter_action_flows as priced_flows

hunt = priced_flows.hunt
advancement = earned_flows.advancement

pytestmark = pytest.mark.django_db


def issued(client, url):
    props = client.get(url, follow=True).context["action_props"]
    names = (
        set(props["fields"])
        | {name for name in props["values"] if name.startswith("target_")}
        | {"command_key", "revision", "submitted_summary"}
    )
    return props, {name: props["values"][name] for name in names}


def start(client, data):
    client.force_login(data.owner)
    url = reverse("n26-action-start", args=[data.fighter.pk, data.action.pk])
    props, body = issued(client, url)
    body["outcome"] = str(data.upgrade.pk)
    response = client.post(props["commandHref"], body)
    assert response.status_code == 200
    record = ActionRecord.objects.get(fighter=data.fighter)
    return record, props, body, response.json()


def counts():
    return tuple(
        model.objects.count()
        for model in (ActionRecord, Assignment, LedgerEvent, ModelChoiceReceipt)
    )


def test_get_json_roundtrip_and_native_share_one_receipt(client, hunt):
    record, props, body, saved = start(client, hunt)
    before = counts()
    replay = client.post(props["commandHref"], body).json()
    assert replay["replayed"] is True
    assert replay["facts"] == saved["facts"]
    assert counts() == before
    # The same issued body is also a valid native form submission.
    native = client.post(
        reverse("n26-action-start", args=[hunt.fighter.pk, hunt.action.pk]), body
    )
    assert native.status_code == 302
    assert native.url == saved["nextUrl"]
    assert counts() == before
    choose = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "choose"])
    props, body = issued(client, choose)
    displayed = client.get(props["displayHref"])
    assert displayed.status_code == 200
    assert displayed.json()["props"]["values"]["revision"] == body["revision"]
    # Consume the public JSON encoding, not Django's Python form objects.
    fresh = displayed.json()["props"]
    body = {name: fresh["values"][name] for name in body}
    body["selection"] = fresh["facts"]["items"][0]["key"]
    selected = client.post(fresh["commandHref"], body)
    assert selected.status_code == 200
    record.refresh_from_db()
    assert record.review["target"]["selection"]["candidate_tier"] == "Tier 1"


def test_changed_payload_and_other_actor_cannot_reuse_a_key(client, hunt):
    _, props, body, _ = start(client, hunt)
    before = counts()
    changed = client.post(props["commandHref"], {**body, "outcome": str(hunt.clear.pk)})
    assert changed.status_code == 409
    assert changed.json()["code"] == "key_conflict"
    stranger = User.objects.create_user("other-action-owner")
    client.force_login(stranger)
    assert client.post(props["commandHref"], body).status_code == 404
    assert counts() == before
    # A previous owner cannot replay after a transfer, either.
    from n26.core.models import Gang

    Gang.objects.filter(pk=hunt.gang.pk).update(owner=stranger)
    client.force_login(hunt.owner)
    assert client.post(props["commandHref"], body).status_code == 404


def test_prior_receipt_survives_archive_but_new_commands_do_not(client, hunt):
    _, props, body, saved = start(client, hunt)
    Assignment.objects.filter(pk=hunt.fighter.membership_id).update(archived=True)
    before = counts()
    replay = client.post(props["commandHref"], body)
    assert replay.status_code == 200
    assert replay.json()["facts"] == saved["facts"]
    assert client.get(props["action"]).status_code == 404
    assert client.get(props["recoveryHref"]).status_code == 200
    assert counts() == before
    assert (
        client.post(
            props["commandHref"], {**body, "command_key": str(uuid4())}
        ).status_code
        == 409
    )
    assert counts()[:-1] == before[:-1]
    assert counts()[-1] == before[-1] + 1


@pytest.mark.parametrize(
    "step,payload",
    [
        ("choose", {"selection": "old-tier"}),
        ("correct", {"selection": "old-tier"}),
        ("skill", {"skill_id": "old-skill"}),
        ("cancel", {}),
        ("by-hand", {}),
        ("reopen", {}),
    ],
)
def test_actual_old_native_payloads_without_identity_write_nothing(
    client, hunt, step, payload
):
    record, _, _, _ = start(client, hunt)
    before = counts()
    url = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, step])
    response = client.post(url, payload, follow=True)
    assert response.status_code == 200
    assert counts() == before
    record.refresh_from_db()
    assert record.state == ActionRecord.State.STARTED


def test_failed_stage_rolls_back_prior_draft_write_and_receipt(
    client, hunt, monkeypatch
):
    record, _, _, _ = start(client, hunt)
    choose = reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "choose"])
    props, body = issued(client, choose)
    body["selection"] = props["facts"]["items"][0]["key"]
    from n26.core.operations import Operation

    def refuse(*args, **kwargs):
        raise Refusal("The current tier cannot be reviewed.")

    monkeypatch.setattr(Operation, "review_action", refuse)
    before = counts()
    revision = record.revision
    response = client.post(props["commandHref"], body)
    assert response.status_code == 422
    assert counts() == before
    record.refresh_from_db()
    assert record.revision == revision
    assert not record.review
    assert "intended_pick" not in record.terms


def test_real_csrf_required_and_get_does_not_create_a_draft(client, hunt):
    client = Client(enforce_csrf_checks=True)
    client.force_login(hunt.owner)
    url = reverse("n26-action-start", args=[hunt.fighter.pk, hunt.action.pk])
    before = counts()
    props, body = issued(client, url)
    assert counts() == before
    assert (
        client.post(
            props["commandHref"], body, HTTP_ACCEPT="application/json"
        ).status_code
        == 403
    )
    body["outcome"] = str(hunt.upgrade.pk)
    assert (
        client.post(
            props["commandHref"],
            body,
            HTTP_X_CSRFTOKEN=props["csrfToken"],
            HTTP_ACCEPT="application/json",
        ).status_code
        == 200
    )


def test_roll_receipt_recalls_original_roll_after_later_stage_changes(
    client, advancement, monkeypatch
):
    data = advancement
    client.force_login(data.owner)
    props, body = issued(
        client, reverse("n26-action-start", args=[data.fighter.pk, data.action.pk])
    )
    assert client.post(props["commandHref"], body).status_code == 200
    record = ActionRecord.objects.get(fighter=data.fighter)
    url = reverse("n26-action-flow", args=[data.fighter.pk, record.pk, "roll"])
    props, body = issued(client, url)
    body["roll_mode"] = "roll"
    body.pop("rolled", None)
    first = client.post(props["commandHref"], body)
    assert first.status_code == 200
    original = first.json()["facts"]
    choose = reverse("n26-action-flow", args=[data.fighter.pk, record.pk, "choose"])
    later, selection = issued(client, choose)
    selection["pickable_id"] = later["facts"]["advancements"][0]["key"]
    assert client.post(later["commandHref"], selection).status_code == 200
    before = counts()
    replay = client.post(props["commandHref"], body)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["facts"] == original
    assert counts() == before
    assert original["rolls"]


@pytest.mark.django_db(transaction=True)
def test_concurrent_same_start_commits_one_draft_and_one_receipt(hunt):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections

    actor = hunt.owner
    body = {
        "request_key": str(uuid4()),
        "command_key": str(uuid4()),
        "outcome": str(hunt.upgrade.pk),
        "allowance": "",
    }
    target = ActionTarget("start", str(hunt.action.pk))

    def submit():
        close_old_connections()
        try:
            return change(actor, hunt.fighter.pk, target, body)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert all(result.saved for result in results)
    assert sum(result.replayed for result in results) == 1
    assert ActionRecord.objects.filter(fighter=hunt.fighter).count() == 1
    assert ModelChoiceReceipt.objects.filter(gang=hunt.gang).count() == 1


def test_settlement_refusal_never_returns_success_or_a_receipt(
    client, hunt, monkeypatch
):
    client.force_login(hunt.owner)
    props, body = issued(
        client, reverse("n26-action-start", args=[hunt.fighter.pk, hunt.action.pk])
    )
    body["outcome"] = str(hunt.upgrade.pk)
    from n26.core.operations import Operation

    def refuse(self):
        raise Refusal("The current balance cannot settle this action.")

    monkeypatch.setattr(Operation, "settle", refuse)
    before = counts()
    result = client.post(props["commandHref"], body)
    assert result.status_code == 422
    assert result.json().get("saved") is not True
    assert counts() == before


def test_terminal_refusal_stays_consumed_when_the_model_returns(client, hunt):
    record, _, _, _ = start(client, hunt)
    props, body = issued(
        client, reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "cancel"])
    )
    membership = hunt.fighter.membership
    membership.archived = True
    membership.save()
    first = client.post(props["commandHref"], body)
    assert first.status_code == 409
    assert first.json()["terminal"] is True
    assert first.json()["reviewUrl"] == reverse("n26-gang", args=[hunt.gang.pk])
    receipt = ModelChoiceReceipt.objects.get(request_key=body["command_key"])
    assert receipt.result["outcome"] == "unavailable"
    membership.archived = False
    membership.save()
    before = counts()
    replay = client.post(props["commandHref"], body)
    assert replay.status_code == 409
    assert replay.json()["errors"] == first.json()["errors"]
    assert counts() == before
    record.refresh_from_db()
    assert record.state == ActionRecord.State.STARTED


def test_missing_record_refusal_stays_consumed_if_its_identity_returns(client, hunt):
    record, _, _, _ = start(client, hunt)
    props, body = issued(
        client, reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "cancel"])
    )
    original_pk = record.pk
    record.delete()
    assert client.get(props["action"]).status_code == 404
    recovery = client.get(props["recoveryHref"])
    assert recovery.status_code == 200
    assert recovery.context["action_props"]["facts"]["recovery_only"] is True
    first = client.post(props["commandHref"], body)
    assert first.status_code == 409
    record.pk = original_pk
    record._state.adding = True
    record.save(force_insert=True)
    before = counts()
    assert client.post(props["commandHref"], body).status_code == 409
    assert counts() == before
    record.refresh_from_db()
    assert record.state == ActionRecord.State.STARTED


def test_history_undo_posts_its_rendered_key_and_revision_once(client, advancement):
    from bs4 import BeautifulSoup

    data = advancement
    client.force_login(data.owner)
    props, body = issued(
        client,
        reverse("n26-action-by-hand", args=[data.fighter.pk, data.action.pk])
        + f"?allowance={data.allowance.pk}",
    )
    assert client.post(props["commandHref"], body).status_code == 200
    edit = client.get(reverse("n26-edit-fighter", args=[data.fighter.pk]))
    native = BeautifulSoup(edit.content, "html.parser").select_one(
        "#n26-action-history form"
    )
    assert native
    body = {
        field["name"]: field.get("value", "") for field in native.select("input[name]")
    }
    assert body["command_key"]
    assert body["revision"]
    response = client.post(native["action"], body)
    assert response.status_code == 302
    record = ActionRecord.objects.get(fighter=data.fighter)
    assert record.state == ActionRecord.State.CANCELLED
    before = counts()
    assert client.post(native["action"], body).status_code == 302
    assert counts() == before


def test_action_pages_and_json_display_are_never_cached(client, hunt):
    client.force_login(hunt.owner)
    url = reverse("n26-action-start", args=[hunt.fighter.pk, hunt.action.pk])
    page = client.get(url)
    props = page.context["action_props"]
    for response in [page, client.get(props["displayHref"])]:
        assert "no-store" in response["Cache-Control"]
        assert "private" in response["Cache-Control"]


def test_action_display_query_count_does_not_grow_with_the_roster(client, hunt):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from n26.tests.sandbox.actions import hire

    client.force_login(hunt.owner)
    url = reverse("n26-action-start", args=[hunt.fighter.pk, hunt.action.pk])
    props = client.get(url).context["action_props"]

    def measure():
        with CaptureQueriesContext(connection) as captured:
            response = client.get(props["displayHref"])
        assert response.status_code == 200
        return len(captured)

    one = measure()
    for number in range(4):
        hire(hunt.gang, hunt.fighter.membership.profile, f"Extra {number}")
    assert measure() == one


def test_successful_receipt_recalls_after_model_deletion_without_new_authority(
    client, hunt
):
    _, props, body, saved = start(client, hunt)
    body["gang_id"] = str(hunt.gang.pk)
    hunt.fighter.membership.delete()
    before = counts()
    response = client.post(props["commandHref"], body)
    assert response.status_code == 200
    assert response.json()["facts"] == saved["facts"]
    assert response.json()["reviewUrl"] == reverse("n26-gang", args=[hunt.gang.pk])
    assert client.get(props["recoveryHref"]).status_code == 200
    assert (
        client.post(
            props["commandHref"], {**body, "command_key": str(uuid4())}
        ).status_code
        == 404
    )
    assert counts() == before


def test_write_pause_refuses_before_locking_or_changing_the_action(client, hunt):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    from n26.write_pause import SCOPE, WritesPaused, pause_scope

    client.force_login(hunt.owner)
    props, body = issued(
        client, reverse("n26-action-start", args=[hunt.fighter.pk, hunt.action.pk])
    )
    body["outcome"] = str(hunt.upgrade.pk)
    pause_scope(SCOPE, actor=hunt.owner, reason="Counter history maintenance")
    before = counts()
    with CaptureQueriesContext(connection) as captured, pytest.raises(WritesPaused):
        change(
            hunt.owner,
            hunt.fighter.pk,
            ActionTarget("start", str(hunt.action.pk)),
            body,
        )
    assert counts() == before
    assert not any(
        '"n26_gang"' in query["sql"] and "FOR UPDATE" in query["sql"]
        for query in captured
    )


def test_correction_query_preserves_absent_and_explicitly_blank_pick(
    client, advancement
):
    data = advancement
    client.force_login(data.owner)
    props, body = issued(
        client, reverse("n26-action-start", args=[data.fighter.pk, data.action.pk])
    )
    assert client.post(props["commandHref"], body).status_code == 200
    record = ActionRecord.objects.get(fighter=data.fighter)
    props, body = issued(
        client, reverse("n26-action-flow", args=[data.fighter.pk, record.pk, "roll"])
    )
    body.update(roll_mode="record", rolled="12")
    assert client.post(props["commandHref"], body).status_code == 200
    props, body = issued(
        client, reverse("n26-action-flow", args=[data.fighter.pk, record.pk, "choose"])
    )
    body["pickable_id"] = str(data.results["primary"].pk)
    assert client.post(props["commandHref"], body).status_code == 200
    props, body = issued(
        client, reverse("n26-action-flow", args=[data.fighter.pk, record.pk, "skill"])
    )
    body["skill_id"] = str(data.skills["primary"].pk)
    assert client.post(props["commandHref"], body).status_code == 200
    props, body = issued(
        client, reverse("n26-action-flow", args=[data.fighter.pk, record.pk, "review"])
    )
    assert client.post(props["commandHref"], body).status_code == 200
    url = reverse("n26-action-flow", args=[data.fighter.pk, record.pk, "correct"])
    normal = client.get(url).context["action_props"]
    assert normal["values"]["pickable_id"] == str(data.results["primary"].pk)
    assert normal["values"]["target_pick_present"] == "0"
    normal_json = client.get(normal["displayHref"]).json()["props"]
    assert normal_json["values"]["pickable_id"] == str(data.results["primary"].pk)
    blank = client.get(url + "?pick=").context["action_props"]
    assert blank["values"]["pickable_id"] == ""
    assert blank["values"]["target_pick_present"] == "1"
    assert client.get(blank["displayHref"]).json()["props"]["action"].endswith("?pick=")
    assert (
        client.get(blank["displayHref"]).json()["props"]["values"]["pickable_id"] == ""
    )


def test_terminal_settlement_refusal_cannot_acknowledge_a_no_write_receipt(
    client, hunt, monkeypatch
):
    record, _, _, _ = start(client, hunt)
    props, body = issued(
        client, reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "cancel"])
    )
    membership = hunt.fighter.membership
    membership.archived = True
    membership.save()
    from n26.core.operations import Operation

    def refuse(self):
        raise Refusal("This terminal acknowledgement cannot settle.")

    monkeypatch.setattr(Operation, "settle", refuse)
    before = counts()
    response = client.post(props["commandHref"], body)
    assert response.status_code == 422
    assert response.json()["terminal"] is False
    assert response.json()["conflict"] is False
    assert response.json()["reviewUrl"] == ""
    assert counts() == before


def test_native_navigation_keeps_the_cancelled_flow_notice(client, hunt):
    record, _, _, _ = start(client, hunt)
    props, body = issued(
        client, reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "cancel"])
    )
    assert client.post(props["commandHref"], body).status_code == 200
    resumed = client.get(
        reverse("n26-action-flow", args=[hunt.fighter.pk, record.pk, "resume"]),
        follow=True,
    )
    assert resumed.status_code == 200
    assert "This flow was cancelled." in resumed.content.decode()
