"""The retained delete transport enforces timeline protection after receipt replay."""

from datetime import date
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import User

from gyrinx.site.models import Availability, FeatureFlag
from n26.core import cycles
from n26.core import schedule as s
from n26.core.campaigns import campaign_operation
from n26.core.cycle_data import template_data
from n26.core.models import CampaignCycle, CampaignCycleTransition
from n26.core.operations import Refusal
from n26.flags import CYCLE_TRACKING
from n26.tests.sandbox.actions import found_campaign
from n26.tests.test_timeline_commands import snapshot

pytestmark = pytest.mark.django_db


@pytest.fixture
def table(campaign_type):
    owner = User.objects.create_user("delete-protection-arbitrator")
    FeatureFlag.objects.create(
        slug=CYCLE_TRACKING, name="Campaign cycles", availability=Availability.EVERYONE
    )
    campaign = found_campaign("Protected planning", campaign_type, owner=owner)
    cycles.configure(
        campaign,
        actor=owner,
        template_id="",
        definition=template_data(s.DEFAULT_TEMPLATE),
        current_position=3,
        mode="fixed",
        request_key=uuid4(),
    )
    return SimpleNamespace(campaign=campaign, owner=owner, state=cycles.load(campaign))


@pytest.mark.parametrize("position", [1, 3])
def test_current_and_earlier_cycles_are_protected_even_without_recorded_activity(
    table, position
):
    state = table.state
    assert state.current.order == 4 and not state.protected_cycle_ids
    assert not CampaignCycleTransition.objects.filter(campaign=table.campaign).exists()
    selected = state.cycles[position]
    before = snapshot(table)
    with pytest.raises(Refusal, match="Current and earlier cycles"):
        cycles.delete_cycle(
            table.campaign,
            actor=table.owner,
            target=s.SavedCycleRef(selected.id),
            expected_revision=state.revision,
            request_key=uuid4(),
        )
    assert snapshot(table) == before


def test_a_committed_future_delete_still_replays_after_its_target_is_archived(table):
    state = table.state
    selected = state.cycles[5]
    key = uuid4()
    arguments = {
        "actor": table.owner,
        "target": s.SavedCycleRef(selected.id),
        "expected_revision": state.revision,
        "request_key": key,
    }
    result = cycles.delete_cycle(table.campaign, **arguments)
    assert CampaignCycle.objects.get(pk=selected.id).archived
    before = snapshot(table)
    replay = cycles.delete_cycle(table.campaign, **arguments)
    assert replay.replayed and replay.revision == result.revision
    assert snapshot(table) == before
    assert cycles.load(table.campaign).current_cycle_id == state.current_cycle_id


def test_deleting_an_unused_future_cycle_cannot_shift_a_later_recorded_cycle(table):
    state = table.state
    with campaign_operation(table.campaign, actor=table.owner) as act:
        battle = act.record_battle(
            date=date(2026, 11, 16),
            scenario="Recorded future",
            cycle=s.SavedCycleRef(state.cycles[6].id),
        )
    before = snapshot(table)
    with pytest.raises(Refusal, match="recorded activity"):
        cycles.delete_cycle(
            table.campaign,
            actor=table.owner,
            target=s.SavedCycleRef(state.cycles[4].id),
            expected_revision=state.revision,
            request_key=uuid4(),
        )
    assert snapshot(table) == before
    assert CampaignCycle.objects.get(pk=battle.cycle_id).order == 7


@pytest.mark.parametrize("replace_current", [False, True])
def test_an_explicit_unstarted_current_choice_can_be_cleared_or_replaced_without_activation(
    table, replace_current
):
    state = table.state
    selected = state.current
    assert state.status == "pre_campaign" and not state.protected_cycle_ids
    key = uuid4()
    choice = (
        {"replacement": s.SavedCycleRef(state.cycles[4].id)}
        if replace_current
        else {"no_current": True}
    )
    arguments = {
        "actor": table.owner,
        "target": s.SavedCycleRef(selected.id),
        "expected_revision": state.revision,
        "request_key": key,
        **choice,
    }
    result = cycles.delete_cycle(table.campaign, **arguments)
    after = cycles.load(table.campaign)
    assert after.current_cycle_id == (state.cycles[4].id if replace_current else None)
    assert after.status == state.status
    assert result.transition_id is None
    assert next(c for c in after.cycles if c.id == selected.id).archived
    assert {c.id: c.source for c in after.cycles} == {
        c.id: c.source for c in state.cycles
    }
    assert not CampaignCycleTransition.objects.filter(campaign=table.campaign).exists()
    before_retry = snapshot(table)
    assert cycles.delete_cycle(table.campaign, **arguments).replayed
    assert snapshot(table) == before_retry
