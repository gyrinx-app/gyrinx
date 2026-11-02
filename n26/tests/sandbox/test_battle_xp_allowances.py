"""A battle XP award earns one durable choice, with reversible unused grants."""

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
from n26.tests.fixtures import library_setup
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


def save_award(s, xp, *, report=None, effects=()):
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
                }
            ],
        },
    )


def apply(s, xp, *, correction=False, report=None, effects=()):
    report = report or s.report
    if correction:
        report = start_correction(report, actor=s.owner)
    report = save_award(s, xp, report=report, effects=effects)
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
