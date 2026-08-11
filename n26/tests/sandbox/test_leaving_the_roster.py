"""A fighter leaving the roster: deleted, or refunded, kit stashed or not.

The gang sheet's card offers two ways out — Delete keeps the money spent,
Refund returns what was actually *paid* — and each dialog offers the same
alternative disposal: the kit money was paid for moves to the stash first,
where every line keeps its pinned rating because a move never re-prices.
Free and granted things return nothing and never move: a built-in knife in
the stash is clutter the next hire re-arms without.

Everything here spends or returns money, so every test ends reconciled.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.models import Miniature
from n26.core.reconcile import assert_reconciled
from n26.core.render import render_gang
from n26.tests.sandbox.actions import (
    create_weapon,
    found_gang,
    give_weapon,
    hire,
)

pytestmark = pytest.mark.django_db

HIRE_PRICE = 55
GUN_PRICE = 30


@pytest.fixture
def owner(db):
    """Staff, because /n26/ is fenced to staff and testers."""
    return User.objects.create_user("player", is_staff=True)


@pytest.fixture
def gang(gang_type, owner):
    return found_gang("The Ashen Choir", gang_type, owner=owner, budget=1000)


@pytest.fixture
def vex(gang, make_profile, make_statline):
    profile = make_profile("Ganger", price=HIRE_PRICE)
    make_statline(profile)
    return hire(gang, profile, "Vex", paid=HIRE_PRICE)


@pytest.fixture
def armed(vex, default_pack):
    """Vex with a bought gun and a granted knife: one line money was paid
    for, one it was not — the pair every disposal rule splits."""
    give_weapon(vex, create_weapon("Autogun", price=GUN_PRICE), paid=GUN_PRICE)
    give_weapon(vex, create_weapon("Knife", price=0), paid=0)
    return vex


def delete_url(miniature):
    return reverse("n26-delete-fighter", args=[miniature.pk])


def refund_url(miniature):
    return reverse("n26-refund-fighter", args=[miniature.pk])


def roster(gang):
    return list(
        Miniature.objects.filter(membership__gang=gang, membership__archived=False)
    )


class TestTheDialogs:
    """Open is a server state, and the dialog quotes its own arithmetic."""

    def test_the_card_offers_both_ways_out(self, client, owner, gang, armed):
        client.force_login(owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert f"?refund={armed.pk}" in body
        assert f"?delete={armed.pk}" in body

    def test_the_refund_dialog_quotes_paid_not_worth(self, client, owner, gang, armed):
        """85¢ paid across fighter and gun; the free knife adds nothing.
        The stash alternative quotes the fighter alone."""
        client.force_login(owner)
        url = reverse("n26-gang", args=[gang.pk])
        body = client.get(f"{url}?refund={armed.pk}").content.decode()
        assert f"Refund everything — {HIRE_PRICE + GUN_PRICE}¢" in body
        assert f"Stash kit, refund {HIRE_PRICE}¢" in body

    def test_a_fighter_with_nothing_bought_gets_no_stash_button(
        self, client, owner, gang, vex
    ):
        client.force_login(owner)
        url = reverse("n26-gang", args=[gang.pk])
        body = client.get(f"{url}?delete={vex.pk}").content.decode()
        assert "Delete everything" in body
        assert "Stash their kit" not in body

    def test_get_on_the_act_reopens_the_question(self, client, owner, gang, vex):
        client.force_login(owner)
        response = client.get(delete_url(vex))
        assert response.status_code == 302
        assert f"?delete={vex.pk}" in response.url


class TestDeleting:
    def test_everything_goes_and_the_money_stays_spent(
        self, client, owner, gang, armed
    ):
        client.force_login(owner)
        credits_before = gang.credits
        response = client.post(delete_url(armed))
        assert response.status_code == 302
        gang.refresh_from_db()
        assert roster(gang) == []
        assert gang.credits == credits_before
        assert gang.rating == 0
        assert render_gang(gang).stash == []
        assert_reconciled(gang)

    def test_stashing_the_kit_keeps_only_what_was_bought(
        self, client, owner, gang, armed
    ):
        """The gun moves at its pinned rating; the free knife leaves with
        Vex rather than becoming clutter the next hire re-arms without."""
        client.force_login(owner)
        client.post(delete_url(armed), {"kit": "stash"})
        gang.refresh_from_db()
        assert roster(gang) == []
        sheet = render_gang(gang)
        assert [(line.name, line.rating) for line in sheet.stash] == [
            ("Autogun", GUN_PRICE)
        ]
        assert gang.rating == 0
        assert gang.stash_rating == GUN_PRICE
        assert_reconciled(gang)

    def test_a_stranger_gets_a_404(self, client, gang, armed):
        client.force_login(User.objects.create_user("someone-else", is_staff=True))
        assert client.post(delete_url(armed)).status_code == 404
        assert len(roster(gang)) == 1


class TestRefunding:
    def test_what_was_paid_comes_back_every_credit_and_no_more(
        self, client, owner, gang, armed
    ):
        """55¢ hire and 30¢ gun return; the granted knife was never paid
        for and returns nothing — paid, not worth, is the refunded figure."""
        client.force_login(owner)
        client.post(refund_url(armed))
        gang.refresh_from_db()
        assert roster(gang) == []
        assert gang.credits == 1000
        assert gang.rating == 0
        assert_reconciled(gang)

    def test_stashing_the_kit_refunds_the_fighter_alone(
        self, client, owner, gang, armed
    ):
        client.force_login(owner)
        client.post(refund_url(armed), {"kit": "stash"})
        gang.refresh_from_db()
        assert roster(gang) == []
        # The gun was kept, so its 30¢ stays spent and its rating moves
        # to the stash; only the hire price returns.
        assert gang.credits == 1000 - GUN_PRICE
        assert gang.stash_rating == GUN_PRICE
        assert gang.rating == 0
        assert_reconciled(gang)
