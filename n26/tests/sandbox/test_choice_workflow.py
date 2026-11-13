"""One intentional computed-choice command commits once across both transports."""

from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.http import QueryDict
from django.urls import reverse

from n26.core import choice_workflow
from n26.core.models import Assignment, LedgerEvent, ModelChoiceReceipt
from n26.core.operations import operation
from n26.core.render import option_key
from n26.core.views.choose import find_slot
from n26.tests.sandbox.actions import (
    add_picklist_member,
    create_gang_type,
    create_pickable,
    create_picklist,
    create_slot,
    create_slot_type,
    found_gang,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def choices(default_pack):
    owner = User.objects.create_user("choice-owner")
    kind = create_slot_type("Result", allows_repeats=True)
    table = create_picklist("Results", kind, dice="d6", roll_selects="band")
    pick = create_pickable("Extra armour", kind)
    add_picklist_member(table, pick, roll_low=1, roll_high=6)
    slot = create_slot("Results", kind, table, max_picks=3, assigned_to="gang")
    gang = found_gang("Choice gang", create_gang_type("Choice type"), owner=owner)
    with operation(gang, actor=owner) as op:
        anchor = op.assign(slot, gang=gang)
    key = f"gang:{anchor.pk}:{slot.pk}"
    return SimpleNamespace(
        gang=gang, owner=owner, slot=slot, anchor=anchor, pick=pick, key=key
    )


def command(choices, **values):
    data = QueryDict(mutable=True)
    data.update({"request_key": str(uuid4()), **values})
    return data


def change(choices, data):
    return choice_workflow.change(
        choices.gang,
        choices.owner,
        choices.key,
        data,
        here=reverse("n26-choose", args=[choices.gang.pk, choices.key]),
        back=reverse("n26-gang", args=[choices.gang.pk]),
    )


def test_repeated_roll_requests_return_one_recorded_result(choices):
    data = command(choices, act="enter", rolled="4")
    first, replay = change(choices, data), change(choices, data)
    assert first.saved and replay.saved and replay.replayed
    assert first.next_url == replay.next_url
    assert (
        LedgerEvent.objects.filter(
            gang=choices.gang, kind=LedgerEvent.Kind.ROLLED
        ).count()
        == 1
    )
    assert ModelChoiceReceipt.objects.count() == 1
    changed = data.copy()
    changed["rolled"] = "5"
    assert not change(choices, changed).saved
    assert (
        LedgerEvent.objects.filter(
            gang=choices.gang, kind=LedgerEvent.Kind.ROLLED
        ).count()
        == 1
    )


def test_a_deliberate_repeat_needs_a_new_key(choices):
    data = command(choices, thing=option_key(choices.pick))
    assert change(choices, data).saved
    assert change(choices, data).replayed
    assert len(find_slot(choices.gang, choices.key).slot.picks) == 1
    assert change(choices, command(choices, thing=option_key(choices.pick))).saved
    assert len(find_slot(choices.gang, choices.key).slot.picks) == 2


def test_a_committed_pick_replays_after_its_carrier_is_removed(choices):
    data = command(choices, thing=option_key(choices.pick))
    assert change(choices, data).saved
    with operation(choices.gang, actor=choices.owner) as op:
        op.remove(choices.anchor)
    replay = change(choices, data)
    assert replay.saved and replay.replayed
    assert replay.next_url == reverse("n26-gang", args=[choices.gang.pk])
    assert not Assignment.objects.filter(
        gang_root=choices.gang, pickable=choices.pick, archived=False
    ).exists()


def test_a_removed_choice_consumes_the_key_before_it_can_be_restored(choices):
    data = command(choices, thing=option_key(choices.pick))
    with operation(choices.gang, actor=choices.owner) as op:
        op.remove(choices.anchor)
    result = change(choices, data)
    assert result.terminal and not result.saved
    choices.anchor.archived = False
    choices.anchor.save()
    replay = change(choices, data)
    assert replay.terminal and replay.replayed
    assert not Assignment.objects.filter(
        gang_root=choices.gang, pickable=choices.pick, archived=False
    ).exists()


def test_ownership_is_rechecked_before_confirming_an_old_receipt(choices):
    data = command(choices, thing=option_key(choices.pick))
    assert change(choices, data).saved
    choices.gang.owner = User.objects.create_user("new-choice-owner")
    choices.gang.save()
    assert not change(choices, data).saved
    assert ModelChoiceReceipt.objects.count() == 1


def test_an_unkeyed_old_roll_form_cannot_create_a_new_roll(choices):
    data = command(choices, act="roll")
    del data["request_key"]
    assert not change(choices, data).saved
    assert not LedgerEvent.objects.filter(
        gang=choices.gang, kind=LedgerEvent.Kind.ROLLED
    ).exists()
    assert not ModelChoiceReceipt.objects.exists()


def test_a_stale_option_is_rejected_by_the_current_locked_offer(choices):
    choices.pick.archived = True
    choices.pick.save()
    result = change(choices, command(choices, thing=option_key(choices.pick)))
    assert not result.saved
    assert not Assignment.objects.filter(
        gang_root=choices.gang, pickable=choices.pick
    ).exists()


def test_arrival_repeat_picks_keep_the_original_command(choices):
    from n26.library.authoring import create_interstitial

    create_interstitial("New results", slots=[choices.slot])
    back = reverse("n26-gang", args=[choices.gang.pk])
    data = command(
        choices,
        selection="{}",
        choice=choices.key,
        act="choose",
        thing=option_key(choices.pick),
    )
    first = choice_workflow.change_arrivals(
        choices.gang, choices.owner, [choices.key], data, back=back
    )
    replay = choice_workflow.change_arrivals(
        choices.gang, choices.owner, [choices.key], data, back=back
    )
    assert first.saved and replay.saved and replay.replayed
    assert first.next_url == replay.next_url
    assert len(find_slot(choices.gang, choices.key).slot.picks) == 1


def test_arrival_questions_use_the_same_available_options(choices):
    from n26.library.authoring import create_interstitial

    create_interstitial("New results", slots=[choices.slot])
    back = reverse("n26-gang", args=[choices.gang.pk])
    read = choice_workflow.prepare_arrivals(
        choices.gang, choices.owner, [choices.key], back
    )
    question = read.screen.blocks[0].questions[0]
    assert [
        option.key for group in question.offer.groups for option in group.options
    ] == [option_key(choices.pick)]
    assert choices.key in read.found
    assert not read.screen.may_continue


def test_arrival_refusal_rolls_back_all_picks(choices):
    import json

    from n26.library.authoring import create_interstitial

    choices.slot.max_picks = 1
    choices.slot.save()
    create_interstitial("New results", slots=[choices.slot])
    back = reverse("n26-gang", args=[choices.gang.pk])
    data = command(
        choices,
        selection=json.dumps(
            {
                choices.key: option_key(choices.pick),
                "gang:missing:missing": "pickable:missing",
            }
        ),
    )
    result = choice_workflow.change_arrivals(
        choices.gang, choices.owner, [choices.key], data, back=back
    )
    assert result.terminal
    assert not Assignment.objects.filter(
        gang_root=choices.gang, pickable=choices.pick
    ).exists()
    assert ModelChoiceReceipt.objects.get().result["outcome"] == "unavailable"


@pytest.mark.django_db(transaction=True)
def test_concurrent_generated_rolls_create_one_receipt_and_event(choices):
    from concurrent.futures import ThreadPoolExecutor

    from django.db import close_old_connections

    from n26.core.models import Gang

    data = command(choices, act="roll")
    here = reverse("n26-choose", args=[choices.gang.pk, choices.key])
    back = reverse("n26-gang", args=[choices.gang.pk])

    def submit():
        close_old_connections()
        try:
            gang = Gang.objects.get(pk=choices.gang.pk)
            actor = User.objects.get(pk=choices.owner.pk)
            return choice_workflow.change(
                gang, actor, choices.key, data.copy(), here=here, back=back
            )
        finally:
            close_old_connections()

    with ThreadPoolExecutor(max_workers=2) as pool:
        first, second = list(pool.map(lambda _: submit(), range(2)))
    assert first.saved and second.saved
    assert first.next_url == second.next_url
    assert sum([first.replayed, second.replayed]) == 1
    assert ModelChoiceReceipt.objects.filter(gang=choices.gang).count() == 1
    assert (
        LedgerEvent.objects.filter(
            gang=choices.gang, kind=LedgerEvent.Kind.ROLLED
        ).count()
        == 1
    )


@pytest.mark.parametrize("transport", ["native", "json"])
def test_native_and_json_picks_share_effects_and_navigation(client, choices, transport):
    client.force_login(choices.owner)
    route = "n26-choose" if transport == "native" else "n26-choice-command"
    data = command(choices, thing=option_key(choices.pick))
    response = client.post(reverse(route, args=[choices.gang.pk, choices.key]), data)
    assert response.status_code == (302 if transport == "native" else 200)
    destination = response.url if transport == "native" else response.json()["nextUrl"]
    assert destination == reverse("n26-choose", args=[choices.gang.pk, choices.key])
    assert len(find_slot(choices.gang, choices.key).slot.picks) == 1
    assert ModelChoiceReceipt.objects.count() == 1
    assert (
        client.post(
            reverse(route, args=[choices.gang.pk, choices.key]), data
        ).status_code
        == response.status_code
    )
    assert len(find_slot(choices.gang, choices.key).slot.picks) == 1


def test_retrying_a_dismissal_after_restoration_does_not_hide_it_again(choices):
    from n26.core.models import DismissedOffer

    first = command(choices, act="dismiss")
    assert change(choices, first).saved
    assert DismissedOffer.objects.filter(
        gang=choices.gang, slot_key=choices.key
    ).exists()
    assert change(choices, command(choices, act="restore")).saved
    assert change(choices, first).replayed
    assert not DismissedOffer.objects.filter(
        gang=choices.gang, slot_key=choices.key
    ).exists()


def test_retained_arrival_scope_survives_a_different_current_question_url(choices):
    import json

    from n26.library.authoring import create_interstitial

    create_interstitial("New results", slots=[choices.slot])
    back = reverse("n26-gang", args=[choices.gang.pk])
    data = command(
        choices,
        asks=json.dumps([choices.key]),
        next=back,
        selection="{}",
        choice=choices.key,
        act="choose",
        thing=option_key(choices.pick),
    )
    original = choice_workflow.change_arrivals(
        choices.gang, choices.owner, [choices.key], data, back=back
    )
    replay = choice_workflow.change_arrivals(
        choices.gang, choices.owner, ["unrelated:choice:address"], data, back=back
    )
    assert original.saved and replay.saved and replay.replayed
    assert len(find_slot(choices.gang, choices.key).slot.picks) == 1


def test_failed_settlement_rolls_back_both_pick_and_receipt(choices, monkeypatch):
    from n26.core.operations import Operation, Refusal

    def refuse(_op):
        raise Refusal("This change cannot be applied.")

    monkeypatch.setattr(Operation, "settle", refuse)
    result = change(choices, command(choices, thing=option_key(choices.pick)))
    assert not result.saved
    assert not ModelChoiceReceipt.objects.exists()
    assert not Assignment.objects.filter(
        gang_root=choices.gang, pickable=choices.pick
    ).exists()


def test_another_actor_cannot_reuse_the_previous_owners_key(choices):
    data = command(choices, thing=option_key(choices.pick))
    assert change(choices, data).saved
    choices.owner = User.objects.create_user("replacement-choice-owner")
    choices.gang.owner = choices.owner
    choices.gang.save()
    assert not change(choices, data).saved
    assert ModelChoiceReceipt.objects.count() == 1


def test_choice_queries_do_not_grow_with_picklist_results(client, choices):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client.force_login(choices.owner)
    here = reverse("n26-choose", args=[choices.gang.pk, choices.key])
    client.get(here)
    with CaptureQueriesContext(connection) as first:
        assert client.get(here).status_code == 200
    for number in range(12):
        add_picklist_member(
            choices.slot.picklist,
            create_pickable(f"Extra result {number}", choices.slot.slot_type),
            roll_low=1,
            roll_high=6,
        )
    with CaptureQueriesContext(connection) as larger:
        assert client.get(here).status_code == 200
    assert len(larger) <= len(first)


def test_expired_session_and_real_csrf_failures_return_json_without_writes(
    client, choices
):
    from django.test import Client

    endpoint = reverse("n26-choice-command", args=[choices.gang.pk, choices.key])
    data = command(choices, act="roll")
    assert client.post(endpoint, data).status_code == 401
    strict = Client(enforce_csrf_checks=True)
    strict.force_login(choices.owner)
    rejected = strict.post(endpoint, data, HTTP_ACCEPT="application/json")
    assert rejected.status_code == 403
    assert rejected["Content-Type"].startswith("application/json")
    assert not ModelChoiceReceipt.objects.exists()
    assert not LedgerEvent.objects.filter(
        gang=choices.gang, kind=LedgerEvent.Kind.ROLLED
    ).exists()


def test_receipt_replay_keeps_one_queued_confirmation_and_one_analytics_event(
    client, choices, monkeypatch
):
    from django.contrib.messages import get_messages

    from n26 import analytics

    events = []
    monkeypatch.setattr(
        analytics, "record", lambda *args, **kwargs: events.append((args, kwargs))
    )
    client.force_login(choices.owner)
    endpoint = reverse("n26-choice-command", args=[choices.gang.pk, choices.key])
    data = command(choices, thing=option_key(choices.pick))
    assert client.post(endpoint, data).status_code == 200
    replay = client.post(endpoint, data)
    assert replay.status_code == 200
    assert [str(message) for message in get_messages(replay.wsgi_request)] == [
        "Added Extra armour — Results."
    ]
    assert len(events) == 1


def test_other_owners_cannot_read_or_submit_choice_commands(client, choices):
    client.force_login(User.objects.create_user("unrelated-choice-owner"))
    assert (
        client.get(
            reverse("n26-choose", args=[choices.gang.pk, choices.key])
        ).status_code
        == 404
    )
    assert (
        client.post(
            reverse("n26-choice-command", args=[choices.gang.pk, choices.key]),
            command(choices, act="roll"),
        ).status_code
        == 404
    )
    assert not ModelChoiceReceipt.objects.exists()


def test_a_picker_confirmation_is_drawn_once_by_its_react_owner(client, choices):
    client.force_login(choices.owner)
    endpoint = reverse("n26-choice-command", args=[choices.gang.pk, choices.key])
    response = client.post(endpoint, command(choices, thing=option_key(choices.pick)))
    page = client.get(response.json()["nextUrl"])
    assert page.status_code == 200
    assert page.context["choice_props"]["messages"] == [
        {"text": "Added Extra armour — Results.", "tone": "success"}
    ]
    assert page.content.decode().count("Added Extra armour") == 1


def test_rendered_arrival_values_round_trip_into_the_real_command(client, choices):
    import json

    from n26.core.arrivals import next_url
    from n26.library.authoring import create_interstitial

    create_interstitial("New results", slots=[choices.slot])
    client.force_login(choices.owner)
    back = reverse("n26-gang", args=[choices.gang.pk])
    page = client.get(next_url(choices.gang, [choices.key], back))
    props = page.context["choice_props"]
    assert json.loads(props["values"]["asks"]) == [choices.key]
    assert json.loads(props["values"]["selection"]) == {}
    payload = {
        **props["values"],
        "choice": choices.key,
        "act": "choose",
        "thing": option_key(choices.pick),
    }
    response = client.post(
        props["commandHref"], payload, HTTP_ACCEPT="application/json"
    )
    assert response.status_code == 200, response.content
    assert len(find_slot(choices.gang, choices.key).slot.picks) == 1


def test_none_and_removal_keep_their_archive_analytics_without_replay_duplicates(
    client, choices, monkeypatch
):
    from n26 import analytics

    events = []
    monkeypatch.setattr(
        analytics,
        "record",
        lambda request, noun, verb, subject, **facts: events.append((verb, facts)),
    )
    client.force_login(choices.owner)
    endpoint = reverse("n26-choice-command", args=[choices.gang.pk, choices.key])
    assert (
        client.post(
            endpoint, command(choices, thing=option_key(choices.pick))
        ).status_code
        == 200
    )
    removed = command(choices, remove=option_key(choices.pick))
    assert client.post(endpoint, removed).status_code == 200
    assert client.post(endpoint, removed).status_code == 200
    choices.slot.min_picks, choices.slot.max_picks = 0, 1
    choices.slot.save()
    assert client.post(endpoint, command(choices, thing="none")).status_code == 200
    assert [verb for verb, _ in events] == [
        analytics.EventVerb.CONFIRM,
        analytics.EventVerb.ARCHIVE,
        analytics.EventVerb.ARCHIVE,
    ]
    assert events[1][1] == {"offer": "Results", "picked": "Extra armour"}
    assert events[2][1] == {"offer": "Results", "picked": "None"}


def test_arrivals_emit_one_flat_event_per_changed_choice_and_none_for_empty_continue(
    client, choices, monkeypatch
):
    import json
    from urllib.parse import urlencode

    from n26 import analytics
    from n26.library.authoring import create_interstitial

    choices.slot.max_picks = 1
    choices.slot.save()
    second = create_slot(
        "Second result",
        choices.slot.slot_type,
        choices.slot.picklist,
        assigned_to="gang",
    )
    with operation(choices.gang, actor=choices.owner) as op:
        anchor = op.assign(second, gang=choices.gang)
    second_key = f"gang:{anchor.pk}:{second.pk}"
    keys = [choices.key, second_key]
    create_interstitial("Starting results", slots=[choices.slot, second])
    events = []
    monkeypatch.setattr(
        analytics,
        "record",
        lambda request, noun, verb, subject, **facts: events.append((verb, facts)),
    )
    client.force_login(choices.owner)
    back = reverse("n26-gang", args=[choices.gang.pk])
    endpoint = (
        reverse("n26-next-command", args=[choices.gang.pk])
        + "?"
        + urlencode([*(("ask", key) for key in keys), ("next", back)])
    )
    empty = command(choices, selection="{}", asks=json.dumps(keys), next=back)
    assert client.post(endpoint, empty).status_code == 200
    assert events == []
    data = command(
        choices,
        selection=json.dumps({key: option_key(choices.pick) for key in keys}),
        asks=json.dumps(keys),
        next=back,
    )
    assert client.post(endpoint, data).status_code == 200
    assert client.post(endpoint, data).status_code == 200
    assert len(events) == 2
    assert all(
        verb == analytics.EventVerb.CONFIRM and set(facts) == {"offer", "picked"}
        for verb, facts in events
    )


def test_arrivals_settle_in_url_order_and_ignore_json_object_order_on_replay(
    choices, monkeypatch
):
    import json

    from n26.library.authoring import create_interstitial

    choices.slot.max_picks = 1
    choices.slot.save()
    second = create_slot(
        "Second result",
        choices.slot.slot_type,
        choices.slot.picklist,
        assigned_to="gang",
    )
    with operation(choices.gang, actor=choices.owner) as op:
        anchor = op.assign(second, gang=choices.gang)
    second_key = f"gang:{anchor.pk}:{second.pk}"
    keys = [choices.key, second_key]
    create_interstitial("Starting results", slots=[choices.slot, second])
    data = command(
        choices,
        asks=json.dumps(keys),
        selection=json.dumps({key: option_key(choices.pick) for key in reversed(keys)}),
    )
    written = []
    apply_pick = choice_workflow.write_pick

    def remember(op, gang, actor, key, *args, **kwargs):
        written.append(key)
        return apply_pick(op, gang, actor, key, *args, **kwargs)

    monkeypatch.setattr(choice_workflow, "write_pick", remember)
    back = reverse("n26-gang", args=[choices.gang.pk])
    assert choice_workflow.change_arrivals(
        choices.gang, choices.owner, keys, data, back=back
    ).saved
    assert written == keys
    data["selection"] = json.dumps({key: option_key(choices.pick) for key in keys})
    replay = choice_workflow.change_arrivals(
        choices.gang, choices.owner, keys, data, back=back
    )
    assert replay.saved and replay.replayed
    assert written == keys
