"""Counter steps refresh equipment without repeating an uncertain delta."""

from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.http import QueryDict
from django.urls import reverse

from n26.core.model_card_commands import tally_step
from n26.core.models import CounterValue, EquipReceipt, LedgerEvent
from n26.core.operations import Refusal
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import create_counter
from n26.tests.sandbox.actions import assign, found_gang, hire, remove

pytestmark = pytest.mark.django_db


@pytest.fixture
def gang(gang_type):
    return found_gang(
        "Choir", gang_type, owner=User.objects.create_user("equip-counter"), budget=100
    )


@pytest.fixture
def fighter(gang, make_profile):
    return hire(gang, make_profile("Ganger", price=0), "Vex")


@pytest.fixture
def counter(fighter):
    return assign(create_counter("Marks"), miniature=fighter)


def step(change="1", key=None):
    data = QueryDict(mutable=True)
    data.update({"change": change, "request_key": key or str(uuid4())})
    return data


def test_replay_is_checked_before_a_counter_that_was_removed(gang, fighter, counter):
    data = step()
    first = tally_step(
        gang,
        gang.owner,
        str(counter.pk),
        data,
        require_key=True,
        model_key=str(fighter.pk),
    )
    assert first.value == 1
    remove(counter)
    events = LedgerEvent.objects.filter(gang=gang).count()
    replay = tally_step(
        gang,
        gang.owner,
        str(counter.pk),
        data,
        require_key=True,
        model_key=str(fighter.pk),
    )
    assert replay.replayed and replay.value == 1
    assert LedgerEvent.objects.filter(gang=gang).count() == events
    assert EquipReceipt.objects.filter(gang=gang).count() == 1
    assert_reconciled(gang)


def test_a_deliberate_second_step_uses_a_new_key_and_a_changed_retry_is_refused(
    gang, fighter, counter
):
    data = step()
    tally_step(
        gang,
        gang.owner,
        str(counter.pk),
        data,
        require_key=True,
        model_key=str(fighter.pk),
    )
    changed = step("2", data["request_key"])
    conflict = tally_step(
        gang,
        gang.owner,
        str(counter.pk),
        changed,
        require_key=True,
        model_key=str(fighter.pk),
    )
    assert conflict.conflict
    assert CounterValue.objects.get(assignment=counter).value == 1
    tally_step(
        gang,
        gang.owner,
        str(counter.pk),
        step(),
        require_key=True,
        model_key=str(fighter.pk),
    )
    assert CounterValue.objects.get(assignment=counter).value == 2
    assert EquipReceipt.objects.filter(gang=gang).count() == 2
    assert_reconciled(gang)


def test_a_counter_on_another_model_is_not_a_step_on_this_screen(
    gang, fighter, counter, make_profile
):
    from n26.core.equip_purchase import UnavailableEquipment

    other = hire(gang, make_profile("Other", price=0), "Nell")
    with pytest.raises(UnavailableEquipment, match="not on this model"):
        tally_step(
            gang,
            gang.owner,
            str(counter.pk),
            step(),
            require_key=True,
            model_key=str(other.pk),
        )
    assert not CounterValue.objects.filter(assignment=counter, value=1).exists()
    assert not EquipReceipt.objects.filter(gang=gang).exists()


def test_a_rolled_back_counter_step_leaves_no_receipt(
    gang, fighter, counter, monkeypatch
):
    from n26.core.operations import Operation

    def refuse(*args, **kwargs):
        raise Refusal("The change could not be recorded.")

    monkeypatch.setattr(Operation, "record_equip_receipt", refuse)
    result = tally_step(
        gang,
        gang.owner,
        str(counter.pk),
        step(),
        require_key=True,
        model_key=str(fighter.pk),
    )
    assert result.refused
    assert not CounterValue.objects.filter(assignment=counter, value=1).exists()
    assert not EquipReceipt.objects.filter(gang=gang).exists()
    assert not LedgerEvent.objects.filter(
        gang=gang, kind=LedgerEvent.Kind.TALLIED
    ).exists()
    assert_reconciled(gang)


def test_native_and_json_retries_share_the_same_counter_command(
    client, gang, fighter, counter
):
    client.force_login(gang.owner)
    data = step()
    native = client.post(reverse("n26-tally", args=[counter.pk]), data)
    assert native.status_code == 302
    data.update({"action": "tally", "assignment": str(counter.pk)})
    replay = client.post(reverse("n26-equip-fighter-command", args=[fighter.pk]), data)
    assert replay.status_code == 200
    assert replay.json()["outcome"] == "completed"
    assert CounterValue.objects.get(assignment=counter).value == 1
    assert EquipReceipt.objects.filter(gang=gang).count() == 1
    shown = next(
        row
        for row in replay.json()["page"]["model"]["card"]["details"]
        if row["label"] == "Marks"
    )
    assert shown["parts"][0]["value"] == 1
    assert_reconciled(gang)


def test_a_keyed_native_counter_retry_can_confirm_after_removal(
    client, gang, fighter, counter
):
    client.force_login(gang.owner)
    data = step()
    at = reverse("n26-tally", args=[counter.pk])
    assert client.post(at, data).status_code == 302
    remove(counter)
    before = LedgerEvent.objects.filter(gang=gang).count()
    assert client.post(at, data).status_code == 302
    assert LedgerEvent.objects.filter(gang=gang).count() == before
    assert EquipReceipt.objects.filter(gang=gang).count() == 1
    assert_reconciled(gang)


def test_a_counter_receipt_cannot_crash_the_native_equipment_adapter(
    client, gang, fighter, counter
):
    client.force_login(gang.owner)
    data = step()
    assert client.post(reverse("n26-tally", args=[counter.pk]), data).status_code == 302
    result = client.post(reverse("n26-remove", args=[counter.pk]), data)
    assert result.status_code == 302
    assert CounterValue.objects.get(assignment=counter).value == 1
    counter.refresh_from_db()
    assert not counter.archived
    assert EquipReceipt.objects.filter(gang=gang).count() == 1
    assert_reconciled(gang)


def test_the_campaign_arbitrator_keeps_access_to_a_model_hosted_campaign_counter(
    client, gang, fighter
):
    from n26.library.authoring import create_campaign_type
    from n26.tests.sandbox.actions import found_campaign, join_campaign

    arbitrator = User.objects.create_user("counter-arbitrator")
    campaign = found_campaign(
        "Campaign", create_campaign_type("Campaign type"), owner=arbitrator
    )
    membership = join_campaign(gang, campaign)
    counter = assign(
        create_counter("Campaign marks"),
        miniature=fighter,
        caused_by=membership.type_carrier,
    )
    client.force_login(arbitrator)
    response = client.post(reverse("n26-tally", args=[counter.pk]), {"change": "1"})
    assert response.status_code == 302
    assert CounterValue.objects.get(assignment=counter).value == 1
    assert_reconciled(gang)


@pytest.mark.django_db(transaction=True)
def test_concurrent_counter_retries_record_one_delta(gang, fighter, counter):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, connections

    from n26.core.models import Gang

    data = step()
    barrier = Barrier(2)

    def submit():
        close_old_connections()
        try:
            current = Gang.objects.get(pk=gang.pk)
            actor = User.objects.get(pk=gang.owner_id)
            barrier.wait(timeout=10)
            return tally_step(
                current,
                actor,
                str(counter.pk),
                data,
                require_key=True,
                model_key=str(fighter.pk),
            ).replayed
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: submit(), range(2)))
    assert sorted(results) == [False, True]
    assert CounterValue.objects.get(assignment=counter).value == 1
    assert EquipReceipt.objects.filter(gang=gang).count() == 1
    assert (
        LedgerEvent.objects.filter(gang=gang, kind=LedgerEvent.Kind.TALLIED).count()
        == 1
    )
    assert_reconciled(gang)
