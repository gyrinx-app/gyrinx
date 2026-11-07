"""Equipment retries confirm one purchase or repeat the original question."""

from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.http import QueryDict
from django.utils.text import slugify

from n26.core.browse import browse
from n26.core.equip_purchase import PurchaseCatalogue, purchase
from n26.core.models import Assignment, EquipReceipt, LedgerEvent
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import create_collection, create_wargear
from n26.tests.sandbox.actions import assign, found_gang, remove

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user("equip-owner")


@pytest.fixture
def gang(gang_type, owner):
    return found_gang("Ashen Choir", gang_type, owner=owner, budget=100)


@pytest.fixture
def kit(gang):
    sword = create_wargear("Sword", price=35)
    collection = create_collection("House equipment list", entries=[sword])
    assign(collection, gang=gang)
    return sword, collection


def submission(thing, paid="35"):
    key = f"{thing._meta.label_lower}:{thing.pk}"
    data = QueryDict(mutable=True)
    data.update(
        {
            "thing": key,
            f"{slugify(key)}:price": paid,
            "request_key": str(uuid4()),
            "rate": "",
        }
    )
    return data


def command(gang, owner, kit, data, **kwargs):
    _, collection = kit

    def current():
        return PurchaseCatalogue(
            holder=gang.stash,
            view=browse(collection),
            into="the stash",
            collection=collection.name,
        )

    return purchase(
        gang,
        owner,
        data,
        kwargs.pop("catalogue", current),
        action="/equip/",
        back="/equip/",
        require_key=True,
        identity=kwargs.pop(
            "identity", {"holder": "stash", "list": str(collection.pk)}
        ),
        **kwargs,
    )


def test_a_lost_success_replays_without_another_payment_or_assignment(gang, owner, kit):
    sword, _ = kit
    data = submission(sword)
    first = command(gang, owner, kit, data)
    events = LedgerEvent.objects.filter(gang=gang).count()
    replay = command(gang, owner, kit, data)
    assert first.assignment is not None and not first.replayed
    assert replay.replayed and replay.key == first.key
    assert replay.message == first.message
    assert Assignment.objects.filter(stash=gang.stash, wargear=sword).count() == 1
    assert EquipReceipt.objects.filter(gang=gang).count() == 1
    assert LedgerEvent.objects.filter(gang=gang).count() == events
    gang.refresh_from_db()
    assert gang.credits == 65
    assert_reconciled(gang)


def test_a_receipt_is_recalled_before_removed_holdings_or_changed_catalogue(
    gang, owner, kit
):
    sword, collection = kit
    data = submission(sword)
    first = command(gang, owner, kit, data)
    remove(first.assignment)
    collection.entries.all().delete()

    def unavailable():
        raise AssertionError("A settled purchase must not resolve the catalogue.")

    replay = command(gang, owner, kit, data, catalogue=unavailable)
    assert replay.replayed and not replay.refused
    assert not Assignment.objects.filter(wargear=sword, archived=False).exists()
    assert_reconciled(gang)


@pytest.mark.parametrize("field,value", [("rate", "paid"), ("thing", "other")])
def test_a_key_cannot_be_reused_for_changed_business_input(
    gang, owner, kit, field, value
):
    data = submission(kit[0])
    command(gang, owner, kit, data)
    data[field] = value
    refused = command(gang, owner, kit, data)
    assert refused.conflict and refused.refused
    assert EquipReceipt.objects.filter(gang=gang).count() == 1
    assert_reconciled(gang)


def test_a_key_cannot_move_a_purchase_to_another_offer_scope(gang, owner, kit):
    data = submission(kit[0])
    command(gang, owner, kit, data)
    refused = command(
        gang, owner, kit, data, identity={"holder": "stash", "list": "all"}
    )
    assert refused.conflict
    assert_reconciled(gang)


def test_a_lost_rating_question_remains_a_question_after_the_quote_changes(
    gang, owner, kit
):
    sword, _ = kit
    data = submission(sword, paid="10")
    first = command(gang, owner, kit, data)
    assert first.confirmation is not None
    assert not Assignment.objects.filter(wargear=sword).exists()
    sword.price = 10
    sword.save()
    replay = command(gang, owner, kit, data)
    assert replay.replayed and replay.confirmation == first.confirmation
    assert not Assignment.objects.filter(wargear=sword).exists()
    assert EquipReceipt.objects.filter(gang=gang).count() == 1
    assert_reconciled(gang)


def test_explicit_confirmation_has_one_new_key_and_can_be_retried(gang, owner, kit):
    sword, _ = kit
    data = submission(sword, paid="10")
    first = command(gang, owner, kit, data)
    question = first.confirmation
    confirmed = QueryDict(mutable=True)
    for name, value in question.carry:
        confirmed.appendlist(name, value)
    confirmed[question.confirm_field] = question.confirm_value
    confirmed["rate"] = "paid"
    assert confirmed["request_key"] != data["request_key"]
    written = command(gang, owner, kit, confirmed)
    replay = command(gang, owner, kit, confirmed)
    original = command(gang, owner, kit, data)
    assert written.assignment is not None
    assert replay.replayed and replay.key == written.key
    assert original.confirmation == question
    assert Assignment.objects.filter(stash=gang.stash, wargear=sword).count() == 1
    assert EquipReceipt.objects.filter(gang=gang).count() == 2
    gang.refresh_from_db()
    assert gang.credits == 90
    assert written.assignment.rating == 10
    assert_reconciled(gang)


def test_an_unaffordable_purchase_leaves_no_receipt_or_partial_holdings(
    gang, owner, kit
):
    sword, _ = kit
    data = submission(sword, paid="101")
    result = command(gang, owner, kit, data)
    assert result.refused and result.assignment is None
    assert not EquipReceipt.objects.filter(gang=gang).exists()
    assert not Assignment.objects.filter(wargear=sword).exists()
    assert_reconciled(gang)


def test_a_saved_command_still_requires_current_ownership(gang, owner, kit):
    data = submission(kit[0])
    command(gang, owner, kit, data)
    gang.owner = User.objects.create_user("new-equip-owner")
    gang.save(update_fields=["owner"])
    refused = command(gang, owner, kit, data)
    assert refused.refused and not refused.replayed
    assert_reconciled(gang)


@pytest.mark.parametrize("raw", ["", "not-a-key"])
def test_new_commands_require_a_valid_stable_key(gang, owner, kit, raw):
    data = submission(kit[0])
    data["request_key"] = raw
    assert command(gang, owner, kit, data).refused
    assert not EquipReceipt.objects.filter(gang=gang).exists()
    assert_reconciled(gang)


def test_native_and_json_purchase_adapters_use_the_same_price_and_destination(
    client, gang, owner, kit
):
    import json

    from django.urls import reverse

    sword, collection = kit
    client.force_login(owner)
    data = submission(sword)
    data.update(
        {
            "action": "buy",
            "list": str(collection.pk),
            "paid": "35",
            "selection": "[]",
            "parts": "[]",
        }
    )
    response = client.post(reverse("n26-equip-stash-command", args=[gang.pk]), data)
    assert response.status_code == 200
    result = response.json()
    assert result["outcome"] == "completed"
    assert "Sword" in json.dumps(result["page"]["sections"])
    assert "about" not in json.dumps(result["page"]["sections"])
    assert Assignment.objects.filter(stash=gang.stash, wargear=sword).count() == 1
    replay = client.post(reverse("n26-equip-stash-command", args=[gang.pk]), data)
    assert replay.status_code == 200 and replay.json()["outcome"] == "completed"
    assert Assignment.objects.filter(stash=gang.stash, wargear=sword).count() == 1
    gang.refresh_from_db()
    assert gang.credits == 65
    native = found_gang(
        "Native equipment gang", gang.gang_type, owner=owner, budget=100
    )
    assign(collection, gang=native)
    native_response = client.post(
        reverse("n26-equip-gang", args=[native.pk]) + f"?list={collection.pk}",
        {"thing": data["thing"], "request_key": str(uuid4())},
    )
    assert native_response.status_code == 302
    native.refresh_from_db()
    assert native.credits == gang.credits
    original = Assignment.objects.get(stash=gang.stash, wargear=sword).ledger_entry
    equivalent = Assignment.objects.get(stash=native.stash, wargear=sword).ledger_entry
    assert (original.paid, original.list_price, original.rating_contribution) == (
        equivalent.paid,
        equivalent.list_price,
        equivalent.rating_contribution,
    )
    assert_reconciled(native)
    assert_reconciled(gang)


def test_the_display_endpoint_uses_the_same_scope_and_owned_facts(
    client, gang, owner, kit
):
    from django.urls import reverse

    command(gang, owner, kit, submission(kit[0]))
    client.force_login(owner)
    response = client.get(
        reverse("n26-equip-stash-display", args=[gang.pk]), {"list": "stash"}
    )
    assert response.status_code == 200
    page = response.json()["page"]
    assert page["scope"] == "stash"
    entries = [
        entry
        for section in page["sections"]
        for category in section["categories"]
        for entry in category["entries"]
    ]
    assert len(entries) == 1
    assert entries[0]["purchase"] is None
    assert entries[0]["count"] == 1
    assert entries[0]["copies"][0]["name"] == "Sword"
    assert_reconciled(gang)


def test_an_owned_json_refund_replays_after_its_assignment_is_removed(
    client, gang, owner, kit
):
    from django.urls import reverse

    bought = command(gang, owner, kit, submission(kit[0])).assignment
    client.force_login(owner)
    at = reverse("n26-equip-stash-command", args=[gang.pk])
    data = {
        "action": "refund",
        "assignment": str(bought.pk),
        "request_key": str(uuid4()),
        "list": "stash",
    }
    first = client.post(at, data)
    assert first.status_code == 200 and first.json()["outcome"] == "completed"
    count = LedgerEvent.objects.filter(gang=gang).count()
    second = client.post(at, data)
    assert second.status_code == 200 and second.json()["outcome"] == "completed"
    assert LedgerEvent.objects.filter(gang=gang).count() == count
    gang.refresh_from_db()
    assert gang.credits == 100
    assert_reconciled(gang)


@pytest.mark.parametrize(
    "endpoint", ["n26-equip-stash-display", "n26-equip-stash-command"]
)
def test_json_endpoints_return_session_failure_without_an_account_redirect(
    client, gang, endpoint
):
    from django.urls import reverse

    at = reverse(endpoint, args=[gang.pk])
    response = client.get(at) if endpoint.endswith("display") else client.post(at, {})
    assert response.status_code == 401
    assert response["Content-Type"] == "application/json"


def test_stable_option_identity_keeps_the_full_payment_when_the_default_reorders(
    gang, owner
):
    import json

    from n26.library.authoring import offer_option

    harness = create_wargear("Harness", price=30)
    plain = offer_option(harness, "Plain", price=0)
    armed = offer_option(harness, "Armed", price=15)
    collection = create_collection("Harness list", entries=[harness])
    assign(collection, gang=gang)
    data = submission(harness)
    data.update({"selection": json.dumps([str(armed.pk)]), "parts": "[]", "paid": "45"})
    plain.position = 1
    plain.save(update_fields=["position"])
    armed.position = 0
    armed.save(update_fields=["position"])
    result = command(gang, owner, (harness, collection), data)
    assert result.assignment is not None
    assert result.assignment.ledger_entry.paid == 45
    assert result.assignment.rating == 45
    assert list(
        result.assignment.chosen_options.values_list("default_set_id", flat=True)
    ) == [armed.default_set_id]
    gang.refresh_from_db()
    assert gang.credits == 55
    assert_reconciled(gang)


@pytest.mark.django_db(transaction=True)
def test_concurrent_copies_of_a_purchase_have_one_receipt_and_payment(gang, owner, kit):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, connections

    from n26.core.models import Gang

    data = submission(kit[0])
    barrier = Barrier(2)

    def submit():
        close_old_connections()
        try:
            fresh = Gang.objects.get(pk=gang.pk)
            actor = User.objects.get(pk=owner.pk)
            barrier.wait(timeout=10)
            return command(fresh, actor, kit, data).replayed
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as executor:
        results = list(executor.map(lambda _: submit(), range(2)))
    assert sorted(results) == [False, True]
    assert EquipReceipt.objects.filter(gang=gang).count() == 1
    assert Assignment.objects.filter(stash=gang.stash, wargear=kit[0]).count() == 1
    gang.refresh_from_db()
    assert gang.credits == 65
    assert_reconciled(gang)


def test_real_csrf_rejection_does_not_save_equipment(gang, owner, kit):
    from django.test import Client
    from django.urls import reverse

    client = Client(enforce_csrf_checks=True)
    client.force_login(owner)
    data = submission(kit[0])
    data.update({"action": "buy", "list": str(kit[1].pk)})
    response = client.post(
        reverse("n26-equip-stash-command", args=[gang.pk]),
        data,
        headers={"Accept": "application/json"},
    )
    assert response.status_code == 403
    assert "session could not be verified" in response.json()["error"]
    assert not EquipReceipt.objects.filter(gang=gang).exists()
    assert not Assignment.objects.filter(wargear=kit[0]).exists()
    assert_reconciled(gang)


def test_cached_native_panel_requests_navigate_to_the_complete_owner(
    client, gang, owner, kit
):
    from django.urls import reverse

    client.force_login(owner)
    at = reverse("n26-equip-gang", args=[gang.pk]) + f"?list={kit[1].pk}"
    response = client.get(at, headers={"HX-Request": "true"})
    assert response.status_code == 200
    assert response.headers["HX-Redirect"] == at
    assert response.content == b""


@pytest.mark.parametrize(
    "action,credits", [("sell", 83), ("refund", 100), ("remove", 65)]
)
def test_owned_removals_settle_once_and_replay_without_resolving_the_removed_assignment(
    gang, owner, kit, action, credits
):
    from n26.core.owned_actions import change

    bought = command(gang, owner, kit, submission(kit[0])).assignment
    data = QueryDict(mutable=True)
    data["request_key"] = str(uuid4())
    first = change(gang, owner, action, str(bought.pk), data, require_key=True)
    count = LedgerEvent.objects.filter(gang=gang).count()
    replay = change(gang, owner, action, str(bought.pk), data, require_key=True)
    assert first.changed and not first.replayed
    assert replay.replayed and replay.message == first.message
    assert LedgerEvent.objects.filter(gang=gang).count() == count
    gang.refresh_from_db()
    assert gang.credits == credits
    assert_reconciled(gang)


def test_reassignment_replays_after_the_possession_has_left_its_original_host(
    gang, owner, kit, make_profile
):
    from n26.core.operations import operation
    from n26.core.owned_actions import change

    with operation(gang, actor=owner) as op:
        model = op.hire(make_profile("Ganger", price=0), "Vex")
    bought = command(gang, owner, kit, submission(kit[0])).assignment
    data = QueryDict(mutable=True)
    data.update(
        {"request_key": str(uuid4()), "to": "model", "miniature": str(model.pk)}
    )
    first = change(gang, owner, "reassign", str(bought.pk), data, require_key=True)
    count = LedgerEvent.objects.filter(gang=gang).count()
    replay = change(gang, owner, "reassign", str(bought.pk), data, require_key=True)
    assert first.changed and replay.replayed
    assert first.touched.miniature is None and replay.touched.miniature is None
    bought.refresh_from_db()
    assert bought.miniature_root_id == model.pk
    assert LedgerEvent.objects.filter(gang=gang).count() == count
    gang.refresh_from_db()
    assert gang.credits == 65 and gang.stash_rating == 0 and gang.rating == 35
    assert_reconciled(gang)


def test_an_accessory_purchase_is_not_repeated_after_a_lost_response(
    gang, owner, default_pack
):
    from n26.core.operations import operation
    from n26.core.owned_actions import change
    from n26.library.authoring import create_weapon, create_weapon_accessory

    gun = create_weapon("Autogun", price=35)
    sight = create_weapon_accessory("Sight", price=10, staged=False)
    with operation(gang, actor=owner) as op:
        bought = op.buy(gang.stash, thing=gun)
    data = QueryDict(mutable=True)
    data.update({"request_key": str(uuid4()), "accessory": str(sight.pk)})
    first = change(gang, owner, "accessorise", str(bought.pk), data, require_key=True)
    count = LedgerEvent.objects.filter(gang=gang).count()
    replay = change(gang, owner, "accessorise", str(bought.pk), data, require_key=True)
    assert first.changed and replay.replayed
    assert Assignment.objects.filter(parent=bought, weapon_accessory=sight).count() == 1
    assert LedgerEvent.objects.filter(gang=gang).count() == count
    gang.refresh_from_db()
    assert gang.credits == 55 and gang.stash_rating == 45
    assert_reconciled(gang)


def test_stable_option_changes_are_paid_once_and_replay_after_the_offer_is_removed(
    gang, owner
):
    import json

    from n26.core.operations import operation
    from n26.core.owned_actions import change
    from n26.library.authoring import offer_option

    harness = create_wargear("Harness", price=30)
    offer_option(harness, "Plain", price=0)
    armed = offer_option(harness, "Armed", price=15)
    with operation(gang, actor=owner) as op:
        bought = op.buy(gang.stash, thing=harness)
    data = QueryDict(mutable=True)
    data.update({"request_key": str(uuid4()), "selection": json.dumps([str(armed.pk)])})
    first = change(gang, owner, "rechoose", str(bought.pk), data, require_key=True)
    count = LedgerEvent.objects.filter(gang=gang).count()
    armed.delete()
    replay = change(gang, owner, "rechoose", str(bought.pk), data, require_key=True)
    assert first.changed and replay.replayed
    assert LedgerEvent.objects.filter(gang=gang).count() == count
    gang.refresh_from_db()
    assert gang.credits == 55 and gang.stash_rating == 45
    assert_reconciled(gang)


@pytest.mark.parametrize("scope", ["stash", "list"])
def test_owned_option_descriptions_do_not_add_queries_per_copy(
    client, gang, owner, scope
):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext
    from django.urls import reverse

    from n26.core.operations import operation
    from n26.library.authoring import offer_option

    harness = create_wargear("Harness", price=5)
    offer_option(harness, "Plain", price=0)
    offer_option(harness, "Armed", price=5)
    collection = create_collection("Harness list", entries=[harness])
    assign(collection, gang=gang)
    with operation(gang, actor=owner) as op:
        op.buy(gang.stash, thing=harness)
    client.force_login(owner)
    at = (
        reverse("n26-equip-gang", args=[gang.pk])
        + f"?list={collection.pk if scope == 'list' else 'stash'}"
    )

    def measured():
        assert client.get(at).status_code == 200
        with CaptureQueriesContext(connection) as captured:
            assert client.get(at).status_code == 200
        return len(captured)

    few = measured()
    with operation(gang, actor=owner) as op:
        for _ in range(4):
            op.buy(gang.stash, thing=harness)
    assert measured() == few
    gang.refresh_from_db()
    assert_reconciled(gang)


def test_a_missing_offer_scope_does_not_fall_back_to_another_lists_terms(
    client, gang, owner, kit
):
    from django.urls import reverse

    sword, original = kit
    other = create_collection(
        "Another equipment list", entries=[(sword, {"price_override": 10})]
    )
    assign(other, gang=gang)
    original.entries.all().delete()
    client.force_login(owner)
    data = submission(sword)
    data.update(
        {
            "action": "buy",
            "list": str(original.pk),
            "selection": "[]",
            "parts": "[]",
            "paid": "35",
        }
    )
    result = client.post(reverse("n26-equip-stash-command", args=[gang.pk]), data)
    assert result.status_code == 422
    assert "equipment list has changed" in str(result.json()["errors"])
    assert not Assignment.objects.filter(wargear=sword).exists()
    assert not EquipReceipt.objects.filter(gang=gang).exists()
    assert_reconciled(gang)


def test_a_native_purchase_receipt_is_recalled_even_when_its_list_disappears(
    client, gang, owner, kit
):
    from django.urls import reverse

    sword, collection = kit
    client.force_login(owner)
    data = submission(sword)
    at = reverse("n26-equip-gang", args=[gang.pk]) + f"?list={collection.pk}"
    first = client.post(at, data)
    assert first.status_code == 302
    collection.entries.all().delete()
    replay = client.post(at, data)
    assert replay.status_code == 302
    assert Assignment.objects.filter(stash=gang.stash, wargear=sword).count() == 1
    assert EquipReceipt.objects.filter(gang=gang).count() == 1
    gang.refresh_from_db()
    assert gang.credits == 65
    assert_reconciled(gang)


@pytest.mark.parametrize("action", ["sell", "refund", "remove"])
def test_a_keyed_native_removal_replays_after_the_assignment_is_archived(
    client, gang, owner, kit, action
):
    from django.urls import reverse

    sword, _ = kit
    assignment = assign(sword, stash=gang.stash, paid=35)
    client.force_login(owner)
    data = {"request_key": str(uuid4()), "list": "stash", "accessories": "stash"}
    at = reverse(
        {"sell": "n26-sell", "refund": "n26-refund", "remove": "n26-remove"}[action],
        args=[assignment.pk],
    )
    first = client.post(at, data)
    assert first.status_code == 302
    assignment.refresh_from_db()
    assert assignment.archived
    gang.refresh_from_db()
    before = (
        gang.credits,
        gang.stash_rating,
        gang.wealth,
        LedgerEvent.objects.filter(gang=gang).count(),
    )
    replay = client.post(at, data)
    assert replay.status_code == 302
    assert replay["Location"] == first["Location"]
    gang.refresh_from_db()
    assert (
        gang.credits,
        gang.stash_rating,
        gang.wealth,
        LedgerEvent.objects.filter(gang=gang).count(),
    ) == before
    assert EquipReceipt.objects.filter(gang=gang).count() == 1
    assert_reconciled(gang)


def test_a_fighter_purchase_refreshes_the_complete_card_and_replays_once(
    client, gang, owner, kit, make_profile
):
    from django.urls import reverse

    from n26.tests.sandbox.actions import hire

    fighter = hire(gang, make_profile("Ganger", price=0), "Vex")
    sword, collection = kit
    client.force_login(owner)
    data = submission(sword)
    data.update(
        {
            "action": "buy",
            "list": str(collection.pk),
            "selection": "[]",
            "parts": "[]",
            "paid": "35",
            "personal_activity": "",
        }
    )
    at = reverse("n26-equip-fighter-command", args=[fighter.pk])
    first = client.post(at, data)
    assert first.status_code == 200
    page = first.json()["page"]
    assert page["model"]["card"]["rating"] == 35
    gear = next(
        row for row in page["model"]["card"]["details"] if row["label"] == "Gear"
    )
    assert gear["parts"][0]["lines"][0]["text"] == "Sword"
    assert (
        next(item for item in page["figures"]["items"] if item["short"] == "Cr")[
            "value"
        ]
        == "65¢"
    )
    current = client.get(
        reverse("n26-equip-fighter-display", args=[fighter.pk]),
        {"list": str(collection.pk)},
    ).json()["page"]
    assert current["model"] == page["model"]
    assert current["figures"] == page["figures"]
    assert current["sections"] == page["sections"]
    replay = client.post(at, data)
    assert replay.status_code == 200
    assert Assignment.objects.filter(miniature=fighter, wargear=sword).count() == 1
    assert EquipReceipt.objects.filter(gang=gang).count() == 1
    gang.refresh_from_db()
    assert gang.credits == 65 and gang.rating == 35
    assert_reconciled(gang)


@pytest.mark.parametrize(
    "endpoint", ["n26-equip-fighter-display", "n26-equip-fighter-command"]
)
def test_fighter_equipment_endpoints_require_the_model_owner(
    client, gang, owner, make_profile, endpoint
):
    from django.urls import reverse

    from n26.tests.sandbox.actions import hire

    fighter = hire(gang, make_profile("Ganger", price=0), "Vex")
    at = reverse(endpoint, args=[fighter.pk])
    call = client.get if endpoint.endswith("display") else client.post
    assert call(at).status_code == 401
    client.force_login(User.objects.create_user("other-equip-owner"))
    assert call(at).status_code == 404
