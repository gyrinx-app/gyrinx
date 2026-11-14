"""Transport-independent stages for starting and completing model actions."""

from collections.abc import Mapping
from contextlib import nullcontext
from copy import copy
from dataclasses import dataclass, field, replace
from urllib.parse import urlencode
from uuid import uuid4

from django.core import signing
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404
from django.urls import reverse

from n26.core.access import actions_for
from n26.core.action_flow import (
    earned_threshold,
    payment_figures,
    payment_tallies,
    receipt_lines,
)
from n26.core.action_forms import (
    ActionOutcomeForm,
    ActionSelectionForm,
    ApplyByHandForm,
    ConfirmActionForm,
    EmptyActionForm,
    StartActionForm,
)
from n26.core.action_payments import Balance, Quote, QuotedLine, Resource
from n26.core.action_records import (
    active_action_record,
    preview_changes_review,
    quote_for,
)
from n26.core.counter_tracking import is_active as counter_tracking_is_active
from n26.core.flow import FlowStep
from n26.core.models import ActionAllowance, ActionRecord, LedgerEvent
from n26.core.operations import Refusal
from n26.library.models import (
    Action,
    ApplyChanges,
    AugmentCarriedItem,
    ResolveAdvancement,
)


@dataclass
class StageInput:
    """Exact business fields and actor supplied by either HTTP adapter."""

    data: Mapping[str, str]
    query: Mapping[str, str]
    actor: object
    submitted: bool = False
    op: object = None
    notices: list = field(default_factory=list)

    def notice(self, tone, text):
        self.notices.append({"tone": tone, "text": text})


@dataclass
class StagePage:
    context: dict


@dataclass
class StageNavigation:
    href: str
    notices: list = field(default_factory=list)


def navigate(destination, **kwargs):
    return StageNavigation(
        reverse(destination, kwargs=kwargs) if kwargs else destination
    )


REVIEW_SALT = "n26.fighter-action-review"
UNDO_SALT = "n26.fighter-action-undo"


def flow_url(fighter, record, step):
    return flow_url_for(fighter, record.pk, step)


def flow_url_for(fighter, record_id, step):
    return reverse("n26-action-flow", args=[fighter.pk, record_id, step])


def link_action_panels(fighter, panels):
    """Attach navigation to the read-only values used below the model card."""
    for panel in panels:
        if (
            not panel.problem
            and panel.available_uses != 0
            and not any(not draft.suspended for draft in panel.drafts)
        ):
            panel.start_href = reverse(
                "n26-action-start", args=[fighter.pk, panel.action_id]
            )
            if panel.allowance_id:
                panel.start_href += f"?allowance={panel.allowance_id}"
                panel.menu = [
                    {
                        "label": "Mark as applied",
                        "href": reverse(
                            "n26-action-by-hand", args=[fighter.pk, panel.action_id]
                        )
                        + f"?allowance={panel.allowance_id}",
                    }
                ]
        panel.menu += [
            {
                "label": "Mark as applied"
                if len(panel.drafts) == 1
                else f"Mark flow {number} as applied",
                "href": flow_url_for(fighter, draft.key, "by-hand"),
            }
            for number, draft in enumerate(panel.drafts, start=1)
            if draft.earned and not draft.problem
        ]
        panel.drafts = [
            replace(draft, href=flow_url_for(fighter, draft.key, "resume"))
            for draft in panel.drafts
        ]
        panel.completed = [
            replace(
                completed, reopen_href=flow_url_for(fighter, completed.key, "reopen")
            )
            if completed.applied_by_hand
            else replace(
                completed,
                href=flow_url_for(fighter, completed.key, "done"),
                undo_href=flow_url_for(fighter, completed.key, "undo")
                if completed.undoable
                else "",
            )
            for completed in panel.completed
        ]
    return panels


def split_action_panels(panels):
    """Separate actions the model can use now from completed results."""

    return (
        [
            panel
            for panel in panels
            if panel.start_href or panel.drafts or panel.held_uses
        ],
        [panel for panel in panels if panel.completed],
    )


def _outcomes(action):
    return [
        member.outcome
        for member in action.outcomes.select_related(
            "outcome__augment_carried_item__slot_type",
            "outcome__resolve_advancement__slot",
            "outcome__apply_changes",
        )
    ]


def _description(outcome):
    configured = outcome.operation
    if isinstance(configured, AugmentCarriedItem):
        return "Raise the level of one carried item by one tier."
    if isinstance(configured, ApplyChanges):
        return ""
    return "Gain an advancement."


def _steps(record=None, *, action=None, stage="start", correction=False):
    """Keep step numbering stable by marking unused steps as skipped.

    Cancellation and unavailable pages have no current step.
    """
    if stage in {"undo", "on-hold", "reopen"}:
        return []
    configured = record.outcome.operation if record and record.outcome_id else None
    if record is None and action:
        outcomes = _outcomes(action)
        if len(outcomes) == 1:
            configured = outcomes[0].operation
    skipped = set()
    if isinstance(configured, ResolveAdvancement):
        from n26.core.promotions import replaces_roll

        promotion = record is not None and replaces_roll(record, configured)
        stages = [] if correction else [("start", "Choice"), ("roll", "Roll")]
        stages += [
            ("advancement", "Promotion" if promotion else "Advancement"),
            ("skill", "Skill or power"),
            ("review", "Review"),
            ("done", "Completed"),
        ]
        if promotion:
            skipped.add("roll")
        target = record.review.get("target", {}) if record else {}
        skill = getattr(record, "skill_selection", None)
        takes_a_skill = (
            stage == "skill"
            or (stage == "review" and isinstance(target, dict) and target.get("skill"))
            or (
                stage == "done"
                and skill
                and skill.skill_assignment_id
                and not skill.skill_assignment.archived
            )
        )
        if stage in {"review", "done"} and not takes_a_skill:
            skipped.add("skill")
    else:
        middle = (
            [("choose", "Item and tier")]
            if isinstance(configured, AugmentCarriedItem)
            else ([("choose", "Selection")] if configured is None else [])
        )
        stages = (
            [("correct", "Choose tier")]
            if correction
            else [("start", "Choice"), *middle]
        )
        stages += [("review", "Review"), ("done", "Completed")]
    keys = [key for key, _ in stages]
    current = keys.index(stage) if stage in keys else None
    return [
        FlowStep(
            label,
            current=index == current,
            complete=current is not None and index < current and key not in skipped,
            skipped=key in skipped,
        )
        for index, (key, label) in enumerate(stages)
    ]


def _record_or_404(fighter, key):
    try:
        return get_object_or_404(
            ActionRecord.objects.select_related(
                "action", "outcome", "allowance__rank_table__counter"
            ),
            pk=key,
            fighter=fighter,
            gang=fighter.gang,
        )
    except ValidationError:
        raise Http404("No such action use") from None


def _review_token(record):
    return signing.dumps(
        {
            "record": str(record.pk),
            "revision": record.revision,
            "review": record.review,
        },
        salt=REVIEW_SALT,
        compress=True,
    )


def _submitted_review(record, token):
    try:
        reviewed = signing.loads(token, salt=REVIEW_SALT)
    except signing.BadSignature:
        raise Refusal("Review this action again before confirming it.") from None
    if reviewed.get("record") != str(record.pk):
        raise Refusal("That confirmation belongs to another action use.")
    return reviewed


def _review_payments(record):
    return payment_tallies(
        Quote(
            tuple(
                QuotedLine(
                    Balance(
                        Resource(part["resource"]),
                        part["gang_id"],
                        part["assignment_id"],
                    ),
                    part["amount"],
                    part["available"],
                    part["position"],
                    part["name"],
                )
                for part in record.review.get("price", [])
            )
        )
    )


def _page(
    command,
    fighter,
    action,
    *,
    record=None,
    allowance=None,
    stage="start",
    correction=False,
    **context,
):
    back = reverse("n26-edit-fighter", args=[fighter.pk])
    cancel_href = flow_url(fighter, record, "cancel") if _can_cancel(record) else ""
    outcome_href = (
        flow_url(fighter, record, "outcome")
        if _can_cancel(record)
        and not correction
        and stage not in {"start", "done", "cancel", "by-hand", "on-hold"}
        else ""
    )
    done_href = ""
    if stage == "done":
        done_href = back
        back_href = context.get("correct_href", "")
        back_label = "Change result" if back_href else ""
    elif stage == "cancel":
        back_href = flow_url(fighter, record, "resume")
        back_label = "Save and return later"
    elif stage == "skill":
        back_href = flow_url(fighter, record, "correct" if correction else "choose")
        if correction:
            back_href += "?" + urlencode({"pick": context["selected_pick"]})
        back_label = "← Back"
    elif stage == "review" and context.get("change_href"):
        target = record.review.get("target", {})
        if isinstance(target, dict) and target.get("skill"):
            back_href = flow_url(fighter, record, "skill")
            if correction:
                back_href += "?" + urlencode(
                    {"pick": record.review["terms"]["pickable_id"]}
                )
        else:
            back_href = context["change_href"]
        back_label = "← Back"
    elif (
        stage == "advancement"
        and not correction
        and context.get("roll_value")
        and not record.completed_event_id
    ):
        back_href = flow_url(fighter, record, "roll")
        back_label = "← Back"
    elif outcome_href:
        back_href = outcome_href
        back_label = "← Back"
    else:
        back_href = back
        back_label = "← Back to model"
    return StagePage(
        {
            "miniature": fighter,
            "gang": fighter.gang,
            "action": action,
            "record": record,
            "earned_threshold": earned_threshold(
                record.allowance if record is not None else allowance
            ),
            "stage": stage,
            "correction": correction,
            "steps": _steps(record, action=action, stage=stage, correction=correction),
            "back": back,
            "back_href": back_href,
            "back_label": back_label,
            "done_href": done_href,
            "cancel_href": cancel_href,
            "selection_summary": _selection_summary(record, stage),
            "outcome_href": outcome_href,
            **context,
        },
    )


def _refusal_page(command, fighter, action, refusal, *, record=None, correction=False):
    if command.submitted:
        raise refusal
    form = EmptyActionForm({})
    form.add_error(None, str(refusal))
    return _page(
        command,
        fighter,
        action,
        record=record,
        stage="unavailable",
        correction=correction,
        form=form,
        submit_label="",
    )


def _can_cancel(record):
    if record is None or record.state != ActionRecord.State.STARTED:
        return False
    advancement = getattr(record, "advancement_selection", None)
    skill = getattr(record, "skill_selection", None)
    return not (advancement and advancement.roll_event_id) and not (
        skill and skill.random_attempts
    )


def _selection_summary(record, stage):
    if record is None:
        return ""
    if stage == "review":
        target = record.review.get("target", {})
        selected = target.get("selection") if isinstance(target, dict) else None
        if selected:
            effect = selected["effect"]
            return f"{selected['item_name']}: {selected['candidate_tier']}. {effect[:1].upper()}{effect[1:]}"
        if isinstance(target, dict) and target.get("result"):
            return (
                f"{target['result']}: {target['skill']}"
                if target.get("skill")
                else target["result"]
            )
    if stage in {"done", "undo"}:
        selection = getattr(record, "slot_selection", None)
        if selection and selection.item_assignment and selection.intended_pick:
            return f"{selection.item_assignment.assignable}: {selection.intended_pick}."
        advancement = getattr(record, "advancement_selection", None)
        if advancement and advancement.intended_pick:
            skill = getattr(record, "skill_selection", None)
            return (
                f"{advancement.intended_pick}: {skill.selected}."
                if skill
                and skill.selected
                and skill.skill_assignment_id
                and not skill.skill_assignment.archived
                else str(advancement.intended_pick)
            )
    return ""


def _review_choice(record):
    """Name the result selected inside a reviewed outcome."""

    target = record.review.get("target", {})
    if not isinstance(target, dict):
        return None
    selected = target.get("selection")
    if selected:
        return {
            "label": "Selection",
            "title": f"{selected['item_name']}: {selected['candidate_tier']}",
            "description": selected["effect"],
            "meta": (
                f"Model rating {selected['rating_before']}¢ → "
                f"{selected['rating_after']}¢"
            ),
        }
    if target.get("result"):
        stashed = target.get("promotion", {}) or {}
        equipment = stashed.get("stash", [])
        equipment_note = (
            "Move to stash: " + ", ".join(item["name"] for item in equipment)
            if equipment
            else ""
        )
        return {
            "label": "Advancement",
            "title": target["result"],
            "description": ". ".join(
                text.rstrip(". ")
                for text in [
                    target.get("skill"),
                    target.get("promotion_result"),
                    equipment_note,
                ]
                if text
            ),
            "meta": f"Rating +{target['rating']}¢" if target.get("rating") else "",
        }
    return None


def action_start(command, fighter, action_id):
    gang = fighter.gang
    try:
        action = get_object_or_404(Action, pk=action_id)
    except ValidationError:
        raise Http404("No such action") from None
    if command.submitted:
        try:
            request_key = StartActionForm.base_fields["request_key"].clean(
                command.data.get("request_key")
            )
        except ValidationError:
            request_key = None
        existing = (
            ActionRecord.objects.filter(
                gang=gang, fighter=fighter, action=action, request_key=request_key
            ).first()
            if request_key
            else None
        )
        if existing:
            return navigate(flow_url(fighter, existing, "resume"))
    existing = active_action_record(fighter, action)
    if existing:
        return navigate(flow_url(fighter, existing, "resume"))
    allowances = list(
        ActionAllowance.objects.filter(fighter=fighter, action=action)
        .unused()
        .with_progression_value()
        .select_related("rank_table__counter")
        .order_by("threshold", "created", "pk")
    )
    if not allowances and action.pk not in {
        access.action.pk for access in actions_for(fighter)
    }:
        raise Http404("No such action")
    if not counter_tracking_is_active():
        form = EmptyActionForm({})
        form.add_error(
            None,
            "This flow is temporarily unavailable.",
        )
        try:
            prices = payment_figures(quote_for(fighter, action))
        except Refusal as refusal:
            if command.submitted:
                raise
            form.add_error(None, str(refusal))
            prices = ()
        return _page(
            command,
            fighter,
            action,
            form=form,
            prices=prices,
            tracking_unavailable=True,
            submit_label="",
            submit_variant="primary",
        )
    from n26.core.allowances import allowance_hold_reason

    held = [row for row in allowances if allowance_hold_reason(row)]
    allowances = [row for row in allowances if not allowance_hold_reason(row)]
    if not allowances and held:
        return _held_page(command, fighter, action, allowance_hold_reason(held[0]))
    outcomes = _outcomes(action)
    initial = {
        "request_key": uuid4(),
        "outcome": str(outcomes[0].pk) if len(outcomes) == 1 else "",
        "allowance": command.query.get("allowance")
        or (str(allowances[0].pk) if allowances else ""),
    }
    form = StartActionForm(
        command.data or None, initial=initial, outcomes=outcomes, allowances=allowances
    )
    if command.submitted and form.is_valid():
        outcome = next(
            item for item in outcomes if str(item.pk) == form.cleaned_data["outcome"]
        )
        allowance = next(
            (
                item
                for item in allowances
                if str(item.pk) == form.cleaned_data["allowance"]
            ),
            None,
        )
        try:
            with nullcontext(command.op) as op:
                record = op.start_action(
                    fighter,
                    action,
                    form.cleaned_data["request_key"],
                    allowance=allowance,
                )
                if record.state != ActionRecord.State.STARTED:
                    return navigate(flow_url(fighter, record, "done"))
                if (
                    record.outcome_id is not None
                    or record.request_key != form.cleaned_data["request_key"]
                ):
                    return navigate(flow_url(fighter, record, "resume"))
                record = op.save_action_choices(record, outcome=outcome, terms={})
                if isinstance(outcome.operation, ApplyChanges):
                    record = op.review_action(
                        record, outcome=outcome, terms=record.terms
                    )
            return navigate(flow_url(fighter, record, "resume"))
        except Refusal as refusal:
            if command.submitted:
                raise
            form.add_error(None, str(refusal))
    try:
        quote = quote_for(fighter, action)
    except Refusal as refusal:
        return _refusal_page(command, fighter, action, refusal)
    return _page(
        command,
        fighter,
        action,
        form=form,
        allowance=next(
            (
                row
                for row in allowances
                if str(row.pk) == str(form["allowance"].value())
            ),
            None,
        ),
        prices=payment_figures(quote),
        outcomes=[
            {
                "key": str(item.pk),
                "name": str(item),
                "description": _description(item),
                "checked": str(form["outcome"].value()) == str(item.pk),
            }
            for item in outcomes
        ],
        submit_label="Continue",
        submit_variant="primary",
    )


def action_by_hand(command, fighter, action_id):
    """Confirm, then mark an unused earned use as applied by hand."""
    try:
        action = get_object_or_404(Action, pk=action_id)
    except ValidationError:
        raise Http404("No such action") from None
    try:
        allowance = (
            ActionAllowance.objects.filter(
                pk=command.query.get("allowance"), fighter=fighter, action=action
            )
            .select_related("rank_table__counter")
            .first()
            if command.query.get("allowance")
            else None
        )
    except ValidationError:
        allowance = None
    form = ApplyByHandForm(command.data or None, initial={"request_key": uuid4()})
    if command.submitted and form.is_valid():
        try:
            with nullcontext(command.op) as op:
                record = op.apply_allowance_by_hand(
                    fighter, action, form.cleaned_data["request_key"], allowance
                )
            if record.state == ActionRecord.State.APPLIED_BY_HAND:
                command.notice("success", f"{action} marked as applied by hand.")
            else:
                command.notice("info", "This form is out of date. Nothing changed.")
            return navigate("n26-edit-fighter", pk=fighter.pk)
        except Refusal as refusal:
            if command.submitted:
                raise
            form.add_error(None, str(refusal))
    if allowance is None:
        allowance = (
            ActionAllowance.objects.filter(fighter=fighter, action=action)
            .unused()
            .eligible()
            .select_related("rank_table__counter")
            .order_by("threshold", "created", "pk")
            .first()
        )
    return _by_hand_page(command, fighter, action, form, allowance=allowance)


def _by_hand_page(command, fighter, action, form, *, record=None, allowance=None):
    return _page(
        command,
        fighter,
        action,
        record=record,
        allowance=allowance,
        stage="by-hand",
        form=form,
        submit_label="Mark as applied",
        submit_variant="success",
    )


def action_flow(command, fighter, record_id, step):
    record = _record_or_404(fighter, record_id)
    if record.state == ActionRecord.State.CANCELLED:
        command.notice("info", "This flow was cancelled.")
        return navigate("n26-edit-fighter", pk=fighter.pk)
    if step == "undo":
        return _undo(command, fighter, record)
    if (
        record.state == ActionRecord.State.STARTED
        and record.allowance_id
        and step not in {"cancel", "reopen"}
    ):
        from n26.core.allowances import require_allowance_available

        try:
            require_allowance_available(record.allowance)
        except Refusal as refusal:
            return _held_page(
                command, fighter, record.action, str(refusal), record=record
            )
    if step == "by-hand" and record.state == ActionRecord.State.STARTED:
        form = EmptyActionForm(command.data or None)
        if command.submitted:
            try:
                with nullcontext(command.op) as op:
                    op.apply_action_by_hand(record)
                command.notice("success", f"{record.action} marked as applied by hand.")
                return navigate("n26-edit-fighter", pk=fighter.pk)
            except Refusal as refusal:
                if command.submitted:
                    raise
                form.add_error(None, str(refusal))
        return _by_hand_page(command, fighter, record.action, form, record=record)
    if step == "reopen":
        if command.submitted:
            try:
                with nullcontext(command.op) as op:
                    op.reopen_action(record)
                command.notice("success", f"{record.action} is waiting again.")
            except Refusal:
                raise
        if command.submitted:
            return navigate("n26-edit-fighter", pk=fighter.pk)
        return _page(
            command,
            fighter,
            record.action,
            record=record,
            stage="reopen",
            form=EmptyActionForm(),
            submit_label="Undo marking as applied",
            submit_variant="primary",
        )
    if record.state == ActionRecord.State.APPLIED_BY_HAND:
        command.notice("info", "This earned use was applied by hand.")
        return navigate("n26-edit-fighter", pk=fighter.pk)
    if not record.outcome_id and step in {
        "resume",
        "choose",
        "correct",
        "skill",
        "roll",
    }:
        return navigate(flow_url(fighter, record, "outcome"))
    if step == "resume":
        next_step = (
            "done"
            if record.state == ActionRecord.State.COMPLETED
            else (
                "review"
                if record.review
                else (
                    "skill"
                    if isinstance(record.outcome.operation, ResolveAdvancement)
                    and record.terms.get("pickable_id")
                    else "choose"
                )
            )
        )
        return navigate(flow_url(fighter, record, next_step))
    if step == "cancel":
        if command.submitted:
            try:
                with nullcontext(command.op) as op:
                    op.cancel_action(record)
                command.notice("success", "Flow cancelled.")
            except Refusal:
                raise
            return navigate("n26-edit-fighter", pk=fighter.pk)
        return _page(
            command,
            fighter,
            record.action,
            record=record,
            stage="cancel",
            form=EmptyActionForm(),
            submit_label="Cancel flow",
            submit_variant="danger",
        )
    if step == "done":
        if record.state != ActionRecord.State.COMPLETED:
            return navigate(flow_url(fighter, record, "resume"))
        can_correct = not isinstance(record.outcome.operation, ApplyChanges)
        return _page(
            command,
            fighter,
            record.action,
            record=record,
            stage="done",
            receipt=receipt_lines(record),
            correct_href=flow_url(fighter, record, "correct") if can_correct else "",
            undo_href=flow_url(fighter, record, "undo")
            if record.allowance_id
            and isinstance(record.outcome.operation, ResolveAdvancement)
            else "",
        )
    correction = record.state == ActionRecord.State.COMPLETED
    if step == "outcome" and not correction:
        return _choose_outcome(command, fighter, record)
    if step == "review":
        return _review(command, fighter, record, correction=correction)
    if step not in {"choose", "correct", "skill", "roll"}:
        raise Http404("No such flow step")
    if correction and step not in {"correct", "skill"}:
        return navigate(flow_url(fighter, record, "done"))
    configured = record.outcome.operation if record.outcome_id else None
    if step == "roll" and not isinstance(configured, ResolveAdvancement):
        return navigate(flow_url(fighter, record, "choose"))
    if isinstance(configured, AugmentCarriedItem):
        try:
            return _choose_augmentation(
                command, fighter, record, configured, correction=correction
            )
        except Refusal as refusal:
            return _refusal_page(
                command,
                fighter,
                record.action,
                refusal,
                record=record,
                correction=correction,
            )
    if isinstance(configured, ApplyChanges):
        return navigate(flow_url(fighter, record, "review"))
    from n26.core.advancement_stages import advancement_step

    try:
        return advancement_step(
            command, fighter, record, step=step, correction=correction
        )
    except Refusal as refusal:
        if command.submitted:
            raise
        form = EmptyActionForm({})
        form.add_error(None, str(refusal))
        return _page(
            command,
            fighter,
            record.action,
            record=record,
            form=form,
            stage="advancement",
            correction=correction,
        )


def _choose_outcome(command, fighter, record):
    outcomes = _outcomes(record.action)
    form = ActionOutcomeForm(
        command.data or None,
        outcomes=outcomes,
        initial={"outcome": str(record.outcome_id)},
    )
    if command.submitted and form.is_valid():
        outcome = next(
            item for item in outcomes if str(item.pk) == form.cleaned_data["outcome"]
        )
        try:
            with nullcontext(command.op) as op:
                record = op.save_action_choices(record, outcome=outcome, terms={})
                if isinstance(outcome.operation, ApplyChanges):
                    record = op.review_action(
                        record, outcome=outcome, terms=record.terms
                    )
            return navigate(flow_url(fighter, record, "resume"))
        except Refusal as refusal:
            if command.submitted:
                raise
            form.add_error(None, str(refusal))
    try:
        prices = payment_figures(quote_for(fighter, record.action))
    except Refusal as refusal:
        return _refusal_page(command, fighter, record.action, refusal, record=record)
    return _page(
        command,
        fighter,
        record.action,
        record=record,
        form=form,
        prices=prices,
        outcomes=[
            {
                "key": str(item.pk),
                "name": str(item),
                "description": _description(item),
                "checked": str(form["outcome"].value()) == str(item.pk),
            }
            for item in outcomes
        ],
        submit_label="Continue",
        submit_variant="primary",
    )


def _choose_augmentation(command, fighter, record, configured, *, correction):
    from n26.core.augmentations import augmentation_options

    options = augmentation_options(record, configured)
    choices = [
        (
            f"{item.item_assignment_id}|{item.candidate_pick_id}",
            f"{item.item_name}: {item.candidate_tier}",
        )
        for item in options.candidates
    ]
    previous = record.terms
    initial = {
        "selection": f"{previous.get('item_assignment', '')}|{previous.get('intended_pick', '')}"
    }
    form = ActionSelectionForm(command.data or None, choices=choices, initial=initial)
    if command.submitted and form.is_valid():
        item, tier = form.cleaned_data["selection"].split("|")
        terms = {"item_assignment": item, "intended_pick": tier}
        try:
            with nullcontext(command.op) as op:
                if correction:
                    record = op.review_action_correction(record, terms=terms)
                else:
                    record = op.save_action_choices(
                        record, outcome=record.outcome, terms=terms
                    )
                    record = op.review_action(
                        record, outcome=record.outcome, terms=record.terms
                    )
            return navigate(flow_url(fighter, record, "review"))
        except Refusal as refusal:
            if command.submitted:
                raise
            form.add_error(None, str(refusal))
    return _page(
        command,
        fighter,
        record.action,
        record=record,
        stage="correct" if correction else "choose",
        correction=correction,
        form=form,
        item_options=[
            {"item": item, "key": key, "checked": str(form["selection"].value()) == key}
            for item, (key, _) in zip(options.candidates, choices, strict=True)
        ],
        submit_label="Review" if choices else "",
        submit_variant="primary",
    )


def _review(command, fighter, record, *, correction):
    if not command.submitted and not record.review:
        return navigate(
            flow_url(fighter, record, "correct" if correction else "outcome")
        )
    if (
        not command.submitted
        and not correction
        and isinstance(record.outcome.operation, ApplyChanges)
    ):
        try:
            # The signed form carries this preview into confirmation. Reading
            # a draft must not rewrite it or invalidate another open tab.
            record = copy(record)
            record.review = preview_changes_review(record)
        except Refusal as refusal:
            return _refusal_page(
                command, fighter, record.action, refusal, record=record
            )
    form = ConfirmActionForm(
        command.data or None, initial={"review": _review_token(record)}
    )
    if command.submitted and form.is_valid():
        try:
            reviewed = _submitted_review(record, form.cleaned_data["review"])
            correction = reviewed["review"].get("correction") is True
            with nullcontext(command.op) as op:
                if correction:
                    op.correct_action(
                        record,
                        revision=reviewed["revision"],
                        review=reviewed["review"],
                        terms=reviewed["review"]["terms"],
                    )
                else:
                    op.complete_action(
                        record,
                        revision=reviewed["revision"],
                        review=reviewed["review"],
                        outcome=record.outcome,
                    )
            return navigate(flow_url(fighter, record, "done"))
        except Refusal as refusal:
            if command.submitted:
                raise
            form.add_error(None, str(refusal))
    return _page(
        command,
        fighter,
        record.action,
        record=record,
        stage="review",
        correction=correction,
        form=form,
        prices=(),
        payment_tallies=() if correction else _review_payments(record),
        outcome_description=_description(record.outcome),
        review_choice=_review_choice(record),
        show_outcome=not isinstance(record.outcome.operation, ResolveAdvancement),
        change_preview=record.review.get("target", [])
        if isinstance(record.outcome.operation, ApplyChanges)
        else [],
        retained_payment=bool(record.payment_id),
        retained_roll=bool(
            getattr(
                getattr(record, "advancement_selection", None), "roll_event_id", None
            )
        ),
        change_href=flow_url(fighter, record, "correct" if correction else "choose")
        if not isinstance(record.outcome.operation, ApplyChanges)
        else flow_url(fighter, record, "outcome"),
        submit_label="Save correction" if correction else "Confirm",
        submit_variant="success",
    )


def _undo(command, fighter, record):
    from n26.core.advancements import advancement_undo_snapshot

    if command.submitted:
        form = ConfirmActionForm(command.data)
        if form.is_valid():
            try:
                try:
                    expected = signing.loads(
                        form.cleaned_data["review"], salt=UNDO_SALT
                    )
                except signing.BadSignature:
                    raise Refusal(
                        "Review this advancement again before undoing it."
                    ) from None
                if expected.get("record") != str(record.pk):
                    raise Refusal("That confirmation belongs to another advancement.")
                with nullcontext(command.op) as op:
                    op.undo_action(record, expected=expected)
                command.notice(
                    "success", "Advancement undone. Its earned use is waiting again."
                )
                return navigate("n26-edit-fighter", pk=fighter.pk)
            except Refusal as refusal:
                if command.submitted:
                    raise
                form.add_error(None, str(refusal))
    else:
        try:
            expected = advancement_undo_snapshot(record)
        except Refusal as refusal:
            return _refusal_page(
                command, fighter, record.action, refusal, record=record
            )
        form = ConfirmActionForm(
            initial={"review": signing.dumps(expected, salt=UNDO_SALT, compress=True)}
        )
    return _page(
        command,
        fighter,
        record.action,
        record=record,
        stage="undo",
        form=form,
        submit_label="Undo advancement",
        submit_variant="danger",
        keeps_stashed_weapons=record.ledger_events.filter(
            kind=LedgerEvent.Kind.MOVED, note="Promotion"
        ).exists(),
    )


def _held_page(command, fighter, action, reason, *, record=None):
    return _page(
        command,
        fighter,
        action,
        record=record,
        stage="on-hold",
        form=EmptyActionForm(),
        hold_reason=reason,
        submit_label="",
    )
