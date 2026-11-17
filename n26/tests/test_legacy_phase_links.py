"""Retained definition links can save one unambiguous phase block without changing retries."""

import json
from dataclasses import asdict
from types import SimpleNamespace
from uuid import uuid4

import pytest
from bs4 import BeautifulSoup
from django.contrib.auth.models import User

from gyrinx.site.models import Availability, FeatureFlag
from n26.core import cycles
from n26.core import schedule as s
from n26.core.cycle_data import template_data
from n26.core.cycle_display import editor_url
from n26.core.models import (
    CampaignCycle,
    CampaignCycleCommand,
    CampaignPhase,
    CampaignPhaseOccurrence,
    CampaignPlan,
    CampaignSchedule,
)
from n26.core.operations import Refusal
from n26.flags import CYCLE_TRACKING
from n26.tests.sandbox.actions import found_campaign

pytestmark = pytest.mark.django_db


@pytest.fixture
def table(client, campaign_type):
    owner = User.objects.create_user("legacy-phase-owner")
    client.force_login(owner)
    FeatureFlag.objects.create(
        slug=CYCLE_TRACKING,
        name="Campaign cycles",
        availability=Availability.EVERYONE,
    )
    campaign = found_campaign("Retained phase links", campaign_type, owner=owner)
    cycles.configure(
        campaign,
        actor=owner,
        template_id="",
        definition=template_data(s.DEFAULT_TEMPLATE),
        current_position=0,
        mode="fixed",
        request_key=uuid4(),
    )
    state = cycles.load(campaign)
    return SimpleNamespace(
        campaign=campaign, owner=owner, state=state, block=state.occurrences[1]
    )


def snapshot(table):
    return {
        model.__name__: list(
            model.objects.filter(campaign=table.campaign).order_by("pk").values()
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


def editor(response, native):
    assert response.status_code == 200
    if not native:
        return response.json()["schedule"]["editor"]
    page = BeautifulSoup(response.content, "html.parser")
    host = page.select_one('[data-react-name="campaign-schedule"]')
    return json.loads(page.find(id=host["data-react-props"]).string)["editor"]


@pytest.mark.parametrize("native", [False, True])
@pytest.mark.parametrize("action", ["phase", "duplicate-phase", "delete-phase"])
def test_fresh_legacy_phase_links_save_and_retry_the_selected_block(
    client, table, native, action
):
    definition_id = table.block.phase_id
    url = editor_url(table.campaign, action, phase=definition_id)
    prepared = editor(
        client.get(url, headers={} if native else {"Accept": "application/json"}),
        native,
    )
    assert prepared["values"]["phase_id"] == definition_id
    data = dict(prepared["values"])
    if action in {"phase", "duplicate-phase"}:
        data["name"] = "Edited downtime" if action == "phase" else "Copied downtime"
    target = url if native else prepared["commandHref"]
    first = client.post(target, data)
    assert first.status_code == (302 if native else 200), first.content.decode()
    first_snapshot = snapshot(table)
    repeated = client.post(target, data)
    assert repeated.status_code == first.status_code
    assert snapshot(table) == first_snapshot
    receipt = CampaignCycleCommand.objects.get(request_key=data["request_key"])
    assert receipt.inputs["phase"] == definition_id
    assert receipt.inputs["expected_revision"] == table.state.revision
    state = cycles.load(table.campaign)
    assert state.current_cycle_id == table.state.current_cycle_id
    originals = {c.id: c.source for c in table.state.cycles}
    assert {c.id: c.source for c in state.cycles if c.id in originals} == originals
    block = next(o for o in state.occurrences if o.id == table.block.id)
    if action == "phase":
        assert s._phase(state, block.phase_id).details.name == "Edited downtime"
    elif action == "duplicate-phase":
        assert len([o for o in state.occurrences if not o.archived]) == 4
        assert any(p.details.name == "Copied downtime" for p in state.phases)
    else:
        assert block.archived
        assert all(c.archived for c in state.cycles if c.occurrence_id == block.id)


@pytest.mark.parametrize(
    "action", ["edit_occurrence", "duplicate_occurrence", "remove_occurrence"]
)
def test_a_definition_matching_two_active_blocks_refuses_without_writes(table, action):
    CampaignPhaseOccurrence.objects.create(
        campaign=table.campaign,
        phase_id=table.block.phase_id,
        position=4,
    )
    before = snapshot(table)
    arguments = (
        {"details": s.PhaseDetails("Ambiguous edit")}
        if action == "edit_occurrence"
        else {}
    )
    with pytest.raises(Refusal, match="active phase block"):
        cycles.author_timeline(
            table.campaign,
            actor=table.owner,
            action=action,
            occurrence_id=table.block.phase_id,
            expected_revision=table.state.revision,
            request_key=uuid4(),
            **arguments,
        )
    assert snapshot(table) == before


def test_legacy_phase_receipt_replays_before_loading_removed_blocks(table, monkeypatch):
    details = s.PhaseDetails("Edited downtime")
    key = uuid4()
    arguments = dict(
        actor=table.owner,
        action="edit_occurrence",
        occurrence_id=table.block.phase_id,
        details=details,
        receipt_inputs={"phase": table.block.phase_id, "details": asdict(details)},
        expected_revision=table.state.revision,
        request_key=key,
    )
    first = cycles.author_timeline(table.campaign, **arguments)
    state = cycles.load(table.campaign)
    cycles.author_timeline(
        table.campaign,
        actor=table.owner,
        action="remove_occurrence",
        occurrence_id=table.block.id,
        expected_revision=state.revision,
        request_key=uuid4(),
    )
    before = snapshot(table)
    monkeypatch.setattr(
        cycles,
        "_load_locked",
        lambda campaign: pytest.fail(
            "Exact retries must reach their receipt before resolving any block"
        ),
    )
    replay = cycles.author_timeline(table.campaign, **arguments)
    assert replay.replayed and replay.revision == first.revision
    assert snapshot(table) == before
