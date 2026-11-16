"""Adding upcoming pattern slots saves editable entries without activating a cycle."""

from dataclasses import replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import User

from gyrinx.site.models import Availability, FeatureFlag
from n26.core import cycles
from n26.core import schedule as s
from n26.core.campaigns import campaign_operation
from n26.core.cycle_data import template_data
from n26.core.models import CampaignCycle, CampaignCycleCommand
from n26.core.operations import Refusal
from n26.flags import CYCLE_TRACKING
from n26.tests.sandbox.actions import found_campaign
from n26.tests.test_timeline_commands import snapshot

pytestmark = pytest.mark.django_db


@pytest.fixture
def table(campaign_type, request):
    owner = User.objects.create_user("pattern-arbitrator")
    flag = FeatureFlag.objects.create(
        slug=CYCLE_TRACKING, name="Campaign cycles", availability=Availability.EVERYONE
    )
    campaign = found_campaign("Pattern campaign", campaign_type, owner=owner)
    cycles.configure(
        campaign,
        actor=owner,
        template_id="",
        definition=template_data(s.DEFAULT_TEMPLATE),
        current_position=getattr(request, "param", 0),
        mode="repeating",
        request_key=uuid4(),
    )
    return SimpleNamespace(
        owner=owner, campaign=campaign, flag=flag, state=cycles.load(campaign)
    )


def add(table, count, *, expected_revision=None, request_key=None, actor=None):
    return cycles.plan_cycles(
        table.campaign,
        actor=actor or table.owner,
        count=count,
        expected_revision=cycles.load(table.campaign).revision
        if expected_revision is None
        else expected_revision,
        request_key=request_key or uuid4(),
    )


def stored(ids):
    return list(CampaignCycle.objects.filter(pk__in=ids).order_by("pk").values())


@pytest.mark.parametrize("table", [None, 0], indirect=True)
def test_adding_pattern_slots_preserves_current_selection_and_does_not_activate_any_cycle(
    table,
):
    before = table.state
    old_ids = [c.id for c in before.cycles]
    original_rows = stored(old_ids)
    history = snapshot(table)
    result = add(table, 2)
    after = cycles.load(table.campaign)
    added = [c for c in after.cycles if c.id not in old_ids]
    assert len(added) == 2
    assert [c.source.position.index for c in added] == [
        before.next_position,
        before.next_position + 1,
    ]
    assert after.next_position == before.next_position + 2
    assert after.plan == before.plan
    assert after.current_cycle_id == before.current_cycle_id
    assert after.status == before.status
    assert result.cycle_id == added[-1].id and result.transition_id is None
    assert stored(old_ids) == original_rows
    for key in ("CampaignCycleTransition", "deliveries", "notifications"):
        assert snapshot(table)[key] == history[key]
    assert [c.order for c in after.cycles if not c.archived] == list(
        range(1, len(after.cycles) + 1)
    )
    receipt = CampaignCycleCommand.objects.get(
        campaign=table.campaign, kind="plan_cycles"
    )
    assert receipt.inputs == {"count": 2, "expected_revision": before.revision}


def test_authored_insert_consumes_no_pattern_slot_and_later_planning_preserves_customisations(
    table,
):
    first = add(table, 1)
    before = cycles.load(table.campaign)
    selected = next(c for c in before.cycles if c.id == first.cycle_id)
    cycles.edit_cycle(
        table.campaign,
        actor=table.owner,
        target=s.SavedCycleRef(selected.id),
        details=replace(
            selected.details,
            custom_name="Market week",
            description="Keep this story",
            effects="Keep this effect",
        ),
        expected_revision=before.revision,
        request_key=uuid4(),
    )
    before = cycles.load(table.campaign)
    cycles.author_timeline(
        table.campaign,
        actor=table.owner,
        action="insert_cycle",
        occurrence_id=selected.occurrence_id,
        after_cycle_id=selected.id,
        expected_revision=before.revision,
        request_key=uuid4(),
    )
    authored = cycles.load(table.campaign)
    assert authored.next_position == before.next_position
    assert len(authored.cycles) == len(before.cycles) + 1
    assert authored.cycles[-1].source == s.CycleSource()
    ids = [c.id for c in authored.cycles]
    original_rows = stored(ids)
    add(table, 2)
    after = cycles.load(table.campaign)
    assert after.next_position == before.next_position + 2
    assert stored(ids) == original_rows
    assert len(after.cycles) == len(authored.cycles) + 2
    assert [c.source.position.index for c in after.cycles if c.id not in ids] == [
        before.next_position,
        before.next_position + 1,
    ]


def test_known_retry_replays_after_mode_change_but_changed_count_and_other_actors_refuse(
    table,
):
    before = table.state
    key = uuid4()
    result = add(table, 2, expected_revision=before.revision, request_key=key)
    planned = cycles.load(table.campaign)
    cycles.replace_plan(
        table.campaign,
        actor=table.owner,
        steps=s.editable_steps(planned),
        mode="fixed",
        expected_revision=planned.revision,
        request_key=uuid4(),
    )
    player = User.objects.create_user("pattern-participant")
    with campaign_operation(table.campaign, actor=table.owner) as act:
        act.invite(player)
    with campaign_operation(table.campaign, actor=player) as act:
        act.answer_invitation(player, True)
    current = snapshot(table)
    replay = add(table, 2, expected_revision=before.revision, request_key=key)
    assert (
        replay.replayed
        and replay.cycle_id == result.cycle_id
        and replay.revision == result.revision
    )
    assert snapshot(table) == current
    assert cycles.load(table.campaign).plan.mode == "fixed"
    with pytest.raises(cycles.CycleKeyConflict):
        add(table, 3, expected_revision=before.revision, request_key=key)
    with pytest.raises(Refusal):
        add(table, 2, expected_revision=before.revision, request_key=key, actor=player)
    assert snapshot(table) == current
    with pytest.raises(Refusal, match="Only a repeating pattern"):
        add(table, 1)
    assert snapshot(table) == current
    table.flag.availability = Availability.OFF
    table.flag.save()
    with pytest.raises(Refusal, match="not available"):
        add(table, 2, expected_revision=before.revision, request_key=key)
    assert snapshot(table) == current


@pytest.mark.parametrize("count", [0, cycles.MAX_PREFIX + 1, True])
def test_invalid_counts_are_refused_without_creating_any_receipt_or_cycle(table, count):
    before = snapshot(table)
    with pytest.raises(Refusal, match="between 1 and 1,000"):
        add(table, count)
    assert snapshot(table) == before


def test_a_stale_revision_is_rejected_before_new_count_validation(table):
    before = table.state
    add(table, 1)
    current = snapshot(table)
    with pytest.raises(cycles.CycleConflict, match="schedule changed"):
        add(table, 0, expected_revision=before.revision)
    assert snapshot(table) == current
