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
    assert replay["nextUrl"] == saved["nextUrl"]
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


@pytest.mark.parametrize("deleted", ["membership", "model"])
def test_successful_receipt_recalls_after_model_deletion_without_new_authority(
    client, hunt, deleted
):
    _, props, body, saved = start(client, hunt)
    body["gang_id"] = str(hunt.gang.pk)
    (hunt.fighter.membership if deleted == "membership" else hunt.fighter).delete()
    before = counts()
    response = client.post(props["commandHref"], body)
    assert response.status_code == 200
    assert response.json()["facts"] == saved["facts"]
    surviving = reverse("n26-gang", args=[hunt.gang.pk])
    assert response.json()["reviewUrl"] == surviving
    assert response.json()["nextUrl"] == surviving
    recovered = client.get(props["recoveryHref"])
    assert recovered.status_code == 200
    display_href = recovered.context["action_props"]["displayHref"]
    displayed = client.get(display_href)
    assert displayed.status_code == 200
    displayed_props = displayed.json()["props"]
    assert displayed_props["facts"]["recovery_only"] is True
    assert displayed_props["values"]["gang_id"] == str(hunt.gang.pk)
    assert client.get(displayed_props["displayHref"]).status_code == 200
    native = client.post(props["action"], body)
    assert native.status_code == 302
    assert native.url == surviving
    assert client.get(native.url).status_code == 200
    assert (
        client.post(
            props["commandHref"], {**body, "command_key": str(uuid4())}
        ).status_code
        == 404
    )
    assert counts() == before
    client.force_login(User.objects.create_user(f"deleted-{deleted}-recovery-stranger"))
    assert client.get(display_href).status_code == 404
    assert client.post(props["action"], body).status_code == 404


@pytest.mark.parametrize("removed", ["record", "membership", "gang"])
def test_successful_native_replay_follows_a_surviving_destination(
    client, hunt, removed
):
    from n26.core.operations import operation

    record, props, body, saved = start(client, hunt)
    if removed == "record":
        record.delete()
    else:
        with operation(hunt.gang, actor=hunt.owner) as op:
            if removed == "gang":
                op.archive_gang()
            else:
                op.remove(hunt.fighter.membership)
    surviving = (
        reverse("n26-gangs")
        if removed == "gang"
        else reverse("n26-gang", args=[hunt.gang.pk])
    )
    before = counts()
    replay = client.post(props["commandHref"], body)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["facts"] == saved["facts"]
    assert replay.json()["nextUrl"] == surviving
    assert replay.json()["reviewUrl"] == surviving
    native = client.post(props["action"], body)
    assert native.status_code == 302
    assert native.url == surviving
    assert client.get(native.url).status_code == 200
    assert counts() == before
    stored = ModelChoiceReceipt.objects.get(request_key=body["command_key"])
    assert stored.result["facts"] == saved["facts"]
    assert stored.result["next_url"] == saved["nextUrl"]


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


@pytest.mark.parametrize("step", ["cancel", "by-hand"])
def test_explicit_recovery_mounts_after_a_successful_navigation(
    client, advancement, step
):
    data = advancement
    client.force_login(data.owner)
    props, body = issued(
        client, reverse("n26-action-start", args=[data.fighter.pk, data.action.pk])
    )
    assert client.post(props["commandHref"], body).status_code == 200
    record = ActionRecord.objects.get(fighter=data.fighter)
    url = reverse("n26-action-flow", args=[data.fighter.pk, record.pk, step])
    props, body = issued(client, url)
    original = client.post(props["commandHref"], body)
    assert original.status_code == 200
    before = counts()
    # The completed response can be lost before the browser learns its result.
    recovered = client.get(props["recoveryHref"])
    assert recovered.status_code == 200
    recovered_props = recovered.context["action_props"]
    assert recovered_props["facts"]["recovery_only"] is True
    assert recovered_props["facts"]["back_href"] == reverse(
        "n26-edit-fighter", args=[data.fighter.pk]
    )
    assert recovered_props["facts"]["back_label"] == "Continue"
    assert recovered_props["fields"] == []
    display = client.get(recovered_props["displayHref"])
    assert display.status_code == 200
    assert display.json()["props"]["facts"]["recovery_only"] is True
    ordinary = client.get(url)
    assert ordinary.status_code == 302
    assert ordinary.url == reverse("n26-edit-fighter", args=[data.fighter.pk])
    replay = client.post(props["commandHref"], body)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["facts"] == original.json()["facts"]
    assert client.post(url, body).status_code == 302
    assert counts() == before
    client.force_login(User.objects.create_user(f"recovery-stranger-{step}"))
    assert client.get(props["recoveryHref"]).status_code == 404


def _tier_command(client, data):
    record, _, _, _ = start(client, data)
    props, body = issued(
        client, reverse("n26-action-flow", args=[data.fighter.pk, record.pk, "choose"])
    )
    body["selection"] = props["facts"]["items"][0]["key"]
    return record, props, body


def _remove_tier_item(data):
    from n26.core.operations import operation, subtree

    removed = [data.item, *subtree(data.item)]
    with operation(data.gang, actor=data.owner) as op:
        op.remove(data.item)
    return removed


def _restore_tier_item(data, removed):
    from n26.core.operations import operation

    with operation(data.gang, actor=data.owner) as op:
        for assignment in removed:
            op.restore(assignment)


@pytest.mark.parametrize("transport", ["native", "json"])
def test_removed_tier_selection_consumes_the_original_key_before_delayed_retry(
    client, hunt, monkeypatch, transport
):
    from n26.core.operations import Operation

    record, props, body = _tier_command(client, hunt)
    original_revision = record.revision

    def refused_review(*args, **kwargs):
        raise Refusal("This review did not complete.")

    with monkeypatch.context() as patch:
        patch.setattr(Operation, "review_action", refused_review)
        rejected = client.post(props["commandHref"], body)
    assert rejected.status_code == 422
    assert not ModelChoiceReceipt.objects.filter(
        request_key=body["command_key"]
    ).exists()
    removed = _remove_tier_item(hunt)
    record.refresh_from_db()
    assert record.revision == original_revision
    before = counts()
    first = client.post(
        props["commandHref"] if transport == "json" else props["action"], body
    )
    assert first.status_code == (409 if transport == "json" else 200)
    if transport == "json":
        assert first.json()["code"] == "unavailable"
    else:
        assert first.context["action_props"]["initialConflict"] is True
    receipt = ModelChoiceReceipt.objects.get(request_key=body["command_key"])
    assert receipt.result["outcome"] == "unavailable"
    assert counts()[:-1] == before[:-1]
    assert counts()[-1] == before[-1] + 1
    _restore_tier_item(hunt, removed)
    current = client.get(props["action"]).context["action_props"]
    assert body["selection"] in {item["key"] for item in current["facts"]["items"]}
    before_delayed = counts()
    replay = client.post(props["commandHref"], body)
    assert replay.status_code == 409
    assert replay.json()["code"] == "unavailable"
    assert replay.json()["errors"] == receipt.result["errors"]
    native = client.post(props["action"], body)
    assert native.status_code == 200
    assert native.context["action_props"]["initialConflict"] is True
    assert counts() == before_delayed
    record.refresh_from_db()
    assert record.revision == original_revision
    assert not record.review


def test_removed_tier_terminal_receipt_rolls_back_if_settlement_fails(
    client, hunt, monkeypatch
):
    from n26.core.operations import Operation

    record, props, body = _tier_command(client, hunt)
    removed = _remove_tier_item(hunt)

    def refused_settlement(self):
        raise Refusal("This acknowledgement cannot settle.")

    before = counts()
    with monkeypatch.context() as patch:
        patch.setattr(Operation, "settle", refused_settlement)
        result = client.post(props["commandHref"], body)
    assert result.status_code == 422
    assert result.json()["terminal"] is False
    assert result.json()["conflict"] is False
    assert counts() == before
    _restore_tier_item(hunt, removed)
    retry = client.post(props["commandHref"], body)
    assert retry.status_code == 200
    assert retry.json()["saved"] is True
    record.refresh_from_db()
    assert record.review


def test_successful_tier_receipt_is_recalled_before_the_item_is_rechecked(client, hunt):
    record, props, body = _tier_command(client, hunt)
    original = client.post(props["commandHref"], body)
    assert original.status_code == 200
    _remove_tier_item(hunt)
    before = counts()
    replay = client.post(props["commandHref"], body)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["facts"] == original.json()["facts"]
    assert counts() == before


@pytest.mark.parametrize(
    "selection",
    ["not-an-item|not-a-tier", "{removed}|", "{removed}|bad-tier", "{live}|{missing}"],
)
def test_other_tier_validation_failures_do_not_publish_a_terminal_receipt(
    client, hunt, selection
):
    record, props, body = _tier_command(client, hunt)
    item = str(hunt.item.pk)
    _remove_tier_item(hunt) if "{removed}" in selection else None
    body["selection"] = selection.format(removed=item, live=item, missing=str(uuid4()))
    before = counts()
    result = client.post(props["commandHref"], body)
    assert result.status_code == 422
    assert result.json()["terminal"] is False
    assert counts() == before


@pytest.mark.django_db(transaction=True)
def test_concurrent_removed_tier_retries_record_one_durable_refusal(client, hunt):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections

    record, props, body = _tier_command(client, hunt)
    removed = _remove_tier_item(hunt)
    target = ActionTarget("flow", str(record.pk), "choose")

    def submit():
        close_old_connections()
        try:
            return change(hunt.owner, hunt.fighter.pk, target, body)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert all(result.terminal and result.code == "unavailable" for result in results)
    assert sum(result.replayed for result in results) == 1
    assert (
        ModelChoiceReceipt.objects.filter(request_key=body["command_key"]).count() == 1
    )
    _restore_tier_item(hunt, removed)
    before = counts()
    delayed = change(hunt.owner, hunt.fighter.pk, target, body)
    assert delayed.replayed and delayed.terminal
    assert counts() == before


def _recorded_roll_cancel_command(client, data):
    record = earned_flows._start(client, data)
    props, body = issued(
        client, reverse("n26-action-flow", args=[data.fighter.pk, record.pk, "roll"])
    )
    body.update(roll_mode="record", rolled="4")
    assert client.post(props["commandHref"], body).status_code == 200
    record.refresh_from_db()
    props, body = issued(
        client, reverse("n26-action-flow", args=[data.fighter.pk, record.pk, "cancel"])
    )
    return record, props, body


@pytest.mark.parametrize("transport", ["native", "json"])
def test_recorded_roll_cancel_settles_without_cancelling_and_replays_after_reopen(
    client, advancement, transport
):
    from n26.core.action_records import has_recorded_action_roll
    from n26.core.operations import operation

    data = advancement
    record, props, body = _recorded_roll_cancel_command(client, data)
    original_rolls = list(record.ledger_events.filter(kind=LedgerEvent.Kind.ROLLED))
    original_revision = record.revision
    assert has_recorded_action_roll(record)
    with pytest.raises(Refusal, match="A recorded advancement roll must be resumed."):
        with operation(data.gang, actor=data.owner) as op:
            op.cancel_action(record)
    before = counts()
    response = client.post(
        props["commandHref"] if transport == "json" else props["action"], body
    )
    resume = reverse("n26-action-flow", args=[data.fighter.pk, record.pk, "resume"])
    if transport == "json":
        assert response.status_code == 409
        assert response.json()["terminal"] is True
        assert response.json()["reviewUrl"] == resume
        assert response.json()["code"] == "unavailable"
        assert response.json()["errors"] == {
            "__all__": ["A recorded advancement roll must be resumed."]
        }
    else:
        assert response.status_code == 302
        assert response.url == resume
        assert (
            "A recorded advancement roll must be resumed."
            in client.get(response.url, follow=True).content.decode()
        )
    assert counts()[:-1] == before[:-1]
    assert counts()[-1] == before[-1] + 1
    record.refresh_from_db()
    assert record.state == ActionRecord.State.STARTED
    assert record.revision == original_revision
    receipt = ModelChoiceReceipt.objects.get(request_key=body["command_key"])
    assert receipt.result["outcome"] == "unavailable"
    assert receipt.result["resume_record"] == str(record.pk)
    # Ordinary by-hand and Undo keep the roll. Recall the terminal receipt
    # before resolving either later state as a fresh cancellation intent.
    with operation(data.gang, actor=data.owner) as op:
        op.apply_action_by_hand(record)
    record.refresh_from_db()
    assert record.state == ActionRecord.State.APPLIED_BY_HAND
    before_applied_replay = counts()
    applied_replay = client.post(props["commandHref"], body)
    assert applied_replay.status_code == 409
    assert applied_replay.json()["terminal"] is True
    assert counts() == before_applied_replay
    with operation(data.gang, actor=data.owner) as op:
        op.reopen_action(record)
    record.refresh_from_db()
    assert has_recorded_action_roll(record)
    before_delayed = counts()
    delayed = client.post(props["commandHref"], body)
    assert delayed.status_code == 409
    assert delayed.json()["terminal"] is True
    assert delayed.json()["reviewUrl"] == resume
    assert delayed.json()["errors"] == receipt.result["errors"]
    assert client.post(props["action"], body).status_code == 302
    assert counts() == before_delayed
    assert (
        list(record.ledger_events.filter(kind=LedgerEvent.Kind.ROLLED))
        == original_rolls
    )
    assert not record.ledger_events.filter(
        kind=LedgerEvent.Kind.ACTION_USE_CANCELLED
    ).exists()
    record.refresh_from_db()
    assert record.state == ActionRecord.State.STARTED


def test_recorded_roll_cancel_receipt_rolls_back_if_settlement_refuses(
    client, advancement, monkeypatch
):
    from n26.core.operations import Operation

    record, props, body = _recorded_roll_cancel_command(client, advancement)
    before = counts()

    def refused_settlement(self):
        raise Refusal("This acknowledgement cannot settle.")

    with monkeypatch.context() as patch:
        patch.setattr(Operation, "settle", refused_settlement)
        response = client.post(props["commandHref"], body)
    assert response.status_code == 422
    assert response.json()["terminal"] is False
    assert response.json()["conflict"] is False
    assert response.json()["reviewUrl"] == ""
    assert counts() == before
    assert not ModelChoiceReceipt.objects.filter(
        request_key=body["command_key"]
    ).exists()
    retry = client.post(props["commandHref"], body)
    assert retry.status_code == 409
    assert retry.json()["terminal"] is True
    assert counts()[:-1] == before[:-1]
    assert counts()[-1] == before[-1] + 1
    record.refresh_from_db()
    assert record.state == ActionRecord.State.STARTED


def test_recorded_roll_cancel_checks_identity_revision_and_authority_before_settling(
    client, advancement
):
    record, props, body = _recorded_roll_cancel_command(client, advancement)
    before = counts()
    unkeyed = {name: value for name, value in body.items() if name != "command_key"}
    assert client.post(props["commandHref"], unkeyed).status_code == 422
    stale = client.post(props["commandHref"], {**body, "revision": "-1"})
    assert stale.status_code == 409
    assert stale.json()["code"] == "revision_conflict"
    assert stale.json()["terminal"] is False
    client.force_login(User.objects.create_user("recorded-roll-cancel-stranger"))
    assert client.post(props["commandHref"], body).status_code == 404
    assert counts() == before


def test_recorded_roll_cancel_revalidates_its_resume_destination_on_replay(
    client, advancement
):
    record, props, body = _recorded_roll_cancel_command(client, advancement)
    assert client.post(props["commandHref"], body).json()["terminal"] is True
    Assignment.objects.filter(pk=advancement.fighter.membership_id).update(
        archived=True
    )
    before = counts()
    replay = client.post(props["commandHref"], body)
    assert replay.status_code == 409
    assert replay.json()["terminal"] is True
    assert replay.json()["reviewUrl"] == reverse("n26-gang", args=[advancement.gang.pk])
    assert counts() == before


@pytest.mark.parametrize("deleted", ["membership", "model"])
def test_native_recorded_roll_cancel_replay_uses_the_surviving_page_after_deletion(
    client, advancement, deleted
):
    record, props, body = _recorded_roll_cancel_command(client, advancement)
    body["gang_id"] = str(advancement.gang.pk)
    assert client.post(props["commandHref"], body).json()["terminal"] is True
    target = (
        advancement.fighter.membership
        if deleted == "membership"
        else advancement.fighter
    )
    target.delete()
    before = counts()
    replay = client.post(props["action"], body)
    assert replay.status_code == 302
    assert replay.url == reverse("n26-gang", args=[advancement.gang.pk])
    reached = client.get(replay.url)
    assert reached.status_code == 200
    assert "A recorded advancement roll must be resumed." in reached.content.decode()
    assert counts() == before


@pytest.mark.django_db(transaction=True)
def test_concurrent_recorded_roll_cancel_retries_record_one_durable_refusal(
    client, advancement
):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections

    record, props, body = _recorded_roll_cancel_command(client, advancement)
    target = ActionTarget("flow", str(record.pk), "cancel")
    before = counts()

    def submit():
        close_old_connections()
        try:
            return change(advancement.owner, advancement.fighter.pk, target, body)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert all(result.terminal and result.code == "unavailable" for result in results)
    assert sum(result.replayed for result in results) == 1
    assert counts()[:-1] == before[:-1]
    assert counts()[-1] == before[-1] + 1
    record.refresh_from_db()
    assert record.state == ActionRecord.State.STARTED


@pytest.mark.parametrize("earlier_step", ["by-hand", "reopen"])
def test_native_receipt_replay_acknowledges_history_without_asserting_the_current_state(
    client, advancement, earlier_step
):
    record = earned_flows._start(client, advancement)
    by_hand, by_hand_body = issued(
        client,
        reverse("n26-action-flow", args=[advancement.fighter.pk, record.pk, "by-hand"]),
    )
    applied = client.post(by_hand["action"], by_hand_body, follow=True)
    assert "Advance marked as applied by hand." in applied.content.decode()
    reopen, reopen_body = issued(
        client,
        reverse("n26-action-flow", args=[advancement.fighter.pk, record.pk, "reopen"]),
    )
    waiting = client.post(reopen["action"], reopen_body, follow=True)
    assert "Advance is waiting again." in waiting.content.decode()
    if earlier_step == "by-hand":
        earlier, body = by_hand, by_hand_body
        stale_notice = "Advance marked as applied by hand."
        current_state = ActionRecord.State.STARTED
    else:
        fresh, fresh_body = issued(client, by_hand["action"])
        assert client.post(fresh["action"], fresh_body, follow=True).status_code == 200
        earlier, body = reopen, reopen_body
        stale_notice = "Advance is waiting again."
        current_state = ActionRecord.State.APPLIED_BY_HAND
    before = counts()
    replay = client.post(earlier["action"], body, follow=True)
    assert replay.status_code == 200
    content = replay.content.decode()
    assert (
        "This confirms the earlier action. The current flow may have changed."
        in content
    )
    assert stale_notice not in content
    record.refresh_from_db()
    assert record.state == current_state
    assert counts() == before


def _tier_confirmation(client, data):
    record, props, body = _tier_command(client, data)
    assert client.post(props["commandHref"], body).status_code == 200
    props, body = issued(
        client,
        reverse("n26-action-flow", args=[data.fighter.pk, record.pk, "review"]),
    )
    record.refresh_from_db()
    return record, props, body


@pytest.mark.parametrize("transport", ["native", "json"])
def test_interrupted_tier_confirmation_settles_after_item_removal_and_cannot_apply_after_restore(
    client, hunt, monkeypatch, transport
):
    from n26.core.operations import Operation

    record, props, body = _tier_confirmation(client, hunt)
    original_revision = record.revision
    original_body = dict(body)

    def interrupted_confirmation(*args, **kwargs):
        raise ConnectionAbortedError(
            "The confirmation response was lost before commit."
        )

    with monkeypatch.context() as patch:
        patch.setattr(Operation, "complete_action", interrupted_confirmation)
        with pytest.raises(ConnectionAbortedError):
            client.post(props["commandHref"], body)
    assert not ModelChoiceReceipt.objects.filter(
        request_key=body["command_key"]
    ).exists()
    removed = _remove_tier_item(hunt)
    record.refresh_from_db()
    assert record.revision == original_revision
    before = counts()
    refused = client.post(
        props["commandHref"] if transport == "json" else props["action"], body
    )
    assert refused.status_code == (409 if transport == "json" else 200)
    if transport == "json":
        assert refused.json()["terminal"] is True
        assert refused.json()["code"] == "unavailable"
    else:
        assert refused.context["action_props"]["initialConflict"] is True
    receipt = ModelChoiceReceipt.objects.get(request_key=body["command_key"])
    assert receipt.result["outcome"] == "unavailable"
    assert counts()[:-1] == before[:-1]
    assert counts()[-1] == before[-1] + 1
    _restore_tier_item(hunt, removed)
    before_delayed = counts()
    delayed = client.post(props["commandHref"], original_body)
    assert delayed.status_code == 409
    assert delayed.json()["terminal"] is True
    assert delayed.json()["errors"] == receipt.result["errors"]
    native = client.post(props["action"], original_body)
    assert native.status_code == 200
    assert native.context["action_props"]["initialConflict"] is True
    assert body == original_body
    assert counts() == before_delayed
    record.refresh_from_db()
    assert record.state == ActionRecord.State.STARTED
    assert record.payment_id is None
    assert not record.ledger_events.filter(
        kind=LedgerEvent.Kind.ACTION_USE_COMPLETED
    ).exists()


def test_removed_confirmation_acknowledgement_rolls_back_if_settlement_refuses(
    client, hunt, monkeypatch
):
    from n26.core.operations import Operation

    record, props, body = _tier_confirmation(client, hunt)
    removed = _remove_tier_item(hunt)
    before = counts()

    def refused_settlement(self):
        raise Refusal("This acknowledgement cannot settle.")

    with monkeypatch.context() as patch:
        patch.setattr(Operation, "settle", refused_settlement)
        response = client.post(props["commandHref"], body)
    assert response.status_code == 422
    assert response.json()["terminal"] is False
    assert response.json()["conflict"] is False
    assert counts() == before
    assert not ModelChoiceReceipt.objects.filter(
        request_key=body["command_key"]
    ).exists()
    retry = client.post(props["commandHref"], body)
    assert retry.status_code == 409
    assert retry.json()["terminal"] is True
    assert counts()[:-1] == before[:-1]
    assert counts()[-1] == before[-1] + 1
    _restore_tier_item(hunt, removed)
    before_delayed = counts()
    assert client.post(props["commandHref"], body).json()["terminal"] is True
    assert counts() == before_delayed
    record.refresh_from_db()
    assert record.state == ActionRecord.State.STARTED
    assert record.payment_id is None


@pytest.mark.parametrize("invalid", ["unsigned", "other-record", "older-review"])
def test_removed_item_confirmation_requires_the_matching_current_signed_review(
    client, hunt, invalid
):
    from n26.core.action_stages import _review_token

    record, props, body = _tier_confirmation(client, hunt)
    if invalid == "unsigned":
        body["review"] = "not-a-signed-review"
    elif invalid == "other-record":
        from copy import copy

        other = copy(record)
        other.pk = hunt.fighter.pk
        body["review"] = _review_token(other)
    else:
        from n26.core.operations import operation

        with operation(hunt.gang, actor=hunt.owner) as op:
            op.review_action(record, outcome=hunt.upgrade, terms=record.terms)
        record.refresh_from_db()
        body["revision"] = str(record.revision)
    _remove_tier_item(hunt)
    before = counts()
    response = client.post(props["commandHref"], body)
    assert response.status_code == 422
    assert response.json()["terminal"] is False
    assert counts() == before


def test_removed_item_confirmation_keeps_authority_and_exact_receipt_binding(
    client, hunt
):
    record, props, body = _tier_confirmation(client, hunt)
    _remove_tier_item(hunt)
    before = counts()
    stranger = User.objects.create_user("removed-confirmation-stranger")
    client.force_login(stranger)
    assert client.post(props["commandHref"], body).status_code == 404
    assert client.post(props["action"], body).status_code == 404
    assert counts() == before
    client.force_login(hunt.owner)
    assert client.post(props["commandHref"], body).json()["terminal"] is True
    before_reuse = counts()
    changed = client.post(props["commandHref"], {**body, "review": "changed"})
    assert changed.status_code == 409
    assert changed.json()["code"] == "key_conflict"
    assert changed.json()["terminal"] is False
    from n26.core.models import Gang

    Gang.objects.filter(pk=hunt.gang.pk).update(owner=stranger)
    assert client.post(props["commandHref"], body).status_code == 404
    assert counts() == before_reuse


def test_successful_confirmation_receipt_is_recalled_before_item_removal(client, hunt):
    record, props, body = _tier_confirmation(client, hunt)
    saved = client.post(props["commandHref"], body)
    assert saved.status_code == 200
    _remove_tier_item(hunt)
    before = counts()
    replay = client.post(props["commandHref"], body)
    assert replay.status_code == 200
    assert replay.json()["replayed"] is True
    assert replay.json()["facts"] == saved.json()["facts"]
    assert client.post(props["action"], body).status_code == 302
    assert counts() == before


@pytest.mark.django_db(transaction=True)
def test_concurrent_removed_item_confirmation_retries_record_one_durable_refusal(
    client, hunt
):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections

    record, props, body = _tier_confirmation(client, hunt)
    _remove_tier_item(hunt)
    target = ActionTarget("flow", str(record.pk), "review")
    before = counts()

    def submit():
        close_old_connections()
        try:
            return change(hunt.owner, hunt.fighter.pk, target, body)
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert all(result.terminal for result in results)
    assert sum(result.replayed for result in results) == 1
    assert counts()[:-1] == before[:-1]
    assert counts()[-1] == before[-1] + 1


def _history_undo(client, data):
    from bs4 import BeautifulSoup

    edit = client.get(reverse("n26-edit-fighter", args=[data.fighter.pk]))
    form = BeautifulSoup(edit.content, "html.parser").select_one(
        "#n26-action-history form"
    )
    assert form is not None
    body = {
        field["name"]: field.get("value", "") for field in form.select("input[name]")
    }
    return form["action"], body


@pytest.mark.parametrize("transport", ["native", "json"])
def test_an_unused_history_undo_cannot_undo_a_newer_application_of_the_same_action(
    client, advancement, transport
):
    data = advancement
    record = earned_flows._start(client, data)
    assert not hasattr(record, "advancement_selection")
    by_hand = reverse("n26-action-flow", args=[data.fighter.pk, record.pk, "by-hand"])
    first, first_body = issued(client, by_hand)
    assert client.post(first["commandHref"], first_body).status_code == 200
    old_action, old_body = _history_undo(client, data)
    original_revision = int(old_body["revision"])
    assert not ModelChoiceReceipt.objects.filter(
        request_key=old_body["command_key"]
    ).exists()
    # Another tab deliberately undoes and applies the same use again. This
    # original history form has never been sent and has no receipt to replay.
    undo, undo_body = issued(client, old_action)
    undone = client.post(undo["commandHref"], undo_body)
    assert undone.status_code == 200
    fresh, fresh_body = issued(client, by_hand)
    assert client.post(fresh["commandHref"], fresh_body).status_code == 200
    record.refresh_from_db()
    assert record.state == ActionRecord.State.APPLIED_BY_HAND
    assert record.revision == original_revision + 2
    before = counts()
    consumed = client.post(undo["commandHref"], undo_body)
    assert consumed.status_code == 200
    assert consumed.json()["replayed"] is True
    assert consumed.json()["facts"] == undone.json()["facts"]
    record.refresh_from_db()
    assert record.state == ActionRecord.State.APPLIED_BY_HAND
    assert record.revision == original_revision + 2
    assert counts() == before
    if transport == "native":
        refused = client.post(old_action, old_body, follow=True)
        assert refused.status_code == 200
        assert "This flow changed in another tab." in refused.content.decode()
    else:
        refused = client.post(
            first["commandHref"],
            {
                **old_body,
                "target_kind": "flow",
                "target_id": str(record.pk),
                "target_step": "reopen",
            },
        )
        assert refused.status_code == 409
        assert refused.json()["code"] == "revision_conflict"
        assert refused.json()["terminal"] is False
    assert counts() == before
    assert not ModelChoiceReceipt.objects.filter(
        request_key=old_body["command_key"]
    ).exists()
    record.refresh_from_db()
    assert record.state == ActionRecord.State.APPLIED_BY_HAND
    assert record.revision == original_revision + 2
    # A newly issued history Undo has the same intent and the current revision.
    current_action, current_body = _history_undo(client, data)
    assert int(current_body["revision"]) == record.revision
    assert client.post(current_action, current_body).status_code == 302
    record.refresh_from_db()
    assert record.state == ActionRecord.State.STARTED
    assert record.revision == original_revision + 3


@pytest.mark.parametrize("stage", ["unrolled", "reviewed"])
def test_by_hand_and_reopen_each_advance_revision_once_even_when_rebinding_a_reviewed_slot(
    client, advancement, monkeypatch, stage
):
    from n26.core.operations import operation

    data = advancement
    record = earned_flows._start(client, data)
    if stage == "reviewed":
        earned_flows._load_rolls(monkeypatch, 12)
        earned_flows._post_roll(client, data, record)
        skill = earned_flows._choose_result(
            client, data, record, data.results["primary"]
        )
        assert (
            earned_flows.post_action(
                client, skill, {"skill_id": str(data.skills["primary"].pk)}
            ).status_code
            == 302
        )
    record.refresh_from_db()
    revision = record.revision
    with operation(data.gang, actor=data.owner) as op:
        op.apply_action_by_hand(record)
    record.refresh_from_db()
    assert record.state == ActionRecord.State.APPLIED_BY_HAND
    assert record.revision == revision + 1
    before = counts()
    with operation(data.gang, actor=data.owner) as op:
        op.apply_action_by_hand(record)
    record.refresh_from_db()
    assert record.revision == revision + 1
    assert counts() == before
    with operation(data.gang, actor=data.owner) as op:
        op.reopen_action(record)
    record.refresh_from_db()
    assert record.state == ActionRecord.State.STARTED
    assert record.revision == revision + 2
    assert not record.review


def test_allowance_by_hand_creation_and_idempotent_replays_keep_their_original_revision(
    advancement,
):
    from n26.core.operations import operation

    data = advancement
    key = uuid4()
    with operation(data.gang, actor=data.owner) as op:
        record = op.apply_allowance_by_hand(
            data.fighter, data.action, key, allowance=data.allowance
        )
    assert record.state == ActionRecord.State.APPLIED_BY_HAND
    assert record.revision == 0
    before = counts()
    with operation(data.gang, actor=data.owner) as op:
        replay = op.apply_allowance_by_hand(
            data.fighter, data.action, key, allowance=data.allowance
        )
        op.apply_action_by_hand(record)
    assert replay.pk == record.pk
    record.refresh_from_db()
    assert record.revision == 0
    assert counts() == before
    with operation(data.gang, actor=data.owner) as op:
        op.reopen_action(record)
    record.refresh_from_db()
    assert record.state == ActionRecord.State.CANCELLED
    assert record.revision == 1
    with operation(data.gang, actor=data.owner) as op:
        newer = op.apply_allowance_by_hand(
            data.fighter, data.action, uuid4(), allowance=data.allowance
        )
    assert newer.pk != record.pk
    assert newer.state == ActionRecord.State.APPLIED_BY_HAND
    assert newer.revision == 0
    before_replay = counts()
    with operation(data.gang, actor=data.owner) as op:
        old = op.apply_allowance_by_hand(
            data.fighter, data.action, key, allowance=data.allowance
        )
    assert old.pk == record.pk
    assert old.state == ActionRecord.State.CANCELLED
    assert old.revision == 1
    assert counts() == before_replay
