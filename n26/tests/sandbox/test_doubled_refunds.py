"""Repairing the books where one refund was written twice.

A refund whose click reached the server twice was written twice: the
line was archived once, but a second ``refunded`` leg went into the
books, so the entry's pins say zero while its events fold to minus what
the thing cost, and the gang holds credits it was never owed. The repair
drops every leg after the first of its kind on a line — and the removal
legs written in the same act — then writes the gang's pinned numbers
again, and proves the books whole before it commits.

The fault is planted directly here rather than by racing two clicks:
the operations refuse to write it, and what the repair has to undo is
the shape in the books, not the path that led there.
"""

from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.urls import reverse

from n26.core.doubled_refunds import Refused, apply, find
from n26.core.models import LedgerEvent
from n26.core.reconcile import assert_reconciled, check_gang
from n26.maintenance import Operation, repair_doubled_refunds_view
from n26.tests.sandbox.actions import (
    create_weapon,
    found_gang,
    give_weapon,
    hire,
    refund,
    remove,
    sell,
)

pytestmark = [pytest.mark.django_db, pytest.mark.core]

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


def _written_again(event):
    """The same leg, written a second time in an act of its own."""
    return LedgerEvent.objects.create(
        assignment=event.assignment,
        gang=event.gang,
        kind=event.kind,
        batch=uuid4(),
        actor=event.actor,
        credits_delta=event.credits_delta,
        rating_delta=event.rating_delta,
        trade_points_delta=event.trade_points_delta,
    )


@pytest.fixture
def doubled(gang, vex, default_pack):
    """A refunded gun whose refund leg stands twice, and a removed knife
    whose removal leg was written again in the same second act. The
    gang's credits carry the second refund, as they did when the books
    were written this way."""
    gun = give_weapon(vex, create_weapon("Autogun", price=GUN_PRICE), paid=GUN_PRICE)
    knife = give_weapon(vex, create_weapon("Knife", price=0), paid=0)
    refund(gun)
    remove(knife)

    again = _written_again(gun.ledger_events.get(kind=LedgerEvent.Kind.REFUNDED))
    knife_again = _written_again(knife.ledger_events.get(kind=LedgerEvent.Kind.REMOVED))
    knife_again.batch = again.batch
    knife_again.save(update_fields=["batch"])
    gang.repin_credits()
    gang.refresh_from_db()
    assert gang.credits == 1000 - HIRE_PRICE + GUN_PRICE
    assert check_gang(gang)
    return gang


class TestFindingTheSurplus:
    """The plan names each gang, how many legs go, and what its credits
    lose — and nothing at all when no line carries a second leg."""

    @pytest.fixture
    def played(self, gang, vex, default_pack):
        """A gang with a real history: one refund, one sale and one plain
        removal, each on its own line and each written once."""
        refund(give_weapon(vex, create_weapon("Autogun", price=30), paid=30))
        sell(give_weapon(vex, create_weapon("Shotgun", price=40), paid=40))
        remove(give_weapon(vex, create_weapon("Knife", price=0), paid=0))
        gang.refresh_from_db()
        assert_reconciled(gang)
        return gang

    def test_a_gang_with_real_history_has_nothing_to_drop(self, played):
        plan = find()

        assert plan.nothing_here
        assert plan.event_ids == ()
        assert "nothing to drop" in plan.preview()[0]

    def test_the_plan_names_the_gang_its_legs_and_its_credits(self, doubled):
        plan = find()

        assert plan.ok and not plan.nothing_here
        assert [len(ids) for _, ids, _ in plan.gangs] == [2]
        assert [credits for _, _, credits in plan.gangs] == [GUN_PRICE]
        lines = plan.preview()
        assert f"gang {doubled.pk}: drop 2 surplus events" in lines[0]
        assert f"credits fall by {GUN_PRICE}" in lines[0]
        assert "2 surplus events across 1 gang" in lines[-1]

    def test_the_first_leg_of_each_kind_is_never_named(self, doubled):
        plan = find()

        surplus = set(plan.event_ids)
        first_refund = LedgerEvent.objects.filter(
            gang=doubled, kind=LedgerEvent.Kind.REFUNDED
        ).earliest("created")
        first_removal = LedgerEvent.objects.filter(
            gang=doubled, kind=LedgerEvent.Kind.REMOVED
        ).earliest("created")
        assert first_refund.pk not in surplus
        assert first_removal.pk not in surplus

    def test_a_doubled_leg_on_a_live_line_refuses(self, doubled):
        """Not the shape this repairs: a line still on the roster with a
        refund on it is a different fault, and refusing keeps this one
        honest about what it does."""
        line = LedgerEvent.objects.filter(
            gang=doubled, kind=LedgerEvent.Kind.REFUNDED
        ).earliest("created")
        line.assignment.archived = False
        line.assignment.save(update_fields=["archived"])

        plan = find()

        assert not plan.ok
        assert "still on the roster" in plan.problems[0]
        with pytest.raises(Refused):
            apply(plan)


class TestDroppingTheSurplus:
    def test_the_gang_reconciles_and_loses_what_it_was_never_owed(self, doubled):
        report = apply(find())

        doubled.refresh_from_db()
        assert_reconciled(doubled)
        assert doubled.credits == 1000 - HIRE_PRICE
        assert (
            LedgerEvent.objects.filter(
                gang=doubled, kind=LedgerEvent.Kind.REFUNDED
            ).count()
            == 1
        )
        assert (
            LedgerEvent.objects.filter(
                gang=doubled, kind=LedgerEvent.Kind.REMOVED
            ).count()
            == 1
        )
        assert report[-1].startswith(f"gang {doubled.pk}: dropped 2 events")

    def test_a_second_run_finds_nothing(self, doubled):
        apply(find())

        assert find().nothing_here

    def test_a_gang_with_real_history_applies_to_nothing(self, gang, vex):
        report = apply(find())

        assert "nothing to drop" in report[0]


BIG_PRICE = 960


@pytest.fixture
def spent(doubled, vex, default_pack):
    """The doubled gang has since spent the credits it was never owed:
    a purchase that leaves fewer credits than the surplus handed back."""
    give_weapon(vex, create_weapon("Cannon", price=BIG_PRICE), paid=BIG_PRICE)
    doubled.refresh_from_db()
    assert doubled.credits < GUN_PRICE
    return doubled


class TestAGangThatSpentWhatItWasNeverOwed:
    """Dropping its surplus legs would push its credits below zero, and
    the books never allow that — so the repair leaves the gang exactly
    as it stands and says why, which is a decision for a person."""

    def test_the_plan_says_it_would_be_skipped(self, spent):
        plan = find()
        assert spent.pk in plan.overspent
        assert any("WOULD BE SKIPPED" in line for line in plan.preview())

    def test_apply_skips_it_and_changes_nothing(self, spent):
        events_before = LedgerEvent.objects.filter(gang=spent).count()
        credits_before = spent.credits

        report = apply(find())

        spent.refresh_from_db()
        assert any("skipped" in line and "overspent" in line for line in report)
        assert LedgerEvent.objects.filter(gang=spent).count() == events_before
        assert spent.credits == credits_before
        assert check_gang(spent)

    def test_the_other_gangs_are_still_repaired(
        self, spent, gang_type, owner, make_profile, make_statline, default_pack
    ):
        other = found_gang("The Solvent", gang_type, owner=owner, budget=1000)
        profile = make_profile("Ganger of the Solvent", price=HIRE_PRICE)
        make_statline(profile)
        other_vex = hire(other, profile, "Ash", paid=HIRE_PRICE)
        gun = give_weapon(
            other_vex, create_weapon("Lasgun", price=GUN_PRICE), paid=GUN_PRICE
        )
        refund(gun)
        _written_again(gun.ledger_events.get(kind=LedgerEvent.Kind.REFUNDED))
        other.repin_credits()

        report = apply(find())

        other.refresh_from_db()
        assert_reconciled(other)
        assert other.credits == 1000 - HIRE_PRICE
        assert any(line.startswith(f"gang {other.pk}: dropped") for line in report)
        assert any(line.startswith(f"gang {spent.pk}: skipped") for line in report)


class TestTheConsole:
    def test_the_operation_is_registered_and_named(self):
        from gyrinx.maintenance.registry import operations, resolve_operation

        assert Operation.REPAIR_DOUBLED_REFUNDS.value in {
            op.operation for op in operations()
        }
        found = resolve_operation(Operation.REPAIR_DOUBLED_REFUNDS.value)
        assert found.view is repair_doubled_refunds_view

    def test_its_page_shows_the_plan_and_writes_nothing(self, client, doubled):
        from gyrinx.maintenance.models import Backfill

        superuser = User.objects.create_superuser("root", "root@example.com", "x")
        client.force_login(superuser)

        page = client.get(
            reverse("admin:maintenance_n26_repair_doubled_refunds")
        ).content.decode()

        assert f"gang {doubled.pk}: drop 2 surplus events" in page
        assert not Backfill.objects.exists()
        assert check_gang(doubled)
