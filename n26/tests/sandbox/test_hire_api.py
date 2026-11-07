"""Hire's HTML and JSON adapters preserve the same acquisition and ledger facts."""

import json
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User
from django.test import Client
from django.urls import reverse

from n26.core.models import HireReceipt, Miniature
from n26.core.reconcile import assert_reconciled
from n26.library.authoring import offer_option, revise
from n26.tests.sandbox.actions import found_gang

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user("hire-api-owner")


@pytest.fixture
def gang(gang_type, owner):
    return found_gang("Ashen Choir", gang_type, owner=owner, budget=100)


@pytest.fixture
def profile(make_profile):
    return make_profile("Ganger", price=60)


def address(gang, name="n26-hire-command"):
    return reverse(name, args=[gang.pk])


def props(response):
    page = BeautifulSoup(response.content, "html.parser")
    host = page.select_one('[data-react-name="hire"]')
    return json.loads(page.find(id=host["data-react-props"]).string)


def data(profile, **values):
    return {
        "profile": str(profile.pk),
        "selection": "[]",
        "name": "Vex",
        "paid": "",
        "rate": "",
        "request_key": str(uuid4()),
        **values,
    }


class TestEquivalentAdapters:
    @pytest.mark.parametrize("transport", ["html", "json"])
    @pytest.mark.parametrize("paid, expected", [("", 85), ("0", 0), ("40", 40)])
    def test_both_transports_keep_the_same_options_payment_rating_and_destination(
        self, client, owner, gang, profile, transport, paid, expected
    ):
        option = offer_option(profile, "Sword", price=25)
        submitted = data(
            profile,
            selection=json.dumps([str(option.pk)]),
            paid=paid,
            list="all",
            section="Fighters",
        )
        client.force_login(owner)
        name = "n26-hire-fighter" if transport == "html" else "n26-hire-command"
        response = client.post(address(gang, name), submitted)
        next_url = (
            response["Location"] if transport == "html" else response.json()["nextUrl"]
        )
        assert (
            next_url == address(gang, "n26-hire-fighter") + "?list=all&section=Fighters"
        )
        (receipt,) = HireReceipt.objects.filter(gang=gang)
        model = Miniature.objects.get(pk=receipt.miniature_key)
        assert receipt.paid == expected
        assert receipt.payload["selection"] == [str(option.pk)]
        assert model.name == "Vex"
        gang.refresh_from_db()
        assert gang.credits == 100 - expected
        assert gang.rating == 85
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_api_retry_returns_the_committed_hire_after_the_catalogue_changes(
        self, client, owner, gang, profile
    ):
        client.force_login(owner)
        submitted = data(profile, rate="paid")
        first = client.post(address(gang), submitted)
        revise(profile, archived=True)
        replay = client.post(address(gang), submitted)
        assert first.status_code == replay.status_code == 200
        assert first.json() == replay.json()
        assert HireReceipt.objects.filter(gang=gang).count() == 1
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_conflicting_retry_carries_current_figures_without_another_write(
        self, client, owner, gang, profile
    ):
        client.force_login(owner)
        submitted = data(profile, rate="paid")
        assert client.post(address(gang), submitted).status_code == 200
        response = client.post(address(gang), {**submitted, "paid": "0"})
        assert response.status_code == 409
        assert response.json()["errors"]["__all__"]
        figures = {
            item["short"]: item["value"] for item in response.json()["figures"]["items"]
        }
        assert figures["Cr"] == "40¢"
        assert figures["R"] == "60¢"
        assert HireReceipt.objects.filter(gang=gang).count() == 1
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_refused_hire_returns_database_totals_after_rollback(
        self, client, owner, gang, profile
    ):
        client.force_login(owner)
        response = client.post(address(gang), data(profile, paid="101", rate="paid"))
        assert response.status_code == 422
        figures = {
            item["short"]: item["value"] for item in response.json()["figures"]["items"]
        }
        assert figures["Cr"] == "100¢"
        assert figures["R"] == "0¢"
        assert response.json()["figures"]["roster"]["count"] == 0
        assert not HireReceipt.objects.filter(gang=gang).exists()
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_missing_option_is_a_recoverable_error_with_current_figures(
        self, client, owner, gang, profile
    ):
        client.force_login(owner)
        response = client.post(address(gang), data(profile, selection='["missing"]'))
        assert response.status_code == 422
        assert response.json()["errors"]["selection"]
        assert response.json()["figures"]["roster"]["count"] == 0


class TestAccessAndProjection:
    def test_anonymous_json_calls_do_not_redirect_to_html(self, client, gang, profile):
        assert client.post(address(gang), data(profile)).status_code == 401
        preview = reverse("n26-hire-preview", args=[gang.pk, profile.pk])
        assert client.get(preview).status_code == 401

    def test_another_owner_cannot_read_preview_or_hire(self, client, gang, profile):
        client.force_login(User.objects.create_user("other-hirer"))
        assert client.post(address(gang), data(profile)).status_code == 404
        assert (
            client.get(
                reverse("n26-hire-preview", args=[gang.pk, profile.pk])
            ).status_code
            == 404
        )

    def test_json_hire_requires_csrf(self, owner, gang, profile):
        client = Client(enforce_csrf_checks=True)
        client.force_login(owner)
        response = client.post(
            address(gang), data(profile), HTTP_ACCEPT="application/json"
        )
        assert response.status_code == 403
        assert response["Content-Type"].startswith("application/json")
        assert not HireReceipt.objects.filter(gang=gang).exists()

    def test_page_contains_one_owner_and_no_alpine_inside_it(
        self, client, owner, gang, profile
    ):
        client.force_login(owner)
        response = client.get(
            address(gang, "n26-hire-fighter"), {"hire": str(profile.pk)}
        )
        delivered = props(response)
        assert delivered["confirmation"]
        assert delivered["values"]["selection"] == "[]"
        assert delivered["values"]["rate"] == "paid"
        assert delivered["commandHref"] == address(gang)
        page = BeautifulSoup(response.content, "html.parser")
        root = page.select_one('[data-react-name="hire"]')
        assert not root.select("[x-data], [hx-get], [data-react-name]")
        assert "no-store" in response["Cache-Control"]

    def test_lazy_preview_uses_stable_option_keys_and_is_privately_cached(
        self, client, owner, gang, profile
    ):
        option = offer_option(profile, "Sword", price=25)
        client.force_login(owner)
        response = client.get(
            reverse("n26-hire-preview", args=[gang.pk, profile.pk]),
            {"selection": json.dumps([str(option.pk)])},
        )
        assert response.status_code == 200
        assert "private" in response["Cache-Control"]
        assert "max-age=300" in response["Cache-Control"]
        assert response.json()["preview"]["name"] == "Ganger"
        assert "library_author_help" not in response.content.decode()


@pytest.mark.parametrize("transport", ["html", "json"])
def test_an_untouched_confirmation_keeps_its_displayed_payment_after_a_price_change(
    client, owner, gang, profile, transport
):
    client.force_login(owner)
    confirmation = props(
        client.get(address(gang, "n26-hire-fighter"), {"hire": str(profile.pk)})
    )
    assert confirmation["values"]["paid"] == confirmation["values"]["quoted"] == "60"
    revise(profile, price=80)
    name = "n26-hire-fighter" if transport == "html" else "n26-hire-command"
    response = client.post(address(gang, name), confirmation["values"])
    assert response.status_code == (302 if transport == "html" else 200)
    receipt = HireReceipt.objects.get(gang=gang)
    assert receipt.paid == 60
    gang.refresh_from_db()
    assert gang.credits == 40
    assert gang.rating == 60
    assert_reconciled(gang)
