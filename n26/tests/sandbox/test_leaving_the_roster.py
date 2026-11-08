"""Verify fighter deletion and refunds, including the option to stash paid equipment first.
Deletion retains spending; refunds return recorded payments. Stashed equipment keeps its
recorded rating, while free equipment is removed with the fighter.
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

    return User.objects.create_user("player")


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
    """Fighter with a paid gun and a free knife to distinguish salvage and refund
    eligibility.
    """
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
    """Represent dialog state in the URL and display the refund calculation."""

    def test_the_edit_menu_offers_both_ways_out(self, client, owner, gang, armed):
        client.force_login(owner)
        body = client.get(reverse("n26-edit-fighter", args=[armed.pk])).content.decode()
        gang_url = reverse("n26-gang", args=[gang.pk])
        assert f'href="{gang_url}?refund={armed.pk}"' in body
        assert f'href="{gang_url}?delete={armed.pk}"' in body

    def test_the_card_links_to_edit_without_leaving_controls(
        self, client, owner, gang, armed
    ):
        client.force_login(owner)
        body = client.get(reverse("n26-gang", args=[gang.pk])).content.decode()
        assert reverse("n26-edit-fighter", args=[armed.pk]) in body
        assert f"?refund={armed.pk}" not in body
        assert f"?delete={armed.pk}" not in body

    def test_the_refund_dialog_quotes_paid_not_worth(self, client, owner, gang, armed):
        """The full refund includes 55 credits for hiring and 30 for the gun; stashing the
        gun returns only the hire payment.
        """
        client.force_login(owner)
        url = reverse("n26-gang", args=[gang.pk])
        body = client.get(f"{url}?refund={armed.pk}").content.decode()
        assert f"Refund {HIRE_PRICE + GUN_PRICE}¢" in body
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
        """Keep the paid gun at its recorded rating and remove the free knife with the
        fighter.
        """
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
        client.force_login(User.objects.create_user("someone-else"))
        assert client.post(delete_url(armed)).status_code == 404
        assert len(roster(gang)) == 1


class TestRefunding:
    def test_what_was_paid_comes_back_every_credit_and_no_more(
        self, client, owner, gang, armed
    ):
        """Return the recorded hire and gun payments; the free knife contributes no refund."""
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
        # Keep the gun's payment spent and transfer its rating to the stash; refund only
        # the hire payment.
        assert gang.credits == 1000 - GUN_PRICE
        assert gang.stash_rating == GUN_PRICE
        assert gang.rating == 0
        assert_reconciled(gang)


class TestAGangWithNoBudget:
    """Unlimited-credit gangs expose deletion without refunds. A direct refund request must
    follow deletion behaviour without returning credits.
    """

    @pytest.fixture
    def unbudgeted(self, gang):
        gang.starting_credits = None
        gang.save(update_fields=["starting_credits"])
        return gang

    def test_the_edit_menu_offers_no_refund(self, client, owner, unbudgeted, armed):
        client.force_login(owner)
        body = client.get(reverse("n26-edit-fighter", args=[armed.pk])).content.decode()
        assert f"?delete={armed.pk}" in body
        assert f"?refund={armed.pk}" not in body

    def test_a_refund_address_asks_the_delete_question(
        self, client, owner, unbudgeted, armed
    ):
        """Show deletion choices when the gang has no finite credit budget."""
        client.force_login(owner)
        url = reverse("n26-gang", args=[unbudgeted.pk])
        body = client.get(f"{url}?refund={armed.pk}").content.decode()
        assert "Delete everything" in body
        assert "Stash their kit, then delete" in body
        assert "Refund everything" not in body

    def test_a_refund_post_deletes_and_returns_nothing(
        self, client, owner, unbudgeted, armed
    ):
        client.force_login(owner)
        credits_before = unbudgeted.credits
        client.post(refund_url(armed))
        unbudgeted.refresh_from_db()
        assert roster(unbudgeted) == []
        assert unbudgeted.credits == credits_before
        assert unbudgeted.rating == 0
        assert_reconciled(unbudgeted)


class TestTheSameRefundArrivingTwice:
    """Repeated refund, sale or removal requests can hold independently loaded stale
    assignments. Recheck under the gang lock so only the first request changes money or
    history.
    """

    @pytest.fixture
    def loaded_twice(self, vex):
        from n26.core.models import Assignment

        gun = give_weapon(
            vex, create_weapon("Autogun", price=GUN_PRICE), paid=GUN_PRICE
        )
        as_loaded = Assignment.objects.select_related("ledger_entry")
        return as_loaded.get(pk=gun.pk), as_loaded.get(pk=gun.pk)

    def test_a_second_refund_of_the_same_line_returns_nothing(self, gang, loaded_twice):
        from n26.core.models import LedgerEvent
        from n26.tests.sandbox.actions import refund

        first, second = loaded_twice
        refund(first)
        assert refund(second) is None

        gang.refresh_from_db()
        assert_reconciled(gang)
        assert gang.credits == 1000 - HIRE_PRICE
        assert first.ledger_events.filter(kind=LedgerEvent.Kind.REFUNDED).count() == 1

    def test_a_second_sale_of_the_same_line_pays_nothing(self, gang, loaded_twice):
        from n26.core.models import LedgerEvent
        from n26.tests.sandbox.actions import sell

        first, second = loaded_twice
        proceeds = sell(first)
        assert sell(second) is None

        gang.refresh_from_db()
        assert_reconciled(gang)
        assert gang.credits == 1000 - HIRE_PRICE - GUN_PRICE + proceeds
        assert first.ledger_events.filter(kind=LedgerEvent.Kind.SOLD).count() == 1

    def test_a_second_removal_of_the_same_line_writes_nothing(self, gang, loaded_twice):
        from n26.core.models import LedgerEvent
        from n26.tests.sandbox.actions import remove

        first, second = loaded_twice
        remove(first)
        assert remove(second) is None

        gang.refresh_from_db()
        assert_reconciled(gang)
        assert first.ledger_events.filter(kind=LedgerEvent.Kind.REMOVED).count() == 1
