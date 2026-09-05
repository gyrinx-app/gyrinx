"""Credits between gangs, and the ransom that needs them.

A ransomed model (Escape table, 2–4) comes back if the owning gang pays
the captor D6 × 10 credits, and dies otherwise, its kit to the owner's
stash (core rules, the Wrap-up and Update Roster). Paying is the first
thing in n26 that moves credits from one gang to another: one ledger
event on each gang, each naming the other, the payer's a spend and the
receiver's credits in. Neither buys anything, so neither has an entry —
the credits recompute reads them straight off the gang.
"""

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core import history
from n26.core.card import build_card, build_modifier_index
from n26.core.effects import compute
from n26.core.models import LedgerEvent, Miniature
from n26.core.operations import NotEnoughCredits, Refusal, operation
from n26.core.reconcile import assert_reconciled
from n26.core.status import Status
from n26.library.models import Picklist, Slot
from n26.library.standard_content import STANDARD_CONTENT
from n26.tests.sandbox.actions import (
    create_profile,
    create_weapon,
    ef_adds,
    found_campaign,
    found_gang,
    give_weapon,
    hire,
    is_profile_type,
    join_campaign,
    modifier,
    targets_every_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner(db):
    return User.objects.create_user("player")


@pytest.fixture
def rival(db):
    return User.objects.create_user("rival")


@pytest.fixture
def tables(default_pack):
    STANDARD_CONTENT["lasting-effect-tables"].create()
    return {
        "injury": Picklist.objects.get(name="Lasting Injury Table"),
        "escape": Picklist.objects.get(name="Escape Table"),
        "injury_slot": Slot.objects.get(name="Lasting Injury"),
    }


@pytest.fixture
def gang(gang_type, owner, fighter_type, tables):
    modifier(
        "Fighters carry Lasting Injury",
        targets_every_model(is_profile_type(fighter_type)),
        ef_adds(tables["injury_slot"]),
        carried_by=gang_type,
    )
    return found_gang("The Scar Crossing", gang_type, owner=owner, budget=1000)


@pytest.fixture
def captors(gang, gang_type, rival, campaign_type):
    """A rival gang at the same table: only a gang in the campaign can be
    paid a ransom, so the two share one."""
    captors = found_gang("The Sump Dogs", gang_type, owner=rival, budget=500)
    campaign = found_campaign("Dust Falls", campaign_type, owner=rival)
    join_campaign(gang, campaign)
    join_campaign(captors, campaign)
    return captors


@pytest.fixture
def krago(gang, gang_type, fighter_type):
    profile = create_profile("Ganger", fighter_type, gang_type, price=50)
    return hire(gang, profile, "Krago", paid=50)


def computed_for(miniature):
    card = build_card(miniature, with_statlines=True)
    index = build_modifier_index([node.assignable for node in card.all_nodes()])
    return compute(card, index)


def choice_of(miniature, label):
    return next(
        (s for s in computed_for(miniature).choices if s.kind_label == label), None
    )


def result_named(table, name):
    return next(m.pickable for m in table.members.all() if m.pickable.name == name)


def add_result(miniature, label, table, name):
    slot = choice_of(miniature, label)
    gang = miniature.membership.gang
    with operation(gang, actor=gang.owner) as op:
        return op.choose(
            slot.anchor.assignment,
            result_named(table, name),
            slot=slot.slot,
            miniature=miniature,
        )


def hold_for_ransom(krago, tables):
    add_result(krago, "Lasting Injuries", tables["injury"], "Captured")
    add_result(krago, "Escape", tables["escape"], "Ransomed")
    return Miniature.objects.get(pk=krago.pk)


def credits(gang):
    gang.refresh_from_db()
    return gang.credits


def sentences(gang):
    return ["".join(span.text for span in act.spans) for act in history.build(gang)]


class TestATransfer:
    def test_credits_leave_one_gang_and_arrive_at_the_other(self, gang, captors):
        before = credits(gang), credits(captors)
        with operation(gang, actor=gang.owner) as op:
            op.transfer(captors, 30, note="ransom for Krago")
        assert (credits(gang), credits(captors)) == (before[0] - 30, before[1] + 30)
        assert_reconciled(gang)
        assert_reconciled(captors)

    def test_each_gang_gets_one_event_naming_the_other(self, gang, captors):
        with operation(gang, actor=gang.owner) as op:
            op.transfer(captors, 30, note="ransom for Krago")
        paid = LedgerEvent.objects.get(gang=gang, kind=LedgerEvent.Kind.TRANSFERRED)
        got = LedgerEvent.objects.get(gang=captors, kind=LedgerEvent.Kind.TRANSFERRED)
        assert (paid.credits_delta, paid.counterpart) == (30, captors)
        assert (got.credits_delta, got.counterpart) == (-30, gang)
        assert paid.assignment_id is None and got.assignment_id is None
        assert paid.note == got.note == "ransom for Krago"

    def test_more_than_the_gang_has_is_refused_whole(self, gang, captors):
        with pytest.raises(NotEnoughCredits):
            with operation(gang, actor=gang.owner) as op:
                op.transfer(captors, 5000)
        assert not LedgerEvent.objects.filter(
            kind=LedgerEvent.Kind.TRANSFERRED
        ).exists()
        assert credits(captors) == 500

    def test_nothing_or_a_gang_paying_itself_is_refused(self, gang):
        with pytest.raises(Refusal):
            with operation(gang, actor=gang.owner) as op:
                op.transfer(gang, 10)
        with pytest.raises(Refusal):
            with operation(gang, actor=gang.owner) as op:
                op.transfer(None, 0)

    def test_a_payment_to_nobody_the_app_knows_still_leaves(self, gang):
        before = credits(gang)
        with operation(gang, actor=gang.owner) as op:
            op.transfer(None, 20, note="ransom for Krago")
        assert credits(gang) == before - 20
        event = LedgerEvent.objects.get(kind=LedgerEvent.Kind.TRANSFERRED)
        assert event.counterpart is None
        assert_reconciled(gang)

    def test_a_gang_with_no_budget_records_the_receipt_and_counts_nothing(
        self, gang, gang_type, rival
    ):
        free = found_gang("The Free", gang_type, owner=rival)
        with operation(gang, actor=gang.owner) as op:
            op.transfer(free, 30)
        assert LedgerEvent.objects.filter(
            gang=free, kind=LedgerEvent.Kind.TRANSFERRED, credits_delta=-30
        ).exists()
        assert credits(free) == 0
        assert_reconciled(free)

    def test_the_history_says_who_paid_whom(self, gang, captors):
        with operation(gang, actor=gang.owner) as op:
            op.transfer(captors, 30, note="ransom for Krago")
        assert "paid 30¢ to The Sump Dogs — ransom for Krago" in sentences(gang)
        assert "received 30¢ from The Scar Crossing — ransom for Krago" in sentences(
            captors
        )
        act = next(
            a
            for a in history.build(gang)
            if "paid 30¢" in "".join(s.text for s in a.spans)
        )
        assert act.credits == -30 and act.category == "money"


class TestTheRansom:
    @pytest.fixture
    def sheet(self, gang):
        return reverse("n26-gang", args=[gang.pk])

    def test_the_dialog_opens_only_for_a_ransomed_model(
        self, client, owner, gang, krago, tables, sheet
    ):
        client.force_login(owner)
        assert (
            "Pay the ransom"
            not in client.get(f"{sheet}?ransom={krago.pk}").content.decode()
        )
        hold_for_ransom(krago, tables)
        page = client.get(f"{sheet}?ransom={krago.pk}").content.decode()
        assert "Pay the ransom for Krago" in page
        assert "A gang not on Gyrinx" in page
        assert "Could not pay" in page

    def test_the_other_gangs_in_the_campaign_are_offered(
        self, client, owner, gang, captors, krago, tables, sheet
    ):
        hold_for_ransom(krago, tables)
        client.force_login(owner)
        page = client.get(f"{sheet}?ransom={krago.pk}").content.decode()
        assert "The Sump Dogs" in page

    def test_paying_brings_the_model_back_in_recovery(
        self, client, owner, gang, captors, krago, tables, sheet
    ):
        hold_for_ransom(krago, tables)
        client.force_login(owner)
        reply = client.post(
            reverse("n26-pay-ransom", args=[krago.pk]),
            {"outcome": "paid", "credits": "30", "to": str(captors.pk)},
            follow=True,
        )
        assert "Ransom paid" in reply.content.decode()
        assert Miniature.objects.get(pk=krago.pk).status == Status.RECOVERY
        assert credits(gang) == 1000 - 50 - 30
        assert credits(captors) == 530
        assert "paid 30¢ to The Sump Dogs — ransom for Krago" in sentences(gang)
        assert_reconciled(gang)
        assert_reconciled(captors)

    def test_a_ransom_the_gang_cannot_pay_leaves_them_held(
        self, client, owner, gang_type, fighter_type, tables, rival
    ):
        poor = found_gang("The Broke", gang_type, owner=rival, budget=60)
        profile = create_profile("Ganger", fighter_type, gang_type, price=50)
        nix = hire(poor, profile, "Nix", paid=50)
        modifier(
            "Fighters carry Lasting Injury",
            targets_every_model(is_profile_type(fighter_type)),
            ef_adds(tables["injury_slot"]),
            carried_by=gang_type,
        )
        hold_for_ransom(nix, tables)
        client.force_login(rival)
        reply = client.post(
            reverse("n26-pay-ransom", args=[nix.pk]),
            {"outcome": "paid", "credits": "60", "to": ""},
            follow=True,
        )
        assert (
            "Not enough credits" in reply.content.decode()
            or "credits" in reply.content.decode()
        )
        assert Miniature.objects.get(pk=nix.pk).status == Status.RANSOMED
        assert credits(poor) == 10

    def test_not_paying_kills_and_stashes_the_kit(
        self, client, owner, gang, krago, tables, sheet
    ):
        gun = create_weapon("Stub gun", price=30)
        give_weapon(krago, gun, paid=30)
        hold_for_ransom(krago, tables)
        client.force_login(owner)
        reply = client.post(
            reverse("n26-pay-ransom", args=[krago.pk]),
            {"outcome": "unpaid"},
            follow=True,
        )
        assert "is now Dead" in reply.content.decode()
        assert Miniature.objects.get(pk=krago.pk).status == Status.DEAD
        gang.refresh_from_db()
        assert gang.stash.rating == 30
        assert gang.rating == 0
        assert_reconciled(gang)

    def test_a_gang_outside_the_campaign_cannot_be_paid(
        self, client, owner, gang, gang_type, krago, tables, rival
    ):
        stranger = found_gang("The Uninvited", gang_type, owner=rival, budget=1000)
        hold_for_ransom(krago, tables)
        client.force_login(owner)
        reply = client.post(
            reverse("n26-pay-ransom", args=[krago.pk]),
            {"outcome": "paid", "credits": "30", "to": str(stranger.pk)},
            follow=True,
        )
        assert "Select who was paid from the list." in reply.content.decode()
        assert Miniature.objects.get(pk=krago.pk).status == Status.RANSOMED
        assert credits(gang) == 1000 - 50
        assert credits(stranger) == 1000
        assert not LedgerEvent.objects.filter(
            kind=LedgerEvent.Kind.TRANSFERRED
        ).exists()

    def test_only_a_figure_off_the_table_is_accepted(
        self, client, owner, gang, captors, krago, tables
    ):
        hold_for_ransom(krago, tables)
        client.force_login(owner)
        for figure in ("35", "-30", "600", ""):
            reply = client.post(
                reverse("n26-pay-ransom", args=[krago.pk]),
                {"outcome": "paid", "credits": figure, "to": str(captors.pk)},
                follow=True,
            )
            assert "Select what the ransom came to." in reply.content.decode()
        assert Miniature.objects.get(pk=krago.pk).status == Status.RANSOMED
        assert credits(gang) == 1000 - 50
        assert credits(captors) == 500

    def test_only_a_ransomed_model_can_be_paid_for(self, client, owner, gang, krago):
        client.force_login(owner)
        reply = client.post(
            reverse("n26-pay-ransom", args=[krago.pk]),
            {"outcome": "paid", "credits": "30", "to": ""},
            follow=True,
        )
        assert "is not held for ransom" in reply.content.decode()
        assert not LedgerEvent.objects.filter(
            kind=LedgerEvent.Kind.TRANSFERRED
        ).exists()

    def test_a_stranger_cannot_pay(self, client, rival, gang, krago, tables):
        hold_for_ransom(krago, tables)
        client.force_login(rival)
        reply = client.post(
            reverse("n26-pay-ransom", args=[krago.pk]),
            {"outcome": "paid", "credits": "30", "to": ""},
        )
        assert reply.status_code == 404
