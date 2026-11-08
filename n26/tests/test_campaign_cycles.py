"""Campaign schedule commands preserve history and deliver committed transitions once."""

import importlib
from concurrent.futures import ThreadPoolExecutor
from dataclasses import replace
from datetime import date, timedelta
from threading import Barrier, Event, Lock, local
from unittest.mock import patch
from uuid import uuid4

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import close_old_connections, connection, connections, transaction
from django.test.utils import CaptureQueriesContext

from gyrinx.site.models import Availability, FeatureFlag, Notification
from n26.core import cycles
from n26.core import schedule as s
from n26.core.campaigns import campaign_operation
from n26.core.cycle_data import template_data
from n26.core.models import (
    Assignment,
    Campaign,
    CampaignCycle,
    CampaignCycleCommand,
    CampaignCycleDelivery,
    CampaignCycleTransition,
    CampaignPhase,
    CampaignPlan,
    CampaignSchedule,
    CampaignScheduleTemplate,
    LedgerEvent,
)
from n26.core.operations import Refusal
from n26.core.reconcile import assert_reconciled
from n26.flags import CYCLE_TRACKING
from n26.notifications import (
    deliver_cycle_transition,
    retry_pending_cycle_notifications,
)
from n26.tests.sandbox.actions import found_campaign, found_gang, join_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user("cycle-arbitrator")


@pytest.fixture
def campaign(owner, campaign_type):
    return found_campaign("Ash Road", campaign_type, owner=owner)


@pytest.fixture
def opened():
    return FeatureFlag.objects.create(
        slug=CYCLE_TRACKING, name="Campaign cycles", availability=Availability.EVERYONE
    )


@pytest.fixture
def template():
    return CampaignScheduleTemplate.objects.create(
        name=s.DEFAULT_TEMPLATE.name,
        system_key=cycles.DEFAULT_TEMPLATE_KEY,
        definition=template_data(s.DEFAULT_TEMPLATE),
    )


@pytest.fixture
def configured(campaign, owner, template, opened):
    cycles.configure(
        campaign,
        actor=owner,
        template_id=template.pk,
        current_position=0,
        mode="fixed",
        request_key=uuid4(),
    )
    return cycles.load(campaign)


@pytest.fixture
def player(campaign, owner):
    player = User.objects.create_user("cycle-player")
    with campaign_operation(campaign, actor=owner) as act:
        act.invite(player)
    with campaign_operation(campaign, actor=player) as act:
        act.answer_invitation(player, True)
    return player


def start_campaign(campaign, owner):
    with campaign_operation(campaign, actor=owner) as act:
        act.set_status(Campaign.Status.IN_PROGRESS)
    return cycles.load(campaign)


def advance(campaign, owner, before, *, key=None):
    return cycles.advance(
        campaign,
        actor=owner,
        expected_current=before.current_cycle_id,
        expected_revision=before.revision,
        request_key=key or uuid4(),
    )


def concurrent(work):
    barrier = Barrier(2)

    def run():
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SET lock_timeout = '5s'")
            barrier.wait(timeout=10)
            return work()
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        futures = [pool.submit(run) for _ in range(2)]
        return [future.result(timeout=20) for future in futures]


class TestSetupAndAccess:
    def test_seeding_the_template_is_repeatable_and_does_not_opt_existing_campaigns_in(
        self, campaign
    ):
        before = (campaign.pk, campaign.name, campaign.status)
        migration = importlib.import_module(
            "n26.core.migrations.0084_campaign_cycles_and_plans"
        )
        migration.seed_schedule_template(apps, None)
        migration.seed_schedule_template(apps, None)
        template = CampaignScheduleTemplate.objects.get(
            system_key=cycles.DEFAULT_TEMPLATE_KEY
        )
        assert [step["count"] for step in template.definition["steps"]] == [3, 1, 3]
        assert not CampaignCycle.objects.exists()
        assert not CampaignSchedule.objects.exists()
        campaign.refresh_from_db()
        assert (campaign.pk, campaign.name, campaign.status) == before

    def test_foreign_template_and_malformed_template_ids_are_refused(
        self, campaign, owner, template, opened
    ):
        foreign_owner = User.objects.create_user("other-arbitrator")
        foreign = cycles.create_template(
            actor=foreign_owner, name="Private", definition=template.definition
        )
        for identity in (foreign.pk, "not-an-id"):
            with pytest.raises(Refusal, match="your schedule templates"):
                cycles.configure(
                    campaign,
                    actor=owner,
                    template_id=identity,
                    current_position=0,
                    mode="fixed",
                    request_key=uuid4(),
                )
        assert not CampaignSchedule.objects.exists()

    def test_missing_flag_refuses_setup_without_writing(
        self, campaign, owner, template
    ):
        with pytest.raises(Refusal, match="not available"):
            cycles.configure(
                campaign,
                actor=owner,
                template_id=template.pk,
                current_position=0,
                mode="fixed",
                request_key=uuid4(),
            )
        assert not CampaignSchedule.objects.exists()
        assert not CampaignCycle.objects.exists()
        assert not CampaignCycleCommand.objects.exists()

    def test_initial_setup_copies_the_template_without_starting(
        self, campaign, configured
    ):
        assert len(configured.cycles) == 1
        assert configured.current_phase.details.name == "Occupation Phase"
        assert len(s.project(configured)) == 6
        assert configured.status == "pre_campaign"
        assert not CampaignCycleTransition.objects.exists()
        assert not CampaignCycleDelivery.objects.exists()
        assert len(configured.phases) == 3
        assert CampaignPlan.objects.count() == 1

    def test_an_accepted_player_can_select_but_cannot_manage(
        self, campaign, configured, player
    ):
        target = s.project(configured, limit=2)[-1]
        with pytest.raises(Refusal, match="Only the arbitrator"):
            cycles.edit_cycle(
                campaign,
                actor=player,
                target=target.ref,
                details=s.CycleDetails(target.phase_id),
                expected_revision=configured.revision,
                request_key=uuid4(),
            )
        with campaign_operation(campaign, actor=player) as act:
            selected = cycles.resolve_selection(act, target.ref)
        assert selected.order == 3
        assert CampaignCycle.objects.count() == 3
        assert cycles.load(campaign).current_cycle_id == configured.current_cycle_id
        assert not CampaignCycleTransition.objects.exists()

    def test_disabling_the_flag_preserves_data_and_existing_status_actions(
        self, campaign, owner, configured, opened
    ):
        opened.availability = Availability.OFF
        opened.save()
        with pytest.raises(Refusal, match="not available"):
            advance(campaign, owner, configured)
        with campaign_operation(campaign, actor=owner) as act:
            act.set_status(Campaign.Status.IN_PROGRESS)
        retained = cycles.load(campaign)
        assert retained.current_cycle_id == configured.current_cycle_id
        assert retained.status == "in_progress"
        assert not CampaignCycleTransition.objects.exists()
        opened.availability = Availability.EVERYONE
        opened.save()
        advance(campaign, owner, retained)
        assert cycles.load(campaign).current.order == 2

    def test_status_changes_while_disabled_invalidate_old_phase_reassignments(
        self, campaign, owner, configured, opened
    ):
        opened.availability = Availability.OFF
        opened.save()
        with campaign_operation(campaign, actor=owner) as act:
            act.set_status(Campaign.Status.IN_PROGRESS)
        retained = cycles.load(campaign)
        assert retained.revision == configured.revision + 1
        assert retained.current_cycle_id == configured.current_cycle_id
        opened.availability = Availability.EVERYONE
        opened.save()
        with pytest.raises(cycles.CycleConflict, match="schedule changed"):
            cycles.edit_cycle(
                campaign,
                actor=owner,
                target=s.SavedCycleRef(configured.current_cycle_id),
                details=s.CycleDetails(configured.phases[1].id),
                expected_revision=configured.revision,
                request_key=uuid4(),
            )
        after = cycles.load(campaign)
        assert after == retained
        assert not CampaignCycleTransition.objects.exists()
        assert not CampaignCycleDelivery.objects.exists()
        assert CampaignCycleCommand.objects.count() == 1


class TestMaterialisation:
    @pytest.mark.parametrize("identity", ["", "x" * 27])
    def test_invalid_step_identities_cannot_be_committed_as_a_replacement_plan(
        self, campaign, owner, configured, identity
    ):
        with pytest.raises(Refusal):
            cycles.replace_plan(
                campaign,
                actor=owner,
                steps=(s.PlanStep(identity, configured.current_phase.id, 1),),
                mode="fixed",
                expected_revision=configured.revision,
                request_key=uuid4(),
            )
        assert cycles.load(campaign) == configured
        assert CampaignPlan.objects.count() == 1

    def test_editing_cycle_six_saves_the_prefix_without_starting(
        self, campaign, owner, configured
    ):
        target = s.project(configured, limit=5)[-1]
        result = cycles.edit_cycle(
            campaign,
            actor=owner,
            target=target.ref,
            details=s.CycleDetails(target.phase_id, custom_name="The crossing"),
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        after = cycles.load(campaign)
        assert len(after.cycles) == 6
        assert after.current_cycle_id == configured.current_cycle_id
        assert after.cycles[-1].id == result.cycle_id
        assert after.cycles[-1].name == "The crossing"
        assert after.next_position == 6
        assert not CampaignCycleTransition.objects.exists()

    def test_exact_replay_returns_the_receipt_before_checking_a_stale_revision(
        self, campaign, owner, configured
    ):
        target = s.project(configured, limit=3)[-1]
        arguments = dict(
            actor=owner,
            target=target.ref,
            details=s.CycleDetails(target.phase_id),
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        first = cycles.edit_cycle(campaign, **arguments)
        replay = cycles.edit_cycle(campaign, **arguments)
        assert replay.replayed
        assert replay.cycle_id == first.cycle_id
        assert replay.revision == first.revision
        assert CampaignCycle.objects.count() == 4
        assert CampaignCycleCommand.objects.count() == 2
        with pytest.raises(cycles.CycleConflict, match="different change"):
            cycles.edit_cycle(
                campaign,
                **{**arguments, "details": s.CycleDetails(target.phase_id, "Other")},
            )

    def test_an_outer_rollback_removes_the_prefix_and_command_receipt(
        self, campaign, owner, configured
    ):
        target = s.project(configured, limit=5)[-1]
        with pytest.raises(RuntimeError, match="cancel"):
            with transaction.atomic():
                cycles.edit_cycle(
                    campaign,
                    actor=owner,
                    target=target.ref,
                    details=s.CycleDetails(target.phase_id),
                    expected_revision=configured.revision,
                    request_key=uuid4(),
                )
                raise RuntimeError("cancel")
        assert cycles.load(campaign) == configured
        assert CampaignCycleCommand.objects.count() == 1

    def test_date_edits_and_replacement_preserve_sources_and_the_saved_tail(
        self, campaign, owner, configured, template
    ):
        target = s.project(configured, limit=4)[-1]
        cycles.edit_cycle(
            campaign,
            actor=owner,
            target=target.ref,
            details=s.CycleDetails(target.phase_id),
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        before = cycles.load(campaign)
        cycles.edit_cycle(
            campaign,
            actor=owner,
            target=s.SavedCycleRef(before.cycles[0].id),
            details=replace(before.cycles[0].details, starts_on=date(2030, 1, 1)),
            expected_revision=before.revision,
            request_key=uuid4(),
        )
        dated = cycles.load(campaign)
        cycles.apply_template(
            campaign,
            actor=owner,
            template_id=template.pk,
            mode="repeating",
            expected_revision=dated.revision,
            request_key=uuid4(),
        )
        after = cycles.load(campaign)
        assert after.cycles == dated.cycles
        assert [c.source for c in after.cycles] == [c.source for c in before.cycles]
        assert after.current_cycle_id == configured.current_cycle_id
        assert after.next_position == 0
        assert s.project(after, limit=1)[0].order == 6
        assert CampaignPlan.objects.count() == 2


class TestAdvancement:
    def test_entering_a_reward_phase_leaves_gang_money_equipment_and_ledger_unchanged(
        self, campaign, owner, configured, player, gang_type
    ):
        gang = found_gang("Ash choir", gang_type, owner=player, budget=1000)
        join_campaign(gang, campaign)
        downtime = configured.phases[1]
        cycles.edit_phase(
            campaign,
            actor=owner,
            phase_id=downtime.id,
            details=replace(
                downtime.details,
                rewards=s.RewardSettings(
                    win=s.Reward(s.CreditAmount(100), 10),
                    entry_credits=s.CreditAmount(1000),
                ),
            ),
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        before = start_campaign(campaign, owner)
        held = list(Assignment.objects.filter(gang_root=gang).order_by("id").values())
        events = LedgerEvent.objects.filter(gang=gang).count()
        credits, rating = gang.credits, gang.rating
        for _ in range(3):
            advance(campaign, owner, before)
            before = cycles.load(campaign)
        gang.refresh_from_db()
        assert before.current_phase.details.name == "Downtime"
        assert (gang.credits, gang.rating) == (credits, rating)
        assert (
            list(Assignment.objects.filter(gang_root=gang).order_by("id").values())
            == held
        )
        assert LedgerEvent.objects.filter(gang=gang).count() == events
        assert_reconciled(gang)

    def test_saved_future_activation_does_not_consume_another_position(
        self, campaign, owner, configured
    ):
        target = s.project(configured, limit=2)[-1]
        cycles.edit_cycle(
            campaign,
            actor=owner,
            target=target.ref,
            details=s.CycleDetails(target.phase_id),
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        before = start_campaign(campaign, owner)
        result = advance(campaign, owner, before)
        after = cycles.load(campaign)
        assert after.current.order == 2
        assert len(after.cycles) == len(before.cycles)
        assert after.next_position == before.next_position
        assert result.transition_id
        assert CampaignCycleTransition.objects.count() == 2

    def test_advancement_replay_and_stale_submissions_cannot_skip_a_cycle(
        self, campaign, owner, configured
    ):
        before = start_campaign(campaign, owner)
        key = uuid4()
        first = advance(campaign, owner, before, key=key)
        replay = advance(campaign, owner, before, key=key)
        assert replay.replayed
        assert replay.transition_id == first.transition_id
        with pytest.raises(cycles.CycleConflict, match="schedule changed"):
            advance(campaign, owner, before)
        assert cycles.load(campaign).current.order == 2
        assert CampaignCycleTransition.objects.count() == 2

    def test_finishing_retains_the_final_cycle_and_existing_campaign_status(
        self, campaign, owner, configured
    ):
        before = start_campaign(campaign, owner)
        cycles.replace_plan(
            campaign,
            actor=owner,
            steps=(),
            mode="fixed",
            expected_revision=before.revision,
            request_key=uuid4(),
        )
        before = cycles.load(campaign)
        cycles.finish(
            campaign,
            actor=owner,
            expected_current=before.current_cycle_id,
            expected_revision=before.revision,
            request_key=uuid4(),
        )
        campaign.refresh_from_db()
        assert campaign.status == Campaign.Status.POST_CAMPAIGN
        assert cycles.load(campaign).current == before.current
        assert (
            CampaignCycleTransition.objects.order_by("created").last().kind
            == "finished"
        )


class TestTransitionDelivery:
    def test_a_committed_transition_notifies_once_across_task_redelivery(
        self, campaign, owner, configured, player, task_queue
    ):
        with task_queue.capture():
            start_campaign(campaign, owner)
        assert CampaignCycleDelivery.objects.count() == 1
        assert Notification.objects.count() == 0
        task_queue.deliver_all()
        first = CampaignCycleDelivery.objects.get()
        assert first.notification_id
        assert first.delivered_at
        assert Notification.objects.get(pk=first.notification_id).owner == player
        task_queue.redeliver_last("deliver_cycle_transition")
        assert Notification.objects.count() == 1


@pytest.mark.django_db(transaction=True)
class TestConcurrentWriters:
    def test_a_snapshot_cannot_mix_its_header_with_a_concurrent_saved_prefix(
        self, campaign, owner, configured
    ):
        locked, writing = Event(), Event()
        marker = local()
        original = cycles._load_locked
        target = s.project(configured, limit=3)[-1].ref

        def read_locked(fresh):
            if getattr(marker, "reader", False):
                locked.set()
                assert writing.wait(timeout=10)
            return original(fresh)

        def read():
            close_old_connections()
            marker.reader = True
            try:
                return cycles.load(Campaign.objects.get(pk=campaign.pk))
            finally:
                connections.close_all()

        def write():
            close_old_connections()
            try:
                assert locked.wait(timeout=10)
                writing.set()
                with campaign_operation(
                    Campaign.objects.get(pk=campaign.pk),
                    actor=User.objects.get(pk=owner.pk),
                ) as act:
                    cycles.resolve_selection(act, target)
            finally:
                connections.close_all()

        with patch("n26.core.cycles._load_locked", side_effect=read_locked):
            with ThreadPoolExecutor(max_workers=2) as pool:
                reader = pool.submit(read)
                writer = pool.submit(write)
                before = reader.result(timeout=20)
                writer.result(timeout=20)
        assert len(before.cycles) == before.next_position == 1
        after = cycles.load(campaign)
        assert len(after.cycles) == after.next_position == 4

    def test_two_selections_materialise_the_same_prefix_once(
        self, campaign, owner, configured
    ):
        target = s.project(configured, limit=5)[-1].ref

        def select():
            fresh = Campaign.objects.get(pk=campaign.pk)
            actor = User.objects.get(pk=owner.pk)
            with campaign_operation(fresh, actor=actor) as act:
                return cycles.resolve_selection(act, target).pk

        first, second = concurrent(select)
        assert first == second
        assert CampaignCycle.objects.count() == 6
        assert cycles.load(campaign).current_cycle_id == configured.current_cycle_id
        assert not CampaignCycleTransition.objects.exists()

    def test_two_advancements_with_one_request_key_commit_one_transition(
        self, campaign, owner, configured
    ):
        before = start_campaign(campaign, owner)
        key = uuid4()

        def submit():
            return advance(
                Campaign.objects.get(pk=campaign.pk),
                User.objects.get(pk=owner.pk),
                before,
                key=key,
            )

        results = concurrent(submit)
        assert sum(result.replayed for result in results) == 1
        assert len({result.transition_id for result in results}) == 1
        assert cycles.load(campaign).current.order == 2
        assert CampaignCycleTransition.objects.count() == 2

    def test_two_different_advancements_from_one_baseline_cannot_skip_a_cycle(
        self, campaign, owner, configured
    ):
        before = start_campaign(campaign, owner)

        def submit():
            try:
                advance(
                    Campaign.objects.get(pk=campaign.pk),
                    User.objects.get(pk=owner.pk),
                    before,
                )
            except cycles.CycleConflict:
                return "conflict"
            return "saved"

        assert sorted(concurrent(submit)) == ["conflict", "saved"]
        assert cycles.load(campaign).current.order == 2
        assert CampaignCycle.objects.count() == 2


class TestSnapshotQueries:
    def test_more_saved_cycles_do_not_add_queries(self, campaign, owner, configured):
        with CaptureQueriesContext(connection) as small:
            cycles.load(campaign)
        target = s.project(configured, limit=6)[-1]
        cycles.edit_cycle(
            campaign,
            actor=owner,
            target=target.ref,
            details=s.CycleDetails(target.phase_id),
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        with CaptureQueriesContext(connection) as large:
            cycles.load(campaign)
        assert len(large) == len(small)


class TestRetainedDelivery:
    def test_later_flag_changes_and_departure_do_not_retract_committed_delivery(
        self, campaign, owner, configured, player, opened, task_queue
    ):
        with task_queue.capture():
            start_campaign(campaign, owner)
        opened.availability = Availability.OFF
        opened.save()
        campaign.participants.filter(user=player).delete()
        task_queue.deliver_all()
        assert Notification.objects.count() == 1
        assert CampaignCycleDelivery.objects.get().notification_id

    def test_a_failure_after_notification_creation_rolls_back_both_records(
        self, campaign, owner, configured, player, task_queue
    ):
        with task_queue.capture():
            start_campaign(campaign, owner)
        delivery = CampaignCycleDelivery.objects.get()
        with patch.object(
            CampaignCycleDelivery, "save", side_effect=RuntimeError("crash")
        ):
            with pytest.raises(RuntimeError, match="crash"):
                deliver_cycle_transition.func(str(delivery.transition_id))
        assert Notification.objects.count() == 0
        delivery.refresh_from_db()
        assert delivery.notification_id is None
        deliver_cycle_transition.func(str(delivery.transition_id))
        assert Notification.objects.count() == 1

    def test_pending_delivery_recovers_when_publish_fails_after_commit(
        self, campaign, owner, configured, player, task_queue
    ):
        with patch("n26.notifications.deliver_cycle_transition") as task:
            task.enqueue.side_effect = RuntimeError("publish failed")
            with task_queue.capture():
                start_campaign(campaign, owner)
        assert (
            CampaignCycleDelivery.objects.filter(delivered_at__isnull=True).count() == 1
        )
        assert Notification.objects.count() == 0
        retry_pending_cycle_notifications.func()
        assert Notification.objects.count() == 1


class TestCrossCampaignValidation:
    def test_a_phase_kept_only_by_transition_history_cannot_be_deleted(
        self, campaign, owner, configured
    ):
        cycles.duplicate_phase(
            campaign,
            actor=owner,
            phase_id=configured.current_phase.id,
            name="Interlude",
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        copied = cycles.load(campaign)
        phase_id = copied.phases[-1].id
        cycles.edit_cycle(
            campaign,
            actor=owner,
            target=s.SavedCycleRef(copied.current_cycle_id),
            details=replace(copied.current.details, phase_id=phase_id),
            expected_revision=copied.revision,
            request_key=uuid4(),
        )
        before = start_campaign(campaign, owner)
        cycles.edit_cycle(
            campaign,
            actor=owner,
            target=s.SavedCycleRef(before.current_cycle_id),
            details=replace(
                before.current.details, phase_id=configured.current_phase.id
            ),
            expected_revision=before.revision,
            request_key=uuid4(),
        )
        after = cycles.load(campaign)
        with pytest.raises(Refusal, match="recorded in a cycle transition"):
            cycles.delete_phase(
                campaign,
                actor=owner,
                phase_id=phase_id,
                expected_revision=after.revision,
                request_key=uuid4(),
            )
        assert CampaignPhase.objects.filter(pk=phase_id).exists()

    def test_a_cycle_cannot_take_a_foreign_phase(
        self, campaign, owner, configured, campaign_type
    ):
        other = found_campaign("Other road", campaign_type, owner=owner)
        foreign = CampaignPhase.objects.create(campaign=other, name="Foreign")
        cycle = CampaignCycle.objects.get(pk=configured.current_cycle_id)
        cycle.phase = foreign
        with pytest.raises(ValidationError, match="phase from this campaign"):
            cycle.full_clean()
        assert cycles.load(campaign) == configured


class TestStoredCycleDates:
    def test_settings_preserve_saved_dates_and_materialisation_stores_future_ranges(
        self, campaign, owner, configured
    ):
        original = configured.cycles
        start = original[-1].details.ends_on + timedelta(days=8)
        cycles.replace_plan(
            campaign,
            actor=owner,
            steps=s.editable_steps(configured),
            mode="repeating",
            calendar=s.CycleCalendar(start, 2),
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        state = cycles.load(campaign)
        assert state.cycles == original
        selected = s.project(state)[2]
        cycles.edit_cycle(
            campaign,
            actor=owner,
            target=selected.ref,
            details=s.CycleDetails(selected.phase_id),
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        saved = list(campaign.cycles.order_by("order"))
        assert all(cycle.starts_on and cycle.ends_on for cycle in saved)
        assert saved[-1].starts_on == selected.starts_on
        assert saved[-1].ends_on == selected.ends_on
        assert campaign.cycle_transitions.count() == 0

    def test_overlap_refusal_rolls_back_the_prefix_and_receipt(
        self, campaign, owner, configured
    ):
        target = s.project(configured)[2]
        original = configured.current.details
        count = campaign.cycle_commands.count()
        with pytest.raises(Refusal, match="overlap"):
            cycles.edit_cycle(
                campaign,
                actor=owner,
                target=target.ref,
                details=s.CycleDetails(
                    target.phase_id,
                    starts_on=original.starts_on,
                    ends_on=original.ends_on,
                ),
                expected_revision=configured.revision,
                request_key=uuid4(),
            )
        assert cycles.load(campaign) == configured
        assert campaign.cycle_commands.count() == count

    def test_unchanged_settings_preserve_monthly_anchor_and_revision(
        self, campaign, owner, configured
    ):
        first_start = configured.current.details.ends_on + timedelta(days=8)
        cycles.replace_plan(
            campaign,
            actor=owner,
            steps=s.editable_steps(configured),
            mode="repeating",
            calendar=s.CycleCalendar(first_start, unit="months"),
            expected_revision=configured.revision,
            request_key=uuid4(),
        )
        before = cycles.load(campaign)
        cycles.replace_plan(
            campaign,
            actor=owner,
            steps=s.editable_steps(before),
            mode="repeating",
            calendar=s.CycleCalendar(s.project(before)[0].starts_on, unit="months"),
            expected_revision=before.revision,
            request_key=uuid4(),
        )
        assert cycles.load(campaign) == before


@pytest.mark.django_db(transaction=True)
def test_concurrent_date_edits_cannot_commit_overlapping_ranges(
    campaign, owner, configured
):
    target = s.project(configured)[1]
    cycles.edit_cycle(
        campaign,
        actor=owner,
        target=target.ref,
        details=s.CycleDetails(target.phase_id),
        expected_revision=configured.revision,
        request_key=uuid4(),
    )
    before = cycles.load(campaign)
    targets = iter(before.cycles[1:])
    selection = Lock()
    start = before.cycles[-1].details.ends_on + timedelta(days=8)

    def edit():
        with selection:
            selected = next(targets)
        try:
            cycles.edit_cycle(
                campaign,
                actor=owner,
                target=s.SavedCycleRef(selected.id),
                details=replace(
                    selected.details, starts_on=start, ends_on=start + timedelta(days=6)
                ),
                expected_revision=before.revision,
                request_key=uuid4(),
            )
            return "saved"
        except cycles.CycleConflict:
            return "stale"

    assert sorted(concurrent(edit)) == ["saved", "stale"]
    s.validate_cycle_dates(cycles.load(campaign).cycles)


@pytest.mark.django_db(transaction=True)
def test_concurrent_workers_create_one_inbox_notification(
    campaign, owner, configured, player, task_queue
):
    start_campaign(campaign, owner)
    delivery = CampaignCycleDelivery.objects.get()
    baseline = Notification.objects.count()
    results = concurrent(
        lambda: deliver_cycle_transition.func(str(delivery.transition_id))
    )
    delivery.refresh_from_db()
    assert sum(results) == 1
    assert delivery.notification_id
    assert Notification.objects.count() == baseline + 1
