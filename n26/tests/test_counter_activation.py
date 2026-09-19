"""The operator activates counter history after deployment, under a write pause."""

from datetime import timedelta
from uuid import uuid4

import pytest
from django.db import transaction
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from gyrinx.site.models import WritePause
from gyrinx.site.write_pause import WritesPaused, pause_scope, resume_scope
from n26 import maintenance
from n26.core import counter_activation
from n26.core.counter_tracking import is_active
from n26.core.models import Assignment, CounterTracking, CounterValue, Gang, LedgerEvent
from n26.core.operations import operation
from n26.core.reconcile import check_counter_value
from n26.library.authoring import create_counter

pytestmark = [pytest.mark.django_db, pytest.mark.core]


@pytest.fixture
def counters(owner, gang_type):
    counter = create_counter("Kill Count")
    held = []
    for index, value in enumerate((0, 6, 13)):
        gang = Gang.objects.create(
            name=f"Hunt {index}", owner=owner, gang_type=gang_type
        )
        with operation(gang, actor=owner) as op:
            assignment = op.assign(counter, gang=gang)
            op.tally(assignment, value)
        if index == 2:
            assignment.archived = True
            assignment.save(update_fields=["archived"])
        held.append(assignment)
    return held


def start(task_queue, actor):
    with task_queue.capture():
        record = maintenance.start_counter_history(actor)
    return record, record.summary["pause_generation"]


def snapshot():
    return dict(CounterValue.objects.values_list("assignment_id", "value"))


class TestActivationAndManualResume:
    """A deployment stays inactive until an explicitly requested job passes its audit."""

    def test_every_counter_is_checkpointed_before_writes_resume(
        self, counters, owner, task_queue
    ):
        before = snapshot()
        old_events = list(LedgerEvent.objects.values())
        record, generation = start(task_queue, owner)
        assert not is_active()
        with pytest.raises(WritesPaused), operation(counters[0].gang) as op:
            op.tally(counters[0], 1)
        with pytest.raises(WritesPaused):
            resume_scope("n26", generation=generation, actor=owner)

        task_queue.deliver_all()

        record.refresh_from_db()
        assert record.status == Backfill.Status.DONE
        assert is_active()
        assert snapshot() == before
        assert WritePause.objects.get(scope="n26").state == WritePause.State.PAUSED
        assert LedgerEvent.objects.filter(
            batch=record.pk, kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED
        ).count() == len(counters)
        for value in CounterValue.objects.select_related("assignment__counter"):
            assert check_counter_value(value) == []
        assert (
            list(
                LedgerEvent.objects.filter(
                    pk__in=[event["id"] for event in old_events]
                ).values()
            )
            == old_events
        )

        maintenance.resume_after_counter_history(record.pk, generation, owner)
        with operation(counters[1].gang, actor=owner) as op:
            op.tally(counters[1], -4)
        counters[1].counter_value.refresh_from_db()
        assert counters[1].counter_value.value == 2
        assert check_counter_value(counters[1].counter_value) == []

    def test_a_duplicate_delivery_preserves_the_checkpoint_count(
        self, counters, owner, task_queue
    ):
        record, _generation = start(task_queue, owner)
        task_queue.deliver_all()
        before = LedgerEvent.objects.count()

        task_queue.redeliver_last()

        assert LedgerEvent.objects.count() == before
        assert CounterTracking.objects.get(pk=1).activation_run == record.pk

    def test_an_installation_without_counters_can_be_activated(self, owner, task_queue):
        record, generation = start(task_queue, owner)
        task_queue.deliver_all()

        assert is_active()
        maintenance.resume_after_counter_history(record.pk, generation, owner)

    def test_old_controls_cannot_resume_a_different_pause(self, owner, task_queue):
        record, generation = start(task_queue, owner)
        task_queue.deliver_all()
        with pytest.raises(counter_activation.ActivationRefused, match="changed"):
            maintenance.resume_after_counter_history(record.pk, generation + 1, owner)


class TestInterruptedActivation:
    """Partial checkpoints keep writes paused until a retry or recorded cleanup finishes."""

    @pytest.fixture
    def failed(self, counters, owner, task_queue, monkeypatch):
        original = counter_activation.checkpoint_gang

        def fail_one(gang_id, run_id, generation):
            if gang_id == counters[1].gang_id:
                raise RuntimeError("Injected checkpoint failure")
            return original(gang_id, run_id, generation)

        monkeypatch.setattr(counter_activation, "checkpoint_gang", fail_one)
        record, generation = start(task_queue, owner)
        task_queue.deliver_all()
        monkeypatch.setattr(counter_activation, "checkpoint_gang", original)
        record.refresh_from_db()
        assert record.status == Backfill.Status.FAILED
        assert not is_active()
        assert LedgerEvent.objects.filter(batch=record.pk).exists()
        return record, generation

    def test_retry_reuses_the_run_and_keeps_earlier_checkpoints(
        self, failed, task_queue
    ):
        record, generation = failed
        before = snapshot()
        checkpoints = set(
            LedgerEvent.objects.filter(batch=record.pk).values_list("pk", flat=True)
        )
        with task_queue.capture():
            maintenance.restart_counter_history(record.pk, generation)
        task_queue.deliver_all()

        assert is_active()
        assert snapshot() == before
        assert checkpoints <= set(
            LedgerEvent.objects.filter(batch=record.pk).values_list("pk", flat=True)
        )
        assert LedgerEvent.objects.filter(batch=record.pk).count() == len(before)

    def test_cleanup_must_finish_before_legacy_writes_can_resume(
        self, failed, task_queue, owner, counters
    ):
        record, generation = failed
        before = snapshot()
        with task_queue.capture():
            maintenance.restart_counter_history(record.pk, generation, cleanup=True)
        with pytest.raises(counter_activation.ActivationRefused, match="finish"):
            maintenance.resume_after_counter_history(record.pk, generation, owner)
        task_queue.deliver_all()
        assert not is_active()
        assert not LedgerEvent.objects.filter(batch=record.pk).exists()
        assert snapshot() == before
        maintenance.resume_after_counter_history(record.pk, generation, owner)
        with operation(counters[1].gang, actor=owner) as op:
            op.tally(counters[1], 1)
        assert snapshot()[counters[1].pk] == 7

        later, _ = start(task_queue, owner)
        task_queue.deliver_all()
        assert is_active()
        assert (
            LedgerEvent.objects.get(
                assignment=counters[1], batch=later.pk
            ).counter_after
            == 7
        )

    def test_cleanup_only_removes_checkpoints_from_its_own_run(
        self, failed, task_queue, counters
    ):
        record, generation = failed
        other = LedgerEvent.objects.create(
            assignment=counters[0],
            gang=counters[0].gang,
            kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED,
            batch=uuid4(),
            counter_before=0,
            counter_delta=0,
            counter_after=0,
        )
        note = LedgerEvent.objects.create(
            gang=counters[0].gang,
            kind=LedgerEvent.Kind.NOTED,
            batch=record.pk,
            note="A separate journal entry.",
        )
        with task_queue.capture():
            maintenance.restart_counter_history(record.pk, generation, cleanup=True)
        task_queue.deliver_all()
        assert LedgerEvent.objects.filter(pk=other.pk).exists()
        assert LedgerEvent.objects.filter(pk=note.pk).exists()
        assert not LedgerEvent.objects.filter(
            batch=record.pk, kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED
        ).exists()

    def test_full_validation_can_refuse_activation_while_normal_audit_is_inactive(
        self, counters, owner, task_queue, monkeypatch
    ):
        monkeypatch.setattr(
            counter_activation,
            "check_counter_value",
            lambda *_args, **_kwargs: ["Injected audit failure"],
        )
        record, _ = start(task_queue, owner)
        task_queue.deliver_all()
        record.refresh_from_db()
        assert record.status == Backfill.Status.FAILED
        assert not is_active()
        assert WritePause.objects.get(scope="n26").state == WritePause.State.PAUSED

    def test_a_checkpoint_helper_requires_the_exact_delivery_permit(self, counters):
        with pytest.raises(WritesPaused), transaction.atomic():
            counter_activation.checkpoint_gang(counters[0].gang_id, uuid4(), 1)

    def test_an_operator_can_retry_after_the_initial_delivery_is_lost(
        self, counters, owner, task_queue, admin_client
    ):
        before = snapshot()
        record, generation = start(task_queue, owner)
        task_queue.drop_next()
        task_queue.deliver_all()

        record.refresh_from_db()
        assert record.status == Backfill.Status.RUNNING
        assert not LedgerEvent.objects.filter(batch=record.pk).exists()
        page = admin_client.get(
            reverse("admin:maintenance_n26_activate_counter_history")
        )
        assert b"If progress has stopped" in page.content
        assert b"Retry this run" in page.content

        with task_queue.capture():
            maintenance.restart_counter_history(record.pk, generation)
        task_queue.deliver_all()

        assert is_active()
        assert snapshot() == before
        assert LedgerEvent.objects.filter(
            batch=record.pk, kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED
        ).count() == len(counters)

    def test_an_operator_can_retry_after_a_continuation_is_lost(
        self, counters, owner, task_queue, monkeypatch
    ):
        before = snapshot()
        run_per_gang = maintenance.run_per_gang

        def one_gang_per_delivery(*args, **kwargs):
            kwargs["batch_size"] = 1
            kwargs["budget"] = timedelta(0)
            return run_per_gang(*args, **kwargs)

        monkeypatch.setattr(maintenance, "run_per_gang", one_gang_per_delivery)
        record, generation = start(task_queue, owner)
        task_queue.deliver_next()
        task_queue.drop_next()
        task_queue.deliver_next()

        record.refresh_from_db()
        assert record.status == Backfill.Status.RUNNING
        assert (
            LedgerEvent.objects.filter(
                batch=record.pk, kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED
            ).count()
            == 1
        )

        with task_queue.capture():
            maintenance.restart_counter_history(record.pk, generation)
        task_queue.deliver_all()

        assert is_active()
        assert snapshot() == before
        checkpoints = LedgerEvent.objects.filter(
            batch=record.pk, kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED
        )
        assert checkpoints.count() == len(counters)
        assert checkpoints.values("assignment_id").distinct().count() == len(counters)


class TestOperatorPage:
    """The operator confirms rollout readiness before the job can begin."""

    def test_non_superusers_cannot_activate(self, client, owner):
        owner.is_staff = True
        owner.save(update_fields=["is_staff"])
        client.force_login(owner)
        response = client.post(
            reverse("admin:maintenance_n26_activate_counter_history"),
            {"action": "activate", "ready": "confirmed"},
        )
        assert response.status_code == 403
        assert not is_active()
        assert not Backfill.objects.filter(
            operation=maintenance.Operation.ACTIVATE_COUNTER_HISTORY
        ).exists()

    def test_operator_can_resume_through_the_page_while_writes_are_paused(
        self, admin_client, counters, task_queue
    ):
        url = reverse("admin:maintenance_n26_activate_counter_history")
        with task_queue.capture():
            response = admin_client.post(
                url, {"action": "activate", "ready": "confirmed"}
            )
        assert response.status_code == 302
        task_queue.deliver_all()
        record = Backfill.objects.get(
            operation=maintenance.Operation.ACTIVATE_COUNTER_HISTORY
        )
        assert record.status == Backfill.Status.DONE
        assert b"Resume n26 writes" in admin_client.get(url).content
        response = admin_client.post(
            url,
            {
                "action": "resume",
                "run_id": str(record.pk),
                "generation": record.summary["pause_generation"],
            },
        )
        assert response.status_code == 302
        assert WritePause.objects.get(scope="n26").state == WritePause.State.OPEN

    def test_readiness_confirmation_is_required(self, admin_client, task_queue):
        response = admin_client.post(
            reverse("admin:maintenance_n26_activate_counter_history"),
            {"action": "activate"},
        )
        assert response.status_code == 200
        assert b"Confirm that every serving web and task revision" in response.content
        assert not Backfill.objects.filter(
            operation=maintenance.Operation.ACTIVATE_COUNTER_HISTORY
        ).exists()
        assert WritePause.objects.get(scope="n26").state == WritePause.State.OPEN

    @pytest.mark.parametrize("action", ["retry", "cleanup", "resume"])
    def test_deleted_run_controls_show_an_error_and_keep_writes_paused(
        self, action, admin_client, counters, owner, task_queue
    ):
        record, generation = start(task_queue, owner)
        run_id = record.pk
        record.delete()
        before = snapshot()
        old_events = list(LedgerEvent.objects.order_by("pk").values())
        pause_before = WritePause.objects.filter(scope="n26").values().get()
        queued_before = task_queue.pending()

        with task_queue.capture():
            response = admin_client.post(
                reverse("admin:maintenance_n26_activate_counter_history"),
                {
                    "action": action,
                    "run_id": str(run_id),
                    "generation": generation,
                },
            )

        assert response.status_code == 200
        assert (
            b"The maintenance run no longer exists. n26 writes remain paused."
            in response.content
        )
        assert not is_active()
        assert not Backfill.objects.filter(
            operation=maintenance.Operation.ACTIVATE_COUNTER_HISTORY
        ).exists()
        assert task_queue.pending() == queued_before
        assert WritePause.objects.filter(scope="n26").values().get() == pause_before
        assert snapshot() == before
        assert list(LedgerEvent.objects.order_by("pk").values()) == old_events

    @pytest.mark.parametrize("action", ["retry", "cleanup", "resume"])
    @pytest.mark.parametrize(
        "field,value", [("run_id", "not-a-uuid"), ("generation", "not-a-number")]
    )
    def test_malformed_controls_are_rejected_without_changing_the_run(
        self, action, field, value, admin_client, counters, owner, task_queue
    ):
        record, generation = start(task_queue, owner)
        before = snapshot()
        old_events = list(LedgerEvent.objects.order_by("pk").values())
        pause_before = WritePause.objects.filter(scope="n26").values().get()
        run_before = Backfill.objects.filter(pk=record.pk).values().get()
        queued_before = task_queue.pending()
        payload = {
            "action": action,
            "run_id": str(record.pk),
            "generation": generation,
            field: value,
        }

        with task_queue.capture():
            response = admin_client.post(
                reverse("admin:maintenance_n26_activate_counter_history"), payload
            )

        assert response.status_code == 200
        assert b"The write pause changed. Reload this page." in response.content
        assert not is_active()
        assert Backfill.objects.filter(pk=record.pk).values().get() == run_before
        assert task_queue.pending() == queued_before
        assert WritePause.objects.filter(scope="n26").values().get() == pause_before
        assert snapshot() == before
        assert list(LedgerEvent.objects.order_by("pk").values()) == old_events

    def test_existing_structured_history_refuses_activation_without_changing_data(
        self, counters, owner, task_queue
    ):
        LedgerEvent.objects.create(
            assignment=counters[0],
            gang=counters[0].gang,
            kind=LedgerEvent.Kind.COUNTER_CHECKPOINTED,
            batch=uuid4(),
            counter_before=0,
            counter_delta=0,
            counter_after=0,
        )
        before = snapshot()
        old_events = list(LedgerEvent.objects.order_by("pk").values())
        pause_before = WritePause.objects.filter(scope="n26").values().get()

        with (
            task_queue.capture(),
            pytest.raises(
                counter_activation.ActivationRefused,
                match="Structured counter history already exists",
            ),
        ):
            maintenance.start_counter_history(owner)

        assert not is_active()
        assert not Backfill.objects.filter(
            operation=maintenance.Operation.ACTIVATE_COUNTER_HISTORY
        ).exists()
        assert task_queue.pending() == 0
        assert WritePause.objects.filter(scope="n26").values().get() == pause_before
        assert snapshot() == before
        assert list(LedgerEvent.objects.order_by("pk").values()) == old_events

    def test_a_counter_without_a_gang_refuses_activation_without_changing_data(
        self, counters, owner, task_queue
    ):
        Assignment.objects.filter(pk=counters[0].pk).update(gang_root=None)
        before = snapshot()
        old_events = list(LedgerEvent.objects.order_by("pk").values())
        pause_before = WritePause.objects.filter(scope="n26").values().get()

        with (
            task_queue.capture(),
            pytest.raises(
                counter_activation.ActivationRefused,
                match="Repair counters without a gang before activation",
            ),
        ):
            maintenance.start_counter_history(owner)

        assert not is_active()
        assert not Backfill.objects.filter(
            operation=maintenance.Operation.ACTIVATE_COUNTER_HISTORY
        ).exists()
        assert task_queue.pending() == 0
        assert WritePause.objects.filter(scope="n26").values().get() == pause_before
        assert snapshot() == before
        assert list(LedgerEvent.objects.order_by("pk").values()) == old_events
        counters[0].refresh_from_db()
        assert counters[0].gang_root_id is None

    def test_activation_cannot_adopt_an_existing_generic_pause(
        self, admin_client, owner
    ):
        pause = pause_scope(
            "n26", actor=owner, reason="A separate repair is in progress."
        )

        with pytest.raises(
            counter_activation.ActivationRefused,
            match="A separate repair is in progress",
        ):
            maintenance.start_counter_history(owner)

        pause.refresh_from_db()
        assert pause.state == WritePause.State.PAUSED
        assert pause.permitted_task_name == ""
        assert pause.permitted_run_id == ""
        assert not Backfill.objects.filter(
            operation=maintenance.Operation.ACTIVATE_COUNTER_HISTORY
        ).exists()

        page = admin_client.get(
            reverse("admin:maintenance_n26_activate_counter_history")
        )
        assert b"A separate repair is in progress." in page.content
        assert b"Resume the existing write pause" in page.content
        assert b"Pause writes and activate counter history" not in page.content
