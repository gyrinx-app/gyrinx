"""An author's addition reaches the gangs already holding the thing.

Adding a member to a set of defaults files a durable
``BuiltInPropagationTask`` in the edit's own transaction and publishes
a message after commit; the pass reconciles every gang holding the
set. The promises proved here: a rolled-back edit files nothing;
filing is append-only, so every edit gets a row and a pass of its own
— even one landing while another pass is running; delivery is
at-least-once, so a duplicate stands down and grants nothing twice; a
lost message leaves a PENDING row the scheduled sweep drains; a set
reaches every holder and an option set only its selectors; what a gang
already holds — or its owner parted with — is left alone; and the
history tells a propagated grant in the equip screen's own words, with
nobody as the actor. Delivery chaos is scripted through the manual
task queue.
"""

from datetime import timedelta

import pytest
from django.contrib.auth.models import User
from django.db import transaction

from n26.core import history, propagation
from n26.core.models import Assignment, BuiltInPropagationTask, LedgerEvent
from n26.core.propagation import sweep_built_in_propagations
from n26.core.reconcile import assert_reconciled
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


@pytest.fixture
def player():
    return User.objects.create_user("tom")


@pytest.fixture
def gang(gang_type, player):
    return found_gang("The Bad Girls", gang_type, owner=player, budget=1000)


@pytest.fixture
def drain(task_queue):
    """Run everything a piece of authoring files, so the next edit
    under test starts from finished passes rather than standing ones."""

    def _drain(build):
        with task_queue.capture():
            built = build()
        task_queue.deliver_all()
        return built

    return _drain


@pytest.fixture
def ganger(person_type, gang_type, default_pack, drain):
    """A profile with one built-in rule, its founding passes settled."""

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
    """Invoke the sweep the way dev and tests must — directly, since the
    local backend fires no schedules — with its patience removed so a
    just-filed row counts as stale."""
    if at_once:
        monkeypatch.setattr(propagation, "REPUBLISH_AFTER", timedelta(0))
    with task_queue.capture():
        sweep_built_in_propagations.func()


class TestTheFilingRidesTheEdit:
    """Filing happens in the authoring transaction, append-only: an
    edit that commits gets a row and a pass of its own, and one that
    rolls back files nothing."""

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
        """Two edits never share a row: each files its own, the first
        pass grants everything the library holds by then, and the
        second finishes as a no-op rather than being folded away."""
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
    """Delivery is at-least-once and the publish is fire-and-forget: a
    duplicate loses the claim and stands down; a lost message leaves a
    PENDING row the sweep re-publishes."""

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
    """A pass finds every gang holding the set — however many things
    hold it — and an option set reaches only the carriers that chose it."""

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
    """A pass creates only what provenance says is missing: a gang that
    already holds the member gains nothing and hears nothing, and what
    an owner archived is never handed back."""

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
    """A propagated grant is its own kind of act: told in the equip
    screen's "comes with" words, with nobody as the actor, and one
    pass's gains for a gang folded into one line."""

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
    """An edit is never lost to a pass already in flight. A running
    pass reads the library when it runs, so it can miss an edit that
    lands after that read — but the edit filed its own row, whose pass
    publishes only after the edit commits and so always sees it."""

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

        # The first pass granted its member and ended DONE having never
        # seen the later edit; that edit's own row still stands.
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
