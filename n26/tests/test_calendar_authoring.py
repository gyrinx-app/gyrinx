"""Settings retains month-end defaults after arbitrators arrange future cycles."""

from dataclasses import replace
from datetime import date
from uuid import uuid4

import pytest
from django.contrib.auth.models import User

from gyrinx.site.models import Availability, FeatureFlag
from n26.core import cycles
from n26.core import schedule as s
from n26.core.cycle_data import calendar_data, template_data
from n26.core.cycle_display import editor_url, schedule_url
from n26.core.models import (
    CampaignCycle,
    CampaignCycleCommand,
    CampaignPhase,
    CampaignPhaseOccurrence,
    CampaignPlan,
    CampaignSchedule,
)
from n26.flags import CYCLE_TRACKING
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def monthly(campaign_type, client):
    owner = User.objects.create_user("calendar-arbitrator")
    client.force_login(owner)
    FeatureFlag.objects.create(
        slug=CYCLE_TRACKING,
        name="Campaign cycles",
        availability=Availability.EVERYONE,
    )
    campaign = found_campaign("Month-end campaign", campaign_type, owner=owner)
    cycles.configure(
        campaign,
        actor=owner,
        template_id="",
        definition=template_data(s.DEFAULT_TEMPLATE),
        current_position=0,
        mode="repeating",
        request_key=uuid4(),
        calendar=s.CycleCalendar(date(2026, 1, 31), unit="months"),
    )
    state = cycles.load(campaign)
    target = s.project(state, limit=6)[-1]
    cycles.edit_cycle(
        campaign,
        actor=owner,
        target=target.ref,
        details=s.CycleDetails(
            target.phase_id, starts_on=target.starts_on, ends_on=target.ends_on
        ),
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    return campaign, owner, cycles.load(campaign)


@pytest.fixture
def with_appends(monthly):
    campaign, owner, state = monthly
    for name in ("Market week", "Council week"):
        tail = next(c for c in reversed(state.cycles) if not c.archived)
        cycles.author_timeline(
            campaign,
            actor=owner,
            action="insert_cycle",
            occurrence_id=tail.occurrence_id,
            after_cycle_id=tail.id,
            details=s.CycleDetails(tail.details.phase_id, custom_name=name),
            expected_revision=state.revision,
            request_key=uuid4(),
        )
        state = cycles.load(campaign)
    return campaign, owner, state


def settings(client, campaign):
    response = client.get(
        editor_url(campaign, "plan"), headers={"Accept": "application/json"}
    )
    assert response.status_code == 200
    return response.json()["schedule"]["editor"]


def snapshot(campaign):
    return {
        model.__name__: list(
            model.objects.filter(campaign=campaign).order_by("pk").values()
        )
        for model in (
            CampaignCycle,
            CampaignCycleCommand,
            CampaignPhase,
            CampaignPhaseOccurrence,
            CampaignPlan,
            CampaignSchedule,
        )
    }


def test_unchanged_settings_retains_january_anchor_offset_and_august_tail(
    client, with_appends
):
    campaign, owner, before = with_appends
    frozen = snapshot(campaign)
    editor = settings(client, campaign)
    assert snapshot(campaign) == frozen
    assert editor["values"]["date_start"] == "2026-02-28"
    assert editor["context"]["nextCycleNumber"] == 2
    assert before.calendar.position_offset == -2
    original = s.project(before, limit=1)[0]
    response = client.post(editor["commandHref"], editor["values"])
    assert response.status_code == 200, response.content.decode()
    assert (
        client.post(editor["commandHref"], editor["values"]).json() == response.json()
    )
    after = cycles.load(campaign)
    assert after == before
    assert after.calendar.starts_on == date(2026, 1, 31)
    assert after.calendar.position_offset == -2
    following = s.project(after, limit=1)[0]
    assert following.source == original.source
    assert following.starts_on == date(2026, 8, 31)
    assert following.ends_on == date(2026, 9, 29)
    header = CampaignSchedule.objects.get(campaign=campaign)
    assert header.date_settings["position_offset"] == -2
    receipt = CampaignCycleCommand.objects.get(
        request_key=editor["values"]["request_key"]
    )
    assert "position_offset" not in receipt.inputs["calendar"]


def test_changed_monthly_defaults_are_accepted_and_keep_explicit_bounds(
    client, with_appends
):
    campaign, owner, before = with_appends
    pinned = before.cycles[2]
    cycles.edit_cycle(
        campaign,
        actor=owner,
        target=s.SavedCycleRef(pinned.id),
        details=replace(
            pinned.details, starts_on=date(2026, 4, 5), ends_on=date(2026, 4, 25)
        ),
        expected_revision=before.revision,
        request_key=uuid4(),
    )
    before = cycles.load(campaign)
    editor = settings(client, campaign)
    values = {**editor["values"], "date_start": "2026-03-01"}
    response = client.post(editor["commandHref"], values)
    assert response.status_code == 200, response.content.decode()
    after = cycles.load(campaign)
    assert after.calendar.starts_on == date(2026, 3, 1)
    assert after.calendar.position_offset == 0
    assert after.calendar.starts_after_order == 1
    assert after.cycles[1].details.starts_on == date(2026, 3, 1)
    assert after.cycles[2].details == before.cycles[2].details
    assert after.cycles[7:] == before.cycles[7:]
    assert [(c.id, c.source) for c in after.cycles] == [
        (c.id, c.source) for c in before.cycles
    ]
    assert after.next_position == before.next_position == 7
    assert client.post(editor["commandHref"], values).json() == response.json()
    assert cycles.load(campaign) == after


def test_programmatic_unchanged_calendar_keeps_legacy_command_receipt_shape(
    with_appends,
):
    campaign, owner, before = with_appends
    key = uuid4()
    args = dict(
        actor=owner,
        steps=before.plan.steps,
        mode="repeating",
        calendar=before.calendar,
        expected_revision=before.revision,
        request_key=key,
    )
    first = cycles.replace_plan(campaign, **args)
    assert cycles.replace_plan(campaign, **args).replayed
    assert cycles.load(campaign) == before
    receipt = CampaignCycleCommand.objects.get(request_key=key)
    assert receipt.inputs["calendar"] == calendar_data(before.calendar)
    assert "position_offset" not in receipt.inputs["calendar"]
    assert first.revision == before.revision


def test_legacy_calendar_reads_preserve_database_rows_and_skip_archived_slots(
    client, monthly
):
    campaign, owner, before = monthly
    header = CampaignSchedule.objects.get(campaign=campaign)
    legacy = dict(header.date_settings)
    legacy.pop("position_offset")
    CampaignSchedule.objects.filter(pk=header.pk).update(date_settings=legacy)
    CampaignCycle.objects.filter(pk=before.cycles[5].id).update(archived=True)
    frozen = snapshot(campaign)
    loaded = cycles.load(campaign)
    assert loaded.calendar.position_offset == 1
    assert s.project(loaded, limit=1)[0].starts_on == date(2026, 8, 31)
    assert settings(client, campaign)["values"]["date_start"] == "2026-02-28"
    overview = client.get(
        schedule_url(campaign), headers={"Accept": "application/json"}
    )
    assert overview.status_code == 200
    assert snapshot(campaign) == frozen
