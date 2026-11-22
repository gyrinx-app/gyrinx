"""Timeline form adapters retain old receipts and prepare concrete block destinations."""

import json
from dataclasses import asdict, replace
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.http import Http404
from ulid import ULID

from n26.core import cycle_workflow as w
from n26.core import cycles
from n26.core import schedule as s
from n26.core.operations import Refusal


@pytest.fixture
def table(monkeypatch):
    first = s.Phase(str(ULID()), s.PhaseDetails("Occupation", "Story", "Effects"))
    second = s.Phase(str(ULID()), s.PhaseDetails("Downtime"))
    blocks = (
        s.PhaseOccurrence(str(ULID()), first.id, 1),
        s.PhaseOccurrence(str(ULID()), second.id, 2),
        s.PhaseOccurrence(str(ULID()), first.id, 3),
    )
    entries = tuple(
        s.Cycle(
            str(ULID()),
            number,
            s.CycleDetails(block.phase_id),
            s.CycleSource(),
            occurrence_id=block.id,
        )
        for number, block in enumerate((blocks[0], blocks[0], blocks[1]), start=1)
    )
    state = s.Schedule(
        str(ULID()),
        (first, second),
        s.Plan(str(ULID()), "fixed", ()),
        0,
        entries,
        entries[0].id,
        status="in_progress",
        revision=7,
        occurrences=blocks,
    )
    campaign = SimpleNamespace(pk=state.campaign_id, status="in_progress")
    monkeypatch.setattr(cycles, "load", lambda campaign: state)
    return SimpleNamespace(
        state=state,
        campaign=campaign,
        phases=(first, second),
        blocks=blocks,
        entries=entries,
    )


def test_new_cycle_editor_keeps_its_block_fixed_and_prepares_timeline_context(table):
    block = table.blocks[1]
    prepared = w.prepare(table.campaign, "add-cycle", {"phase": block.id})
    assert prepared.initial["occurrence_id"] == block.id
    assert prepared.initial["after_cycle_id"] == table.entries[2].id
    assert prepared.context["definitionPhaseId"] == block.phase_id
    assert prepared.query == {"phase": block.id}
    assert prepared.context["timelineOccurrences"] == [
        {
            "id": occurrence.id,
            "number": occurrence.position,
            "name": s._phase(table.state, occurrence.phase_id).details.name,
            "cycles": [
                {"id": cycle.id, "name": cycle.name, "order": cycle.order}
                for cycle in table.entries
                if cycle.occurrence_id == occurrence.id
            ],
        }
        for occurrence in table.blocks
    ]
    assert "phase_id" not in w.CycleEditorForm("add-cycle").fields


def test_move_defaults_preserve_the_existing_position_and_copy_defaults_after_source(
    table,
):
    selected = table.entries[1]
    moved = w.prepare(table.campaign, "move-cycle", {"cycle": selected.id})
    copied = w.prepare(table.campaign, "duplicate-cycle", {"cycle": selected.id})
    assert moved.initial["after_cycle_id"] == table.entries[0].id
    assert moved.initial["occurrence_id"] == selected.occurrence_id
    assert copied.initial["after_cycle_id"] == selected.id
    assert copied.initial["clear_dates"] is True
    assert moved.context["selectedCycle"] == {
        "id": selected.id,
        "name": selected.name,
        "order": 2,
        "occurrenceId": selected.occurrence_id,
    }
    block = w.prepare(table.campaign, "move-phase", {"phase": table.blocks[1].id})
    assert block.initial["occurrence_id"] == table.blocks[1].id
    assert block.initial["after_occurrence_id"] == table.blocks[0].id


def test_phase_editor_allows_corrections_to_current_and_fully_recorded_blocks(
    table, monkeypatch
):
    prepared = w.prepare(table.campaign, "phase", {"phase": table.blocks[0].id})
    assert (
        prepared.lead
        == "Changes apply to all cycles in this phase. Saving rewards does not give credits or reputation."
    )
    assert prepared.initial["phase_id"] == table.blocks[0].id
    assert prepared.context["definitionPhaseId"] == table.phases[0].id
    protected = replace(
        table.state, protected_cycle_ids=frozenset({table.entries[1].id})
    )
    monkeypatch.setattr(cycles, "load", lambda campaign: protected)
    prepared = w.prepare(table.campaign, "phase", {"phase": table.blocks[0].id})
    assert prepared.initial["phase_id"] == table.blocks[0].id


def test_legacy_single_definition_links_keep_original_identity_and_ambiguous_ones_refuse(
    table,
):
    prepared = w.prepare(table.campaign, "phase", {"phase": table.phases[1].id})
    assert prepared.initial["phase_id"] == table.phases[1].id
    assert prepared.query == {"phase": table.phases[1].id}
    with pytest.raises(Http404):
        w.prepare(table.campaign, "phase", {"phase": table.phases[0].id})


def test_phase_duplication_and_addition_prepare_append_targets(table):
    for action in ("add-phase", "duplicate-phase"):
        prepared = w.prepare(table.campaign, action, {"phase": table.blocks[1].id})
        assert prepared.initial["after_occurrence_id"] == table.blocks[-1].id
        if action == "duplicate-phase":
            assert prepared.initial["clear_dates"] is True


def test_phase_removal_only_counts_selected_block_children(table, monkeypatch):
    def prepare_deletion(campaign, state, initial, context, victims, **kwargs):
        context.update(savedCount=len(victims), victims=victims)

    monkeypatch.setattr(w, "_prepare_deletion", prepare_deletion)
    prepared = w.prepare(table.campaign, "delete-phase", {"phase": table.blocks[0].id})
    assert prepared.context["victims"] == [c.id for c in table.entries[:2]]
    assert prepared.context["occurrenceOnly"] is True
    assert prepared.context["futureCount"] == 0
    assert prepared.context["repeating"] is False
    assert "block" in prepared.lead


def payload(**values):
    return {"request_key": str(uuid4()), "expected_revision": "7", **values}


def capture(monkeypatch):
    calls = []

    def command(campaign, **kwargs):
        calls.append(kwargs)
        return cycles.CommandResult(8, None, None, replayed=True)

    monkeypatch.setattr(cycles, "author_timeline", command)
    monkeypatch.setattr(
        cycles,
        "load",
        lambda *args: pytest.fail("Resources must not resolve before receipt replay"),
    )
    return calls


def test_add_cycle_posts_server_resolved_phase_placeholder_without_loading_removed_resources(
    table, monkeypatch
):
    calls = capture(monkeypatch)
    block = table.blocks[1]
    submitted = w.perform(
        table.campaign,
        object(),
        "add-cycle",
        payload(
            occurrence_id=block.id,
            after_cycle_id="",
            custom_name="Market week",
            starts_on="",
            ends_on="2026-12-01",
            description="",
            effects="A local effect",
        ),
        {"phase": block.id},
    )
    assert submitted.result.replayed
    assert calls[0]["action"] == "insert_cycle"
    assert calls[0]["occurrence_id"] == block.id and calls[0]["after_cycle_id"] is None
    assert calls[0]["details"].phase_id == block.id
    assert calls[0]["details"].description == ""
    assert calls[0]["details"].starts_on is None
    assert calls[0]["details"].ends_on.isoformat() == "2026-12-01"


@pytest.mark.parametrize("action", ["move-cycle", "duplicate-cycle"])
def test_cycle_move_and_copy_targets_bind_to_query_and_preserve_explicit_start(
    table, monkeypatch, action
):
    calls = capture(monkeypatch)
    selected = table.entries[1]
    data = payload(
        cycle_id=selected.id,
        occurrence_id=table.blocks[1].id,
        after_cycle_id="",
        clear_dates="on",
    )
    submitted = w.perform(
        table.campaign, object(), action, data, {"cycle": selected.id}
    )
    assert submitted.result.replayed
    assert calls[0]["cycle_id"] == selected.id
    assert calls[0]["after_cycle_id"] is None
    if action == "duplicate-cycle":
        assert calls[0]["clear_dates"] is True
    mismatch = w.perform(
        table.campaign, object(), action, data, {"cycle": table.entries[0].id}
    )
    assert mismatch.result is None and mismatch.form.non_field_errors()
    assert len(calls) == 1


def test_move_phase_dispatches_occurrence_and_explicit_start_without_lookups(
    table, monkeypatch
):
    calls = capture(monkeypatch)
    selected = table.blocks[1]
    submitted = w.perform(
        table.campaign,
        object(),
        "move-phase",
        payload(occurrence_id=selected.id, after_occurrence_id=""),
        {"phase": selected.id},
    )
    assert submitted.result.replayed
    assert calls[0]["action"] == "move_occurrence"
    assert calls[0]["after_occurrence_id"] is None


@pytest.mark.parametrize(
    "action, service_action",
    [
        ("phase", "edit_occurrence"),
        ("add-phase", "insert_occurrence"),
        ("duplicate-phase", "duplicate_occurrence"),
        ("delete-phase", "remove_occurrence"),
    ],
)
def test_old_phase_payloads_keep_exact_receipt_shape_before_removed_resource_resolution(
    table, monkeypatch, action, service_action
):
    calls = capture(monkeypatch)
    identity = table.phases[1].id
    values = payload(
        phase_id=identity,
        name="Later downtime",
        description="Old story",
        effects="Old effects",
        rewards=json.dumps({"entry_credits": {"fixed": 20}}),
        current_choice="none",
    )
    submitted = w.perform(table.campaign, object(), action, values, {"phase": identity})
    assert submitted.result.replayed, submitted.form.errors
    command = calls[0]
    assert command["action"] == service_action
    assert "after_occurrence_id" not in command and "clear_dates" not in command
    if action in ("phase", "add-phase"):
        expected = {"details": asdict(command["details"])}
        if action == "phase":
            expected["phase"] = identity
    elif action == "duplicate-phase":
        expected = {"phase": identity, "name": values["name"]}
    else:
        expected = {"phase": identity, "no_current": True}
    assert command["receipt_inputs"] == expected


def test_new_duplicate_phase_receipt_binds_placement_and_clear_dates(
    table, monkeypatch
):
    calls = capture(monkeypatch)
    identity = table.blocks[1].id
    submitted = w.perform(
        table.campaign,
        object(),
        "duplicate-phase",
        payload(
            phase_id=identity, name="Copy", after_occurrence_id="", clear_dates="on"
        ),
        {"phase": identity},
    )
    assert submitted.result.replayed
    assert calls[0]["receipt_inputs"] == {
        "phase": identity,
        "name": "Copy",
        "after_occurrence": None,
        "clear_dates": True,
    }
    assert calls[0]["after_occurrence_id"] is None


def test_absent_duplicate_cycle_placement_keeps_default_after_source(
    table, monkeypatch
):
    calls = capture(monkeypatch)
    selected = table.entries[1]
    submitted = w.perform(
        table.campaign,
        object(),
        "duplicate-cycle",
        payload(cycle_id=selected.id, occurrence_id=selected.occurrence_id),
        {"cycle": selected.id},
    )
    assert submitted.result.replayed
    assert "after_cycle_id" not in calls[0]


def test_protection_and_date_refusals_return_form_validation(table, monkeypatch):
    def refuse(*args, **kwargs):
        raise Refusal("The dates must follow the earlier cycle.")

    monkeypatch.setattr(cycles, "author_timeline", refuse)
    selected = table.entries[1]
    submitted = w.perform(
        table.campaign,
        object(),
        "move-cycle",
        payload(
            cycle_id=selected.id,
            occurrence_id=selected.occurrence_id,
            after_cycle_id="",
        ),
        {"cycle": selected.id},
    )
    assert submitted.result is None
    assert list(submitted.form.non_field_errors()) == [
        "The dates must follow the earlier cycle."
    ]


def test_malformed_destination_is_field_validation_without_dispatch(table, monkeypatch):
    calls = capture(monkeypatch)
    selected = table.entries[1]
    submitted = w.perform(
        table.campaign,
        object(),
        "move-cycle",
        payload(
            cycle_id=selected.id,
            occurrence_id=selected.occurrence_id,
            after_cycle_id="not-an-id",
        ),
        {"cycle": selected.id},
    )
    assert "after_cycle_id" in submitted.form.errors and not calls


def test_phase_actions_return_to_the_timeline(table):
    for action in (
        "phase",
        "add-phase",
        "duplicate-phase",
        "delete-phase",
        "move-phase",
    ):
        assert w.editor_back(table.campaign, action) == w.schedule_url(table.campaign)


@pytest.mark.parametrize("next_position, count, expected", [(2, 5, 3), (0, 5000, 1000)])
def test_pattern_add_dialog_defaults_to_the_first_step_remainder_with_a_bounded_count(
    table, monkeypatch, next_position, count, expected
):
    state = replace(
        table.state,
        plan=s.Plan(
            "pattern-plan",
            "repeating",
            (s.PlanStep("step", table.phases[0].id, count),),
        ),
        next_position=next_position,
    )
    monkeypatch.setattr(cycles, "load", lambda campaign: state)
    prepared = w.prepare(table.campaign, "plan-cycles", {})
    assert prepared.initial["pattern_count"] == expected
    assert prepared.heading == "Add cycles from pattern"
    assert (
        prepared.lead
        == "Add upcoming cycles from the repeating pattern to your timeline."
    )
    assert prepared.context["firstUpcoming"]["name"] == "Cycle 4"
    assert set(w.CycleEditorForm("plan-cycles").fields) == {
        "request_key",
        "expected_revision",
        "pattern_count",
    }


def test_fixed_plans_do_not_offer_the_pattern_add_dialog(table):
    with pytest.raises(Http404, match="no repeating pattern"):
        w.prepare(table.campaign, "plan-cycles", {})


def test_pattern_add_dispatch_is_lookup_free_for_retained_retries(table, monkeypatch):
    calls = []

    def command(campaign, **kwargs):
        calls.append(kwargs)
        return cycles.CommandResult(8, table.entries[-1].id, None, replayed=True)

    monkeypatch.setattr(cycles, "plan_cycles", command)
    monkeypatch.setattr(
        cycles,
        "load",
        lambda campaign: pytest.fail(
            "Retained retries must reach receipt replay first"
        ),
    )
    submitted = w.perform(
        table.campaign, object(), "plan-cycles", payload(pattern_count="2"), {}
    )
    assert submitted.result.replayed
    assert calls[0]["count"] == 2 and calls[0]["expected_revision"] == 7
    invalid = w.perform(
        table.campaign, object(), "plan-cycles", payload(pattern_count="1001"), {}
    )
    assert "pattern_count" in invalid.form.errors and len(calls) == 1


def test_add_phase_boundary_sets_the_selected_insertion_point_and_canonical_query(
    table,
):
    selected = table.blocks[0]
    prepared = w.prepare(table.campaign, "add-phase", {"after": selected.id})
    assert prepared.initial["after_occurrence_id"] == selected.id
    assert prepared.query == {"after": selected.id}
    assert (
        w.prepare(table.campaign, "add-phase", {}).initial["after_occurrence_id"]
        == table.blocks[-1].id
    )


@pytest.mark.parametrize("after", ["foreign", "archived"])
def test_add_phase_boundary_refuses_foreign_or_archived_occurrences(
    table, monkeypatch, after
):
    if after == "archived":
        state = replace(
            table.state,
            occurrences=table.blocks[:-1] + (replace(table.blocks[-1], archived=True),),
        )
        monkeypatch.setattr(cycles, "load", lambda campaign: state)
        identity = table.blocks[-1].id
    else:
        identity = str(ULID())
    with pytest.raises(Http404, match="insertion point"):
        w.prepare(table.campaign, "add-phase", {"after": identity})


def test_add_phase_boundary_binds_hidden_placement_but_keeps_retry_lookup_free(
    table, monkeypatch
):
    calls = capture(monkeypatch)
    selected = table.blocks[0].id
    data = payload(
        name="Middle phase",
        after_occurrence_id=selected,
        description="",
        effects="",
        rewards="{}",
    )
    submitted = w.perform(
        table.campaign, object(), "add-phase", data, {"after": selected}
    )
    assert submitted.result.replayed
    assert calls[0]["after_occurrence_id"] == selected
    assert calls[0]["receipt_inputs"]["after_occurrence"] == selected
    forged = w.perform(
        table.campaign,
        object(),
        "add-phase",
        {**data, "after_occurrence_id": table.blocks[-1].id},
        {"after": selected},
    )
    assert forged.result is None
    assert list(forged.form.non_field_errors()) == [
        "The insertion point changed. Reload the editor."
    ]
    assert len(calls) == 1


def test_add_phase_recovery_retains_a_removed_boundary_query(table):
    selected = table.blocks[0].id
    recovered = w.recovery_editor(table.campaign, "add-phase", {"after": selected})
    assert recovered.query == {"after": selected}


def test_phase_editor_allows_a_fully_recorded_phase_without_a_current_cycle(
    table, monkeypatch
):
    state = replace(
        table.state,
        current_cycle_id=None,
        protected_cycle_ids=frozenset({table.entries[1].id}),
    )
    monkeypatch.setattr(cycles, "load", lambda campaign: state)
    prepared = w.prepare(table.campaign, "phase", {"phase": table.blocks[0].id})
    assert prepared.initial["phase_id"] == table.blocks[0].id


def test_phase_editor_applies_corrections_to_recorded_and_future_cycles(
    table, monkeypatch
):
    last = replace(table.entries[1], id=str(ULID()), order=3)
    following = replace(table.entries[2], order=4)
    state = replace(
        table.state,
        current_cycle_id=None,
        cycles=(*table.entries[:2], last, following),
        protected_cycle_ids=frozenset({table.entries[1].id}),
    )
    monkeypatch.setattr(cycles, "load", lambda campaign: state)
    prepared = w.prepare(table.campaign, "phase", {"phase": table.blocks[0].id})
    assert "Changes apply to all cycles in this phase." in prepared.lead
    assert prepared.initial["phase_id"] == table.blocks[0].id
