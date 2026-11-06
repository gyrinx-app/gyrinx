"""Manage credits: adding credits to a gang, or removing them, by hand."""

import json
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.contrib.messages import get_messages
from django.urls import reverse

from n26.core import history
from n26.core.models import Gang, LedgerEvent
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.tests.sandbox.actions import found_campaign, found_gang, join_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def table(default_pack, gang_type, campaign_type, counter_tracking):
    owner = User.objects.create_user("credits-owner")
    arbitrator = User.objects.create_user("credits-arbitrator")
    campaign = found_campaign("Dust Falls", campaign_type, owner=arbitrator)
    gang = found_gang("Ashen Choir", gang_type, owner=owner, budget=100)
    join_campaign(gang, campaign)
    return SimpleNamespace(
        owner=owner, arbitrator=arbitrator, campaign=campaign, gang=gang
    )


def url(gang):
    return reverse("n26-gang-credits", args=[gang.pk])


def submit(client, target, data):
    return client.post(target, {"request_key": str(uuid4()), **data})


def props(response):
    page = BeautifulSoup(response.content, "html.parser")
    host = page.select_one('[data-react-name="manage-credits"]')
    return json.loads(page.find(id=host["data-react-props"]).string)


def fresh(gang):
    return Gang.objects.get(pk=gang.pk)


def told(gang, viewer):
    return [
        "".join(span.text for span in act.spans)
        for act in history.build(gang, viewer=viewer)
        if act.category == "credits"
    ]


@pytest.mark.parametrize("actor", ["owner", "arbitrator"])
def test_credit_changes_keep_a_safe_campaign_table_return_url(client, table, actor):
    client.force_login(getattr(table, actor))
    back = (
        reverse("n26-campaign", args=[table.campaign.pk]) + "?sort=-wealth&group=#gangs"
    )
    response = client.get(url(table.gang), {"back": back})
    assert response.context["back"] == back
    assert props(response)["back"] == back
    bad = submit(
        client, url(table.gang), {"direction": "add", "amount": "words", "back": back}
    )
    assert bad.status_code == 200 and bad.context["back"] == back
    saved = submit(
        client, url(table.gang), {"direction": "add", "amount": "5", "back": back}
    )
    assert saved.status_code == 302 and saved.url == back
    outside = client.get(url(table.gang), {"back": "https://example.com/"})
    assert outside.context["back"] != "https://example.com/"


class TestTheOwner:
    """The gang's owner adds and removes credits, and the gang never
    goes below zero."""

    def test_adding_credits_raises_the_balance_and_says_so(self, client, table):
        client.force_login(table.owner)
        response = submit(
            client,
            url(table.gang),
            {"direction": "add", "amount": "40", "note": "Scenario reward"},
        )

        assert response.status_code == 302
        assert response.url == reverse("n26-gang", args=[table.gang.pk])
        assert fresh(table.gang).credits == 140
        assert [str(m) for m in get_messages(response.wsgi_request)] == [
            "Added 40¢ to Ashen Choir."
        ]
        assert_reconciled(fresh(table.gang))

    def test_removing_credits_lowers_the_balance(self, client, table):
        client.force_login(table.owner)
        submit(client, url(table.gang), {"direction": "remove", "amount": "30"})

        assert fresh(table.gang).credits == 70
        assert_reconciled(fresh(table.gang))

    def test_the_history_says_added_and_removed_with_the_note(self, client, table):
        client.force_login(table.owner)
        submit(
            client,
            url(table.gang),
            {"direction": "add", "amount": "40", "note": "Scenario reward"},
        )
        submit(client, url(table.gang), {"direction": "remove", "amount": "25"})

        assert told(table.gang, table.owner) == [
            "added 40¢ — Scenario reward",
            "removed 25¢",
        ]
        kinds = LedgerEvent.objects.filter(
            gang=table.gang, kind=LedgerEvent.Kind.CREDITS_ADJUSTED
        ).values_list("credits_delta", "campaign", "actor")
        assert sorted(kinds) == sorted(
            [
                (-40, table.campaign.pk, table.owner.pk),
                (25, table.campaign.pk, table.owner.pk),
            ]
        )

    def test_removing_more_than_the_gang_has_is_refused_whole(self, client, table):
        client.force_login(table.owner)
        response = submit(
            client, url(table.gang), {"direction": "remove", "amount": "101"}
        )

        assert response.status_code == 200
        assert response.context["form"].errors["amount"] == [
            "You cannot remove more than Ashen Choir has (100¢)."
        ]
        assert fresh(table.gang).credits == 100
        assert not LedgerEvent.objects.filter(
            kind=LedgerEvent.Kind.CREDITS_ADJUSTED
        ).exists()

    def test_removing_everything_leaves_zero(self, client, table):
        client.force_login(table.owner)
        submit(client, url(table.gang), {"direction": "remove", "amount": "100"})

        assert fresh(table.gang).credits == 0
        assert_reconciled(fresh(table.gang))

    @pytest.mark.parametrize("amount", ["0", "-5", "", "3000000000"])
    def test_an_amount_below_one_is_a_form_error(self, client, table, amount):
        client.force_login(table.owner)
        response = submit(
            client, url(table.gang), {"direction": "add", "amount": amount}
        )

        assert response.status_code == 200
        assert "amount" in response.context["form"].errors
        assert fresh(table.gang).credits == 100

    def test_an_unknown_direction_is_an_error_and_add_stays_selected(
        self, client, table
    ):
        client.force_login(table.owner)
        response = submit(client, url(table.gang), {"direction": "foo", "amount": "5"})

        assert "direction" in response.context["form"].errors
        assert props(response)["values"]["direction"] == "add"
        assert fresh(table.gang).credits == 100

    def test_the_page_shows_the_balance_and_both_choices(self, client, table):
        client.force_login(table.owner)
        response = client.get(url(table.gang))

        assert response.status_code == 200
        page = BeautifulSoup(response.content, "html.parser")
        data = props(response)
        assert data["gangName"] == "Ashen Choir" and data["balance"] == 100
        assert [d["value"] for d in data["directions"]] == ["add", "remove"]
        assert data["values"]["direction"] == "add"
        assert (
            data["historyHref"]
            == reverse("n26-gang-history", args=[table.gang.pk]) + "?kind=credits"
        )
        assert page.select_one('[data-react-name="manage-credits"] [x-data]') is None

    def test_the_gang_page_offers_manage_credits(self, client, table):
        client.force_login(table.owner)
        response = client.get(reverse("n26-gang", args=[table.gang.pk]))

        page = BeautifulSoup(response.content, "html.parser")
        links = page.select(f'a[href="{url(table.gang)}"]')
        texts = {link.get_text(strip=True) for link in links}
        # The button, and the Credits figure in the wealth strip.
        assert "Manage credits" in texts
        assert "100¢" in texts


class TestUnlimitedCredits:
    """A gang with unlimited credits has no figure to change, so it gets
    no page and no way in."""

    @pytest.fixture
    def gang(self, default_pack, gang_type, owner):
        return found_gang("No Ceiling", gang_type, owner=owner)

    def test_the_page_is_not_there(self, client, owner, gang):
        assert gang.credits_unlimited
        client.force_login(owner)

        assert client.get(url(gang)).status_code == 404
        assert (
            submit(client, url(gang), {"direction": "add", "amount": "5"}).status_code
            == 404
        )

    def test_the_gang_page_offers_nothing(self, client, owner, gang):
        client.force_login(owner)
        response = client.get(reverse("n26-gang", args=[gang.pk]))

        assert url(gang).encode() not in response.content
        assert b"Manage credits" not in response.content


class TestTheArbitrator:
    """The arbitrator of the campaign a gang is playing may change its
    credits while the gang is in a campaign still being played."""

    def test_may_add_credits_and_returns_to_the_campaign(self, client, table):
        client.force_login(table.arbitrator)
        response = submit(client, url(table.gang), {"direction": "add", "amount": "10"})

        assert response.status_code == 302
        assert response.url == (
            reverse("n26-campaign", args=[table.campaign.pk]) + "#gangs"
        )
        assert fresh(table.gang).credits == 110
        event = LedgerEvent.objects.get(kind=LedgerEvent.Kind.CREDITS_ADJUSTED)
        assert event.actor == table.arbitrator
        assert_reconciled(fresh(table.gang))

    def test_loses_the_page_once_the_gang_leaves(self, client, table):
        with operation(table.gang, actor=table.owner) as op:
            op.leave_campaign()
        client.force_login(table.arbitrator)

        assert client.get(url(table.gang)).status_code == 404

    def test_loses_the_page_once_the_campaign_is_archived(self, client, table):
        table.campaign.archived = True
        table.campaign.save(update_fields=["archived"])
        client.force_login(table.arbitrator)

        assert client.get(url(table.gang)).status_code == 404
        assert (
            submit(
                client, url(table.gang), {"direction": "add", "amount": "5"}
            ).status_code
            == 404
        )
        assert fresh(table.gang).credits == 100

    def test_is_refused_if_the_gang_leaves_while_the_change_waits(
        self, client, table, monkeypatch
    ):
        """The page opened while the gang was in the campaign; by the time
        the change holds the gang's lock, it has left."""
        from n26.core import credits

        def leave_first(gang, user):
            with operation(table.gang, actor=table.owner) as op:
                op.leave_campaign()
            return real(gang, user)

        real = credits.still_allowed
        monkeypatch.setattr(credits, "still_allowed", leave_first)
        client.force_login(table.arbitrator)
        response = submit(client, url(table.gang), {"direction": "add", "amount": "5"})

        assert response.status_code == 200
        assert response.context["form"].non_field_errors() == [
            "You can no longer change this gang's credits."
        ]
        assert not LedgerEvent.objects.filter(
            kind=LedgerEvent.Kind.CREDITS_ADJUSTED
        ).exists()
        assert fresh(table.gang).credits == 100

    def test_the_campaign_table_links_each_gangs_credits(self, client, table):
        client.force_login(table.arbitrator)
        response = client.get(reverse("n26-campaign", args=[table.campaign.pk]))
        from n26.tests.fixtures import island_props

        props = island_props(response.content, "campaign-gangs")
        line = next(line for line in props["gangs"] if line["id"] == str(table.gang.pk))
        assert line["creditsHref"] == url(table.gang)
        assert line["credits"] == 100


class TestEveryoneElse:
    """Nobody else reaches the page or sees a way in."""

    def test_a_stranger_gets_404(self, client, table):
        client.force_login(User.objects.create_user("stranger"))

        assert client.get(url(table.gang)).status_code == 404
        assert (
            submit(
                client, url(table.gang), {"direction": "add", "amount": "5"}
            ).status_code
            == 404
        )
        assert fresh(table.gang).credits == 100

    def test_signed_out_is_sent_to_sign_in(self, client, table):
        response = client.get(url(table.gang))

        assert response.status_code == 302
        assert "login" in response.url

    def test_a_stranger_sees_no_link_on_the_campaign_table(self, client, table):
        client.force_login(User.objects.create_user("stranger"))
        response = client.get(reverse("n26-campaign", args=[table.campaign.pk]))

        assert url(table.gang).encode() not in response.content


@pytest.mark.parametrize("transport", ["html", "json"])
@pytest.mark.parametrize("actor", ["owner", "arbitrator"])
@pytest.mark.parametrize(
    "direction,amount,expected",
    [
        ("add", "40", 140),
        ("remove", "30", 70),
        ("remove", "100", 0),
        ("remove", "101", 100),
        ("add", "0", 100),
        ("bad", "5", 100),
    ],
)
def test_transports_apply_the_same_credit_rules(
    client, table, transport, actor, direction, amount, expected
):
    client.force_login(getattr(table, actor))
    target = (
        url(table.gang)
        if transport == "html"
        else reverse("n26-gang-credits-command", args=[table.gang.pk])
    )
    response = submit(
        client,
        target,
        {"direction": direction, "amount": amount, "note": "Scenario reward"},
    )
    saved = expected != 100
    assert (
        response.status_code == (302 if saved else 200)
        if transport == "html"
        else response.status_code == (200 if saved else 422)
    )
    assert fresh(table.gang).credits == expected
    events = LedgerEvent.objects.filter(
        gang=table.gang, kind=LedgerEvent.Kind.CREDITS_ADJUSTED
    )
    assert events.count() == int(saved)
    if saved:
        event = events.get()
        assert event.actor == getattr(table, actor)
        assert event.campaign == table.campaign
        assert event.credits_delta == 100 - expected
        assert event.note == "Scenario reward"
        default = (
            reverse("n26-gang", args=[table.gang.pk])
            if actor == "owner"
            else reverse("n26-campaign", args=[table.campaign.pk]) + "#gangs"
        )
        assert (
            response.url if transport == "html" else response.json()["nextUrl"]
        ) == default
    else:
        errors = (
            response.context["form"].errors
            if transport == "html"
            else response.json()["errors"]
        )
        assert "direction" in errors if direction == "bad" else "amount" in errors
    assert_reconciled(fresh(table.gang))


@pytest.mark.parametrize("transport", ["html", "json"])
def test_replaying_a_save_changes_credits_and_records_analytics_once(
    client, table, monkeypatch, transport
):
    from unittest.mock import Mock

    from n26 import analytics

    record = Mock()
    monkeypatch.setattr(analytics, "record", record)
    client.force_login(table.owner)
    target = (
        url(table.gang)
        if transport == "html"
        else reverse("n26-gang-credits-command", args=[table.gang.pk])
    )
    data = {
        "direction": "remove",
        "amount": "70",
        "note": " Supplies ",
        "request_key": str(uuid4()),
    }
    first = client.post(target, data)
    # A replay must succeed even when repeating the removal would now overspend.
    second = client.post(target, data)
    assert (
        first.status_code == second.status_code == (302 if transport == "html" else 200)
    )
    assert fresh(table.gang).credits == 30
    assert (
        LedgerEvent.objects.filter(
            gang=table.gang, request_key=data["request_key"]
        ).count()
        == 1
    )
    assert record.call_count == 1
    different = client.post(target, {**data, "amount": "20"})
    assert different.status_code == (200 if transport == "html" else 409)
    assert fresh(table.gang).credits == 30
    assert_reconciled(fresh(table.gang))


def test_json_command_requires_authentication_csrf_and_a_request_key(client, table):
    from django.test import Client

    target = reverse("n26-gang-credits-command", args=[table.gang.pk])
    assert client.post(target, {}).status_code == 401
    client.force_login(table.owner)
    response = client.post(target, {"direction": "add", "amount": "10"})
    assert response.status_code == 422 and "request_key" in response.json()["errors"]
    assert client.get(target).status_code == 405
    protected = Client(enforce_csrf_checks=True)
    protected.force_login(table.owner)
    assert (
        protected.post(
            target,
            {"direction": "add", "amount": "10", "request_key": str(uuid4())},
            HTTP_ACCEPT="application/json",
        ).status_code
        == 403
    )
    assert fresh(table.gang).credits == 100


def test_losing_a_response_body_does_not_duplicate_success_feedback(client, table):
    client.force_login(table.owner)
    target = reverse("n26-gang-credits-command", args=[table.gang.pk])
    data = {"direction": "add", "amount": "10", "request_key": str(uuid4())}
    client.post(target, data)
    retry = client.post(target, data)
    assert [str(message) for message in get_messages(retry.wsgi_request)] == [
        "Added 10¢ to Ashen Choir."
    ]
    assert fresh(table.gang).credits == 110
    assert_reconciled(fresh(table.gang))


@pytest.mark.django_db(transaction=True)
def test_concurrent_duplicate_commands_apply_one_adjustment(table):
    from concurrent.futures import ThreadPoolExecutor
    from threading import Barrier

    from django.db import close_old_connections, connections

    from n26.core import credits

    ready = Barrier(2)
    data = {
        "direction": "remove",
        "amount": "70",
        "note": "Supplies",
        "request_key": str(uuid4()),
    }

    def save():
        close_old_connections()
        try:
            gang = Gang.objects.get(pk=table.gang.pk)
            user = User.objects.get(pk=table.owner.pk)
            ready.wait(timeout=10)
            result = credits.change(gang, user, data)
            return result.saved, result.applied
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: save(), range(2)))
    assert sorted(results) == [(True, False), (True, True)]
    assert (
        LedgerEvent.objects.filter(
            gang=table.gang, request_key=data["request_key"]
        ).count()
        == 1
    )
    assert fresh(table.gang).credits == 30
    assert_reconciled(fresh(table.gang))


@pytest.mark.parametrize("change", [{"note": "Different"}, {"actor": "arbitrator"}])
def test_a_request_key_cannot_be_reused_for_a_different_note_or_actor(
    client, table, change
):
    target = reverse("n26-gang-credits-command", args=[table.gang.pk])
    data = {
        "direction": "add",
        "amount": "10",
        "note": "Supplies",
        "request_key": str(uuid4()),
    }
    client.force_login(table.owner)
    assert client.post(target, data).status_code == 200
    if "actor" in change:
        client.force_login(getattr(table, change["actor"]))
    else:
        data.update(change)
    assert client.post(target, data).status_code == 409
    assert fresh(table.gang).credits == 110


def test_a_rejected_adjustment_does_not_use_the_request_key(client, table):
    client.force_login(table.owner)
    target = reverse("n26-gang-credits-command", args=[table.gang.pk])
    data = {"direction": "remove", "amount": "101", "request_key": str(uuid4())}
    assert client.post(target, data).status_code == 422
    assert not LedgerEvent.objects.filter(request_key=data["request_key"]).exists()
    assert client.post(target, {**data, "amount": "30"}).status_code == 200
    assert fresh(table.gang).credits == 70
    assert_reconciled(fresh(table.gang))


@pytest.mark.parametrize(
    "back",
    ["/n26/gangs/?sort=-wealth&group=#gangs", "https://example.com/", "//example.com/"],
)
def test_json_save_validates_its_return_url(client, table, back):
    client.force_login(table.owner)
    target = reverse("n26-gang-credits-command", args=[table.gang.pk])
    response = submit(
        client, target, {"direction": "add", "amount": "10", "back": back}
    )
    assert response.json()["nextUrl"] == (
        back if back.startswith("/n26/") else reverse("n26-gang", args=[table.gang.pk])
    )


@pytest.mark.parametrize(
    "state", ["stranger", "archived", "unlimited", "campaign_left", "campaign_archived"]
)
def test_json_rejects_the_same_unavailable_gangs(client, table, state):
    actor = table.owner
    if state == "stranger":
        actor = User.objects.create_user("credits-stranger")
    elif state == "archived":
        table.gang.archived = True
        table.gang.save(update_fields=["archived"])
    elif state == "unlimited":
        with operation(table.gang, actor=actor) as op:
            op.set_budget(None)
    elif state == "campaign_left":
        actor = table.arbitrator
        with operation(table.gang, actor=table.owner) as op:
            op.leave_campaign()
    else:
        actor = table.arbitrator
        table.campaign.archived = True
        table.campaign.save(update_fields=["archived"])
    client.force_login(actor)
    target = reverse("n26-gang-credits-command", args=[table.gang.pk])
    assert (
        submit(client, target, {"direction": "add", "amount": "10"}).status_code == 404
    )
    assert not LedgerEvent.objects.filter(
        gang=table.gang, kind=LedgerEvent.Kind.CREDITS_ADJUSTED
    ).exists()


def test_manage_credits_queries_do_not_grow_with_ledger_history(client, table):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    client.force_login(table.owner)
    client.get(url(table.gang))
    with CaptureQueriesContext(connection) as small:
        assert client.get(url(table.gang)).status_code == 200
    for _ in range(12):
        with operation(table.gang, actor=table.owner) as op:
            op.adjust_credits(1)
    with CaptureQueriesContext(connection) as large:
        assert client.get(url(table.gang)).status_code == 200
    assert len(large) == len(small)


def test_a_committed_command_can_be_recovered_after_csrf_rotation(table):
    from django.test import Client

    client = Client(enforce_csrf_checks=True)
    client.force_login(table.owner)
    original = props(client.get(url(table.gang)))
    target = original["commandHref"]
    data = {
        "direction": "add",
        "amount": "10",
        "request_key": original["values"]["request_key"],
        "csrfmiddlewaretoken": original["csrfToken"],
    }
    assert client.post(target, data, HTTP_ACCEPT="application/json").status_code == 200
    client.logout()
    client.force_login(table.owner)
    fresh_page = props(client.get(url(table.gang)))
    assert client.post(target, data, HTTP_ACCEPT="application/json").status_code == 403
    retry = client.post(
        target,
        {**data, "csrfmiddlewaretoken": fresh_page["csrfToken"]},
        HTTP_ACCEPT="application/json",
    )
    assert retry.status_code == 200
    assert fresh(table.gang).credits == 110
    assert (
        LedgerEvent.objects.filter(
            gang=table.gang, request_key=data["request_key"]
        ).count()
        == 1
    )
    assert_reconciled(fresh(table.gang))
