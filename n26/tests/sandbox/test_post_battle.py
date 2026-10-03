"""One gang's battle contribution is applied once and corrected by differences."""

from copy import deepcopy
from datetime import date
from uuid import uuid4

import pytest
from django.contrib.auth.models import User
from django.core.exceptions import ValidationError
from django.db import connection
from django.test.utils import CaptureQueriesContext

from n26.core import history
from n26.core.campaigns import campaign_operation
from n26.core.models import Assignment, CounterValue, LedgerEvent, PostBattleRevision
from n26.core.operations import Refusal, operation
from n26.core.post_battle import (
    Option,
    apply_report,
    can_edit_report,
    preview_report,
    save_draft,
    start_correction,
    start_report,
)
from n26.core.reconcile import assert_reconciled
from n26.core.status import Status, status_colour
from n26.library.authoring import add_picklist_member
from n26.tests.sandbox.actions import (
    add_built_in,
    assign,
    attach,
    create_counter,
    create_pickable,
    create_picklist,
    create_profile,
    create_slot,
    create_slot_type,
    create_weapon,
    create_weapon_accessory,
    ef_adds,
    found_campaign,
    found_gang,
    give_weapon,
    hire,
    join_campaign,
    modifier,
    op_changes_counter,
    op_sets_status,
    remove,
    tally,
    targets_every_model,
    targets_model,
)

pytestmark = pytest.mark.django_db


@pytest.fixture
def owner():
    return User.objects.create_user("report-owner")


@pytest.fixture
def arbitrator():
    return User.objects.create_user("report-arbitrator")


@pytest.fixture
def content(default_pack, gang_type, fighter_type):
    xp = create_counter("XP")
    kind = create_slot_type("Lasting injury", is_lasting_effect=True)
    wound = create_pickable(
        "Grievous Wound",
        kind,
        effects=[(targets_model(), op_sets_status(Status.RECOVERY))],
    )
    death = create_pickable(
        "Memorable Death",
        kind,
        effects=[(targets_model(), op_sets_status(Status.DEAD))],
    )
    lesson = create_pickable(
        "Lesson Learned",
        kind,
        effects=[(targets_model(), op_changes_counter(xp, mode="add", amount=2))],
    )
    table = create_picklist(
        "Lasting Injury Table", kind, members=[wound, death, lesson]
    )
    slot = create_slot("Lasting Injury", kind, table, min_picks=0, max_picks=100)
    modifier(
        "Models carry the injury table",
        targets_every_model(),
        ef_adds(slot),
        carried_by=gang_type,
    )
    profile = create_profile("Ganger", fighter_type, gang_type)
    add_built_in(profile, xp)
    return {
        "xp": xp,
        "kind": kind,
        "wound": wound,
        "death": death,
        "lesson": lesson,
        "table": table,
        "slot": slot,
        "profile": profile,
    }


@pytest.fixture
def gang(owner, gang_type, content):
    return found_gang("Ashen Choir", gang_type, owner=owner, budget=1000)


@pytest.fixture
def model(gang, content):
    return hire(gang, content["profile"], "Cinder")


@pytest.fixture
def report(gang, owner, model):
    return start_report(gang, actor=owner, request_key=uuid4(), reference="Stand-off")


@pytest.fixture
def battle(gang, arbitrator, campaign_type):
    campaign = found_campaign(
        "Dust Falls", campaign_type, owner=arbitrator, budget=1000
    )
    join_campaign(gang, campaign)
    with campaign_operation(campaign, actor=arbitrator) as op:
        return op.record_battle(date(2026, 8, 3), [gang], scenario="Stand-off")


def payload_for(model, *, xp=0, credits=0, effects=(), status="", equipment="keep"):
    return {
        "schema": 1,
        "credits": credits,
        "reason": "Scenario reward",
        "participation_confirmed": True,
        "models": [
            {
                "id": str(model.pk),
                "participated": True,
                "xp": xp,
                "status": status,
                "equipment": equipment,
                "effects": list(effects),
            }
        ],
    }


def save(report, owner, payload):
    return save_draft(
        report,
        actor=owner,
        generation=report.generation,
        revision=report.draft_revision,
        payload=payload,
    )


def apply(report, owner, *, key=None, review=None):
    plan = preview_report(report, actor=owner)
    assert plan.valid, plan.errors
    return apply_report(
        report,
        actor=owner,
        generation=report.generation,
        revision=report.draft_revision,
        submission_key=key or uuid4(),
        review=review or plan.review,
    )


def effect_for(report, owner, pick):
    plan = preview_report(report, actor=owner)
    slot = next(
        slot
        for slot in plan.models[0].effect_slots
        if any(option.value == str(pick.pk) for option in slot.options)
    )
    return {"id": str(uuid4()), "slot": slot.key, "pick": str(pick.pk), "choices": {}}


def unpin_historical_revision(revision):
    """Represent immutable receipts written before XP assignment pins existed."""
    inputs = deepcopy(revision.inputs)
    receipt = deepcopy(revision.receipt)
    for model in [*inputs["models"], *receipt["models"]]:
        model.pop("xp_award_assignment_id", None)
    PostBattleRevision.objects.filter(pk=revision.pk).update(
        inputs=inputs, receipt=receipt
    )


class TestDrafts:
    def test_incomplete_draft_is_saved_without_changing_the_gang(
        self, report, owner, gang
    ):
        before = LedgerEvent.objects.count()
        report = save(report, owner, {"credits": "not finished", "models": []})
        assert report.draft["credits"] == "not finished"
        assert report.draft_revision == 1
        assert LedgerEvent.objects.count() == before
        assert not preview_report(report, actor=owner).valid
        assert_reconciled(gang)

    def test_newer_draft_cannot_be_overwritten_by_an_old_tab(self, report, owner):
        save(report, owner, {"credits": "10"})
        with pytest.raises(Refusal, match="another tab"):
            save(report, owner, {"credits": "20"})

    def test_start_requests_and_battle_gang_pair_are_idempotent(
        self, gang, owner, battle
    ):
        key = uuid4()
        first = start_report(gang, actor=owner, battle=battle, request_key=key)
        assert (
            start_report(gang, actor=owner, battle=battle, request_key=key).pk
            == first.pk
        )
        assert (
            start_report(gang, actor=owner, battle=battle, request_key=uuid4()).pk
            == first.pk
        )

    def test_arbitrator_has_authority_only_while_the_gang_is_a_member(
        self, gang, owner, arbitrator, battle
    ):
        report = start_report(
            gang, actor=arbitrator, battle=battle, request_key=uuid4()
        )
        assert can_edit_report(report, arbitrator)
        with operation(gang, actor=owner) as op:
            op.leave_campaign()
        assert not can_edit_report(report, arbitrator)
        assert can_edit_report(report, owner)

    def test_stranger_cannot_read_or_write_private_draft(self, report):
        stranger = User.objects.create_user("stranger")
        assert not can_edit_report(report, stranger)
        with pytest.raises(Refusal, match="owner"):
            preview_report(report, actor=stranger)


@pytest.mark.usefixtures("counter_tracking")
class TestApplication:
    def test_stale_material_review_refuses_every_write(
        self, report, owner, model, content
    ):
        injury = effect_for(report, owner, content["death"])
        report = save(report, owner, payload_for(model, credits=40, effects=[injury]))
        shown = preview_report(report, actor=owner).review
        with operation(report.gang, actor=owner) as op:
            op.set_status(model, Status.CRITICAL)
        count = LedgerEvent.objects.count()
        with pytest.raises(Refusal):
            apply_report(
                report,
                actor=owner,
                generation=report.generation,
                revision=report.draft_revision,
                submission_key=uuid4(),
                review=shown,
            )
        assert LedgerEvent.objects.count() == count
        assert not report.revisions.exists()

    def test_receipt_snapshots_survive_renames(self, report, owner, model, gang):
        report = save(report, owner, payload_for(model, credits=40))
        saved = apply(report, owner)
        with operation(gang, actor=owner) as op:
            op.rename(model, "New name")
        saved.refresh_from_db()
        assert saved.receipt["models"][0]["name"] == "Cinder"

    def test_income_and_xp_are_applied_once_and_receipt_is_immutable(
        self, report, owner, model, gang
    ):
        report = save(report, owner, payload_for(model, xp=3, credits=40))
        key = uuid4()
        receipt = apply(report, owner, key=key)
        count = LedgerEvent.objects.count()
        assert (
            apply_report(
                report,
                actor=owner,
                generation=report.generation,
                revision=report.draft_revision,
                submission_key=key,
                review="ignored",
            ).pk
            == receipt.pk
        )
        assert LedgerEvent.objects.count() == count
        gang.refresh_from_db()
        assert gang.credits == 1040
        assert CounterValue.objects.get(assignment__miniature=model).value == 3
        assert receipt.receipt["models"][0]["xp_after"] == 3
        assert receipt.ledger_events.exclude(gang=gang).count() == 0
        with pytest.raises(ValidationError, match="cannot be edited"):
            receipt.save()
        with pytest.raises(Refusal, match="already been applied"):
            save(report, owner, payload_for(model))
        assert_reconciled(gang)

    def test_first_apply_accepts_typed_xp_and_income_without_a_second_review(
        self, report, owner, model
    ):
        shown = preview_report(report, actor=owner).review
        report = save(report, owner, payload_for(model, xp=2, credits=30))
        apply(report, owner, review=shown)

    def test_participation_confirmation_is_required(self, report, owner, model):
        payload = payload_for(model)
        payload["participation_confirmed"] = False
        report = save(report, owner, payload)
        assert "Confirm which models" in " ".join(
            preview_report(report, actor=owner).errors
        )
        assert not PostBattleRevision.objects.exists()

    def test_out_of_action_does_not_imply_did_not_participate(
        self, report, owner, model
    ):
        with operation(report.gang, actor=owner) as op:
            op.set_status(model, Status.RECOVERY)
        report = save(report, owner, payload_for(model, xp=1))
        receipt = apply(report, owner)
        assert receipt.receipt["models"][0]["participated"]
        model.refresh_from_db()
        assert model.status == Status.RECOVERY

    def test_every_induced_event_names_the_battle_and_occurrence(
        self, gang, owner, battle, model, content
    ):
        report = start_report(gang, actor=owner, battle=battle, request_key=uuid4())
        injury = effect_for(report, owner, content["wound"])
        report = save(report, owner, payload_for(model, effects=[injury]))
        saved = apply(report, owner)
        events = saved.ledger_events.filter(post_battle_occurrence=injury["id"])
        assert events.filter(kind=LedgerEvent.Kind.STATUS_SET).exists()
        assert not saved.ledger_events.exclude(
            battle=battle, campaign=battle.campaign
        ).exists()
        model.refresh_from_db()
        assert model.status == Status.RECOVERY
        assert_reconciled(gang)

    def test_repeated_injuries_are_separate_occurrences(
        self, report, owner, model, content
    ):
        injuries = [effect_for(report, owner, content["wound"]) for _ in range(2)]
        report = save(report, owner, payload_for(model, effects=injuries))
        saved = apply(report, owner)
        assert len(saved.receipt["occurrences"]) == 2
        assert (
            Assignment.objects.filter(
                miniature=model, pickable=content["wound"], archived=False
            ).count()
            == 2
        )

    def test_conflicting_injuries_require_explicit_final_status(
        self, report, owner, model, content
    ):
        injuries = [
            effect_for(report, owner, content[name]) for name in ("death", "wound")
        ]
        report = save(report, owner, payload_for(model, effects=injuries))
        assert "final status" in " ".join(preview_report(report, actor=owner).errors)
        report = save(
            report, owner, payload_for(model, effects=injuries, status=Status.DEAD)
        )
        apply(report, owner)
        model.refresh_from_db()
        assert model.status == Status.DEAD

    def test_conflicting_injuries_name_each_result_and_status(
        self, report, owner, model, content
    ):
        injuries = [
            effect_for(report, owner, content[name]) for name in ("wound", "death")
        ]
        report = save(report, owner, payload_for(model, effects=injuries))

        (result,) = preview_report(report, actor=owner).models

        message = (
            "Grievous Wound makes Cinder In Recovery and Memorable Death makes "
            "Cinder Dead. Choose the final status."
        )
        assert result.status_conflict == message
        assert f"Cinder: {message}" in preview_report(report, actor=owner).errors

    def test_content_counter_effect_is_in_the_receipt(
        self, report, owner, model, content
    ):
        injury = effect_for(report, owner, content["lesson"])
        report = save(report, owner, payload_for(model, xp=1, effects=[injury]))
        saved = apply(report, owner)
        assert saved.receipt["models"][0]["xp_after"] == 3
        assert CounterValue.objects.get(assignment__miniature=model).value == 3


@pytest.mark.usefixtures("counter_tracking")
class TestCorrections:
    @pytest.mark.parametrize(
        "effect_mode,original_xp,spent_xp,corrected_xp,reversal_delta",
        [("add", 0, 2, 2, -2), ("subtract", 2, 0, 0, 2)],
    )
    def test_manual_xp_and_effect_reversal_share_one_unclipped_balance(
        self,
        report,
        owner,
        model,
        content,
        effect_mode,
        original_xp,
        spent_xp,
        corrected_xp,
        reversal_delta,
    ):
        from n26.tests.sandbox.actions import add_picklist_member

        pick = create_pickable(
            "Counter adjustment",
            content["kind"],
            effects=[
                (
                    targets_model(),
                    op_changes_counter(content["xp"], mode=effect_mode, amount=2),
                )
            ],
        )
        add_picklist_member(content["table"], pick)
        injury = effect_for(report, owner, pick)
        report = save(
            report, owner, payload_for(model, xp=original_xp, effects=[injury])
        )
        original = apply(report, owner)
        original_tally = original.ledger_events.get(
            kind=LedgerEvent.Kind.TALLIED, post_battle_occurrence=injury["id"]
        )
        xp = Assignment.objects.get(miniature=model, counter__name="XP")
        if spent_xp:
            tally(xp, -spent_xp)
        assert CounterValue.objects.get(assignment=xp).value == 0

        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model, xp=corrected_xp))
        plan = preview_report(report, actor=owner)
        assert plan.valid, plan.errors
        assert plan.models[0].xp_after == 0
        key = uuid4()
        saved = apply(report, owner, key=key)
        tallies = saved.ledger_events.filter(kind=LedgerEvent.Kind.TALLIED)
        assert list(
            tallies.order_by("created", "pk").values_list(
                "counter_before", "counter_delta", "counter_after"
            )
        ) == [(0, 2, 2), (2, -2, 0)]
        reversal = tallies.get(reversal_of=original_tally)
        assert reversal.counter_delta == reversal_delta
        assert str(reversal.post_battle_occurrence) == injury["id"]
        manual = tallies.get(reversal_of__isnull=True)
        assert manual.counter_delta == -reversal_delta
        assert manual.post_battle_occurrence is None
        assert CounterValue.objects.get(assignment=xp).value == 0
        assert saved.receipt["models"][0]["xp_before"] == 0
        assert saved.receipt["models"][0]["xp_after"] == 0
        event_count = LedgerEvent.objects.count()
        retry = apply_report(
            report,
            actor=owner,
            generation=report.generation,
            revision=report.draft_revision,
            submission_key=key,
            review=plan.review,
        )
        assert retry.pk == saved.pk
        assert LedgerEvent.objects.count() == event_count
        assert CounterValue.objects.get(assignment=xp).value == 0
        assert_reconciled(report.gang)

    def test_incomplete_correction_cannot_silently_zero_an_omitted_model(
        self, report, owner, model
    ):
        report = save(report, owner, payload_for(model, xp=3))
        apply(report, owner)
        report = start_correction(report, actor=owner)
        payload = deepcopy(report.draft)
        payload["models"] = []
        report = save(report, owner, payload)
        assert "Include every model" in " ".join(
            preview_report(report, actor=owner).errors
        )

    def test_replacing_an_occurrence_does_not_reverse_it_twice(
        self, report, owner, model, content
    ):
        injury = effect_for(report, owner, content["lesson"])
        report = save(report, owner, payload_for(model, effects=[injury]))
        apply(report, owner)
        report = start_correction(report, actor=owner)
        injury["pick"] = str(content["wound"].pk)
        report = save(report, owner, payload_for(model, effects=[injury]))
        apply(report, owner)
        assert CounterValue.objects.get(assignment__miniature=model).value == 0
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model, status=Status.ACTIVE))
        apply(report, owner)
        assert CounterValue.objects.get(assignment__miniature=model).value == 0

    def test_a_replaced_injury_takes_its_status_with_it(
        self, report, owner, model, content
    ):
        injury = effect_for(report, owner, content["wound"])
        report = save(report, owner, payload_for(model, effects=[injury]))
        apply(report, owner)
        model.refresh_from_db()
        assert model.status == Status.RECOVERY
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model))

        plan = preview_report(report, actor=owner)

        assert plan.errors == []
        assert plan.models[0].final_status == Status.ACTIVE
        apply(report, owner)
        model.refresh_from_db()
        assert model.status == Status.ACTIVE

    def test_a_replacing_injury_sets_the_status_it_implies(
        self, report, owner, model, content
    ):
        injury = effect_for(report, owner, content["wound"])
        report = save(report, owner, payload_for(model, effects=[injury]))
        apply(report, owner)
        report = start_correction(report, actor=owner)
        injury["pick"] = str(content["death"].pk)
        report = save(report, owner, payload_for(model, effects=[injury]))

        plan = preview_report(report, actor=owner)

        assert plan.errors == []
        assert plan.models[0].final_status == Status.DEAD

    def test_an_explicit_final_status_wins_over_a_replaced_injury(
        self, report, owner, model, content
    ):
        injury = effect_for(report, owner, content["wound"])
        report = save(report, owner, payload_for(model, effects=[injury]))
        apply(report, owner)
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model, status=Status.CRITICAL))

        plan = preview_report(report, actor=owner)

        assert plan.errors == []
        assert plan.models[0].final_status == Status.CRITICAL

    def test_a_result_that_disagrees_with_the_status_now_names_both(
        self, report, owner, model, content
    ):
        with operation(report.gang, actor=owner) as op:
            op.set_status(model, Status.RECOVERY)
        injury = effect_for(report, owner, content["death"])
        report = save(report, owner, payload_for(model, effects=[injury]))

        plan = preview_report(report, actor=owner)

        assert plan.errors == [
            "Cinder: Memorable Death makes Cinder Dead, but Cinder's final status "
            "is In Recovery. Choose the final status."
        ]

    def test_two_reversed_contributions_cannot_clip_the_counter(
        self, report, owner, model, content
    ):
        injuries = [effect_for(report, owner, content["lesson"]) for _ in range(2)]
        report = save(report, owner, payload_for(model, effects=injuries))
        apply(report, owner)
        tally(Assignment.objects.get(miniature=model, counter__name="XP"), -1)
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model))
        assert "below zero" in " ".join(preview_report(report, actor=owner).errors)

    def test_new_dependency_below_injury_refuses_removal(
        self, report, owner, model, content
    ):
        injury = effect_for(report, owner, content["lesson"])
        report = save(report, owner, payload_for(model, effects=[injury]))
        saved = apply(report, owner)
        root = Assignment.objects.get(
            pk=saved.receipt["occurrences"][injury["id"]]["root_id"]
        )
        with operation(report.gang, actor=owner) as op:
            op.assign(
                create_counter("Later tally"), miniature=model, caused_by=root, paid=0
            )
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model))
        assert "changed since" in " ".join(preview_report(report, actor=owner).errors)

    def test_contribution_difference_preserves_later_xp_and_income(
        self, report, owner, model, gang
    ):
        report = save(report, owner, payload_for(model, xp=4, credits=40))
        apply(report, owner)
        xp = Assignment.objects.get(miniature=model, counter__name="XP")
        tally(xp, 5)
        with operation(gang, actor=owner) as op:
            op.receive_credits(30, "Another reward")
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model, xp=2, credits=25))
        saved = apply(report, owner)
        assert saved.sequence == 2
        assert CounterValue.objects.get(assignment=xp).value == 7
        gang.refresh_from_db()
        assert gang.credits == 1055
        assert_reconciled(gang)

    def test_retained_effects_do_not_reapply_status_or_counters(
        self, report, owner, model, content
    ):
        injuries = [
            effect_for(report, owner, content[name]) for name in ("wound", "lesson")
        ]
        report = save(report, owner, payload_for(model, effects=injuries))
        apply(report, owner)
        with operation(report.gang, actor=owner) as op:
            op.set_status(model, Status.ACTIVE)
        report = start_correction(report, actor=owner)
        payload = deepcopy(report.draft)
        payload["credits"] = 10
        report = save(report, owner, payload)
        saved = apply(report, owner)
        model.refresh_from_db()
        assert model.status == Status.ACTIVE
        assert CounterValue.objects.get(assignment__miniature=model).value == 2
        assert not saved.ledger_events.filter(
            post_battle_occurrence__isnull=False
        ).exists()

    def test_exact_injury_removal_reverses_its_counter_contribution_only(
        self, report, owner, model, content
    ):
        injury = effect_for(report, owner, content["lesson"])
        report = save(report, owner, payload_for(model, effects=[injury]))
        apply(report, owner)
        xp = Assignment.objects.get(miniature=model, counter__name="XP")
        tally(xp, 7)
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model))
        apply(report, owner)
        assert CounterValue.objects.get(assignment=xp).value == 7
        assert not Assignment.objects.filter(
            miniature=model, pickable=content["lesson"], archived=False
        ).exists()

    def test_stale_original_draft_cannot_overwrite_correction(
        self, report, owner, model
    ):
        report = save(report, owner, payload_for(model))
        apply(report, owner)
        correction = start_correction(report, actor=owner)
        assert correction.generation != report.generation
        with pytest.raises(Refusal, match="another tab"):
            save(report, owner, payload_for(model, credits=20))

    def test_negative_correction_cannot_silently_clip_xp(self, report, owner, model):
        report = save(report, owner, payload_for(model, xp=3))
        apply(report, owner)
        tally(Assignment.objects.get(miniature=model, counter__name="XP"), -3)
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model))
        assert "below zero" in " ".join(preview_report(report, actor=owner).errors)


@pytest.mark.usefixtures("counter_tracking")
class TestManualXpSources:
    @pytest.mark.parametrize("change", ["archive", "move", "replace"])
    @pytest.mark.parametrize("historical", [False, True])
    def test_changed_counter_refuses_xp_correction_without_partial_income(
        self, report, owner, model, gang, content, change, historical
    ):
        report = save(report, owner, payload_for(model, xp=4))
        original = apply(report, owner)
        xp = Assignment.objects.get(miniature=model, counter__name="XP")
        source = str(xp.pk)
        assert original.inputs["models"][0]["xp_award_assignment_id"] == source
        assert original.receipt["models"][0]["xp_award_assignment_id"] == source
        if historical:
            unpin_historical_revision(original)
        other = hire(gang, content["profile"], "Ember") if change == "move" else None
        with operation(gang, actor=owner) as op:
            if other:
                op.move(xp, other)
            else:
                op.remove(xp)
            if change == "replace":
                replacement = op.assign(content["xp"], miniature=model, paid=0)
                op.tally(replacement, 2)
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model, xp=2, credits=40))
        plan = preview_report(report, actor=owner)
        assert not plan.valid
        assert "original XP counter" in " ".join(plan.errors)
        event_count = LedgerEvent.objects.count()
        with pytest.raises(Refusal, match="original XP counter"):
            apply_report(
                report,
                actor=owner,
                generation=report.generation,
                revision=report.draft_revision,
                submission_key=uuid4(),
                review=plan.review,
            )
        assert LedgerEvent.objects.count() == event_count
        assert report.revisions.count() == 1
        gang.refresh_from_db()
        assert gang.credits == 1000
        if change == "replace":
            assert CounterValue.objects.get(assignment=replacement).value == 2

    @pytest.mark.parametrize("historical", [False, True])
    def test_credit_only_corrections_preserve_the_original_counter(
        self, report, owner, model, gang, content, historical
    ):
        report = save(report, owner, payload_for(model, xp=4))
        original = apply(report, owner)
        xp = Assignment.objects.get(miniature=model, counter__name="XP")
        source = str(xp.pk)
        if historical:
            unpin_historical_revision(original)
        # A zero-delta historical revision has no manual tally of its own.
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model, xp=4, credits=10))
        interim = apply(report, owner)
        assert interim.inputs["models"][0]["xp_award_assignment_id"] == source
        if historical:
            unpin_historical_revision(interim)
        with operation(gang, actor=owner) as op:
            op.remove(xp)
            replacement = op.assign(content["xp"], miniature=model, paid=0)
            op.tally(replacement, 2)
        report = start_correction(report, actor=owner)
        draft = payload_for(model, xp=4, credits=20)
        draft["models"][0]["xp_award_assignment_id"] = str(replacement.pk)
        report = save(report, owner, draft)
        saved = apply(report, owner)
        assert saved.inputs["models"][0]["xp_award_assignment_id"] == source
        assert saved.receipt["models"][0]["xp_award_assignment_id"] == source
        assert not saved.ledger_events.filter(kind=LedgerEvent.Kind.TALLIED).exists()
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model, xp=2, credits=30))
        assert "original XP counter" in " ".join(
            preview_report(report, actor=owner).errors
        )
        assert CounterValue.objects.get(assignment=replacement).value == 2
        gang.refresh_from_db()
        assert gang.credits == 1020

    def test_zero_contribution_can_start_a_new_award_on_the_current_counter(
        self, report, owner, model, gang, content
    ):
        report = save(report, owner, payload_for(model, xp=4))
        apply(report, owner)
        xp = Assignment.objects.get(miniature=model, counter__name="XP")
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model, xp=0))
        apply(report, owner)
        with operation(gang, actor=owner) as op:
            op.remove(xp)
            replacement = op.assign(content["xp"], miniature=model, paid=0)
            op.tally(replacement, 2)
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model, xp=3))
        saved = apply(report, owner)
        assert saved.inputs["models"][0]["xp_award_assignment_id"] == str(
            replacement.pk
        )
        assert CounterValue.objects.get(assignment=replacement).value == 5

    def test_historical_award_corrects_the_same_counter(self, report, owner, model):
        report = save(report, owner, payload_for(model, xp=4))
        original = apply(report, owner)
        unpin_historical_revision(original)
        xp = Assignment.objects.get(miniature=model, counter__name="XP")
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model, xp=2))
        saved = apply(report, owner)
        assert saved.inputs["models"][0]["xp_award_assignment_id"] == str(xp.pk)
        assert CounterValue.objects.get(assignment=xp).value == 2

    def test_more_historical_awards_do_not_add_preview_queries(
        self, report, owner, model, gang, content
    ):
        report = save(report, owner, payload_for(model, xp=4))
        unpin_historical_revision(apply(report, owner))
        report = start_correction(report, actor=owner)
        with CaptureQueriesContext(connection) as one:
            first = preview_report(report, actor=owner)
        models = [
            model,
            hire(gang, content["profile"], "Ember"),
            hire(gang, content["profile"], "Ash"),
        ]
        report = start_report(gang, actor=owner, request_key=uuid4())
        payload = payload_for(model, xp=4)
        payload["models"] = [payload_for(m, xp=4)["models"][0] for m in models]
        report = save(report, owner, payload)
        unpin_historical_revision(apply(report, owner))
        report = start_correction(report, actor=owner)
        with CaptureQueriesContext(connection) as many:
            expanded = preview_report(report, actor=owner)
        assert first.valid and expanded.valid
        assert len(one) == len(many), (len(one), len(many))
        assert all(
            result.xp_award_assignment_id == result.xp_assignment_id
            for result in expanded.models
        )

    def test_reselected_injury_counter_cannot_receive_an_old_manual_correction(
        self, report, owner, model, gang, content
    ):
        xp = Assignment.objects.get(miniature=model, counter__name="XP")
        with operation(gang, actor=owner) as op:
            op.remove(xp)
        injury_report = start_report(gang, actor=owner, request_key=uuid4())
        injury = effect_for(injury_report, owner, content["lesson"])
        injury_report = save(injury_report, owner, payload_for(model, effects=[injury]))
        injury_result = apply(injury_report, owner)
        report = save(report, owner, payload_for(model, xp=4))
        original = apply(report, owner)
        root = Assignment.objects.get(
            pk=injury_result.receipt["occurrences"][injury["id"]]["root_id"]
        )
        with operation(gang, actor=owner) as op:
            op.remove(root)
            op.choose(
                root.chosen_for,
                content["lesson"],
                slot=content["slot"],
                miniature=model,
            )
        replacement = Assignment.objects.get(
            miniature=model, counter__name="XP", archived=False
        )
        assert CounterValue.objects.get(assignment=replacement).value == 2
        assert original.inputs["models"][0]["xp_award_assignment_id"] != str(
            replacement.pk
        )
        report = start_correction(report, actor=owner)
        report = save(report, owner, payload_for(model, xp=2))
        assert "original XP counter" in " ".join(
            preview_report(report, actor=owner).errors
        )


@pytest.mark.usefixtures("counter_tracking")
class TestRequiredChoicesAndEquipment:
    def test_subchoices_are_projected_required_saved_and_retained(
        self, report, owner, model, content
    ):
        kind = create_slot_type("Injured location")
        hand = create_pickable("Hand", kind)
        eye = create_pickable("Eye", kind)
        table = create_picklist("Location", kind, members=[hand, eye])
        slot = create_slot("Choose location", kind, table)
        injury = create_pickable(
            "Location injury",
            content["kind"],
            effects=[(targets_model(), ef_adds(slot))],
        )
        from n26.tests.sandbox.actions import add_picklist_member

        add_picklist_member(content["table"], injury)
        effect = effect_for(report, owner, injury)
        report = save(report, owner, payload_for(model, effects=[effect]))
        plan = preview_report(report, actor=owner)
        assert not plan.valid
        question = plan.models[0].effects[0].questions[0]
        effect["choices"][question.key] = [
            next(o.value for o in question.options if o.label == "Hand")
        ]
        report = save(report, owner, payload_for(model, effects=[effect]))
        apply(report, owner)
        assert Assignment.objects.filter(
            miniature=model, pickable=hand, archived=False
        ).exists()
        report = start_correction(report, actor=owner)
        plan = preview_report(report, actor=owner)
        assert plan.valid, plan.errors
        assert (
            plan.models[0].effects[0].questions[0].selected
            == effect["choices"][question.key]
        )
        assert not plan._writes

    @pytest.mark.parametrize("disposition", ["keep", "stash", "lost"])
    def test_death_equipment_disposition_is_explicit_and_reconciled(
        self, report, owner, model, gang, content, disposition
    ):
        weapon = create_weapon("Autogun", price=20)
        assignment = give_weapon(model, weapon, paid=20)
        injury = effect_for(report, owner, content["death"])
        report = save(
            report, owner, payload_for(model, effects=[injury], equipment=disposition)
        )
        saved = apply(report, owner)
        recorded = saved.receipt["models"][0]
        assert recorded["equipment_disposition"] == disposition
        assert recorded["equipment_changed"] == (disposition != "keep")
        assert recorded["equipment_names"] == (
            ["Autogun"] if disposition != "keep" else []
        )
        assignment.refresh_from_db()
        model.refresh_from_db()
        assert model.status == Status.DEAD
        assert assignment.archived == (disposition == "lost")
        assert bool(assignment.stash_id) == (disposition == "stash")
        gang.refresh_from_db()
        assert_reconciled(gang)

    @pytest.mark.parametrize("disposition", ["stash", "lost"])
    def test_equipment_only_result_names_every_item_and_freezes_the_receipt(
        self, report, owner, model, gang, disposition
    ):
        weapon = create_weapon("Autogun")
        gun = give_weapon(model, weapon)
        sight = create_weapon_accessory("Sight")
        attached = attach(gun, sight)
        with operation(gang, actor=owner) as op:
            op.set_status(model, Status.DEAD)
        report = save(report, owner, payload_for(model, equipment=disposition))
        plan = preview_report(report, actor=owner)
        result = plan.models[0]
        assert plan.valid, plan.errors
        assert not plan._status_writes
        assert not plan._writes
        assert result.xp_change == 0
        assert result.equipment_changed
        assert result.equipment_disposition == disposition
        assert set(result.equipment_affected_names) == {"Autogun", "Sight"}
        assert not result.equipment_exclusions
        saved = apply(report, owner)
        recorded = saved.receipt["models"][0]
        assert recorded["equipment_changed"]
        assert recorded["equipment_disposition"] == disposition
        assert set(recorded["equipment_names"]) == {"Autogun", "Sight"}
        assert recorded["equipment_exclusions"] == []
        gun.refresh_from_db()
        attached.refresh_from_db()
        assert gun.archived == attached.archived == (disposition == "lost")
        assert (
            bool(gun.stash_root_id)
            == bool(attached.stash_root_id)
            == (disposition == "stash")
        )
        weapon.name = "Renamed weapon"
        weapon.save(update_fields=["name"])
        sight.name = "Renamed attachment"
        sight.save(update_fields=["name"])
        saved.refresh_from_db()
        assert set(saved.receipt["models"][0]["equipment_names"]) == {
            "Autogun",
            "Sight",
        }
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_new_attachment_requires_an_updated_equipment_review(
        self, report, owner, model, gang
    ):
        gun = give_weapon(model, create_weapon("Autogun"))
        with operation(gang, actor=owner) as op:
            op.set_status(model, Status.DEAD)
        report = save(report, owner, payload_for(model, equipment="lost"))
        shown = preview_report(report, actor=owner).review
        attach(gun, create_weapon_accessory("New sight"))
        with pytest.raises(Refusal, match="Check the changes"):
            apply_report(
                report,
                actor=owner,
                generation=report.generation,
                revision=report.draft_revision,
                submission_key=uuid4(),
                review=shown,
            )
        gun.refresh_from_db()
        assert not gun.archived
        assert not report.revisions.exists()

    def test_computed_equipment_is_named_as_unchanged(
        self, report, owner, model, gang, content
    ):
        give_weapon(model, create_weapon("Autogun"))
        modifier(
            "Granted weapon",
            targets_model(),
            ef_adds(create_weapon("Rule-granted gun")),
            carried_by=content["profile"],
        )
        with operation(gang, actor=owner) as op:
            op.set_status(model, Status.DEAD)
        report = save(report, owner, payload_for(model, equipment="stash"))
        result = preview_report(report, actor=owner).models[0]
        assert result.equipment_affected_names == ["Autogun"]
        assert "Rule-granted gun (provided by a rule)" in result.equipment_exclusions
        saved = apply(report, owner)
        assert (
            saved.receipt["models"][0]["equipment_exclusions"]
            == result.equipment_exclusions
        )

    def test_equipment_with_another_holders_dependency_is_named_as_unchanged(
        self, report, owner, model, gang, content
    ):
        other = hire(gang, content["profile"], "Ember")
        gun = give_weapon(model, create_weapon("Linked gun"))
        ordinary = give_weapon(model, create_weapon("Autogun"))
        with operation(gang, actor=owner) as op:
            dependent = op.assign(
                create_counter("Linked counter"), miniature=other, caused_by=gun, paid=0
            )
            op.set_status(model, Status.DEAD)
        report = save(report, owner, payload_for(model, equipment="lost"))
        plan = preview_report(report, actor=owner)
        result = next(item for item in plan.models if item.id == str(model.pk))
        assert result.equipment_affected_names == ["Autogun"]
        assert any("Linked gun" in excluded for excluded in result.equipment_exclusions)
        saved = apply(report, owner)
        gun.refresh_from_db()
        dependent.refresh_from_db()
        ordinary.refresh_from_db()
        assert not gun.archived
        assert not dependent.archived
        assert ordinary.archived
        recorded = next(
            item for item in saved.receipt["models"] if item["id"] == str(model.pk)
        )
        assert recorded["equipment_exclusions"] == result.equipment_exclusions

    def test_later_correction_does_not_repeat_equipment_disposal(
        self, report, owner, model, gang
    ):
        give_weapon(model, create_weapon("Autogun"))
        with operation(gang, actor=owner) as op:
            op.set_status(model, Status.DEAD)
        report = save(report, owner, payload_for(model, equipment="stash"))
        first = apply(report, owner)
        report = start_correction(report, actor=owner)
        payload = deepcopy(report.draft)
        payload["credits"] = 10
        report = save(report, owner, payload)
        plan = preview_report(report, actor=owner)
        assert not plan.models[0].equipment_changed
        second = apply(report, owner)
        assert first.receipt["models"][0]["equipment_names"] == ["Autogun"]
        assert not second.receipt["models"][0]["equipment_changed"]
        assert second.receipt["models"][0]["equipment_names"] == []

    def test_more_models_do_not_add_preview_queries(
        self, report, owner, gang, content, model
    ):
        with CaptureQueriesContext(connection) as first:
            preview_report(report, actor=owner)
        hire(gang, content["profile"], "Ember")
        hire(gang, content["profile"], "Ash")
        with CaptureQueriesContext(connection) as many:
            preview_report(report, actor=owner)
        assert len(first) == len(many), (len(first), len(many))


class TestWithoutCounterTracking:
    def test_income_and_status_work_without_xp_tracking(self, report, owner, model):
        report = save(
            report, owner, payload_for(model, credits=20, status=Status.RECOVERY)
        )
        plan = preview_report(report, actor=owner)
        assert plan.valid, plan.errors
        assert not plan.models[0].xp_available
        apply(report, owner)

    def test_xp_is_refused_without_counter_tracking(self, report, owner, model):
        report = save(report, owner, payload_for(model, xp=2))
        plan = preview_report(report, actor=owner)
        assert plan.models[0].xp_blocked == "tracking_off"
        assert "counter history is switched on" in " ".join(plan.errors)

    def test_no_xp_counter_is_created_as_a_fallback(
        self, gang, owner, gang_type, fighter_type
    ):
        profile = create_profile("Civilian", fighter_type, gang_type)
        model = hire(gang, profile, "Visitor")
        report = start_report(gang, actor=owner, request_key=uuid4())
        report = save(report, owner, payload_for(model, xp=2))
        assert not preview_report(report, actor=owner).valid
        assert not Assignment.objects.filter(
            miniature=model, counter__isnull=False
        ).exists()

    def test_unlimited_credit_report_records_income_without_inventing_a_balance(
        self, owner, gang_type, content
    ):
        gang = found_gang("Free table", gang_type, owner=owner)
        model = hire(gang, content["profile"], "Visitor")
        report = start_report(gang, actor=owner, request_key=uuid4())
        report = save(report, owner, payload_for(model, credits=30))
        plan = preview_report(report, actor=owner)
        assert plan.credits_before is None
        assert plan.credits_after is None
        saved = apply(report, owner)
        assert saved.receipt["credits_change"] == 30
        assert saved.receipt["credits_after"] is None


def payload_for_all(models, **by_name):
    """One entry per model, with XP entered by model name."""
    payload = payload_for(models[0])
    payload["models"] = [
        {
            "id": str(m.pk),
            "participated": True,
            "xp": by_name.get(m.name, 0),
            "status": "",
            "equipment": "keep",
            "effects": [],
        }
        for m in models
    ]
    return payload


@pytest.mark.usefixtures("counter_tracking")
class TestXpBlockedReasons:
    """Each reason a model cannot take XP is named, and it blocks only that model."""

    def test_a_model_with_one_xp_counter_can_take_xp(self, report, owner, model):
        result = preview_report(report, actor=owner).models[0]
        assert result.xp_blocked == ""
        assert result.xp_available
        assert result.xp_blocked_message == ""

    def test_a_model_without_an_xp_counter_is_named(
        self, report, owner, gang, gang_type, fighter_type
    ):
        visitor = hire(
            gang, create_profile("Civilian", fighter_type, gang_type), "Visitor"
        )
        result = next(
            m
            for m in preview_report(report, actor=owner).models
            if m.id == str(visitor.pk)
        )
        assert result.xp_blocked == "no_counter"
        assert not result.xp_available
        assert result.xp_blocked_message == (
            "Visitor has no XP counter, so XP cannot be recorded here."
        )

    def test_a_model_with_two_xp_counters_is_named(self, report, owner, model):
        duplicate = Assignment.objects.get(miniature=model, counter__isnull=False)
        # A second, hand-added XP counter beside the built-in one.
        duplicate.pk = None
        duplicate.materialised_from = None
        duplicate.materialised_for = None
        duplicate.save()
        result = preview_report(report, actor=owner).models[0]
        assert result.xp_blocked == "several_counters"
        assert result.xp_blocked_message.startswith(
            "Cinder has more than one XP counter."
        )

    def test_a_crafted_award_for_a_blocked_model_is_still_refused(
        self, report, owner, gang, model, gang_type, fighter_type
    ):
        visitor = hire(
            gang, create_profile("Civilian", fighter_type, gang_type), "Visitor"
        )
        report = save(report, owner, payload_for_all([model, visitor], Visitor=2))
        plan = preview_report(report, actor=owner)
        assert not plan.valid
        assert (
            "Visitor: This model has no XP counter, so XP cannot be recorded here."
            in plan.errors
        )

    def test_a_blocked_participant_without_xp_does_not_stop_the_report(
        self, report, owner, gang, model, content, gang_type, fighter_type
    ):
        visitor = hire(
            gang, create_profile("Civilian", fighter_type, gang_type), "Visitor"
        )
        payload = payload_for_all([model, visitor], Cinder=2)
        payload["credits"] = 20
        payload["models"][1]["status"] = Status.RECOVERY
        report = save(report, owner, payload)
        wound = effect_for(report, owner, content["wound"])
        payload["models"][0]["effects"] = [wound]
        report = save(report, owner, payload)
        saved = apply(report, owner)
        gang.refresh_from_db()
        visitor.refresh_from_db()
        model.refresh_from_db()
        assert gang.credits == 1020
        assert visitor.status == Status.RECOVERY
        assert model.status == Status.RECOVERY
        assert saved.receipt["models"][0]["xp_change"] == 2
        assert not Assignment.objects.filter(
            miniature=visitor, counter__isnull=False
        ).exists()
        assert_reconciled(gang)


class TestEquipmentOnlyForTheDead:
    """A disposition applies to a dead model. A stale one waits in the draft."""

    def test_an_active_model_with_equipment_lost_applies_and_moves_nothing(
        self, report, owner, model, gang
    ):
        assignment = give_weapon(model, create_weapon("Autogun", price=20), paid=20)
        report = save(report, owner, payload_for(model, equipment="lost"))
        plan = preview_report(report, actor=owner)
        assert plan.valid, plan.errors
        result = plan.models[0]
        assert not result.equipment_applies
        assert result.equipment_ignored
        assert not result.equipment_changed
        saved = apply(report, owner)
        assert saved.inputs["models"][0]["equipment"] == "keep"
        assert not saved.receipt["models"][0]["equipment_changed"]
        assignment.refresh_from_db()
        assert not assignment.archived
        assert assignment.stash_id is None
        gang.refresh_from_db()
        assert_reconciled(gang)

    def test_a_draft_value_survives_a_status_flip_and_returns_on_death(
        self, report, owner, model, content
    ):
        give_weapon(model, create_weapon("Autogun", price=20), paid=20)
        death = effect_for(report, owner, content["death"])
        report = save(
            report, owner, payload_for(model, effects=[death], equipment="stash")
        )
        dead = preview_report(report, actor=owner).models[0]
        assert dead.equipment_applies and dead.equipment_changed
        report = save(report, owner, payload_for(model, equipment="stash"))
        assert report.draft["models"][0]["equipment"] == "stash"
        alive = preview_report(report, actor=owner)
        assert alive.valid, alive.errors
        assert alive.models[0].equipment_ignored
        assert not alive.models[0].equipment_changed
        report = save(
            report, owner, payload_for(model, effects=[death], equipment="stash")
        )
        again = preview_report(report, actor=owner).models[0]
        assert again.equipment_changed
        assert again.equipment_affected_names == ["Autogun"]


class TestRollBands:
    """Roll-table options lead with their band; the values stay the same."""

    def test_options_on_a_roll_table_carry_their_band(
        self, default_pack, gang_type, fighter_type
    ):
        kind = create_slot_type("Lasting injury", is_lasting_effect=True)
        out_cold = create_pickable("Out Cold", kind)
        wound = create_pickable("Grievous Wound", kind)
        table = create_picklist("Injuries", kind, dice="d66", roll_selects="band")
        add_picklist_member(table, out_cold, roll_low=11, roll_high=16)
        add_picklist_member(table, wound, roll_low=21)
        slot = create_slot("Lasting injury", kind, table, min_picks=0, max_picks=9)
        profile = create_profile("Ganger", fighter_type, gang_type)
        add_built_in(profile, slot)
        owner = User.objects.create_user("band-owner")
        gang = found_gang("Test gang", gang_type, owner=owner, budget=100)
        hire(gang, profile, "Cinder")
        report = start_report(gang, actor=owner, request_key=uuid4())
        (slot_offer,) = preview_report(report, actor=owner).models[0].effect_slots
        assert [(o.value, o.text) for o in slot_offer.options] == [
            (str(out_cold.pk), "11–16 Out Cold"),
            (str(wound.pk), "21 Grievous Wound"),
        ]

    def test_a_table_without_dice_shows_names_only(self, report, owner):
        (slot_offer,) = preview_report(report, actor=owner).models[0].effect_slots
        assert [o.text for o in slot_offer.options] == [
            o.label for o in slot_offer.options
        ]
        assert all(not o.band for o in slot_offer.options)

    def test_option_text(self):
        assert Option("x", "Out Cold", "11-16").text == "11–16 Out Cold"
        assert Option("x", "Out Cold").text == "Out Cold"


@pytest.mark.parametrize(
    "status,colour",
    [
        (Status.ACTIVE, "ink"),
        ("", "ink"),
        (Status.RECOVERY, "amber"),
        (Status.CRITICAL, "red"),
        (Status.CAPTURED, "red"),
        (Status.RANSOMED, "red"),
        (Status.DEAD, "red"),
    ],
)
def test_status_colour(status, colour):
    assert status_colour(status) == colour


def with_lines(model, *lines, counters=None):
    """A schema-2 report: ``lines`` are ``(id, amount, reason)``."""
    payload = payload_for(model)
    del payload["credits"], payload["reason"]
    payload["schema"] = 2
    payload["credit_lines"] = [
        {"id": key, "amount": amount, "reason": reason} for key, amount, reason in lines
    ]
    payload["gang_counters"] = counters or {}
    return payload


def income_events(gang):
    return list(
        LedgerEvent.objects.filter(gang=gang, kind=LedgerEvent.Kind.INCOME)
        .order_by("created", "pk")
        .values_list("credits_delta", "note")
    )


@pytest.mark.usefixtures("counter_tracking")
class TestCreditLines:
    """Each line of credits is its own event, and corrections go line by line."""

    def test_lines_add_up_and_each_is_one_event(self, report, owner, model, gang):
        scenario, bounty = str(uuid4()), str(uuid4())
        report = save(
            report,
            owner,
            with_lines(
                model, (scenario, 40, "Scenario reward"), (bounty, 15, "Bounty")
            ),
        )
        plan = preview_report(report, actor=owner)
        assert plan.credits_total == plan.credits_change == 55
        saved = apply(report, owner)
        assert income_events(gang) == [(-40, "Scenario reward"), (-15, "Bounty")]
        gang.refresh_from_db()
        assert gang.credits == 1055
        assert saved.receipt["credit_lines"] == [
            {"id": scenario, "amount": 40, "reason": "Scenario reward"},
            {"id": bounty, "amount": 15, "reason": "Bounty"},
        ]
        assert saved.inputs["schema"] == 2
        assert_reconciled(gang)

    def test_each_amount_needs_a_reason_and_empty_lines_are_dropped(
        self, report, owner, model
    ):
        unexplained = str(uuid4())
        report = save(
            report,
            owner,
            with_lines(model, (unexplained, 10, ""), (str(uuid4()), "", "")),
        )
        plan = preview_report(report, actor=owner)
        assert "Add a reason for each amount of credits." in plan.errors
        assert [line["id"] for line in plan.inputs["credit_lines"]] == [unexplained]

    def test_at_most_twenty_lines(self, report, owner, model):
        lines = [(str(uuid4()), 1, "Tithe") for _ in range(21)]
        report = save(report, owner, with_lines(model, *lines))
        assert (
            "Add up to 20 lines of credits."
            in preview_report(report, actor=owner).errors
        )

    def test_a_correction_changes_and_removes_lines_one_event_each(
        self, report, owner, model, gang
    ):
        scenario, bounty, loot = str(uuid4()), str(uuid4()), str(uuid4())
        report = save(
            report,
            owner,
            with_lines(
                model, (scenario, 40, "Scenario reward"), (bounty, 15, "Bounty")
            ),
        )
        apply(report, owner)
        report = start_correction(report, actor=owner)
        report = save(
            report,
            owner,
            with_lines(model, (scenario, 30, "Scenario reward"), (loot, 5, "Loot")),
        )
        apply(report, owner)
        assert income_events(gang)[2:] == [
            (10, "Scenario reward"),
            (-5, "Loot"),
            (15, "Bounty"),
        ]
        told = [
            "".join(span.text for span in act.spans)
            for act in history.build(gang, viewer=owner)
        ]
        assert "corrected credits by −10¢ — Scenario reward" in told
        assert "corrected credits by +5¢ — Loot" in told
        assert "received 40¢ — Scenario reward" in told
        gang.refresh_from_db()
        assert gang.credits == 1035
        assert_reconciled(gang)

    def test_a_reason_change_alone_writes_nothing(self, report, owner, model, gang):
        line = str(uuid4())
        report = save(report, owner, with_lines(model, (line, 20, "Reward")))
        apply(report, owner)
        report = start_correction(report, actor=owner)
        report = save(report, owner, with_lines(model, (line, 20, "Scenario reward")))
        apply(report, owner)
        assert len(income_events(gang)) == 1

    def test_a_schema_one_report_corrects_through_its_legacy_line(
        self, report, owner, model, gang
    ):
        report = save(report, owner, payload_for(model, credits=40))
        first = apply(report, owner)
        assert first.inputs["credit_lines"] == [
            {"id": "legacy", "amount": 40, "reason": "Scenario reward"}
        ]
        # Stand in for a revision applied before lines of credits existed.
        inputs = deepcopy(first.inputs)
        del inputs["credit_lines"], inputs["gang_counters"]
        inputs |= {"schema": 1, "credits": 40, "reason": "Scenario reward"}
        PostBattleRevision.objects.filter(pk=first.pk).update(inputs=inputs)
        report = start_correction(report, actor=owner)
        assert report.draft["credit_lines"] == [
            {"id": "legacy", "amount": 40, "reason": "Scenario reward"}
        ]
        payload = deepcopy(report.draft)
        payload["credit_lines"][0]["amount"] = 25
        payload["credit_lines"].append(
            {"id": str(uuid4()), "amount": 5, "reason": "Bounty"}
        )
        report = save(report, owner, payload)
        apply(report, owner)
        assert income_events(gang)[1:] == [
            (15, "Scenario reward"),
            (-5, "Bounty"),
        ]
        gang.refresh_from_db()
        assert gang.credits == 1030
        assert_reconciled(gang)


@pytest.fixture
def reputation(gang, owner):
    counter = assign(create_counter("Reputation"), gang=gang, actor=owner)
    tally(counter, 5)
    return counter


def counter_value(assignment):
    return CounterValue.objects.get(assignment=assignment).value


@pytest.mark.usefixtures("counter_tracking")
class TestGangCounters:
    """The gang's counters change by hand, and corrections by the difference."""

    def test_preview_matches_what_is_applied(self, report, owner, model, reputation):
        key = str(reputation.pk)
        report = save(report, owner, with_lines(model, counters={key: "2"}))
        plan = preview_report(report, actor=owner)
        (change,) = plan.gang_counters
        assert (change.name, change.before, change.manual, change.after) == (
            "Reputation",
            5,
            2,
            7,
        )
        saved = apply(report, owner)
        assert counter_value(reputation) == change.after == 7
        assert saved.inputs["gang_counters"] == {key: 2}
        (line,) = saved.receipt["gang_counters"]
        assert (line["name"], line["before"], line["after"]) == ("Reputation", 5, 7)
        event = LedgerEvent.objects.get(
            assignment=reputation, post_battle_revision=saved
        )
        assert event.counter_delta == 2

    def test_xp_and_income_are_not_offered(
        self, report, owner, model, gang, reputation
    ):
        income = assign(create_counter("Income"), gang=gang, actor=owner)
        plan = preview_report(report, actor=owner)
        offered = {change.assignment_id for change in plan.gang_counters}
        assert offered == {str(reputation.pk)}
        assert str(income.pk) not in offered

    def test_a_correction_keeps_a_later_tally(self, report, owner, model, reputation):
        key = str(reputation.pk)
        report = save(report, owner, with_lines(model, counters={key: 3}))
        apply(report, owner)
        tally(reputation, 4)
        report = start_correction(report, actor=owner)
        assert report.draft["gang_counters"] == {key: 3}
        report = save(report, owner, with_lines(model, counters={key: 1}))
        apply(report, owner)
        assert counter_value(reputation) == 5 + 3 + 4 - 2

    def test_below_zero_is_refused(self, report, owner, model, reputation):
        report = save(
            report, owner, with_lines(model, counters={str(reputation.pk): -6})
        )
        assert (
            "Reputation cannot go below 0."
            in preview_report(report, actor=owner).errors
        )

    def test_a_removed_counter_cannot_be_corrected(
        self, report, owner, model, reputation
    ):
        key = str(reputation.pk)
        report = save(report, owner, with_lines(model, counters={key: 2}))
        apply(report, owner)
        remove(reputation, actor=owner)
        report = start_correction(report, actor=owner)
        report = save(report, owner, with_lines(model, counters={key: 1}))
        errors = preview_report(report, actor=owner).errors
        assert any("correct the change to Reputation" in error for error in errors)
        report = save(report, owner, with_lines(model, counters={key: 2}))
        assert preview_report(report, actor=owner).valid

    def test_a_result_that_moves_a_model_counter_leaves_the_gang_alone(
        self, report, owner, model, content, reputation
    ):
        key = str(reputation.pk)
        payload = with_lines(model, counters={key: 1})
        payload["models"][0]["effects"] = [effect_for(report, owner, content["lesson"])]
        report = save(report, owner, payload)
        plan = preview_report(report, actor=owner)
        (change,) = plan.gang_counters
        assert change.effect == 0
        assert not plan.gang_counter_effects
        assert plan.models[0].xp_after == plan.models[0].xp_before + 2
        apply(report, owner)
        assert counter_value(reputation) == 6


@pytest.fixture
def kill_count(model):
    counter = assign(create_counter("Kill Count"), miniature=model)
    tally(counter, 2)
    return counter


@pytest.fixture
def glitches(model):
    return assign(create_counter("Glitch count"), miniature=model)


@pytest.fixture
def glitch(content, glitches):
    """An injury whose stored effect adds 1 to Glitch count."""
    pick = create_pickable(
        "Neural Glitch",
        content["kind"],
        effects=[
            (
                targets_model(),
                op_changes_counter(glitches.assignable, mode="add", amount=1),
            )
        ],
    )
    add_picklist_member(content["table"], pick)
    return pick


def with_model(model, **values):
    """A schema-2 report with ``values`` on its one model."""
    payload = with_lines(model)
    payload["models"][0] |= values
    return payload


@pytest.mark.usefixtures("counter_tracking")
class TestModelCounters:
    """A model's counters change by hand, beside what its results add."""

    def test_kill_count_plus_one_applies(self, report, owner, model, kill_count):
        key = str(kill_count.pk)
        report = save(report, owner, with_model(model, counters={key: "1"}))
        plan = preview_report(report, actor=owner)
        (change,) = plan.models[0].counters
        assert (change.name, change.before, change.manual, change.after) == (
            "Kill Count",
            2,
            1,
            3,
        )
        saved = apply(report, owner)
        assert counter_value(kill_count) == 3
        assert saved.inputs["models"][0]["counters"] == {key: 1}
        (line,) = saved.receipt["models"][0]["counters"]
        assert (line["name"], line["before"], line["after"]) == ("Kill Count", 2, 3)
        event = LedgerEvent.objects.get(
            assignment=kill_count, post_battle_revision=saved
        )
        assert event.counter_delta == 1
        assert event.note.endswith("Post-battle results")

    def test_xp_is_not_offered_and_every_held_counter_is(
        self, report, owner, model, kill_count, glitches
    ):
        plan = preview_report(report, actor=owner)
        assert [change.name for change in plan.models[0].counters] == [
            "Kill Count",
            "Glitch count",
        ]

    def test_an_injury_glitch_shows_once_in_preview_and_receipt(
        self, report, owner, model, glitches, glitch
    ):
        payload = with_model(model)
        payload["models"][0]["effects"] = [effect_for(report, owner, glitch)]
        report = save(report, owner, payload)
        plan = preview_report(report, actor=owner)
        (change,) = plan.models[0].counters
        assert (change.manual, change.effect, change.after) == (0, 1, 1)
        assert plan.models[0].counter_effects
        saved = apply(report, owner)
        assert counter_value(glitches) == 1
        (line,) = saved.receipt["models"][0]["counters"]
        assert (line["manual"], line["effect"], line["after"]) == (0, 1, 1)
        # The injury's own stored effect wrote the tally; nothing else did.
        assert (
            LedgerEvent.objects.filter(
                assignment=glitches, kind=LedgerEvent.Kind.TALLIED
            ).count()
            == 1
        )

    def test_a_manual_change_and_an_injury_add_up(
        self, report, owner, model, glitches, glitch
    ):
        key = str(glitches.pk)
        payload = with_model(model, counters={key: 2})
        payload["models"][0]["effects"] = [effect_for(report, owner, glitch)]
        report = save(report, owner, payload)
        (change,) = preview_report(report, actor=owner).models[0].counters
        assert (change.manual, change.effect, change.after) == (2, 1, 3)
        saved = apply(report, owner)
        assert counter_value(glitches) == 3
        (line,) = saved.receipt["models"][0]["counters"]
        assert line["after"] == 3

    def test_a_correction_keeps_a_later_tally(self, report, owner, model, kill_count):
        key = str(kill_count.pk)
        report = save(report, owner, with_model(model, counters={key: 3}))
        apply(report, owner)
        tally(kill_count, 4)
        report = start_correction(report, actor=owner)
        assert report.draft["models"][0]["counters"] == {key: 3}
        report = save(report, owner, with_model(model, counters={key: 1}))
        apply(report, owner)
        assert counter_value(kill_count) == 2 + 3 + 4 - 2
        assert_reconciled(model.gang)

    def test_below_zero_is_refused(self, report, owner, model, kill_count):
        report = save(
            report, owner, with_model(model, counters={str(kill_count.pk): -3})
        )
        errors = preview_report(report, actor=owner).errors
        assert "Cinder: Kill Count cannot go below 0." in errors

    def test_a_removed_counter_leaves_the_rest_correctable(
        self, report, owner, model, kill_count
    ):
        key = str(kill_count.pk)
        report = save(report, owner, with_model(model, counters={key: 1}, xp=1))
        apply(report, owner)
        remove(kill_count, actor=owner)
        report = start_correction(report, actor=owner)
        # The form no longer lists the counter, so nothing is posted for it.
        payload = deepcopy(report.draft)
        payload["models"][0]["counters"] = {}
        payload["models"][0]["xp"] = 2
        report = save(report, owner, payload)
        plan = preview_report(report, actor=owner)
        assert plan.valid, plan.errors
        assert plan.inputs["models"][0]["counters"] == {key: 1}
        report = save(report, owner, with_model(model, counters={key: 2}, xp=2))
        errors = preview_report(report, actor=owner).errors
        assert any("correct the change to Kill Count" in error for error in errors)


def notes_of(model):
    model.refresh_from_db(fields=["notes"])
    return model.notes


@pytest.mark.usefixtures("counter_tracking")
class TestModelNotes:
    """A note is added to the model's notes once, and never taken away."""

    def test_appears_once_with_the_battle_and_date(self, report, owner, model):
        model.notes = "<p>Old notes.</p>"
        model.save(update_fields=["notes"])
        report = save(report, owner, with_model(model, note="Took <the> bridge."))
        saved = apply(report, owner)
        expected = (
            f"<p>Old notes.</p><p><strong>Stand-off, "
            f"{report.date:%-d %B %Y}:</strong> Took &lt;the&gt; bridge.</p>"
        )
        assert notes_of(model) == expected
        assert saved.receipt["models"][0]["note_appended"] == "Took <the> bridge."
        event = LedgerEvent.objects.get(miniature=model, kind=LedgerEvent.Kind.NOTED)
        assert event.post_battle_revision == saved

    def test_a_retry_does_not_add_it_twice(self, report, owner, model):
        report = save(report, owner, with_model(model, note="Held the line."))
        key = uuid4()
        apply(report, owner, key=key)
        report.refresh_from_db()
        apply_report(
            report,
            actor=owner,
            generation=report.generation,
            revision=report.draft_revision,
            submission_key=key,
            review="",
        )
        assert notes_of(model).count("Held the line.") == 1

    def test_an_empty_note_changes_nothing(self, report, owner, model):
        report = save(report, owner, with_model(model, note="   "))
        saved = apply(report, owner)
        assert notes_of(model) == ""
        assert saved.receipt["models"][0]["note_appended"] == ""
        assert not LedgerEvent.objects.filter(kind=LedgerEvent.Kind.NOTED).exists()

    def test_a_correction_with_the_same_note_adds_nothing(self, report, owner, model):
        report = save(report, owner, with_model(model, note="Held the line."))
        apply(report, owner)
        report = start_correction(report, actor=owner)
        assert report.draft["models"][0]["note"] == "Held the line."
        report = save(report, owner, with_model(model, note="Held the line.", xp=1))
        plan = preview_report(report, actor=owner)
        assert not plan.models[0].note_appends
        saved = apply(report, owner)
        assert notes_of(model).count("Held the line.") == 1
        assert saved.receipt["models"][0]["note_appended"] == ""

    def test_a_changed_note_adds_once_and_keeps_the_old(self, report, owner, model):
        report = save(report, owner, with_model(model, note="Held the line."))
        apply(report, owner)
        report = start_correction(report, actor=owner)
        report = save(report, owner, with_model(model, note="Held the bridge."))
        plan = preview_report(report, actor=owner)
        assert plan.models[0].earlier_note_stays
        apply(report, owner)
        notes = notes_of(model)
        assert notes.count("Held the line.") == 1
        assert notes.count("Held the bridge.") == 1
        # A later correction with the new text, after one with none, adds nothing.
        report = start_correction(report, actor=owner)
        report = save(report, owner, with_model(model, note=""))
        apply(report, owner)
        report = start_correction(report, actor=owner)
        report = save(report, owner, with_model(model, note="Held the bridge."))
        apply(report, owner)
        assert notes_of(model).count("Held the bridge.") == 1

    def test_a_long_note_is_refused(self, report, owner, model):
        report = save(report, owner, with_model(model, note="x" * 2001))
        errors = preview_report(report, actor=owner).errors
        assert "Cinder: Keep the note to 2,000 characters or fewer." in errors


@pytest.mark.usefixtures("counter_tracking")
def test_a_correction_leaves_an_unchanged_counter_off_the_receipt(
    report, owner, model, kill_count
):
    key = str(kill_count.pk)
    report = save(report, owner, with_model(model, counters={key: 1}))
    apply(report, owner)
    report = start_correction(report, actor=owner)
    report = save(report, owner, with_model(model, counters={key: 1}, xp=1))
    saved = apply(report, owner)
    assert saved.receipt["models"][0]["counters"] == []


@pytest.mark.usefixtures("counter_tracking")
def test_a_correction_leaves_an_unchanged_gang_counter_off_the_receipt(
    report, owner, model, reputation
):
    key = str(reputation.pk)
    report = save(report, owner, with_lines(model, counters={key: 2}))
    apply(report, owner)
    report = start_correction(report, actor=owner)
    report = save(
        report, owner, with_lines(model, (str(uuid4()), 5, "Bounty"), counters={key: 2})
    )
    saved = apply(report, owner)
    assert saved.receipt["gang_counters"] == []


@pytest.fixture
def capture_content(content):
    kind = create_slot_type("Release result")
    escaped = create_pickable(
        "Back to the gang",
        kind,
        effects=[(targets_model(), op_sets_status(Status.RECOVERY))],
    )
    table = create_picklist("Release table", kind, members=[escaped])
    slot = create_slot("Release", kind, table, min_picks=0, max_picks=1)
    captured = create_pickable(
        "Taken prisoner",
        content["kind"],
        effects=[
            (targets_model(), op_sets_status(Status.CAPTURED)),
            (targets_model(), ef_adds(slot)),
        ],
    )
    add_picklist_member(content["table"], captured)
    return captured, slot, escaped


def test_pending_escape_can_be_added_to_the_same_battles_report(
    gang, owner, model, battle, capture_content
):
    captured, escape_slot, escaped = capture_content
    report = start_report(gang, actor=owner, battle=battle, request_key=uuid4())
    plan = preview_report(report, actor=owner)
    injury_key = plan.models[0].effect_slots[0].key
    injury = {"id": str(uuid4()), "slot": injury_key, "pick": str(captured.pk)}
    report = save(
        report, owner, payload_for(model, effects=[injury], status=Status.CAPTURED)
    )
    applied = apply(report, owner)
    assert model.__class__.objects.get(pk=model.pk).status == Status.CAPTURED
    report = start_correction(applied.report, actor=owner)
    before_events = LedgerEvent.objects.count()
    plan = preview_report(report, actor=owner)
    assert LedgerEvent.objects.count() == before_events
    offered = next(
        slot for slot in plan.models[0].effect_slots if slot.label == "Release result"
    )
    result = {"id": str(uuid4()), "slot": offered.key, "pick": str(escaped.pk)}
    payload = deepcopy(report.draft)
    payload["models"][0]["effects"].append(result)
    payload["models"][0]["status"] = Status.RECOVERY
    report = save(report, owner, payload)
    applied = apply(report, owner)
    assert model.__class__.objects.get(pk=model.pk).status == Status.RECOVERY
    picked = Assignment.objects.get(miniature=model, pickable=escaped, archived=False)
    assert picked.chosen_for.pickable_id == captured.pk
    assert picked.chosen_for_slot_id == escape_slot.pk
    assert picked.chosen_for.archived is False
    report = start_correction(applied.report, actor=owner)
    payload = deepcopy(report.draft)
    payload["models"][0]["effects"] = [
        effect
        for effect in payload["models"][0]["effects"]
        if effect["id"] != result["id"]
    ]
    payload["models"][0]["status"] = Status.CAPTURED
    report = save(report, owner, payload)
    apply(report, owner)
    model.refresh_from_db()
    assert model.status == Status.CAPTURED
    assert not Assignment.objects.filter(
        miniature=model, pickable=escaped, archived=False
    ).exists()
    assert Assignment.objects.filter(
        miniature=model, pickable=captured, archived=False
    ).exists()
    assert_reconciled(gang)


def test_pending_escape_preserves_choice_limit(report, owner, model, capture_content):
    captured, _, escaped = capture_content
    injury = effect_for(report, owner, captured)
    report = save(
        report, owner, payload_for(model, effects=[injury], status=Status.CAPTURED)
    )
    applied = apply(report, owner)
    report = start_correction(applied.report, actor=owner)
    offered = effect_for(report, owner, escaped)
    payload = deepcopy(report.draft)
    payload["models"][0]["effects"].extend([offered, offered | {"id": str(uuid4())}])
    payload["models"][0]["status"] = Status.RECOVERY
    report = save(report, owner, payload)
    plan = preview_report(report, actor=owner)
    assert not plan.valid
    assert any("no space" in error for error in plan.errors), plan.errors
    assert not Assignment.objects.filter(miniature=model, pickable=escaped).exists()


def test_unrelated_non_lasting_choices_are_not_post_battle_results(
    report, owner, model, capture_content
):
    _, slot, _ = capture_content
    assign(slot, miniature=model)
    plan = preview_report(report, actor=owner)
    assert all(
        offered.label != "Release result" for offered in plan.models[0].effect_slots
    )


@pytest.mark.parametrize("new_occurrence", [False, True])
def test_an_applied_escape_can_be_replaced_in_a_correction(
    report, owner, model, gang, capture_content, new_occurrence
):
    captured, slot, escaped = capture_content
    ransomed = create_pickable(
        "Paid release",
        slot.slot_type,
        effects=[(targets_model(), op_sets_status(Status.RANSOMED))],
    )
    add_picklist_member(slot.picklist, ransomed)
    injury = effect_for(report, owner, captured)
    report = save(
        report, owner, payload_for(model, effects=[injury], status=Status.CAPTURED)
    )
    report = start_correction(apply(report, owner).report, actor=owner)
    escape = effect_for(report, owner, escaped)
    payload = deepcopy(report.draft)
    payload["models"][0]["effects"].append(escape)
    payload["models"][0]["status"] = Status.RECOVERY
    report = save(report, owner, payload)
    report = start_correction(apply(report, owner).report, actor=owner)
    payload = deepcopy(report.draft)
    replacement = escape | {"pick": str(ransomed.pk)}
    if new_occurrence:
        replacement["id"] = str(uuid4())
    payload["models"][0]["effects"] = [injury, replacement]
    payload["models"][0]["status"] = Status.RANSOMED
    before = LedgerEvent.objects.count()
    assert preview_report(report, actor=owner, payload=payload).valid
    assert LedgerEvent.objects.count() == before
    report = save(report, owner, payload)
    apply(report, owner)
    model.refresh_from_db()
    assert model.status == Status.RANSOMED
    assert Assignment.objects.filter(
        miniature=model, pickable=ransomed, archived=False
    ).exists()
    assert Assignment.objects.filter(
        miniature=model, pickable=captured, archived=False
    ).exists()
    assert not Assignment.objects.filter(
        miniature=model, pickable=escaped, archived=False
    ).exists()
    assert_reconciled(gang)
