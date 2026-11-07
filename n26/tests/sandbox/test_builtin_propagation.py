"""Verify durable propagation of built-in additions to existing gangs. File work in the
authoring transaction and publish after commit; duplicate delivery must not create extra
grants.

Exercise lost-message recovery, shared holders, selected options, owner removals,
actorless history and paused execution through the manual task queue.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.db import transaction

from gyrinx.site.models import Availability, FeatureFlag
from n26.core import history, propagation
from n26.core.models import Assignment, BuiltInPropagationTask, LedgerEvent
from n26.core.propagation import sweep_built_in_propagations
from n26.core.reconcile import assert_reconciled
from n26.flags import BUILT_IN_PROPAGATION
from n26.library.authoring import add_default_member
from n26.tests.sandbox.actions import (
    add_built_in,
    create_default_set,
    create_profile,
    create_rule,
    found_gang,
    hire,
    hire_with_option,
    offer_option,
    remove,
)

pytestmark = pytest.mark.django_db


@pytest.fixture(autouse=True)
def flag(db):
    """Enable propagation for this suite; individual disabled-state tests change the flag."""
    return FeatureFlag.objects.create(
        slug=BUILT_IN_PROPAGATION,
        name="Built-in propagation",
        availability=Availability.EVERYONE,
    )


@pytest.fixture
def player():
    return User.objects.create_user("tom")


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Bad Girls", gang_type, owner=player, budget=1000)


@pytest.fixture
def drain(task_queue):
    """Deliver setup propagation tasks before the next authoring change under test."""

    def _drain(build):
        with task_queue.capture():
            built = build()
        task_queue.deliver_all()
        return built

    return _drain


@pytest.fixture
def ganger(person_type, gang_type, default_pack, drain):
    """Profile with one built-in rule and completed setup propagation."""

    def _build():
        profile = create_profile("Ganger", person_type, gang_type, price=50)
        add_built_in(profile, create_rule("Gang Fighter"))
        return profile

    return drain(_build)


def statuses():
    return list(
        BuiltInPropagationTask.objects.order_by("created").values_list(
            "status", flat=True
        )
    )


def run_sweep(task_queue, monkeypatch, at_once=True):
    """Invoke the sweep directly because the local backend does not run schedules.
    Optionally make newly filed work immediately eligible for republication.
    """
    if at_once:
        monkeypatch.setattr(propagation, "REPUBLISH_AFTER", timedelta(0))
    with task_queue.capture():
        sweep_built_in_propagations.func()


class TestTheFilingRidesTheEdit:
    """Persist a distinct propagation task per committed edit and none for rolled-back
    changes.
    """

    def test_a_rolled_back_edit_files_nothing_and_sends_nothing(
        self, gang, person_type, gang_type, default_pack, task_queue
    ):
        profile = create_profile("Undecided", person_type, gang_type, price=50)
        before = BuiltInPropagationTask.objects.count()

        with task_queue.capture():
            with pytest.raises(RuntimeError):
                with transaction.atomic():
                    add_built_in(profile, create_rule("Second Thoughts"))
                    raise RuntimeError("changed my mind")

        assert BuiltInPropagationTask.objects.count() == before
        assert task_queue.pending() == 0

    def test_an_edit_reaches_an_existing_fighter_in_one_delivery(
        self, gang, ganger, default_pack, task_queue
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)

        with task_queue.capture():
            member = add_built_in(ganger, create_rule("Nerves of Steel"))
        task_queue.deliver_all()

        copies = Assignment.objects.filter(
            materialised_from=member, materialised_for=fighter.membership
        )
        assert copies.count() == 1
        filed = (
            BuiltInPropagationTask.objects.filter(
                status="DONE", default_set=member.default_set
            )
            .order_by("created")
            .last()
        )
        ending = filed.states.history.get(to_status="DONE")
        assert ending.metadata["gangs"] == 1
        assert ending.metadata["granted"] == 1
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_every_edit_files_its_own_row_and_every_row_is_run(
        self, gang, ganger, default_pack, task_queue
    ):
        """Retain both edit records even when the first pass grants all current members and
        the second has no remaining work.
        """
        fighter = hire(gang, ganger, "Ana", paid=50)
        before = BuiltInPropagationTask.objects.count()

        with task_queue.capture():
            first = add_built_in(ganger, create_rule("First Wind"))
            second = add_built_in(ganger, create_rule("Second Wind"))
        task_queue.deliver_all()

        assert BuiltInPropagationTask.objects.count() == before + 2
        for member in (first, second):
            assert (
                Assignment.objects.filter(
                    materialised_from=member, materialised_for=fighter.membership
                ).count()
                == 1
            )
        assert "PENDING" not in statuses()
        assert "RUNNING" not in statuses()
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestDeliveryChaos:
    """Ignore duplicate claims and recover lost publication from durable pending work."""

    def test_a_duplicate_delivery_stands_down_and_grants_nothing_twice(
        self, gang, ganger, default_pack, task_queue
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        with task_queue.capture():
            member = add_built_in(ganger, create_rule("Nerves of Steel"))
        task_queue.deliver_all()

        task_queue.redeliver_last(task_name="propagate_built_ins")

        assert (
            Assignment.objects.filter(
                materialised_from=member, materialised_for=fighter.membership
            ).count()
            == 1
        )
        filed = (
            BuiltInPropagationTask.objects.filter(
                status="DONE", default_set=member.default_set
            )
            .order_by("created")
            .last()
        )
        assert filed.states.history.filter(to_status="DONE").count() == 1
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_dropped_message_leaves_a_row_the_sweep_drains(
        self, gang, ganger, default_pack, task_queue, monkeypatch
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        with task_queue.capture():
            member = add_built_in(ganger, create_rule("Nerves of Steel"))
        task_queue.drop_next()
        task_queue.deliver_all()

        assert not Assignment.objects.filter(materialised_from=member).exists()
        filed = BuiltInPropagationTask.objects.get(
            default_set=member.default_set, status="PENDING"
        )

        run_sweep(task_queue, monkeypatch)
        task_queue.deliver_all()

        assert Assignment.objects.filter(
            materialised_from=member, materialised_for=fighter.membership
        ).exists()
        filed.refresh_from_db()
        assert filed.status == "DONE"
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestReach:
    """Reach every holder of a shared set, restricting option-set updates to models that
    selected that option.
    """

    def test_a_set_shared_by_two_profiles_reaches_every_holder(
        self, gang_type, person_type, player, default_pack, task_queue, drain
    ):
        shared = create_default_set("Shared kit", members=[create_rule("Common Lore")])

        def _holders():
            first = create_profile("Ganger", person_type, gang_type, price=50)
            second = create_profile("Juve", person_type, gang_type, price=25)
            for profile in (first, second):
                profile.built_ins = shared
                profile.save()
            return first, second

        first, second = drain(_holders)
        here = found_gang("The Bad Girls", gang_type, owner=player, budget=1000)
        there = found_gang("The Movers", gang_type, owner=player, budget=1000)
        ana = hire(here, first, "Ana", paid=50)
        bea = hire(there, second, "Bea", paid=25)

        with task_queue.capture():
            member = add_built_in(first, create_rule("Nerves of Steel"))
        task_queue.deliver_all()

        assert member.default_set_id == shared.pk
        for fighter in (ana, bea):
            assert Assignment.objects.filter(
                materialised_from=member, materialised_for=fighter.membership
            ).exists()
        for settled in (here, there):
            settled.refresh_from_db()
            assert_reconciled(settled)

    def test_an_option_set_change_reaches_only_its_selectors(
        self, gang, person_type, gang_type, default_pack, task_queue, drain
    ):
        def _build():
            profile = create_profile("Chooser", person_type, gang_type, price=100)
            offer_option(profile, "Plain", thing=create_rule("Plain Style"))
            fancy = offer_option(profile, "Fancy", thing=create_rule("Fancy Style"))
            return profile, fancy.default_set

        profile, fancy_kit = drain(_build)
        took_it = hire_with_option(gang, profile, "Ana", option=fancy_kit)
        went_plain = hire(gang, profile, "Bea", paid=100)

        with task_queue.capture():
            member = add_default_member(fancy_kit, create_rule("Poise"))
        task_queue.deliver_all()

        assert Assignment.objects.filter(
            materialised_from=member, materialised_for=took_it.membership
        ).exists()
        assert not Assignment.objects.filter(
            materialised_from=member, materialised_for=went_plain.membership
        ).exists()
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestSettledGangsAreUntouched:
    """Grant only missing provenance-linked assignments, preserving existing assignments
    and owner removals.
    """

    def test_a_redundant_pass_writes_no_assignment_and_no_event(
        self, gang, ganger, default_pack, task_queue
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        with task_queue.capture():
            member = add_built_in(ganger, create_rule("Nerves of Steel"))
        task_queue.deliver_all()
        rows = Assignment.objects.filter(gang_root=gang).count()
        events = LedgerEvent.objects.filter(gang=gang).count()

        with task_queue.capture():
            propagation.file_propagation_task(member.default_set)
        task_queue.deliver_all()

        assert Assignment.objects.filter(gang_root=gang).count() == rows
        assert LedgerEvent.objects.filter(gang=gang).count() == events
        assert (
            Assignment.objects.filter(
                materialised_from=member, materialised_for=fighter.membership
            ).count()
            == 1
        )
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_what_an_owner_parted_with_is_never_re_granted(
        self, gang, ganger, default_pack, task_queue
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        with task_queue.capture():
            member = add_built_in(ganger, create_rule("Nerves of Steel"))
        task_queue.deliver_all()
        copy = Assignment.objects.get(
            materialised_from=member, materialised_for=fighter.membership
        )
        remove(copy)
        events = LedgerEvent.objects.filter(gang=gang).count()

        with task_queue.capture():
            propagation.file_propagation_task(member.default_set)
        task_queue.deliver_all()

        copies = Assignment.objects.filter(
            materialised_from=member, materialised_for=fighter.membership
        )
        assert copies.count() == 1
        assert copies.get().archived is True
        assert LedgerEvent.objects.filter(gang=gang).count() == events
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestTheHistoryTellsIt:
    """Record actorless propagated grants, grouping changes from one source into one
    history entry.
    """

    def test_a_lone_gain_names_the_model_and_the_source(
        self, gang, ganger, default_pack, task_queue
    ):
        hire(gang, ganger, "Ana", paid=50)
        with task_queue.capture():
            add_built_in(ganger, create_rule("Nerves of Steel"))
        task_queue.deliver_all()

        acts = history.build(gang)
        told = ["".join(span.text for span in act.spans) for act in acts]
        assert (
            "Ana gained Nerves of Steel — now part of what a Ganger comes with" in told
        )
        act = acts[
            told.index(
                "Ana gained Nerves of Steel — now part of what a Ganger comes with"
            )
        ]
        assert act.actor == ""
        assert act.subs == []
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_several_models_fold_into_one_line_about_the_source(
        self, gang, ganger, default_pack, task_queue
    ):
        hire(gang, ganger, "Ana", paid=50)
        hire(gang, ganger, "Bea", paid=50)
        with task_queue.capture():
            add_built_in(ganger, create_rule("Nerves of Steel"))
        task_queue.deliver_all()

        acts = history.build(gang)
        told = ["".join(span.text for span in act.spans) for act in acts]
        assert told.count("what a Ganger comes with changed") == 1
        act = acts[told.index("what a Ganger comes with changed")]
        assert act.actor == ""
        assert sorted(sub.name for sub in act.subs) == ["Ana", "Bea"]
        assert {sub.note for sub in act.subs} == {"gained Nerves of Steel"}
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_an_acquisitions_grants_keep_their_own_words(
        self, gang, ganger, default_pack, task_queue
    ):
        hire(gang, ganger, "Ana", paid=50)

        assert not LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.CAUGHT_UP
        ).exists()
        assert LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.GRANTED
        ).exists()
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestAnEditLandingMidPass:
    """Each concurrent edit files independent work, so a change missed by an active pass
    remains pending for another pass.
    """

    def test_it_files_its_own_row_and_both_passes_end_done(
        self, gang, ganger, default_pack, task_queue, monkeypatch
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        second = create_rule("Second Wind")
        real = propagation._reconcile_holders
        landed = []

        def edit_mid_pass(default_set):
            summary = real(default_set)
            if not landed:
                landed.append(add_built_in(ganger, second))
            return summary

        monkeypatch.setattr(propagation, "_reconcile_holders", edit_mid_pass)
        with task_queue.capture():
            first_member = add_built_in(ganger, create_rule("First Wind"))
        task_queue.deliver_all()

        # The first delivery completed before the second edit; its independent task
        # remains pending.
        assert Assignment.objects.filter(
            materialised_from=first_member, materialised_for=fighter.membership
        ).exists()
        assert not Assignment.objects.filter(materialised_from=landed[0]).exists()
        assert statuses().count("DONE") >= 1
        assert statuses().count("PENDING") == 1

        run_sweep(task_queue, monkeypatch)
        task_queue.deliver_all()

        assert Assignment.objects.filter(
            materialised_from=landed[0], materialised_for=fighter.membership
        ).exists()
        assert "PENDING" not in statuses()
        assert "RUNNING" not in statuses()
        gang.refresh_from_db()
        assert_reconciled(gang)


class TestTheFeatureFlagIsTheKillSwitch:
    """File work while execution is disabled without delivering or republishing it.
    Re-enabling execution allows the sweep to process the backlog.
    """

    def test_shut_an_edit_files_a_row_a_delivery_leaves_pending(
        self, gang, ganger, default_pack, task_queue, flag
    ):
        hire(gang, ganger, "Ana", paid=50)
        flag.availability = Availability.OFF
        flag.save()
        events = LedgerEvent.objects.filter(gang=gang).count()

        with task_queue.capture():
            member = add_built_in(ganger, create_rule("Nerves of Steel"))
        task_queue.deliver_all()

        assert BuiltInPropagationTask.objects.filter(
            default_set=member.default_set, status="PENDING"
        ).exists()
        assert not Assignment.objects.filter(materialised_from=member).exists()
        assert not LedgerEvent.objects.filter(
            gang=gang, kind=LedgerEvent.Kind.CAUGHT_UP
        ).exists()
        assert LedgerEvent.objects.filter(gang=gang).count() == events

    def test_shut_the_sweep_republishes_nothing_and_refiles_nothing(
        self, gang, ganger, default_pack, task_queue, monkeypatch, flag
    ):
        hire(gang, ganger, "Ana", paid=50)
        flag.availability = Availability.OFF
        flag.save()
        with task_queue.capture():
            member = add_built_in(ganger, create_rule("First Wind"))
            failed = propagation.file_propagation_task(member.default_set)
        task_queue.deliver_all()
        # Include both pending and failed tasks so disabling the flag checks both sweep
        # retry paths.
        failed.states.transition_to("RUNNING")
        failed.states.transition_to("FAILED", metadata={})
        rows = BuiltInPropagationTask.objects.count()

        run_sweep(task_queue, monkeypatch)

        assert task_queue.pending() == 0
        assert BuiltInPropagationTask.objects.count() == rows
        assert statuses().count("PENDING") == 1

    def test_a_backlog_filed_while_shut_drains_when_the_flag_opens(
        self, gang, ganger, default_pack, task_queue, monkeypatch, flag
    ):
        fighter = hire(gang, ganger, "Ana", paid=50)
        flag.availability = Availability.OFF
        flag.save()
        with task_queue.capture():
            first = add_built_in(ganger, create_rule("First Wind"))
            second = add_built_in(ganger, create_rule("Second Wind"))
        task_queue.deliver_all()
        assert statuses().count("PENDING") == 2

        flag.availability = Availability.EVERYONE
        flag.save()
        run_sweep(task_queue, monkeypatch)
        task_queue.deliver_all()

        for member in (first, second):
            assert (
                Assignment.objects.filter(
                    materialised_from=member, materialised_for=fighter.membership
                ).count()
                == 1
            )
        assert "PENDING" not in statuses()
        assert "RUNNING" not in statuses()
        gang.refresh_from_db()
        assert_reconciled(gang)
