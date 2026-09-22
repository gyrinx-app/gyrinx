"""The measured reset runs through the real maintenance console."""

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext
from django.urls import reverse

from gyrinx.maintenance.models import Backfill
from n26 import maintenance
from n26.core import reset_spyrer_built_ins as reset
from n26.core.models import ActionRecord, Assignment, Gang
from n26.tests.sandbox.actions import found_gang
from n26.tests.sandbox.test_reset_spyrer_built_ins import setup  # noqa: F401

pytestmark = pytest.mark.django_db


def test_the_console_resets_115_gangs_and_redelivery_is_harmless(setup, client, owner):  # noqa: F811
    with CaptureQueriesContext(connection) as small:
        assert reset.find().ok
    for index in range(114):
        found_gang(f"Reset {index}", setup.gang_type, owner=owner, budget=1000)
    with CaptureQueriesContext(connection) as large:
        plan = reset.find()
    assert len(plan.gangs) == 115
    assert len(large) == len(small)
    staff = User.objects.create_superuser("reset-admin", password="test")
    client.force_login(staff)
    address = reverse("admin:maintenance_n26_reset_spyrer_built_ins")
    page = client.get(address)
    assert page.status_code == 200
    assert "460 propagated assignments across 115 gangs" in page.content.decode()
    assert (
        Assignment.objects.filter(materialised_from_id__in=reset.MEMBERS).count() == 460
    )
    assert not Backfill.objects.exists()

    assert client.post(address).status_code == 302
    run = Backfill.objects.get(operation=maintenance.Operation.RESET_SPYRER_BUILT_INS)
    assert run.status == Backfill.Status.DONE, run.error
    assert len(run.summary["gang_ids"]) == 115
    assert reset.find().nothing_here
    assert not ActionRecord.objects.filter(pk__in=reset.USES).exists()
    assert Gang.objects.filter(gang_type=setup.gang_type).count() == 115
    assert Assignment.objects.filter(rule=setup.kept_rule).count() == 115
    summary = run.summary
    maintenance.reset_spyrer_built_ins.call(backfill_id=str(run.pk))
    run.refresh_from_db()
    assert run.summary == summary
    assert client.post(address).status_code == 302
    assert Backfill.objects.count() == 1


def test_the_reset_console_requires_a_superuser(client, owner):
    client.force_login(owner)
    response = client.post(reverse("admin:maintenance_n26_reset_spyrer_built_ins"))
    assert response.status_code in (302, 403)
    assert not Backfill.objects.exists()
