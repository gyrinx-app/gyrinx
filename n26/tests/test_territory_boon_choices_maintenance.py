"""The boon-choice conversion previews, queues and records one exclusive run."""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from gyrinx.maintenance.registry import resolve_operation
from gyrinx.site.models import WritePause
from gyrinx.tasks.worker import Outcome as TaskOutcome
from n26.library.core_campaign import seed_core_campaign
from n26.library.gang_supertypes import seed_gang_supertypes
from n26.library.models import Asset, Modifier
from n26.library.territory_boon_choices import NOTHING_TO_DO, preview, seed_all
from n26.library.territory_boons import seed_all as seed_baselines
from n26.maintenance import (
    LOCK_KEYS,
    Operation,
    seed_territory_boon_choices,
    task_routes,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def content():
    seed_core_campaign(apps)
    seed_gang_supertypes()
    seed_baselines()


@pytest.fixture
def address():
    return reverse("admin:maintenance_n26_seed_territory_boon_choices")


@pytest.fixture
def superuser():
    return User.objects.create_superuser("operator", "operator@example.com", "password")


def test_the_operation_has_a_separate_lock_and_exclusive_task_route():
    operation = Operation.SEED_TERRITORY_BOON_CHOICES
    assert LOCK_KEYS[operation] == 826_020_632
    assert len(set(LOCK_KEYS.values())) == len(LOCK_KEYS)
    registered = resolve_operation(operation.value)
    assert registered.view is not None
    assert registered.write_scope is None
    route = next(
        route for route in task_routes if route.func == seed_territory_boon_choices
    )
    assert route.exclusive_write


def test_a_superuser_preview_shows_existing_holder_effects_without_writing(
    client, superuser, content, address
):
    client.force_login(superuser)
    before = (Asset.objects.count(), Modifier.objects.count(), Backfill.objects.count())
    response = client.get(address)
    assert response.status_code == 200
    body = response.content.decode()
    assert "What it would do" in body
    assert "current owners start with Income selected" in body
    assert "recruitment discount or equipment reward manually" in body
    assert "Settlement" in body and "Forge Patcher recruitment" in body
    assert (
        Asset.objects.count(),
        Modifier.objects.count(),
        Backfill.objects.count(),
    ) == before


def test_posting_records_exact_preview_and_a_redelivery_stands_down(
    client, superuser, content, address, task_queue
):
    client.force_login(superuser)
    planned = preview()
    with task_queue.capture():
        response = client.post(address)
    record = Backfill.objects.get(operation=Operation.SEED_TERRITORY_BOON_CHOICES)
    assert response.status_code == 302
    assert record.summary["preview"] == planned
    assert record.status == Backfill.Status.RUNNING
    assert Asset.objects.count() == 31
    task_queue.deliver_all()
    task_queue.redeliver_last()
    record.refresh_from_db()
    assert record.status == Backfill.Status.DONE
    assert record.summary["report"] == planned
    assert record.summary["attempts"] == 1
    assert Asset.objects.count() == 31
    assert Asset.objects.get(name="Settlement").income == 15
    assert Asset.objects.filter(base_income_modifier__isnull=False).count() == 12
    body = client.get(
        reverse("admin:maintenance_backfill_detail", args=[record.pk])
    ).content.decode()
    assert "What it did" in body
    assert "Ammo-Jack recruitment" in body


def test_a_rerun_with_nothing_to_change_records_no_run(
    client, superuser, content, address
):
    seed_all()
    client.force_login(superuser)
    response = client.post(address, follow=True)
    assert NOTHING_TO_DO in response.content.decode()
    assert not Backfill.objects.exists()
    assert "Nothing to change" in client.get(address).content.decode()


def test_a_running_update_is_reused_instead_of_enqueuing_another(
    client, superuser, content, address, task_queue
):
    client.force_login(superuser)
    with task_queue.capture():
        client.post(address)
        response = client.post(address)
    record = Backfill.objects.get(operation=Operation.SEED_TERRITORY_BOON_CHOICES)
    assert str(record.pk) in response["Location"]
    assert Backfill.objects.count() == 1


@pytest.mark.django_db(transaction=True)
def test_concurrent_submissions_share_one_committed_run_and_exact_preview(
    superuser, content, address, task_queue, monkeypatch
):
    import importlib
    import threading

    from django.db import close_old_connections, connection
    from django.test import Client

    from gyrinx.tasks.local_backend import DatabaseBackend

    library = importlib.import_module("n26.library.territory_boon_choices")
    admission = importlib.import_module("gyrinx.site.write_pause")
    planned = preview()
    before = (Asset.objects.count(), Modifier.objects.count())
    original_preview = library.preview
    original_advisory = admission._advisory
    original_enqueue = DatabaseBackend.enqueue
    first_preview_started = threading.Event()
    second_admission_started = threading.Event()
    responses = []
    errors = []
    enqueued = []
    backend_pids = []

    def preview_after_second_submission_starts():
        if threading.current_thread() is first:
            first_preview_started.set()
            assert second_admission_started.wait(10)
        return original_preview()

    def observed_advisory(function, scope):
        if (
            threading.current_thread() is second
            and scope == "n26"
            and function == "pg_advisory_xact_lock"
        ):
            second_admission_started.set()
        return original_advisory(function, scope)

    def enqueue_after_commit(backend, task, args, kwargs):
        if task.func is seed_territory_boon_choices.func:
            assert not connection.in_atomic_block
            enqueued.append(kwargs["backfill_id"])
        return original_enqueue(backend, task, args, kwargs)

    def post():
        close_old_connections()
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT pg_backend_pid()")
                backend_pids.append(cursor.fetchone()[0])
            request_client = Client()
            request_client.force_login(User.objects.get(pk=superuser.pk))
            responses.append(request_client.post(address))
        except Exception as exc:
            errors.append(exc)
        finally:
            close_old_connections()

    first = threading.Thread(target=post)
    second = threading.Thread(target=post)
    monkeypatch.setattr(library, "preview", preview_after_second_submission_starts)
    monkeypatch.setattr(admission, "_advisory", observed_advisory)
    monkeypatch.setattr(DatabaseBackend, "enqueue", enqueue_after_commit)
    try:
        first.start()
        assert first_preview_started.wait(10)
        second.start()
    finally:
        first.join(15)
        if second.ident is not None:
            second.join(15)

    assert not first.is_alive()
    assert not second.is_alive()
    assert errors == []
    assert len(set(backend_pids)) == 2
    assert len(responses) == 2
    assert all(response.status_code == 302 for response in responses)
    record = Backfill.objects.get(operation=Operation.SEED_TERRITORY_BOON_CHOICES)
    assert record.status == Backfill.Status.RUNNING
    assert record.summary == {"preview": planned, "attempts": 0}
    assert responses[0]["Location"] == responses[1]["Location"]
    assert str(record.pk) in responses[0]["Location"]
    assert enqueued == [str(record.pk)]
    assert task_queue.pending() == 1
    assert (Asset.objects.count(), Modifier.objects.count()) == before


def test_a_paused_delivery_does_not_change_content_or_consume_an_attempt(
    content, task_queue
):
    record = Backfill.objects.create(
        operation=Operation.SEED_TERRITORY_BOON_CHOICES,
        status=Backfill.Status.RUNNING,
        summary={"attempts": 0},
    )
    with task_queue.capture():
        seed_territory_boon_choices.enqueue(backfill_id=str(record.pk))
    WritePause.objects.filter(scope="n26").update(state=WritePause.State.PAUSED)
    assert task_queue.deliver_next() == TaskOutcome.DEFERRED
    record.refresh_from_db()
    assert record.summary["attempts"] == 0
    assert Asset.objects.count() == 31
    WritePause.objects.filter(scope="n26").update(state=WritePause.State.OPEN)
    task_queue.deliver_all()
    record.refresh_from_db()
    assert record.status == Backfill.Status.DONE
    assert record.summary["attempts"] == 1


def test_only_a_superuser_can_preview_or_apply(client, content, address):
    user = User.objects.create_user("staff", is_staff=True)
    client.force_login(user)
    assert client.get(address).status_code in (302, 403)
    assert client.post(address).status_code in (302, 403)
    assert not Backfill.objects.exists()
    assert Asset.objects.count() == 31


def test_a_preview_error_is_shown_and_posting_records_no_run(
    client, superuser, content, address, monkeypatch
):
    import importlib

    from django.core.exceptions import ValidationError

    library = importlib.import_module("n26.library.territory_boon_choices")

    def unavailable():
        raise ValidationError("An authored graph is inconsistent.")

    monkeypatch.setattr(library, "preview", unavailable)
    client.force_login(superuser)
    response = client.get(address)
    assert response.status_code == 200
    assert "An authored graph is inconsistent." in response.content.decode()
    response = client.post(address, follow=True)
    assert "The content update cannot run" in response.content.decode()
    assert not Backfill.objects.exists()
    assert not Asset.objects.filter(base_income_modifier__isnull=False).exists()


def test_a_failed_recorded_conversion_rolls_back_content_and_keeps_its_error(
    content, task_queue, monkeypatch
):
    import importlib

    from n26.library.models import Pickable, Slot

    library = importlib.import_module("n26.library.territory_boon_choices")
    original_create = library._create
    before = (Modifier.objects.count(), Slot.objects.count(), Pickable.objects.count())

    def fail_after_conversion(*args):
        original_create(*args)
        raise RuntimeError("Forced conversion failure.")

    monkeypatch.setattr(library, "_create", fail_after_conversion)
    record = Backfill.objects.create(
        operation=Operation.SEED_TERRITORY_BOON_CHOICES,
        status=Backfill.Status.RUNNING,
        summary={"attempts": 0},
    )
    with task_queue.capture():
        seed_territory_boon_choices.enqueue(backfill_id=str(record.pk))
    task_queue.deliver_all()
    task_queue.redeliver_last()
    record.refresh_from_db()
    assert record.status == Backfill.Status.FAILED
    assert "Forced conversion failure." in record.error
    assert record.summary["attempts"] == 1
    assert not Asset.objects.filter(base_income_modifier__isnull=False).exists()
    assert (
        Modifier.objects.count(),
        Slot.objects.count(),
        Pickable.objects.count(),
    ) == before
