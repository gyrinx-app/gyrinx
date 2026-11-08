"""A confirmed hire is one acquisition, even when its response is lost."""

from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.db import close_old_connections, connection, connections
from django.http import QueryDict
from django.test import RequestFactory
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils.text import slugify

from n26.core import hire_workflow
from n26.core.arrivals import onward
from n26.core.models import Gang, HireReceipt, LedgerEvent, Miniature
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import (
    add_built_in,
    create_interstitial,
    create_pickable,
    create_picklist,
    create_slot,
    create_slot_type,
    create_wargear,
    modifier,
    offer_option,
    op_adds_model,
    revise,
    targets_model,
)
from n26.tests.sandbox.actions import found_gang, hire, remove

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user("hire-owner")


@pytest.fixture
def gang(gang_type, owner):
    return found_gang("Ashen Choir", gang_type, owner=owner, budget=100)


@pytest.fixture
def profile(make_profile):
    return make_profile("Ganger", price=60)


def submission(profile, **values):
    data = QueryDict(mutable=True)
    data.update(
        {"profile": str(profile.pk), "name": "Vex", "request_key": str(uuid4())}
    )
    data.update(values)
    return data


def url(gang):
    return reverse("n26-hire-fighter", args=[gang.pk])


class TestSavingOneAcquisition:
    def test_a_retry_keeps_built_in_equipment_and_the_pet_it_created_once(
        self, gang, owner, profile, make_profile
    ):
        pet = make_profile("Cyber-mastiff", price=40, hireable=False)
        collar = create_wargear("Cyber-mastiff collar")
        modifier(
            "Collar brings a mastiff",
            targets_model(),
            op_adds_model(pet),
            attach_to=collar,
        )
        add_built_in(profile, collar)
        data = submission(profile)
        first = hire_workflow.change(gang, owner, data)
        assert first.saved
        events = LedgerEvent.objects.filter(gang=gang).count()
        replay = hire_workflow.change(gang, owner, data)
        assert replay.saved and not replay.applied
        assert list(
            Miniature.objects.filter(membership__gang=gang)
            .order_by("name")
            .values_list("name", flat=True)
        ) == ["Cyber-mastiff", "Vex"]
        assert first.written == replay.written
        assert str(first.miniature.membership_id) in replay.written
        assert LedgerEvent.objects.filter(gang=gang).count() == events
        assert_reconciled(gang)

    def test_a_retry_recalls_the_hire_without_spending_again(
        self, gang, owner, profile
    ):
        data = submission(profile)
        first = hire_workflow.change(gang, owner, data)
        replay = hire_workflow.change(gang, owner, data)

        assert first.saved and first.applied
        assert replay.saved and not replay.applied
        assert first.receipt.pk == replay.receipt.pk
        assert first.written == replay.written
        assert str(first.miniature.membership_id) in replay.written
        assert HireReceipt.objects.filter(gang=gang).count() == 1
        assert Miniature.objects.filter(membership__gang=gang).count() == 1
        gang.refresh_from_db()
        assert gang.credits == 40
        assert gang.rating == 60
        assert_reconciled(gang)

    @pytest.mark.parametrize(
        "changed", [{"name": "Sull"}, {"paid": "0"}, {"rate": "paid"}]
    )
    def test_a_consumed_key_cannot_hire_changed_input(
        self, gang, owner, profile, changed
    ):
        data = submission(profile)
        assert hire_workflow.change(gang, owner, data).saved
        for field, value in changed.items():
            data[field] = value
        result = hire_workflow.change(gang, owner, data)

        assert result.conflict and not result.saved
        assert "different hire" in result.form.non_field_errors()[0]
        assert Miniature.objects.filter(membership__gang=gang).count() == 1
        assert_reconciled(gang)

    def test_a_retry_does_not_resolve_a_changed_or_archived_catalogue(
        self, gang, owner, profile
    ):
        knife = create_wargear("Knife", price=0)
        option = offer_option(profile, "Knife", thing=knife)
        data = submission(profile)
        data[f"{slugify(str(profile.pk))}:0"] = "0"
        first = hire_workflow.change(gang, owner, data)
        assert first.saved

        option.delete()
        revise(profile, name="Renamed", price=900, archived=True)
        replay = hire_workflow.change(gang, owner, data)
        assert replay.saved and not replay.applied
        assert replay.receipt.profile_name == "Ganger"
        assert replay.receipt.paid == 60
        assert_reconciled(gang)

    def test_a_consumed_key_cannot_change_the_selected_option(
        self, gang, owner, profile
    ):
        offer_option(profile, "Plain")
        offer_option(profile, "Equipped", price=25)
        data = submission(profile)
        field = f"{slugify(str(profile.pk))}:0"
        data[field] = "0"
        assert hire_workflow.change(gang, owner, data).saved
        data[field] = "1"
        result = hire_workflow.change(gang, owner, data)
        assert result.conflict and not result.saved
        assert Miniature.objects.filter(membership__gang=gang).count() == 1
        assert_reconciled(gang)

    def test_an_unavailable_profile_returns_an_error_without_consuming_the_key(
        self, gang, owner, profile
    ):
        data = submission(profile)
        revise(profile, hireable=False)
        result = hire_workflow.change(gang, owner, data)
        assert not result.saved
        assert result.form.non_field_errors() == [
            "This profile is no longer available. Choose another."
        ]
        assert not HireReceipt.objects.filter(gang=gang).exists()
        assert not Miniature.objects.filter(membership__gang=gang).exists()

    def test_a_retry_does_not_restore_a_model_the_player_removed(
        self, gang, owner, profile
    ):
        data = submission(profile)
        first = hire_workflow.change(gang, owner, data)
        remove(first.miniature.membership)
        replay = hire_workflow.change(gang, owner, data)

        assert replay.saved and not replay.applied
        assert replay.receipt.miniature_key == str(first.miniature.pk)
        assert (
            Miniature.objects.filter(
                membership__gang=gang, membership__archived=False
            ).count()
            == 0
        )
        assert_reconciled(gang)

    def test_replaying_a_hire_has_a_fixed_query_cost_as_the_roster_grows(
        self, gang, owner, profile
    ):
        data = submission(profile)
        assert hire_workflow.change(gang, owner, data).saved
        with CaptureQueriesContext(connection) as small:
            assert hire_workflow.change(gang, owner, data).saved
        for name in ("Sull", "Rook", "Ash"):
            hire(gang, profile, name, paid=0)
        with CaptureQueriesContext(connection) as large:
            assert hire_workflow.change(gang, owner, data).saved
        assert len(large) == len(small)
        assert not any('"library_profile"' in query["sql"] for query in large)
        assert_reconciled(gang)

    def test_an_overspend_rolls_back_the_receipt_and_allows_a_corrected_retry(
        self, gang, owner, profile
    ):
        data = submission(profile, paid="101")
        events = LedgerEvent.objects.filter(gang=gang).count()
        result = hire_workflow.change(gang, owner, data)
        assert not result.saved and not result.applied
        assert result.written == set()
        assert "short" in result.refused
        assert not HireReceipt.objects.filter(gang=gang).exists()
        assert not Miniature.objects.filter(membership__gang=gang).exists()
        assert LedgerEvent.objects.filter(gang=gang).count() == events

        data["paid"] = "40"
        assert hire_workflow.change(gang, owner, data).applied
        gang.refresh_from_db()
        assert gang.credits == 60
        assert gang.rating == 60
        assert_reconciled(gang)

    @pytest.mark.parametrize("key", ["", "invalid"])
    def test_a_missing_or_malformed_key_never_writes(self, gang, owner, profile, key):
        result = hire_workflow.change(gang, owner, submission(profile, request_key=key))
        assert result.form.errors["request_key"] == ["Reload this page before hiring."]
        assert not HireReceipt.objects.filter(gang=gang).exists()
        assert not Miniature.objects.filter(membership__gang=gang).exists()

    @pytest.mark.parametrize("change", ["archived", "owner"])
    def test_current_access_is_checked_before_replaying_a_saved_hire(
        self, gang, owner, profile, change
    ):
        data = submission(profile)
        assert hire_workflow.change(gang, owner, data).saved
        current = Gang.objects.get(pk=gang.pk)
        if change == "archived":
            current.archive()
        else:
            current.owner = User.objects.create_user("new-owner")
            current.save(update_fields=["owner"])
        result = hire_workflow.change(gang, owner, data)
        assert not result.saved
        assert "no longer hire" in result.refused
        assert Miniature.objects.filter(membership__gang=gang).count() == 1
        assert_reconciled(gang)

    def test_a_new_owner_cannot_replay_the_previous_owners_key(
        self, gang, owner, profile
    ):
        data = submission(profile)
        assert hire_workflow.change(gang, owner, data).saved
        new_owner = User.objects.create_user("new-owner")
        gang.owner = new_owner
        gang.save(update_fields=["owner"])
        result = hire_workflow.change(gang, new_owner, data)
        assert result.conflict and not result.saved
        assert_reconciled(gang)

    @pytest.mark.parametrize(
        "paid,quoted,rate,rating",
        [
            ("", 60, "", 60),
            ("0", 60, "", 60),
            ("0", 60, "paid", 0),
        ],
    )
    def test_the_receipt_preserves_blank_and_zero_payment(
        self, gang, owner, profile, paid, quoted, rate, rating
    ):
        revise(profile, price=quoted)
        data = submission(profile, paid=paid, rate=rate)
        result = hire_workflow.change(gang, owner, data)
        assert result.saved
        assert result.receipt.paid == (quoted if paid == "" else int(paid))
        assert result.receipt.payload["paid"] == paid
        assert hire_workflow.change(gang, owner, data).saved
        gang.refresh_from_db()
        assert gang.rating == rating
        assert gang.credits == 100 - result.receipt.paid
        assert_reconciled(gang)

    def test_an_unlimited_gang_still_records_the_actual_price(
        self, gang_type, owner, profile
    ):
        gang = found_gang("Unbudgeted", gang_type, owner=owner)
        data = submission(profile, paid="900")
        result = hire_workflow.change(gang, owner, data)
        assert result.saved and result.receipt.paid == 900
        assert hire_workflow.change(gang, owner, data).saved
        assert_reconciled(gang)


class TestTheNativeForm:
    def test_the_confirmation_carries_a_fresh_key_and_cannot_be_cached(
        self, client, gang, owner, profile
    ):
        client.force_login(owner)
        first = client.get(url(gang), {"hire": str(profile.pk)})
        second = client.get(url(gang), {"hire": str(profile.pk)})
        key = first.context["form"]["request_key"].value()
        assert key != second.context["form"]["request_key"].value()
        page = BeautifulSoup(first.content, "html.parser")
        assert page.select_one('input[name="request_key"]')["value"] == str(key)
        assert "no-store" in first["Cache-Control"]

    def test_a_key_error_is_visible_and_an_invalid_name_keeps_the_same_key(
        self, client, gang, owner, profile
    ):
        client.force_login(owner)
        bad_key = client.post(url(gang), {"profile": str(profile.pk), "name": "Vex"})
        assert "Reload this page before hiring." in bad_key.content.decode()
        data = submission(profile, name="x" * 201)
        failed = client.post(url(gang), data)
        assert failed.context["form"]["request_key"].value() == data["request_key"]
        assert not Miniature.objects.filter(membership__gang=gang).exists()

    @pytest.mark.parametrize("paid", ["40", "0", ""])
    def test_a_name_error_preserves_payment_and_the_unticked_rating_choice(
        self, client, gang, owner, profile, paid
    ):
        client.force_login(owner)
        data = submission(profile, name="x" * 201, paid=paid)
        failed = client.post(url(gang), data)
        page = BeautifulSoup(failed.content, "html.parser")
        assert page.select_one('input[name="paid"]')["value"] == paid
        assert not page.select_one('input[name="rate"]').has_attr("checked")
        assert (
            page.select_one('input[name="request_key"]')["value"] == data["request_key"]
        )

    def test_a_lost_redirect_does_not_duplicate_feedback_or_analytics(
        self, client, gang, owner, profile, monkeypatch
    ):
        recorded = []
        monkeypatch.setattr(
            "n26.analytics.record", lambda *args, **kwargs: recorded.append(kwargs)
        )
        client.force_login(owner)
        data = submission(profile)
        first = client.post(url(gang), data)
        replay = client.post(url(gang), data)
        assert first["Location"] == replay["Location"] == url(gang)
        assert len(recorded) == 1 and recorded[0]["paid"] == 60
        assert [str(message) for message in get_messages(replay.wsgi_request)] == [
            "Hired Vex — Ganger, 60¢."
        ]
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_retry_after_reading_success_says_the_hire_was_already_saved(
        self, client, gang, owner, profile
    ):
        client.force_login(owner)
        data = submission(profile)
        client.post(url(gang), data)
        client.get(url(gang))
        replay = client.post(url(gang), data)
        assert [str(message) for message in get_messages(replay.wsgi_request)] == [
            "Vex was already hired."
        ]
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_replay_retains_the_anchors_for_arrival_screens(self, gang, owner, profile):
        slot_type = create_slot_type("Specialisation")
        pick = create_pickable("Scout", slot_type)
        picklist = create_picklist("Specialisations", slot_type, members=[pick])
        slot = create_slot("Specialisation", slot_type, picklist)
        add_built_in(profile, slot)
        create_interstitial(
            "Specialisation",
            title="Choose a specialisation",
            slots=[slot],
            staged=False,
        )
        data = submission(profile)
        first = hire_workflow.change(gang, owner, data)
        replay = hire_workflow.change(gang, owner, data)
        request = RequestFactory().get(url(gang))
        request.user = owner
        first_url = onward(request, gang, first, url(gang))
        assert first_url.startswith(reverse("n26-next", args=[gang.pk]))
        assert onward(request, gang, replay, url(gang)) == first_url
        assert_reconciled(gang)


@pytest.mark.django_db(transaction=True)
def test_simultaneous_retries_commit_one_hire(gang, owner, profile):
    ready = Barrier(2)
    data = submission(profile)

    def save(_):
        close_old_connections()
        try:
            current = Gang.objects.get(pk=gang.pk)
            actor = User.objects.get(pk=owner.pk)
            ready.wait(timeout=10)
            result = hire_workflow.change(current, actor, data)
            return result.saved, result.applied
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(save, range(2)))
    assert sorted(results) == [(True, False), (True, True)]
    assert HireReceipt.objects.filter(gang=gang).count() == 1
    assert Miniature.objects.filter(membership__gang=gang).count() == 1
    gang.refresh_from_db()
    assert gang.credits == 40
    assert_reconciled(gang)
