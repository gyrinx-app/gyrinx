"""Repair duplicate catch-up grants while preserving the original copy.

Transfer the duplicate's provenance to the unlinked original, remove safe
duplicate grants and their descendants, and retain the larger counter value.
Keep ambiguous groups, paid copies and descendants with recorded tallies.
The repair is idempotent, can target one model and does not write on GET.
"""

from concurrent.futures import ThreadPoolExecutor
from threading import Event

import pytest
from django.contrib.auth.models import User
from django.db import close_old_connections, connection
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from gyrinx.maintenance.registry import operations, resolve_operation
from n26.core.duplicate_grants import (
    de_duplicate,
    duplicate_grants_by_kind,
    what_one_model_carries,
)
from n26.core.models import Assignment, CounterValue, LedgerEvent, Reason
from n26.core.operations import operation
from n26.core.reconcile import assert_reconciled
from n26.maintenance import (
    Operation,
    drop_duplicate_grants,
    drop_duplicate_grants_view,
)
from n26.tests.sandbox.actions import (
    add_built_in,
    buy,
    create_counter,
    create_profile,
    create_rule,
    create_subtype,
    create_wargear,
    found_gang,
    hire,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def player():
    return User.objects.create_user("veteran")


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Old Guard", gang_type, owner=player, budget=1000)


@pytest.fixture
def ganger(person_type, gang_type, default_pack):
    profile = create_profile("Ganger", person_type, gang_type, price=50)
    add_built_in(profile, create_rule("Gang Fighter"))
    return profile


def strip_provenance(gang):
    """Remove materialisation links to simulate an unlinked original grant."""
    return Assignment.objects.filter(
        gang_root=gang, materialised_from__isnull=False
    ).update(materialised_from=None, materialised_for=None)


def caught_up_copy(gang, fighter, member, carrier, assignable):
    """Create an unpaid grant with provenance and a catch-up event."""
    with operation(gang, actor=gang.owner) as op:
        copy = op.assign(
            assignable,
            miniature=fighter,
            caused_by=carrier,
            materialised_from=member,
            materialised_for=carrier,
            paid=0,
            reason=Reason.DEFAULT,
            kind=LedgerEvent.Kind.CAUGHT_UP,
        )
    return copy


def settled(gang):
    gang.refresh_from_db()
    assert_reconciled(gang)
    return gang


class TestTheDuplicateGoesAndTheOwnersCopyStays:
    """Transfer provenance to the original before deleting the duplicate catch-up grant."""

    @pytest.mark.parametrize("budget_drift", [False, True])
    def test_a_walk_without_duplicates_leaves_the_gangs_books_untouched(
        self, budget_drift, gang, ganger
    ):
        hire(gang, ganger, "Ana", paid=50)
        if budget_drift:
            # A repair with nothing to remove must leave unrelated drift alone.
            type(gang).objects.filter(pk=gang.pk).update(starting_credits=40)
        gang.refresh_from_db()
        before = (gang.starting_credits, gang.credits, gang.rating, gang.modified)
        events = LedgerEvent.objects.filter(gang=gang).count()

        outcome = de_duplicate(gang.pk)

        gang.refresh_from_db()
        assert outcome.dropped == 0
        assert (
            gang.starting_credits,
            gang.credits,
            gang.rating,
            gang.modified,
        ) == before
        assert LedgerEvent.objects.filter(gang=gang).count() == events

    def test_the_owners_copy_survives_wearing_the_provenance(self, gang, ganger):
        fighter = hire(gang, ganger, "Ana", paid=50)
        strip_provenance(gang)
        member = ganger.built_ins.members.get(rule__isnull=False)
        original = Assignment.objects.get(rule__isnull=False, miniature_root=fighter)
        caught_up_copy(gang, fighter, member, fighter.membership, member.assignable)
        assert (
            Assignment.objects.filter(
                rule__isnull=False, miniature_root=fighter
            ).count()
            == 2
        )

        outcome = de_duplicate(gang.pk)

        assert outcome.dropped == 1
        assert outcome.retagged == 1
        standing = Assignment.objects.get(rule__isnull=False, miniature_root=fighter)
        assert standing.pk == original.pk
        assert standing.materialised_from == member
        assert standing.materialised_for == fighter.membership
        settled(gang)

    def test_a_later_pass_grants_nothing(self, gang, ganger):
        fighter = hire(gang, ganger, "Ana", paid=50)
        strip_provenance(gang)
        member = ganger.built_ins.members.get(rule__isnull=False)
        caught_up_copy(gang, fighter, member, fighter.membership, member.assignable)
        de_duplicate(gang.pk)

        with operation(gang, actor=gang.owner) as op:
            again = op.reconcile_defaults(fighter.membership, strict=False)

        assert again.created == []
        assert (
            Assignment.objects.filter(
                rule__isnull=False, miniature_root=fighter, archived=False
            ).count()
            == 1
        )


class TestWhatTheDroppedCopyBrought:
    """Remove the dropped duplicate's dependent built-in grants."""

    def test_the_nested_grants_go_with_it(
        self, gang, person_type, gang_type, default_pack
    ):
        spyrer = create_subtype("Spyrer")
        add_built_in(spyrer, create_counter("Kill Count"))
        profile = create_profile("Hunter", person_type, gang_type, price=100)
        add_built_in(profile, spyrer)
        fighter = hire(gang, profile, "Ana", paid=100)
        strip_provenance(gang)
        member = profile.built_ins.members.get(subtype__isnull=False)
        duplicate = caught_up_copy(gang, fighter, member, fighter.membership, spyrer)
        with operation(gang, actor=gang.owner) as op:
            op.reconcile_defaults(duplicate, strict=False)
        assert (
            Assignment.objects.filter(
                counter__isnull=False, miniature_root=fighter, archived=False
            ).count()
            >= 1
        )

        outcome = de_duplicate(gang.pk)

        assert outcome.dropped == 1
        assert outcome.swept >= 1
        assert not Assignment.objects.filter(pk=duplicate.pk).exists()
        assert (
            Assignment.objects.filter(
                subtype=spyrer, miniature_root=fighter, archived=False
            ).count()
            == 1
        )
        settled(gang)


class TestACopySomebodyCountedOn:
    """Merge a duplicate counter into its survivor using the greater value.

    Keep duplicates with tallied descendants when those values cannot be transferred.
    """

    def tallied_duplicate(self, gang, person_type, gang_type, value):
        counter = create_counter("Kill Count")
        profile = create_profile("Hunter", person_type, gang_type, price=100)
        add_built_in(profile, counter)
        fighter = hire(gang, profile, "Ana", paid=100)
        strip_provenance(gang)
        member = profile.built_ins.members.get(counter__isnull=False)
        duplicate = caught_up_copy(gang, fighter, member, fighter.membership, counter)
        CounterValue.objects.filter(assignment=duplicate).delete()
        duplicate.ledger_events.filter(counter_before__isnull=False).delete()
        with operation(gang, actor=gang.owner) as op:
            op.open_counter(duplicate, value)
        return fighter, counter, duplicate

    def test_the_number_moves_to_the_copy_that_stays(
        self, gang, person_type, gang_type, default_pack
    ):
        fighter, counter, duplicate = self.tallied_duplicate(
            gang, person_type, gang_type, 7
        )

        outcome = de_duplicate(gang.pk)

        assert outcome.dropped == 1
        assert outcome.merged == 1
        assert outcome.kept_a_tally == []
        assert not Assignment.objects.filter(pk=duplicate.pk).exists()
        standing = Assignment.objects.get(
            counter=counter, miniature_root=fighter, archived=False
        )
        assert standing.counter_value.value == 7
        settled(gang)

    def test_a_missing_survivor_value_gets_an_opening_event(
        self, gang, person_type, gang_type, default_pack, counter_tracking
    ):
        fighter, counter, duplicate = self.tallied_duplicate(
            gang, person_type, gang_type, 7
        )
        standing = Assignment.objects.exclude(pk=duplicate.pk).get(
            counter=counter, miniature_root=fighter, archived=False
        )
        CounterValue.objects.filter(assignment=standing).delete()
        standing.ledger_events.filter(counter_before__isnull=False).delete()

        de_duplicate(gang.pk)

        standing.refresh_from_db()
        assert standing.counter_value.value == 7
        events = list(
            standing.ledger_events.filter(counter_before__isnull=False).order_by(
                "created", "pk"
            )
        )
        assert events[0].kind == LedgerEvent.Kind.COUNTER_OPENED
        settled(gang)

    def test_the_higher_of_the_two_numbers_is_the_one_kept(
        self, gang, person_type, gang_type, default_pack
    ):
        fighter, counter, duplicate = self.tallied_duplicate(
            gang, person_type, gang_type, 3
        )
        standing = Assignment.objects.exclude(pk=duplicate.pk).get(
            counter=counter, miniature_root=fighter, archived=False
        )
        with operation(gang, actor=gang.owner) as op:
            op.tally(standing, 9)

        de_duplicate(gang.pk)

        standing.refresh_from_db()
        assert standing.counter_value.value == 9


@pytest.mark.django_db(transaction=True)
def test_repair_keeps_a_tally_committed_while_it_waits_for_the_gang_lock(
    gang, person_type, gang_type, default_pack
):
    counter = create_counter("Kill Count")
    profile = create_profile("Hunter", person_type, gang_type, price=100)
    add_built_in(profile, counter)
    fighter = hire(gang, profile, "Ana", paid=100)
    strip_provenance(gang)
    member = profile.built_ins.members.get(counter=counter)
    duplicate = caught_up_copy(gang, fighter, member, fighter.membership, counter)
    with operation(gang, actor=gang.owner) as op:
        op.tally(duplicate, 7)

    lock_attempted = Event()

    def signal_lock(execute, sql, params, many, context):
        if '"n26_gang"' in sql and "FOR UPDATE" in sql:
            lock_attempted.set()
        return execute(sql, params, many, context)

    def repair():
        close_old_connections()
        try:
            with connection.execute_wrapper(signal_lock):
                return de_duplicate(gang.pk)
        finally:
            connection.close()

    with ThreadPoolExecutor(max_workers=1) as pool:
        with operation(gang, actor=gang.owner) as op:
            pending = pool.submit(repair)
            assert lock_attempted.wait(10), "Repair did not try to lock the gang"
            op.tally(duplicate, 5)
        outcome = pending.result(timeout=10)

    assert outcome.merged == 1
    standing = Assignment.objects.get(
        counter=counter, miniature_root=fighter, archived=False
    )
    assert standing.counter_value.value == 12
    assert not Assignment.objects.filter(pk=duplicate.pk).exists()
    settled(gang)


class TestTwinsAreLeftExactlyAsTheyStand:
    """Keep ambiguous groups when multiple built-in members name the same assignable."""

    def test_a_group_a_set_names_twice_stands_and_is_named(
        self, gang, person_type, gang_type, default_pack
    ):
        rule = create_rule("Gang Fighter")
        profile = create_profile("Ganger", person_type, gang_type, price=50)
        add_built_in(profile, rule)
        second = add_built_in(profile, rule)
        fighter = hire(gang, profile, "Ana", paid=50)
        strip_provenance(gang)
        caught_up_copy(gang, fighter, second, fighter.membership, rule)
        before = Assignment.objects.filter(
            rule=rule, miniature_root=fighter, archived=False
        ).count()

        outcome = de_duplicate(gang.pk)

        assert outcome.dropped == 0
        assert len(outcome.kept_a_tally) == 1
        assert "more than one built-in" in outcome.kept_a_tally[0]
        assert (
            Assignment.objects.filter(
                rule=rule, miniature_root=fighter, archived=False
            ).count()
            == before
        )


class TestWhatIsNotADuplicate:
    """Repair only a catch-up grant paired with an unlinked original copy."""

    def test_two_tagged_copies_are_two_members_doing_their_job(
        self, gang, person_type, gang_type, default_pack
    ):
        rule = create_rule("Gang Fighter")
        profile = create_profile("Ganger", person_type, gang_type, price=50)
        add_built_in(profile, rule)
        add_built_in(profile, rule)
        fighter = hire(gang, profile, "Ana", paid=50)
        before = Assignment.objects.filter(
            rule=rule, miniature_root=fighter, archived=False
        ).count()

        outcome = de_duplicate(gang.pk)

        assert outcome.dropped == 0
        assert (
            Assignment.objects.filter(
                rule=rule, miniature_root=fighter, archived=False
            ).count()
            == before
        )

    def test_a_bought_copy_is_the_owners_business(self, gang, ganger, default_pack):
        fighter = hire(gang, ganger, "Ana", paid=50)
        buy(fighter, thing=create_wargear("Respirator", price=10), paid=10)
        strip_provenance(gang)

        outcome = de_duplicate(gang.pk)

        assert outcome.dropped == 0
        settled(gang)


class TestTryingItOnOneModel:
    """Restrict the repair and its preview to one selected model."""

    def two_fighters_each_with_a_duplicate(self, gang, ganger):
        member = ganger.built_ins.members.get(rule__isnull=False)
        made = []
        for name in ("Ana", "Bea"):
            fighter = hire(gang, ganger, name, paid=50)
            made.append(fighter)
        strip_provenance(gang)
        for fighter in made:
            caught_up_copy(gang, fighter, member, fighter.membership, member.assignable)
        return made

    def test_only_the_named_model_is_repaired(self, gang, ganger):
        ana, bea = self.two_fighters_each_with_a_duplicate(gang, ganger)

        outcome = de_duplicate(gang.pk, only_miniature_id=ana.pk)

        assert outcome.dropped == 1
        assert (
            Assignment.objects.filter(
                rule__isnull=False, miniature_root=ana, archived=False
            ).count()
            == 1
        )
        assert (
            Assignment.objects.filter(
                rule__isnull=False, miniature_root=bea, archived=False
            ).count()
            == 2
        )
        settled(gang)

    def test_the_page_reads_back_what_one_model_would_lose(self, gang, ganger):
        ana, _ = self.two_fighters_each_with_a_duplicate(gang, ganger)

        lines = what_one_model_carries(ana)

        assert len(lines) == 1
        assert "takes its provenance" in lines[0]

    def test_a_run_named_for_one_model_leaves_the_rest_alone(self, gang, ganger):
        ana, bea = self.two_fighters_each_with_a_duplicate(gang, ganger)
        record = Backfill.objects.create(
            operation=Operation.DROP_DUPLICATE_GRANTS,
            status=Backfill.Status.RUNNING,
            summary={
                "attempts": 0,
                "only_model": str(ana.pk),
                "only_gang": str(gang.pk),
                "only_model_name": ana.name,
            },
        )

        drop_duplicate_grants.func(backfill_id=str(record.pk))

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert record.summary["totals"]["dropped"] == 1
        assert record.summary["total"] == 1
        assert (
            Assignment.objects.filter(
                rule__isnull=False, miniature_root=bea, archived=False
            ).count()
            == 2
        )


class TestATallyFurtherDown:
    """Inspect all cascade descendants before deleting a duplicate that may contain counter values."""

    def test_a_counter_under_a_granted_subtype_keeps_the_duplicate(
        self, gang, person_type, gang_type, default_pack
    ):
        spyrer = create_subtype("Spyrer")
        add_built_in(spyrer, create_counter("Kill Count"))
        profile = create_profile("Hunter", person_type, gang_type, price=100)
        add_built_in(profile, spyrer)
        fighter = hire(gang, profile, "Ana", paid=100)
        strip_provenance(gang)
        member = profile.built_ins.members.get(subtype__isnull=False)
        duplicate = caught_up_copy(gang, fighter, member, fighter.membership, spyrer)
        with operation(gang, actor=gang.owner) as op:
            op.reconcile_defaults(duplicate, strict=False)
        beneath = Assignment.objects.filter(
            counter__isnull=False, caused_by=duplicate
        ).first()
        CounterValue.objects.update_or_create(assignment=beneath, defaults={"value": 4})

        outcome = de_duplicate(gang.pk)

        assert outcome.dropped == 0
        assert len(outcome.kept_a_tally) == 1
        assert "counts 4" in outcome.kept_a_tally[0]
        assert Assignment.objects.filter(pk=duplicate.pk).exists()
        assert Assignment.objects.filter(pk=beneath.pk).exists()


class TestADuplicateBeneathADuplicate:
    """Skip nested duplicate pairs already removed with a parent duplicate."""

    def test_the_gang_settles_and_one_of_each_thing_stands(
        self, gang, person_type, gang_type, default_pack
    ):
        counter = create_counter("Kill Count")
        spyrer = create_subtype("Spyrer")
        add_built_in(spyrer, counter)
        profile = create_profile("Hunter", person_type, gang_type, price=100)
        add_built_in(profile, spyrer)
        fighter = hire(gang, profile, "Ana", paid=100)
        strip_provenance(gang)
        member = profile.built_ins.members.get(subtype__isnull=False)
        duplicate = caught_up_copy(gang, fighter, member, fighter.membership, spyrer)
        with operation(gang, actor=gang.owner) as op:
            # Catch-up events make the nested counter eligible as a duplicate too.
            op.reconcile_defaults(
                duplicate, strict=False, event_kind=LedgerEvent.Kind.CAUGHT_UP
            )

        outcome = de_duplicate(gang.pk)

        assert outcome.dropped >= 1
        assert (
            Assignment.objects.filter(
                subtype=spyrer, miniature_root=fighter, archived=False
            ).count()
            == 1
        )
        assert (
            Assignment.objects.filter(
                counter=counter, miniature_root=fighter, archived=False
            ).count()
            <= 1
        )
        settled(gang)


class TestRunningTwice:
    def test_a_second_run_finds_nothing(self, gang, ganger):
        fighter = hire(gang, ganger, "Ana", paid=50)
        strip_provenance(gang)
        member = ganger.built_ins.members.get(rule__isnull=False)
        caught_up_copy(gang, fighter, member, fighter.membership, member.assignable)
        first = de_duplicate(gang.pk)
        assert first.dropped == 1

        second = de_duplicate(gang.pk)

        assert second.dropped == 0
        assert second.retagged == 0


class TestTheConsoleDoor:
    @pytest.fixture
    def superuser(self, db):
        return User.objects.create_superuser("boss", "boss@example.com", "password")

    def test_the_operation_is_registered_and_named(self):
        registered = {op.operation for op in operations()}

        assert Operation.DROP_DUPLICATE_GRANTS.value in registered
        found = resolve_operation(Operation.DROP_DUPLICATE_GRANTS.value)
        assert found.name == Operation.DROP_DUPLICATE_GRANTS.label
        assert found.view is drop_duplicate_grants_view

    def test_its_page_counts_the_duplicates_and_writes_nothing(
        self, client, superuser, gang, ganger
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        strip_provenance(gang)
        member = ganger.built_ins.members.get(rule__isnull=False)
        caught_up_copy(gang, fighter, member, fighter.membership, member.assignable)
        client.force_login(superuser)

        response = client.get(reverse("admin:maintenance_n26_drop_duplicate_grants"))

        page = response.content.decode()
        assert response.status_code == 200
        assert "1 duplicate grant" in page
        assert not Backfill.objects.exists()
        assert duplicate_grants_by_kind() == {"rule": 1}
        settled(gang)

    def test_a_real_id_reads_back_that_models_duplicates(
        self, client, superuser, gang, ganger
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        strip_provenance(gang)
        member = ganger.built_ins.members.get(rule__isnull=False)
        caught_up_copy(gang, fighter, member, fighter.membership, member.assignable)
        client.force_login(superuser)

        response = client.get(
            reverse("admin:maintenance_n26_drop_duplicate_grants"),
            {"model": str(fighter.pk)},
        )

        page = response.content.decode()
        assert response.status_code == 200
        assert "takes its provenance" in page
        assert "Drop them for this model only" in page

    def test_a_word_that_is_not_an_id_is_refused_in_words(self, client, superuser):
        client.force_login(superuser)

        response = client.get(
            reverse("admin:maintenance_n26_drop_duplicate_grants"),
            {"model": "not-an-id"},
            follow=True,
        )

        assert response.status_code == 200
        assert "No model in a gang has that id." in response.content.decode()
        assert not Backfill.objects.exists()

    def test_the_run_walks_every_gang(self, gang, ganger):
        fighter = hire(gang, ganger, "Ana", paid=50)
        strip_provenance(gang)
        member = ganger.built_ins.members.get(rule__isnull=False)
        caught_up_copy(gang, fighter, member, fighter.membership, member.assignable)
        record = Backfill.objects.create(
            operation=Operation.DROP_DUPLICATE_GRANTS,
            status=Backfill.Status.RUNNING,
            summary={"attempts": 0},
        )

        drop_duplicate_grants.func(backfill_id=str(record.pk))

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert record.summary["totals"]["dropped"] == 1
        settled(gang)
