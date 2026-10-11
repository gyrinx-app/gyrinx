"""The standing content pass previews, queues and records its own maintenance run."""

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
from n26.library.territory_boons import NOTHING_TO_DO, preview, seed_all
from n26.maintenance import LOCK_KEYS, Operation, seed_territory_boons, task_routes

pytestmark = pytest.mark.django_db


@pytest.fixture
def content(default_pack):
    seed_core_campaign(apps)
    seed_gang_supertypes()


@pytest.fixture
def address():
    return reverse("admin:maintenance_n26_seed_territory_boons")


@pytest.fixture
def superuser():
    return User.objects.create_superuser("operator", "operator@example.com", "password")


def test_the_operation_has_a_separate_lock_and_exclusive_task_route():
    operation = Operation.SEED_TERRITORY_BOONS
    assert LOCK_KEYS[operation] == 826_020_631
    assert len(set(LOCK_KEYS.values())) == len(LOCK_KEYS)
    registered = resolve_operation(operation.value)
    assert registered.view is not None
    assert registered.write_scope is None
    route = next(route for route in task_routes if route.func == seed_territory_boons)
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
    assert "current holders immediately" in body
    assert "recruitment discounts or stash rewards" in body
    assert "Amneo-vats" in body and "Generatorium" in body
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
    record = Backfill.objects.get(operation=Operation.SEED_TERRITORY_BOONS)
    assert response.status_code == 302
    assert record.summary["preview"] == planned
    assert record.status == Backfill.Status.RUNNING
    assert Asset.objects.count() == 1
    task_queue.deliver_all()
    task_queue.redeliver_last()
    record.refresh_from_db()
    assert record.status == Backfill.Status.DONE
    assert record.summary["report"] == planned
    assert record.summary["attempts"] == 1
    assert Asset.objects.count() == 31
    assert Asset.objects.get(name="Settlement").income == 15
    body = client.get(
        reverse("admin:maintenance_backfill_detail", args=[record.pk])
    ).content.decode()
    assert "What it did" in body
    assert "Generatorium" in body


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
    record = Backfill.objects.get(operation=Operation.SEED_TERRITORY_BOONS)
    assert str(record.pk) in response["Location"]
    assert Backfill.objects.count() == 1


def test_a_paused_delivery_does_not_change_content_or_consume_an_attempt(
    content, task_queue
):
    record = Backfill.objects.create(
        operation=Operation.SEED_TERRITORY_BOONS,
        status=Backfill.Status.RUNNING,
        summary={"attempts": 0},
    )
    with task_queue.capture():
        seed_territory_boons.enqueue(backfill_id=str(record.pk))
    WritePause.objects.filter(scope="n26").update(state=WritePause.State.PAUSED)
    assert task_queue.deliver_next() == TaskOutcome.DEFERRED
    record.refresh_from_db()
    assert record.summary["attempts"] == 0
    assert Asset.objects.count() == 1
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
    assert Asset.objects.count() == 1
