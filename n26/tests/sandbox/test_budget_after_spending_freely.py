"""A budget given to a gang that had none opens from what the gang holds.

A gang founded without a budget buys freely, and every purchase is still an
honest ledger line. Deleting a model never refunds it, so the ledger goes on
counting money spent on models no longer in the gang. When the gang later
takes a budget — its own, or its campaign's — its credits are the budget
less what it is worth now, not the budget less everything it ever spent.

A gang that already had a budget keeps counting its whole spending history:
for it, deleting is not a refund.

Everything here moves money, so every test ends reconciled.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.site.models import Availability, FeatureFlag
from n26.core import history
from n26.core.campaigns import campaign_operation
from n26.core.models import Gang, LedgerEvent
from n26.core.reconcile import assert_reconciled
from n26.flags import CAMPAIGNS
from n26.tests.sandbox.actions import (
    create_weapon,
    found_campaign,
    found_gang,
    give_weapon,
    hire,
)

pytestmark = pytest.mark.django_db

HIRE_PRICE = 100
GUN_PRICE = 30


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def gang(gang_type, owner):
    """Founded without a budget."""
    return found_gang("The Ashen Choir", gang_type, owner=owner)


@pytest.fixture
def vex(gang, make_profile, make_statline, default_pack):
    """A 100¢ fighter carrying a 30¢ gun: 130¢ spent."""
    profile = make_profile("Ganger", price=HIRE_PRICE)
    make_statline(profile)
    vex = hire(gang, profile, "Vex", paid=HIRE_PRICE)
    give_weapon(vex, create_weapon("Autogun", price=GUN_PRICE), paid=GUN_PRICE)
    return vex


@pytest.fixture
def deleted(client, owner, gang, vex):
    """Vex deleted, kit and all, while the gang had no budget."""
    client.force_login(owner)
    response = client.post(reverse("n26-delete-fighter", args=[vex.pk]))
    assert response.status_code == 302
    gang.refresh_from_db()
    assert gang.wealth == 0
    return gang


def set_budget(client, gang, budget):
    return client.post(
        reverse("n26-edit-gang", args=[gang.pk]),
        {"name": gang.name, "starting_credits": str(budget)},
    )


def told(gang):
    acts = history.build(Gang.objects.get(pk=gang.pk))
    return {"".join(s.text for s in act.spans): act for act in acts}


class TestDeletedModelsStopCounting:
    def test_a_gang_worth_nothing_can_take_a_zero_budget(self, client, deleted):
        response = set_budget(client, deleted, 0)
        assert response.status_code == 302
        deleted.refresh_from_db()
        assert deleted.starting_credits == 0
        assert deleted.credits == 0
        assert deleted.wealth == 0
        assert_reconciled(deleted)

    def test_a_gang_worth_nothing_keeps_its_whole_budget(self, client, deleted):
        set_budget(client, deleted, 2000)
        deleted.refresh_from_db()
        assert deleted.rating == 0
        assert deleted.credits == 2000
        assert_reconciled(deleted)

    def test_what_was_spent_stays_in_the_ledger(self, client, deleted):
        """The purchases are still true statements of what was paid."""
        spent = list(
            LedgerEvent.objects.filter(
                gang=deleted, kind=LedgerEvent.Kind.PURCHASED
            ).values_list("credits_delta", flat=True)
        )
        set_budget(client, deleted, 0)
        assert sorted(
            LedgerEvent.objects.filter(
                gang=deleted, kind=LedgerEvent.Kind.PURCHASED
            ).values_list("credits_delta", flat=True)
        ) == sorted(spent)
        assert sum(spent) == HIRE_PRICE + GUN_PRICE

    def test_spending_after_the_budget_counts_against_it(
        self, client, deleted, make_profile, make_statline
    ):
        set_budget(client, deleted, 200)
        profile = make_profile("Juve", price=60)
        make_statline(profile)
        hire(deleted, profile, "Rue", paid=60)
        deleted.refresh_from_db()
        assert deleted.credits == 140
        assert deleted.wealth == 200
        assert_reconciled(deleted)


class TestWhatTheGangStillHoldsCounts:
    def test_a_kept_model_and_its_kit_come_out_of_the_budget(
        self, client, owner, gang, vex
    ):
        client.force_login(owner)
        set_budget(client, gang, 2000)
        gang.refresh_from_db()
        assert gang.credits == 2000 - HIRE_PRICE - GUN_PRICE
        assert gang.wealth == 2000
        assert_reconciled(gang)

    def test_stashed_kit_comes_out_of_the_budget(self, client, owner, gang, vex):
        client.force_login(owner)
        client.post(reverse("n26-delete-fighter", args=[vex.pk]), {"kit": "stash"})
        set_budget(client, gang, 2000)
        gang.refresh_from_db()
        assert gang.rating == 0
        assert gang.stash_rating == GUN_PRICE
        assert gang.credits == 2000 - GUN_PRICE
        assert_reconciled(gang)

    def test_a_budget_below_what_the_gang_holds_is_refused(
        self, client, owner, gang, vex
    ):
        client.force_login(owner)
        client.post(reverse("n26-delete-fighter", args=[vex.pk]), {"kit": "stash"})
        response = set_budget(client, gang, GUN_PRICE - 1)
        assert response.status_code == 200
        assert f"worth {GUN_PRICE}¢" in response.content.decode()
        gang.refresh_from_db()
        assert gang.starting_credits is None
        assert_reconciled(gang)


class TestTheCampaignBudget:
    @pytest.fixture
    def campaign(self, campaign_type, owner):
        FeatureFlag.objects.create(
            slug=CAMPAIGNS, name="Campaigns", availability=Availability.EVERYONE
        )
        return found_campaign("Dust Falls", campaign_type, owner=owner, budget=1000)

    def test_adopting_it_opens_from_what_the_gang_holds(
        self, client, owner, deleted, campaign
    ):
        with campaign_operation(campaign, actor=owner) as op:
            op.add_gang(deleted)
        response = client.post(reverse("n26-use-campaign-budget", args=[deleted.pk]))
        assert response.url == reverse("n26-gang", args=[deleted.pk])
        deleted.refresh_from_db()
        assert deleted.starting_credits == 1000
        assert deleted.credits == 1000
        assert_reconciled(deleted)


class TestTheRecord:
    def test_the_history_states_the_budget_without_a_figure(self, client, deleted):
        """The correction is bookkeeping, not money the gang received."""
        set_budget(client, deleted, 0)
        act = told(deleted)["set the budget to 0¢"]
        assert act.note == "unlimited → 0¢"
        assert act.credits == 0

    def test_the_same_budget_twice_is_one_change(self, client, deleted):
        set_budget(client, deleted, 500)
        set_budget(client, deleted, 500)
        deleted.refresh_from_db()
        assert deleted.credits == 500
        assert (
            LedgerEvent.objects.filter(
                gang=deleted, kind=LedgerEvent.Kind.BUDGET_SET
            ).count()
            == 1
        )
        assert_reconciled(deleted)

    def test_lifting_and_setting_again_opens_from_what_is_held_then(
        self, client, deleted, make_profile, make_statline
    ):
        set_budget(client, deleted, 200)
        profile = make_profile("Juve", price=60)
        make_statline(profile)
        rue = hire(deleted, profile, "Rue", paid=60)
        set_budget(client, deleted, "")
        client.post(reverse("n26-delete-fighter", args=[rue.pk]))
        set_budget(client, deleted, 200)
        deleted.refresh_from_db()
        assert deleted.rating == 0
        assert deleted.credits == 200
        assert_reconciled(deleted)


class TestAGangThatAlreadyHadABudget:
    def test_deleting_is_still_not_a_refund(
        self, client, owner, gang_type, make_profile, make_statline
    ):
        """Changing one budget for another keeps the whole spending
        history: what was spent on a deleted model stays spent."""
        gang = found_gang("The Bad Girls", gang_type, owner=owner, budget=1000)
        profile = make_profile("Ganger", price=HIRE_PRICE)
        make_statline(profile)
        vex = hire(gang, profile, "Vex", paid=HIRE_PRICE)
        client.force_login(owner)
        client.post(reverse("n26-delete-fighter", args=[vex.pk]))
        set_budget(client, gang, 1100)
        gang.refresh_from_db()
        assert gang.wealth == 1000
        assert gang.credits == 1100 - HIRE_PRICE
        assert_reconciled(gang)
