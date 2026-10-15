"""The reputation correction previews and records an idempotent task."""

import pytest
from django.apps import apps
from django.contrib.auth.models import User
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from n26.core.models import CounterValue, LedgerEvent
from n26.library.core_campaign import seed_core_campaign
from n26.library.models import CampaignType
from n26.maintenance import Operation
from n26.tests.sandbox.actions import found_campaign, found_gang, join_campaign

pytestmark = pytest.mark.django_db


def test_preview_then_task_corrects_once_and_preserves_credits(
    client, gang_type, default_pack, task_queue
):
    user = User.objects.create_superuser("operator", "operator@example.com", "password")
    seed_core_campaign(apps)
    campaign = found_campaign(
        "Dust Falls", CampaignType.objects.get(name="Territory campaign"), owner=user
    )
    gang = found_gang("Ash Cats", gang_type, owner=user)
    join_campaign(gang, campaign)
    held = gang.assignments.get(archived=False, counter__name="Reputation")
    CounterValue.objects.filter(assignment=held).update(value=0)
    client.force_login(user)
    address = reverse("admin:maintenance_n26_repair_campaign_reputation")
    response = client.get(address)
    assert response.status_code == 200
    assert "Ash Cats" in response.content.decode()
    held.counter_value.refresh_from_db()
    assert held.counter_value.value == 0
    assert not Backfill.objects.exists()
    with task_queue.capture():
        response = client.post(address)
    assert response.status_code == 302
    record = Backfill.objects.get(operation=Operation.REPAIR_CAMPAIGN_REPUTATION)
    assert record.status == Backfill.Status.RUNNING
    task_queue.deliver_all()
    task_queue.redeliver_last()
    record.refresh_from_db()
    assert record.status == Backfill.Status.DONE
    held.counter_value.refresh_from_db()
    assert held.counter_value.value == 1
    assert (
        LedgerEvent.objects.filter(
            assignment=held, kind=LedgerEvent.Kind.TALLIED
        ).count()
        == 1
    )
    assert "corrected 1" in record.summary["report"][0]
    response = client.post(address, follow=True)
    assert response.status_code == 200
    assert Backfill.objects.count() == 1
