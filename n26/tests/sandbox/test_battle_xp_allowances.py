"""A battle XP award earns one durable choice, with reversible unused grants."""

import json
from concurrent.futures import ThreadPoolExecutor
from threading import Barrier
from types import SimpleNamespace
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.db import close_old_connections, connections
from django.urls import reverse

from n26.core.advancements import advancement_undo_snapshot
from n26.core.models import (
    ActionAllowance,
    ActionRecord,
    Assignment,
    LedgerEvent,
    PostBattleReport,
)
from n26.core.operations import Refusal, operation
from n26.core.post_battle import (
    apply_report,
    preview_report,
    save_draft,
    start_correction,
    start_report,
)
from n26.core.reconcile import assert_reconciled
from n26.library import authoring as a
from n26.tests.fixtures import island_props, library_setup
from n26.tests.sandbox.actions import found_gang, hire

pytestmark = [pytest.mark.django_db, pytest.mark.usefixtures("counter_tracking")]


@pytest.fixture
@library_setup
def setup(default_pack, gang_type, make_profile, make_statline):
    owner = User.objects.create_user("battle-xp-player")
    xp = a.create_counter("XP")
    kind = a.create_slot_type("Legendary name")
    pick = a.create_pickable("The Unbroken", kind)
    a.modifier(
        "Name rule",
        a.targets_model(),
        a.ef_adds(a.create_rule("Name effect")),
        attach_to=pick,
    )
    table = a.create_picklist("Names", kind, dice="2d6", roll_selects="threshold")
    a.add_picklist_member(table, pick, roll_low=2)
    slot = a.create_slot("Legendary name", kind, table)
    outcome = a.create_outcome("Legendary name", a.resolve_advancement(slot))
    action = a.create_action(
        "Choose a legendary name",
        "post_cycle",
        outcomes=[outcome],
        allowance_rule=a.battle_allowance_rule(5),
    )
    profile = make_profile("Orlock fighter", price=100)
    make_statline(profile)
    a.add_built_in(profile, xp)
    a.add_built_in(profile, action)
    gang = found_gang("The Ironheads", gang_type, owner=owner, budget=1000)
    fighter = hire(gang, profile, "Any name")
    counter = Assignment.objects.get(miniature_root=fighter, counter=xp)
    report = start_report(gang, actor=owner, request_key=uuid4())
    return SimpleNamespace(
        owner=owner,
        gang=gang,
        fighter=fighter,
        counter=counter,
        xp=xp,
        action=action,
        outcome=outcome,
        pick=pick,
        report=report,
    )


def save_award(s, xp, *, report=None, effects=(), counters=None):
    report = report or s.report
    report.refresh_from_db()
    return save_draft(
        report,
        actor=s.owner,
        generation=report.generation,
        revision=report.draft_revision,
        payload={
            "participation_confirmed": True,
            "models": [
                {
                    "id": str(s.fighter.pk),
                    "participated": True,
                    "xp": xp,
                    "effects": list(effects),
                    "counters": counters or {},
                }
            ],
        },
    )


def apply(s, xp, *, correction=False, report=None, effects=(), counters=None):
    report = report or s.report
    if correction:
        report = start_correction(report, actor=s.owner)
    report = save_award(s, xp, report=report, effects=effects, counters=counters)
    plan = preview_report(report, actor=s.owner)
    assert plan.valid, plan.errors
    revision = apply_report(
        report,
        actor=s.owner,
        generation=report.generation,
        revision=report.draft_revision,
        submission_key=uuid4(),
        review=plan.review,
    )
    report.refresh_from_db()
    return revision


@pytest.mark.parametrize("xp,expected", [(4, 0), (5, 1), (8, 1)])
def test_only_a_qualifying_battle_award_grants_a_choice(setup, xp, expected):
    s = setup
    with operation(s.gang, actor=s.owner) as op:
        op.tally(s.counter, 20)
    apply(s, xp)
    assert ActionAllowance.objects.filter(source_kind="battle").count() == expected
    assert_reconciled(s.gang)


def test_authored_access_controls_eligibility_and_a_later_battle_grants_another(setup):
    s = setup
    with operation(s.gang, actor=s.owner) as op:
        op.rename(s.fighter, "Renamed fighter")
    first = apply(s, 5)
    second_report = start_report(s.gang, actor=s.owner, request_key=uuid4())
    second = apply(s, 7, report=second_report)
    allowances = list(
        ActionAllowance.objects.filter(source_kind="battle").order_by("created")
    )
    assert len(allowances) == 2
    assert [row.granted_event.post_battle_revision for row in allowances] == [
        first,
        second,
    ]
    assert {row.report_id for row in allowances} == {s.report.pk, second_report.pk}
    with operation(s.gang, actor=s.owner) as op:
        op.remove(Assignment.objects.get(miniature_root=s.fighter, action=s.action))
    third = start_report(s.gang, actor=s.owner, request_key=uuid4())
    apply(s, 6, report=third)
    assert ActionAllowance.objects.filter(source_kind="battle").count() == 2


def test_corrections_cross_the_threshold_once_and_hold_then_restore_the_same_use(setup):
    s = setup
    apply(s, 4)
    apply(s, 5, correction=True)
    allowance = ActionAllowance.objects.get(source_kind="battle")
    grant = allowance.granted_event_id
    apply(s, 6, correction=True)
    assert ActionAllowance.objects.filter(source_kind="battle").count() == 1
    apply(s, 4, correction=True)
    allowance.refresh_from_db()
    assert not allowance.is_active
    assert not ActionAllowance.objects.eligible().filter(pk=allowance.pk).exists()
    with pytest.raises(Refusal, match="On hold"):
        with operation(s.gang, actor=s.owner) as op:
            op.start_action(s.fighter, s.action, uuid4(), allowance=allowance)
    apply(s, 5, correction=True)
    allowance.refresh_from_db()
    assert allowance.is_active
    assert allowance.granted_event_id == grant
    assert ActionAllowance.objects.filter(source_kind="battle").count() == 1
    assert s.report.revisions.count() == 5
    assert_reconciled(s.gang)


def test_a_started_unresolved_choice_is_held_and_cannot_be_completed(setup):
    s = setup
    apply(s, 5)
    with operation(s.gang, actor=s.owner) as op:
        record = op.start_action(s.fighter, s.action, uuid4())
    apply(s, 4, correction=True)
    with pytest.raises(Refusal, match="On hold"):
        with operation(s.gang, actor=s.owner) as op:
            op.review_action(
                record, outcome=s.outcome, terms={"pickable_id": str(s.pick.pk)}
            )
    assert ActionRecord.objects.get(pk=record.pk).state == "started"


def complete_name(s):
    with operation(s.gang, actor=s.owner) as op:
        record = op.start_action(s.fighter, s.action, uuid4())
        op.record_action_roll(record, s.outcome.operation, uuid4(), rolled=12)
        record.refresh_from_db()
        record = op.review_action(
            record, outcome=s.outcome, terms={"pickable_id": str(s.pick.pk)}
        )
        return op.complete_action(
            record, revision=record.revision, review=record.review, outcome=s.outcome
        )


def test_a_selected_name_blocks_lowering_xp_until_its_result_is_safely_undone(setup):
    s = setup
    apply(s, 5)
    record = complete_name(s)
    chosen = Assignment.objects.get(
        miniature_root=s.fighter, pickable=s.pick, archived=False
    )
    assert record.allowance.report == s.report
    report = start_correction(s.report, actor=s.owner)
    report = save_award(s, 4, report=report)
    plan = preview_report(report, actor=s.owner)
    assert not plan.valid
    assert "already been used" in " ".join(plan.errors)
    with pytest.raises(Refusal, match="already been used"):
        apply_report(
            report,
            actor=s.owner,
            generation=report.generation,
            revision=report.draft_revision,
            submission_key=uuid4(),
            review=plan.review,
        )
    chosen.refresh_from_db()
    assert not chosen.archived
    assert s.report.revisions.count() == 1
    snapshot = advancement_undo_snapshot(record)
    with operation(s.gang, actor=s.owner) as op:
        op.undo_action(record, expected=snapshot)
    apply(s, 4)
    assert not ActionAllowance.objects.get(source_kind="battle").is_active
    assert LedgerEvent.objects.filter(
        action_record=record, kind=LedgerEvent.Kind.ACTION_USE_UNDONE
    ).exists()
    assert_reconciled(s.gang)


def test_later_dependent_changes_survive_a_refused_correction(setup):
    s = setup
    apply(s, 5)
    record = complete_name(s)
    chosen = Assignment.objects.get(
        miniature_root=s.fighter, pickable=s.pick, archived=False
    )
    later = a.create_rule("Later independent change")
    with operation(s.gang, actor=s.owner) as op:
        dependent = op.assign(later, miniature=s.fighter, caused_by=chosen)
    with pytest.raises(Refusal, match="Later changes"):
        advancement_undo_snapshot(record)
    report = start_correction(s.report, actor=s.owner)
    report = save_award(s, 4, report=report)
    assert not preview_report(report, actor=s.owner).valid
    dependent.refresh_from_db()
    chosen.refresh_from_db()
    assert not dependent.archived and not chosen.archived


def test_ordinary_rank_progression_continues_alongside_battle_allowances(setup):
    s = setup
    ranks = a.create_rank_table("Ranks", s.xp, thresholds=[4, 7])
    advance = a.create_action(
        "Advance",
        "post_cycle",
        outcomes=[s.outcome],
        allowance_rule=a.rank_allowance_rule(s.xp),
    )
    with operation(s.gang, actor=s.owner) as op:
        op.assign(ranks, miniature=s.fighter)
        op.assign(advance, miniature=s.fighter)
    apply(s, 8)
    assert list(
        ActionAllowance.objects.filter(source_kind="rank")
        .values_list("threshold", flat=True)
        .order_by("threshold")
    ) == [4, 7]
    assert ActionAllowance.objects.filter(source_kind="battle").count() == 1


def test_the_preview_and_receipt_explain_the_new_choice(setup, client):
    s = setup
    client.force_login(s.owner)
    report = save_award(s, 5)
    body = client.get(
        reverse("n26-post-battle-editor", args=[report.pk])
    ).content.decode()
    assert "Earns one use of Choose a legendary name" in body
    revision = apply(s, 5)
    assert revision.receipt["models"][0]["battle_awards"] == [
        "Earns one use of Choose a legendary name."
    ]
    record = complete_name(s)
    from n26.core.action_flow import action_panels
    from n26.core.card import build_card, build_modifier_index, carriers
    from n26.core.effects import compute

    card = build_card(s.fighter)
    panels = action_panels(
        s.fighter,
        card=card,
        computed=compute(card, build_modifier_index(carriers(card))),
    )
    result = next(p for p in panels if p.action_id == str(s.action.pk)).completed[0]
    assert result.report_href == reverse("n26-post-battle-receipt", args=[s.report.pk])
    assert record.allowance.granted_event.post_battle_revision == revision


@pytest.mark.django_db(transaction=True)
def test_concurrent_retries_apply_the_report_and_grant_only_once(setup):
    s = setup
    report = save_award(s, 5)
    plan = preview_report(report, actor=s.owner)
    key, barrier = uuid4(), Barrier(2)

    def submit():
        close_old_connections()
        try:
            local = PostBattleReport.objects.get(pk=report.pk)
            actor = User.objects.get(pk=s.owner.pk)
            barrier.wait(timeout=10)
            return apply_report(
                local,
                actor=actor,
                generation=report.generation,
                revision=report.draft_revision,
                submission_key=key,
                review=plan.review,
            ).pk
        finally:
            connections.close_all()

    with ThreadPoolExecutor(max_workers=2) as pool:
        results = list(pool.map(lambda _: submit(), range(2)))
    assert results[0] == results[1]
    assert ActionAllowance.objects.filter(report=report).count() == 1
    assert report.revisions.count() == 1


def test_a_stale_second_submission_key_cannot_grant_again(setup):
    s = setup
    report = save_award(s, 5)
    generation, draft_revision = report.generation, report.draft_revision
    review = preview_report(report, actor=s.owner).review
    apply_report(
        report,
        actor=s.owner,
        generation=generation,
        revision=draft_revision,
        submission_key=uuid4(),
        review=review,
    )
    with pytest.raises(Refusal, match="already been applied"):
        apply_report(
            report,
            actor=s.owner,
            generation=generation,
            revision=draft_revision,
            submission_key=uuid4(),
            review=review,
        )
    assert ActionAllowance.objects.filter(report=report).count() == 1


def test_an_award_applied_by_hand_must_be_reopened_before_lowering_xp(setup):
    s = setup
    apply(s, 5)
    with operation(s.gang, actor=s.owner) as op:
        record = op.apply_allowance_by_hand(s.fighter, s.action, uuid4())
    report = start_correction(s.report, actor=s.owner)
    report = save_award(s, 4, report=report)
    assert not preview_report(report, actor=s.owner).valid
    with operation(s.gang, actor=s.owner) as op:
        op.reopen_action(record)
    apply(s, 4)
    assert not ActionAllowance.objects.get(report=s.report).is_active


def test_battle_allowance_reads_stay_batched_as_more_fighters_are_in_the_report(setup):
    from django.db import connection
    from django.test.utils import CaptureQueriesContext

    s = setup

    def reads():
        with CaptureQueriesContext(connection) as captured:
            preview_report(s.report, actor=s.owner)
        return sum(
            '"library_battleallowancerule"' in query["sql"] for query in captured
        ), sum('"n26_actionallowance"' in query["sql"] for query in captured)

    before = reads()
    profile = s.fighter.membership.profile
    for name in ("Birch", "Cinder", "Dust"):
        hire(s.gang, profile, name)
    after = reads()
    assert before == after == (1, 1)


@library_setup
def xp_result(s):
    kind = a.create_slot_type("XP injury result", is_lasting_effect=True)
    pick = a.create_pickable(
        "Lesson",
        kind,
        effects=[(a.targets_model(), a.op_changes_counter(s.xp, "add", 2))],
    )
    table = a.create_picklist("XP results", kind, members=[pick])
    slot = a.create_slot("XP result", kind, table, min_picks=0, max_picks=100)
    with operation(s.gang, actor=s.owner) as op:
        op.assign(slot, miniature=s.fighter)
    plan = preview_report(s.report, actor=s.owner)
    offered = next(
        slot
        for slot in plan.models[0].effect_slots
        if any(option.value == str(pick.pk) for option in slot.options)
    )
    return {
        "id": str(uuid4()),
        "slot": offered.key,
        "pick": str(pick.pk),
        "choices": {},
    }


def test_xp_from_results_and_the_entered_award_qualify_together(setup):
    s = setup
    effect = xp_result(s)
    revision = apply(s, 3, effects=[effect])
    assert revision.receipt["models"][0]["battle_xp_award"] == 5
    allowance = ActionAllowance.objects.get(source_kind="battle")
    with operation(s.gang, actor=s.owner) as op:
        op.tally(s.counter, 30)
    corrected = apply(s, 4, correction=True, effects=[effect])
    assert corrected.receipt["models"][0]["battle_xp_award"] == 6
    assert ActionAllowance.objects.filter(source_kind="battle").count() == 1
    apply(s, 2, correction=True, effects=[effect])
    allowance.refresh_from_db()
    assert not allowance.is_active
    assert_reconciled(s.gang)


def test_removing_an_xp_result_holds_the_choice_even_when_entered_xp_is_unchanged(
    setup,
):
    s = setup
    effect = xp_result(s)
    apply(s, 3, effects=[effect])
    revision = apply(s, 3, correction=True)
    assert revision.receipt["models"][0]["battle_xp_award"] == 3
    assert not ActionAllowance.objects.get(source_kind="battle").is_active


def test_old_receipts_recover_the_combined_report_award_before_a_correction(setup):
    from n26.core.models import PostBattleRevision

    s = setup
    effect = xp_result(s)
    revision = apply(s, 3, effects=[effect])
    receipt = revision.receipt
    receipt["models"][0].pop("battle_xp_award")
    PostBattleRevision.objects.filter(pk=revision.pk).update(receipt=receipt)
    corrected = apply(s, 4, correction=True, effects=[effect])
    assert corrected.receipt["models"][0]["battle_xp_award"] == 6
    assert ActionAllowance.objects.get(source_kind="battle").is_active


@library_setup
def test_a_maximum_length_action_name_can_be_granted_held_and_restored(setup):
    s = setup
    a.revise(s.action, name="L" * 200)
    apply(s, 5)
    apply(s, 4, correction=True)
    apply(s, 5, correction=True)
    assert ActionAllowance.objects.get(source_kind="battle").is_active
    assert all(
        len(note) <= 255
        for note in LedgerEvent.objects.filter(
            post_battle_revision__report=s.report
        ).values_list("note", flat=True)
    )


def test_allowance_validation_accepts_its_report_and_rejects_another_gang(
    setup, gang_type
):
    from django.core.exceptions import ValidationError

    s = setup
    apply(s, 5)
    allowance = ActionAllowance.objects.get(source_kind="battle")
    allowance.full_clean()
    other = found_gang("Other gang", gang_type, owner=s.owner, budget=1000)
    other_report = start_report(other, actor=s.owner, request_key=uuid4())
    allowance.report = other_report
    with pytest.raises(ValidationError, match="report must belong"):
        allowance.full_clean()


def test_a_held_rolled_flow_keeps_its_history_without_blocking_a_later_battle(
    setup, client
):
    s = setup
    apply(s, 5)
    with operation(s.gang, actor=s.owner) as op:
        held = op.start_action(s.fighter, s.action, uuid4())
        op.record_action_roll(held, s.outcome.operation, uuid4(), rolled=9)
    held.refresh_from_db()
    original_roll = held.advancement_selection.roll_event_id
    apply(s, 4, correction=True)
    second_report = start_report(s.gang, actor=s.owner, request_key=uuid4())
    apply(s, 5, report=second_report)
    later = ActionAllowance.objects.get(report=second_report)
    client.force_login(s.owner)
    edit = client.get(reverse("n26-edit-fighter", args=[s.fighter.pk]))
    panel = next(
        p for p in edit.context["action_panels"] if p.action_id == str(s.action.pk)
    )
    assert panel.start_href
    assert str(later.pk) in panel.start_href
    assert panel.drafts[0].problem and panel.drafts[0].suspended
    start = client.get(panel.start_href)
    assert start.status_code == 200
    response = client.post(
        reverse("n26-action-start", args=[s.fighter.pk, s.action.pk]),
        {
            "request_key": str(uuid4()),
            "allowance": str(later.pk),
            "outcome": str(s.outcome.pk),
        },
    )
    assert response.status_code == 302
    new = ActionRecord.objects.get(allowance=later)
    assert new.pk != held.pk and new.state == "started"
    held.refresh_from_db()
    assert held.advancement_selection.roll_event_id == original_roll
    assert held.state == "started"
    with pytest.raises(Refusal, match="On hold"):
        with operation(s.gang, actor=s.owner) as op:
            op.record_action_roll(held, s.outcome.operation, uuid4(), rolled=12)
    with operation(s.gang, actor=s.owner) as op:
        op.record_action_roll(new, s.outcome.operation, uuid4(), rolled=12)
        new.refresh_from_db()
        new = op.review_action(
            new, outcome=s.outcome, terms={"pickable_id": str(s.pick.pk)}
        )
        new = op.complete_action(
            new, revision=new.revision, review=new.review, outcome=s.outcome
        )
    snapshot = advancement_undo_snapshot(new)
    with operation(s.gang, actor=s.owner) as op:
        new = op.undo_action(new, expected=snapshot)
        new = op.apply_action_by_hand(new)
        new = op.reopen_action(new)
    assert new.state == "started"
    apply(s, 5, correction=True)
    held.refresh_from_db()
    assert held.allowance.is_active
    assert held.advancement_selection.roll_event_id == original_roll
    assert ActionRecord.objects.filter(action=s.action).count() == 2


def test_the_model_cards_direct_picker_cannot_bypass_a_held_action(setup, client):
    from bs4 import BeautifulSoup

    s = setup
    apply(s, 5)
    with operation(s.gang, actor=s.owner) as op:
        record = op.start_action(s.fighter, s.action, uuid4())
        op.record_action_roll(record, s.outcome.operation, uuid4(), rolled=9)
    apply(s, 4, correction=True)
    client.force_login(s.owner)
    edit = client.get(reverse("n26-edit-fighter", args=[s.fighter.pk]))
    links = BeautifulSoup(edit.content, "html.parser").find_all("a", href=True)
    picker = next(link["href"] for link in links if "/choose/" in link["href"])
    target = reverse("n26-action-flow", args=[s.fighter.pk, record.pk, "resume"])
    assert client.get(picker).url == target
    assert client.post(picker, {"pick": str(s.pick.pk)}).url == target
    held = client.get(target, follow=True)
    assert "On hold" in held.content.decode()
    assert not Assignment.objects.filter(
        miniature_root=s.fighter, pickable=s.pick, archived=False
    ).exists()


@pytest.mark.parametrize("held", [False, True])
@library_setup
def test_an_interstitial_cannot_settle_an_earned_battle_choice(setup, client, held):
    s = setup
    apply(s, 5)
    slot = s.outcome.operation.slot
    a.create_interstitial("Name choice screen", slots=[slot])
    with operation(s.gang, actor=s.owner) as op:
        record = op.start_action(s.fighter, s.action, uuid4())
        op.record_action_roll(record, s.outcome.operation, uuid4(), rolled=9)
    if held:
        apply(s, 4, correction=True)
    record.refresh_from_db()
    selection = record.advancement_selection
    original_roll = selection.roll_event_id
    key = f"{s.fighter.pk}:{selection.slot_assignment_id}:{slot.pk}"
    here = reverse("n26-next", args=[s.gang.pk]) + f"?ask={key}"
    client.force_login(s.owner)
    page = client.get(here)
    assert page.status_code == 200
    props = island_props(page.content, "choice-workflow")
    questions = [
        question for block in props["blocks"] for question in block["questions"]
    ]
    assert [question["key"] for question in questions] == [key]
    picked = f"library.pickable:{s.pick.pk}"
    assert picked in {
        option["key"]
        for group in questions[0]["offer"]["groups"]
        for option in group["options"]
    }
    response = client.post(
        here,
        {**props["values"], "selection": json.dumps({key: picked})},
        follow=True,
    )
    assert response.status_code == 200
    refused = island_props(response.content, "choice-workflow")
    assert any(
        ("On hold" if held else "earned action flow") in message["text"]
        for message in refused["messages"]
    )
    assert not Assignment.objects.filter(
        miniature_root=s.fighter, pickable=s.pick, archived=False
    ).exists()
    record.refresh_from_db()
    assert record.advancement_selection.roll_event_id == original_roll
    assert record.state == "started"


@pytest.mark.parametrize("held", [False, True])
def test_choosing_at_the_operation_boundary_requires_the_earned_battle_flow(
    setup, held
):
    s = setup
    apply(s, 5)
    with operation(s.gang, actor=s.owner) as op:
        record = op.start_action(s.fighter, s.action, uuid4())
        op.record_action_roll(record, s.outcome.operation, uuid4(), rolled=9)
    if held:
        apply(s, 4, correction=True)
    record.refresh_from_db()
    with pytest.raises(Refusal, match="On hold" if held else "earned action flow"):
        with operation(s.gang, actor=s.owner) as op:
            op.choose(
                record.advancement_selection.slot_assignment,
                s.pick,
                slot=s.outcome.operation.slot,
            )
    assert not Assignment.objects.filter(
        miniature_root=s.fighter, pickable=s.pick, archived=False
    ).exists()


def remove_frozen_award(revision):
    from n26.core.models import PostBattleRevision

    receipt = revision.receipt
    receipt["models"][0].pop("battle_xp_award")
    PostBattleRevision.objects.filter(pk=revision.pk).update(receipt=receipt)


@pytest.mark.parametrize("legacy", [False, True])
@library_setup
def test_displayed_xp_contributions_do_not_count_as_battle_awards(setup, legacy):
    s = setup
    influence = a.create_counter("Influence")
    a.modifier(
        "Influence displays XP",
        a.targets_model(),
        a.ef_contributes_to_counter(s.xp, 5, per_counter=influence),
        attach_to=s.fighter.membership.profile,
    )
    with operation(s.gang, actor=s.owner) as op:
        counter = op.assign(influence, miniature=s.fighter)
        op.open_counter(counter, 0)
    first = apply(s, 0, counters={str(counter.pk): 1})
    assert first.receipt["models"][0]["xp_after"] == 5
    assert first.receipt["models"][0]["battle_xp_award"] == 0
    assert not ActionAllowance.objects.filter(source_kind="battle").exists()
    if legacy:
        remove_frozen_award(first)
    corrected = apply(s, 0, correction=True, counters={str(counter.pk): 2})
    assert corrected.receipt["models"][0]["battle_xp_award"] == 0
    assert not ActionAllowance.objects.filter(source_kind="battle").exists()
    qualifying = apply(s, 5, correction=True, counters={str(counter.pk): 2})
    assert qualifying.receipt["models"][0]["battle_xp_award"] == 5
    assert ActionAllowance.objects.filter(source_kind="battle").count() == 1


@pytest.mark.parametrize("legacy", [False, True])
@library_setup
def test_a_displayed_xp_minimum_does_not_reduce_the_recorded_award(setup, legacy):
    s = setup
    a.revise(s.xp, minimum=1)
    first = apply(s, 5)
    assert first.receipt["models"][0]["xp_before"] == 1
    assert first.receipt["models"][0]["xp_after"] == 5
    assert first.receipt["models"][0]["battle_xp_award"] == 5
    assert ActionAllowance.objects.filter(source_kind="battle").count() == 1
    if legacy:
        remove_frozen_award(first)
    corrected = apply(s, 6, correction=True)
    assert corrected.receipt["models"][0]["battle_xp_award"] == 6
    assert ActionAllowance.objects.filter(source_kind="battle").count() == 1


@pytest.mark.parametrize("next_kind", ["battle", "rank"])
@library_setup
def test_a_reused_membership_slot_belongs_to_its_current_flow(setup, client, next_kind):
    s = setup
    slot = s.outcome.operation.slot
    with operation(s.gang, actor=s.owner) as op:
        shared = op.assign(slot, miniature=s.fighter, caused_by=s.fighter.membership)
    apply(s, 5)
    with operation(s.gang, actor=s.owner) as op:
        old = op.start_action(s.fighter, s.action, uuid4())
        op.record_action_roll(old, s.outcome.operation, uuid4(), rolled=9)
        old = op.apply_action_by_hand(old)
    if next_kind == "battle":
        other_report = start_report(s.gang, actor=s.owner, request_key=uuid4())
        apply(s, 5, report=other_report)
        action = s.action
    else:
        action = a.create_action(
            "Rank name choice",
            "post_cycle",
            outcomes=[s.outcome],
            allowance_rule=a.rank_allowance_rule(s.xp),
        )
        ranks = a.create_rank_table("Name ranks", s.xp, thresholds=[6])
        with operation(s.gang, actor=s.owner) as op:
            op.assign(action, miniature=s.fighter)
            op.assign(ranks, miniature=s.fighter)
            op.tally(s.counter, 1)
    with operation(s.gang, actor=s.owner) as op:
        current = op.start_action(s.fighter, action, uuid4())
        op.record_action_roll(current, s.outcome.operation, uuid4(), rolled=12)
    current.refresh_from_db()
    old.refresh_from_db()
    assert old.advancement_selection.slot_assignment_id == shared.pk
    assert current.advancement_selection.slot_assignment_id == shared.pk
    client.force_login(s.owner)
    key = f"{s.fighter.pk}:{shared.pk}:{slot.pk}"
    picker = reverse("n26-choose", args=[s.gang.pk, key])
    page = client.get(picker)
    if next_kind == "battle":
        assert page.url == reverse(
            "n26-action-flow", args=[s.fighter.pk, current.pk, "resume"]
        )
    else:
        assert page.status_code == 200
    with operation(s.gang, actor=s.owner) as op:
        current = op.review_action(
            current, outcome=s.outcome, terms={"pickable_id": str(s.pick.pk)}
        )
        current = op.complete_action(
            current, revision=current.revision, review=current.review, outcome=s.outcome
        )
    assert current.state == "completed"
    assert Assignment.objects.filter(
        miniature_root=s.fighter, pickable=s.pick, archived=False
    ).exists()


@pytest.fixture
@library_setup
def rating_routes(setup):
    s = setup
    slot = s.outcome.operation.slot
    slot.pick_rating_override = 5
    slot.save(update_fields=["pick_rating_override", "modified"])
    s.battle_slot = slot
    s.other_name = a.create_pickable("Ironhand", s.pick.slot_type)
    a.add_picklist_member(slot.picklist, s.other_name, roll_low=2)
    s.recruitment_slot = a.create_slot(
        "Recruitment name",
        s.pick.slot_type,
        slot.picklist,
        label="Legendary name",
        pick_rating_override=0,
    )
    s.advancement_name_slot = a.create_slot(
        "Advancement name",
        s.pick.slot_type,
        slot.picklist,
        label="Legendary name",
        pick_rating_override=0,
    )
    advancement_kind = a.create_slot_type("Advancement")
    s.name_result = a.create_pickable(
        "Gain a legendary name",
        advancement_kind,
        rating_contribution=10,
        record_only=True,
        effects=[(a.targets_model(), a.ef_adds(s.advancement_name_slot))],
    )
    base = a.create_picklist(
        "Standard advancements", advancement_kind, dice="2d6", roll_selects="threshold"
    )
    normal = a.create_pickable(
        "Ordinary advancement", advancement_kind, rating_contribution=5
    )
    a.add_picklist_member(base, normal, roll_low=2)
    variant = a.clone_picklist(base, "Orlock advancements")
    a.add_picklist_member(variant, s.name_result, roll_low=6)
    advancement_slot = a.create_slot(
        "Orlock advancement", advancement_kind, variant, hidden=True
    )
    s.rank_outcome = a.create_outcome(
        "Orlock advancement", a.resolve_advancement(advancement_slot)
    )
    s.rank_action = a.create_action(
        "Orlock advancement",
        "post_cycle",
        outcomes=[s.rank_outcome],
        allowance_rule=a.rank_allowance_rule(s.xp),
    )
    ranks = a.create_rank_table("Standard fighter ranks", s.xp, thresholds=[4])
    with operation(s.gang, actor=s.owner) as op:
        op.assign(s.rank_action, miniature=s.fighter)
        op.assign(ranks, miniature=s.fighter)
        s.recruitment_anchor = op.assign(s.recruitment_slot, miniature=s.fighter)
    return s


def finish_rated_action(s, action, outcome, pick, *, record=None):
    with operation(s.gang, actor=s.owner) as op:
        if record is None:
            record = op.start_action(s.fighter, action, uuid4())
            op.record_action_roll(record, outcome.operation, uuid4(), rolled=6)
        record.refresh_from_db()
        record = op.review_action(
            record, outcome=outcome, terms={"pickable_id": str(pick.pk)}
        )
        return op.complete_action(
            record, revision=record.revision, review=record.review, outcome=outcome
        )


def test_shared_names_use_the_three_acquisition_ratings_without_spending_credits(
    rating_routes,
):
    s = rating_routes
    before = s.fighter.recompute_rating()
    credits = s.gang.recompute_credits()
    with operation(s.gang, actor=s.owner) as op:
        recruit = op.choose(s.recruitment_anchor, s.pick)
        op.tally(s.counter, 4)
    assert recruit.ledger_entry.rating_contribution == 0
    rank_record = finish_rated_action(s, s.rank_action, s.rank_outcome, s.name_result)
    wrapper = rank_record.advancement_selection.pick_assignment
    with operation(s.gang, actor=s.owner) as op:
        advanced_name = op.choose(
            wrapper, s.other_name, slot=s.advancement_name_slot, miniature=s.fighter
        )
    assert wrapper.ledger_entry.rating_contribution == 10
    assert advanced_name.ledger_entry.rating_contribution == 0
    assert s.fighter.recompute_rating() == before + 10
    apply(s, 5)
    battle = finish_rated_action(s, s.action, s.outcome, s.pick)
    assert (
        battle.advancement_selection.pick_assignment.ledger_entry.rating_contribution
        == 5
    )
    assert s.fighter.recompute_rating() == before + 15
    assert s.gang.recompute_rating() == before + 15
    assert s.gang.recompute_credits() == credits

    from bs4 import BeautifulSoup
    from django.template import Context, Template
    from django_cotton.compiler_regex import CottonCompiler

    from n26.core.printing import detail_groups
    from n26.core.render import render_gang
    from n26.core.render_text import render_model_card
    from n26.core.views.choose import link_slots

    card = render_gang(s.gang).models[0]
    link_slots(s.gang, card)
    row = next(row for row in card.detail_rows if row.label == "Legendary name")
    assert len(row.parts) == 3
    assert len({part.value.key for part in row.parts}) == 3
    assert [part.value.chosen for part in row.parts].count("The Unbroken") == 2
    assert [part.value.chosen for part in row.parts].count("Ironhand") == 1
    html = BeautifulSoup(
        Template(
            CottonCompiler().process(
                '<c-n26.model-card.body :card="card" mode="edit" />'
            )
        ).render(Context({"card": card})),
        "html.parser",
    )
    assert (
        len(
            [
                dt
                for dt in html.select("dt")
                if dt.get_text(strip=True) == "Legendary name"
            ]
        )
        == 1
    )
    assert all(html.find("a", href=part.value.href) for part in row.parts)
    printed = [
        group for group in detail_groups(card) if group.label == "Legendary name"
    ]
    assert len(printed) == 1
    assert printed[0].text.count("The Unbroken") == 2
    assert (
        len([line for line in render_model_card(card) if "Legendary name:" in line])
        == 1
    )
    # Rendering groups headings only; each acquisition keeps its frozen price.
    assert recruit.ledger_entry.rating_contribution == 0
    assert wrapper.ledger_entry.rating_contribution == 10
    assert advanced_name.ledger_entry.rating_contribution == 0
    assert (
        battle.advancement_selection.pick_assignment.ledger_entry.rating_contribution
        == 5
    )
    assert_reconciled(s.gang)


def test_battle_rating_previews_receipts_and_retries_agree(rating_routes, client):
    from n26.core.action_records import action_changes
    from n26.core.advancements import advancement_options

    s = rating_routes
    apply(s, 5)
    with operation(s.gang, actor=s.owner) as op:
        record = op.start_action(s.fighter, s.action, uuid4())
        record = op.save_action_choices(record, outcome=s.outcome, terms={})
        op.record_action_roll(record, s.outcome.operation, uuid4(), rolled=6)
    record.refresh_from_db()
    assert {
        option.rating for option in advancement_options(record, s.outcome.operation)
    } == {5}
    client.force_login(s.owner)
    response = client.get(
        reverse("n26-action-flow", args=[s.fighter.pk, record.pk, "choose"])
    )
    assert "Rating +5¢" in response.content.decode()
    with operation(s.gang, actor=s.owner) as op:
        reviewed = op.review_action(
            record, outcome=s.outcome, terms={"pickable_id": str(s.pick.pk)}
        )
        assert reviewed.review["target"]["rating"] == 5
        completed = op.complete_action(
            reviewed,
            revision=reviewed.revision,
            review=reviewed.review,
            outcome=s.outcome,
        )
        op.complete_action(
            reviewed,
            revision=reviewed.revision,
            review=reviewed.review,
            outcome=s.outcome,
        )
    assert action_changes(completed).rating_delta == 5
    assert Assignment.objects.filter(pickable=s.pick, archived=False).count() == 1
    assert_reconciled(s.gang)


def test_undo_and_correction_retain_recorded_ratings_after_the_slot_changes(
    rating_routes,
):
    from n26.core.advancements import advancement_options

    s = rating_routes
    before = s.fighter.recompute_rating()
    apply(s, 5)
    record = finish_rated_action(s, s.action, s.outcome, s.pick)
    s.battle_slot.pick_rating_override = 7
    s.battle_slot.save(update_fields=["pick_rating_override", "modified"])
    record.refresh_from_db()
    options = {
        option.id: option.rating
        for option in advancement_options(record, s.outcome.operation)
    }
    assert options[str(s.pick.pk)] == 5
    assert options[str(s.other_name.pk)] == 5
    with operation(s.gang, actor=s.owner) as op:
        op.undo_action(record, expected=advancement_undo_snapshot(record))
    assert s.fighter.recompute_rating() == before
    record.refresh_from_db()
    record = finish_rated_action(s, s.action, s.outcome, s.pick, record=record)
    assert s.fighter.recompute_rating() == before + 5
    with operation(s.gang, actor=s.owner) as op:
        terms = {"pickable_id": str(s.other_name.pk)}
        record = op.review_action_correction(record, terms=terms)
        assert record.review["target"]["rating"] == 5
        op.correct_action(
            record, revision=record.revision, review=record.review, terms=terms
        )
    assert s.fighter.recompute_rating() == before + 5
    later = start_report(s.gang, actor=s.owner, request_key=uuid4())
    apply(s, 5, report=later)
    finish_rated_action(s, s.action, s.outcome, s.pick)
    assert s.fighter.recompute_rating() == before + 12
    assert_reconciled(s.gang)


def test_holding_and_restoring_a_report_never_duplicates_the_recorded_rating(
    rating_routes,
):
    s = rating_routes
    before = s.fighter.recompute_rating()
    apply(s, 5)
    record = finish_rated_action(s, s.action, s.outcome, s.pick)
    with operation(s.gang, actor=s.owner) as op:
        op.undo_action(record, expected=advancement_undo_snapshot(record))
    apply(s, 4, correction=True)
    assert s.fighter.recompute_rating() == before
    apply(s, 5, correction=True)
    record.refresh_from_db()
    finish_rated_action(s, s.action, s.outcome, s.pick, record=record)
    apply(s, 5, correction=True)
    assert s.fighter.recompute_rating() == before + 5
    assert ActionAllowance.objects.filter(source_kind="battle").count() == 1
    assert_reconciled(s.gang)


@pytest.mark.parametrize("override,expected", [(None, 10), (0, 0), (5, 5)])
def test_an_ordinary_choice_previews_and_applies_the_slot_rating(
    rating_routes, override, expected
):
    from n26.core.card import build_card, build_modifier_index, carriers
    from n26.core.effects import compute
    from n26.core.render import build_choice_offer

    s = rating_routes
    s.pick.rating_contribution = 10
    s.pick.save(update_fields=["rating_contribution", "modified"])
    s.recruitment_slot.pick_rating_override = override
    s.recruitment_slot.save(update_fields=["pick_rating_override", "modified"])
    card = build_card(s.fighter)
    computed = compute(card, build_modifier_index(carriers(card)))
    choice = next(
        choice for choice in computed.choices if choice.slot.pk == s.recruitment_slot.pk
    )
    offer = build_choice_offer(choice, computed)
    option = next(
        option
        for group in offer.groups
        for option in group.options
        if option.thing.pk == s.pick.pk
    )
    assert option.rating == expected
    with operation(s.gang, actor=s.owner) as op:
        chosen = op.choose(s.recruitment_anchor, s.pick)
    assert chosen.ledger_entry.rating_contribution == expected
    assert chosen.ledger_entry.paid == 0
    assert_reconciled(s.gang)


def test_a_rating_change_between_roll_and_first_completion_is_refused(rating_routes):
    s = rating_routes
    apply(s, 5)
    with operation(s.gang, actor=s.owner) as op:
        record = op.start_action(s.fighter, s.action, uuid4())
        op.record_action_roll(record, s.outcome.operation, uuid4(), rolled=6)
    s.battle_slot.pick_rating_override = 7
    s.battle_slot.save(update_fields=["pick_rating_override", "modified"])
    with pytest.raises(Refusal, match="table changed after the roll"):
        finish_rated_action(s, s.action, s.outcome, s.pick, record=record)


def test_a_saved_roll_from_before_slot_ratings_keeps_its_existing_behaviour(setup):
    s = setup
    apply(s, 5)
    with operation(s.gang, actor=s.owner) as op:
        record = op.start_action(s.fighter, s.action, uuid4())
        op.record_action_roll(record, s.outcome.operation, uuid4(), rolled=6)
    record.refresh_from_db()
    record.terms["advancement_table"].pop("slot_configuration")
    record.terms["advancement_table"].pop("pick_rating_override")
    record.save(update_fields=["terms", "modified"])
    completed = finish_rated_action(s, s.action, s.outcome, s.pick, record=record)
    assert (
        completed.advancement_selection.pick_assignment.ledger_entry.rating_contribution
        == 0
    )


def _historical_rating_apps():
    from django.db.migrations.loader import MigrationLoader
    from django.test import override_settings

    # pytest --nomigrations disables disk discovery; this test needs the
    # historical declarations without applying them to its database.
    with override_settings(MIGRATION_MODULES={}):
        return (
            MigrationLoader(None)
            .project_state(
                [
                    ("n26", "0082_recorded_action_pick_ratings"),
                    ("library", "0129_slot_pick_rating_override"),
                ]
            )
            .apps
        )


@pytest.mark.parametrize("original_rating", [0, 9])
def test_legacy_completed_uses_keep_their_rating_after_the_slot_gains_a_rating(
    setup, original_rating
):
    from importlib import import_module

    from django.db import connection

    s = setup
    before = s.fighter.recompute_rating()
    a.revise(s.pick, rating_contribution=original_rating)
    apply(s, 5)
    record = complete_name(s)
    record.terms["advancement_table"].pop("slot_configuration")
    record.terms["advancement_table"].pop("pick_rating_override")
    record.save(update_fields=["terms", "modified"])
    record.recorded_ratings = {}
    record.save(update_fields=["recorded_ratings", "modified"])
    migration = import_module("n26.core.migrations.0082_recorded_action_pick_ratings")
    apps = _historical_rating_apps()
    migration.preserve_legacy_roll_slots(apps, SimpleNamespace(connection=connection))
    migration.preserve_legacy_pick_ratings(apps, SimpleNamespace(connection=connection))
    slot = s.outcome.operation.slot
    slot.pick_rating_override = 5
    slot.save(update_fields=["pick_rating_override", "modified"])
    record.refresh_from_db()
    with operation(s.gang, actor=s.owner) as op:
        op.undo_action(record, expected=advancement_undo_snapshot(record))
    record.refresh_from_db()
    restored = finish_rated_action(s, s.action, s.outcome, s.pick, record=record)
    assert (
        record.recorded_ratings[str(slot.pk)]["picks"][str(s.pick.pk)]
        == original_rating
    )
    assert (
        restored.advancement_selection.pick_assignment.ledger_entry.rating_contribution
        == original_rating
    )
    assert s.fighter.recompute_rating() == before + original_rating
    later = start_report(s.gang, actor=s.owner, request_key=uuid4())
    apply(s, 5, report=later)
    current = finish_rated_action(s, s.action, s.outcome, s.pick)
    assert (
        current.advancement_selection.pick_assignment.ledger_entry.rating_contribution
        == 5
    )
    assert_reconciled(s.gang)


def test_legacy_snapshot_migration_does_not_accept_already_changed_content(setup):
    from importlib import import_module

    from django.db import connection

    s = setup
    apply(s, 5)
    record = complete_name(s)
    record.terms["advancement_table"].pop("slot_configuration")
    record.terms["advancement_table"].pop("pick_rating_override")
    record.save(update_fields=["terms", "modified"])
    slot = s.outcome.operation.slot
    slot.label = "Changed name choice"
    slot.save(update_fields=["label", "modified"])
    migration = import_module("n26.core.migrations.0082_recorded_action_pick_ratings")
    apps = _historical_rating_apps()
    migration.preserve_legacy_roll_slots(apps, SimpleNamespace(connection=connection))
    migration.preserve_legacy_pick_ratings(apps, SimpleNamespace(connection=connection))
    record.refresh_from_db()
    assert "slot_configuration" not in record.terms["advancement_table"]
    with pytest.raises(Refusal, match="table changed after the roll"):
        advancement_undo_snapshot(record)


@pytest.mark.parametrize("assigned_to,gang_host", [("bearer", True), ("gang", False)])
def test_gang_held_choices_preview_the_zero_rating_they_apply(
    rating_routes, assigned_to, gang_host
):
    from n26.core.card import (
        build_card,
        build_gang_card,
        build_modifier_index,
        carriers,
    )
    from n26.core.effects import compute, compute_gang
    from n26.core.render import build_choice_offer

    s = rating_routes
    slot = a.create_slot(
        "Gang name choice",
        s.pick.slot_type,
        s.battle_slot.picklist,
        assigned_to=assigned_to,
        pick_rating_override=5,
    )
    with operation(s.gang, actor=s.owner) as op:
        anchor = op.assign(
            slot, **({"gang": s.gang} if gang_host else {"miniature": s.fighter})
        )
    card = build_gang_card(s.gang) if gang_host else build_card(s.fighter)
    computed = (compute_gang if gang_host else compute)(
        card, build_modifier_index(carriers(card))
    )
    choice = next(choice for choice in computed.choices if choice.slot.pk == slot.pk)
    offer = build_choice_offer(choice, computed)
    assert {option.rating for group in offer.groups for option in group.options} == {0}
    with operation(s.gang, actor=s.owner) as op:
        chosen = op.choose(anchor, s.pick)
    assert chosen.ledger_entry.rating_contribution == 0
    assert_reconciled(s.gang)


@pytest.mark.parametrize("repeats", [False, True])
def test_held_pick_controls_show_the_recorded_removal_and_new_pick_ratings(
    rating_routes, repeats, client
):
    from n26.core.card import build_card, build_modifier_index, carriers
    from n26.core.effects import compute
    from n26.core.models.dismissed_offer import slot_key
    from n26.core.render import build_choice_offer, option_key

    s = rating_routes
    a.revise(s.pick.slot_type, allows_repeats=repeats)
    slot = a.create_slot(
        "Several names",
        s.pick.slot_type,
        s.battle_slot.picklist,
        max_picks=3,
        pick_rating_override=5,
    )
    with operation(s.gang, actor=s.owner) as op:
        anchor = op.assign(slot, miniature=s.fighter)
        original = op.choose(anchor, s.pick)
    a.revise(slot, pick_rating_override=7)
    if repeats:
        with operation(s.gang, actor=s.owner) as op:
            op.choose(anchor, s.pick)
    card = build_card(s.fighter)
    computed = compute(card, build_modifier_index(carriers(card)))
    choice = next(row for row in computed.choices if row.anchor.key == anchor.pk)
    offer = build_choice_offer(choice, computed)
    held = next(
        row for group in offer.groups for row in group.options if row.thing == s.pick
    )
    assert held.control == ("both" if repeats else "remove")
    assert held.rating == (7 if repeats else 5)
    assert held.removal_rating == 5
    client.force_login(s.owner)
    url = reverse(
        "n26-choose", args=[s.gang.pk, slot_key(s.fighter.pk, anchor.pk, slot.pk)]
    )
    page = client.get(url)
    assert page.status_code == 200
    props = island_props(page.content, "choice-workflow")
    shown = next(
        option
        for group in props["offer"]["groups"]
        for option in group["options"]
        if option["key"] == option_key(s.pick)
    )
    assert shown["control"] == ("both" if repeats else "remove")
    assert shown["rating"] == (7 if repeats else 5)
    assert shown["removalRating"] == 5
    before = s.fighter.recompute_rating()
    response = client.post(url, {**props["values"], "remove": option_key(s.pick)})
    assert response.status_code == 302
    original.refresh_from_db()
    assert original.archived
    assert s.fighter.recompute_rating() == before - 5
    with operation(s.gang, actor=s.owner) as op:
        replacement = op.choose(anchor, s.pick)
    assert replacement.ledger_entry.rating_contribution == 7
    assert_reconciled(s.gang)
