"""Legacy fixed plans keep their endpoint and remain editable without GET writes."""

from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.db import connection
from django.test.utils import CaptureQueriesContext

from gyrinx.site.models import Availability, FeatureFlag
from n26.core import cycles
from n26.core import schedule as s
from n26.core.cycle_data import template_data
from n26.core.cycle_display import build, dashboard_summary, editor_url
from n26.core.models import CampaignCycle, CampaignPlan, CampaignSchedule
from n26.flags import CYCLE_TRACKING
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def table(client, campaign_type):
    actor = User.objects.create_user("legacy-fixed-timeline")
    client.force_login(actor)
    FeatureFlag.objects.create(slug=CYCLE_TRACKING, availability=Availability.EVERYONE)
    campaign = found_campaign("Legacy fixed timeline", campaign_type, owner=actor)
    cycles.configure(
        campaign,
        actor=actor,
        template_id="",
        definition=template_data(s.DEFAULT_TEMPLATE),
        mode="repeating",
        current_position=0,
        request_key=uuid4(),
    )
    state = cycles.load(campaign)
    CampaignPlan.objects.filter(pk=state.plan.id).update(mode="fixed")
    return campaign, actor, cycles.load(campaign)


def test_gapped_last_saved_cycle_offers_finish_without_changing_records(table):
    campaign, actor, state = table
    target = s.project(state, limit=6)[-1]
    cycles.edit_cycle(
        campaign,
        actor=actor,
        target=target.ref,
        details=s.CycleDetails(target.phase_id),
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    state = cycles.load(campaign)
    CampaignSchedule.objects.filter(campaign=campaign).update(
        current_cycle_id=state.cycles[-1].id
    )
    cycles.start(
        campaign,
        actor=actor,
        expected_current=state.cycles[-1].id,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    CampaignCycle.objects.filter(pk=state.cycles[1].id).update(archived=True)
    with CaptureQueriesContext(connection) as queries:
        display = build(campaign, actor)
    assert display.actions["transition"] == editor_url(campaign, "finish")
    assert dashboard_summary(campaign, actor).action_href == editor_url(
        campaign, "finish"
    )
    assert CampaignCycle.objects.get(pk=state.cycles[-1].id).order == 7
    assert not any(
        q["sql"].lstrip().startswith(("INSERT", "UPDATE", "DELETE")) for q in queries
    )


@pytest.mark.parametrize("native", [False, True])
def test_fixed_planned_cycle_edit_is_offered_and_saves_only_on_submit(
    client, table, native
):
    campaign, actor, state = table
    before = list(CampaignCycle.objects.filter(campaign=campaign).values())
    display = build(campaign, actor)
    future = [row for row in display.rows if row.state == "Projected"]
    assert len(future) == 6
    assert all(row.editablePreview and row.editHref for row in future)
    assert list(CampaignCycle.objects.filter(campaign=campaign).values()) == before
    selected = future[0]
    response = client.get(selected.editHref, headers={"Accept": "application/json"})
    editor = response.json()["schedule"]["editor"]
    data = {**editor["values"], "custom_name": "Planned market"}
    result = client.post(editor["action"] if native else editor["commandHref"], data)
    assert result.status_code == (302 if native else 200)
    after = cycles.load(campaign)
    assert len([cycle for cycle in after.cycles if not cycle.archived]) == 2
    assert after.cycles[1].name == "Planned market"
    assert after.current_cycle_id == state.current_cycle_id
    assert after.status == "pre_campaign"
    assert (
        str(
            CampaignCycle.objects.filter(campaign=campaign).order_by("order").first().pk
        )
        == state.cycles[0].id
    )
