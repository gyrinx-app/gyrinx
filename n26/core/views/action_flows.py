"""Owner-scoped forms for starting and completing fighter actions."""

from dataclasses import replace
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core import signing
from django.core.exceptions import ValidationError
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from n26.core.access import actions_for
from n26.core.action_flow import payment_figures, receipt_lines
from n26.core.action_forms import (
    ActionOutcomeForm,
    ActionSelectionForm,
    ConfirmActionForm,
    EmptyActionForm,
    StartActionForm,
)
from n26.core.action_payments import Balance, Quote, QuotedLine, Resource
from n26.core.action_records import quote_for
from n26.core.flow import FlowStep
from n26.core.models import ActionAllowance, ActionRecord
from n26.core.operations import Refusal, operation
from n26.core.views.permissions import _own_miniature_or_404
from n26.library.models import (
    Action,
    ApplyChanges,
    AugmentCarriedItem,
    ResolveAdvancement,
)

REVIEW_SALT = "n26.fighter-action-review"


def flow_url(fighter, record, step):
    return reverse("n26-action-flow", args=[fighter.pk, record.pk, step])


def link_action_panels(fighter, panels):
    """Attach navigation to the read-only values used below the model card."""
    for panel in panels:
        if not panel.problem and panel.available_uses != 0:
            panel.start_href = reverse(
                "n26-action-start", args=[fighter.pk, panel.action_id]
            )
            if panel.allowance_id:
                panel.start_href += f"?allowance={panel.allowance_id}"
        panel.drafts = [
            replace(
                draft,
                href=reverse("n26-action-flow", args=[fighter.pk, draft.key, "resume"]),
            )
            for draft in panel.drafts
        ]
        panel.completed = [
            replace(
                completed,
                href=reverse(
                    "n26-action-flow", args=[fighter.pk, completed.key, "done"]
                ),
            )
            for completed in panel.completed
        ]
    return panels


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
    return "Roll and choose an advancement result."


def _steps(record=None, *, action=None, stage="start", correction=False):
    configured = record.outcome.operation if record and record.outcome_id else None
    if record is None and action:
        outcomes = _outcomes(action)
        if len(outcomes) == 1:
            configured = outcomes[0].operation
    if isinstance(configured, ResolveAdvancement):
        stages = [] if correction else [("start", "Outcome"), ("roll", "Roll")]
        stages += [("advancement", "Advancement")]
        target = record.review.get("target", {}) if record else {}
        skill = getattr(record, "skill_selection", None)
        if stage in {"start", "roll", "advancement"}:
            stages.append(("skill", "Skill (if needed)"))
        elif (
            stage == "skill"
            or (stage == "review" and isinstance(target, dict) and target.get("skill"))
            or (
                stage == "done"
                and skill
                and skill.skill_assignment_id
                and not skill.skill_assignment.archived
            )
        ):
            stages.append(("skill", "Skill"))
        stages += [("review", "Review"), ("done", "Completed")]
        current = next(
            (index for index, (key, _) in enumerate(stages) if key == stage), 0
        )
        return [
            FlowStep(label, current=index == current, complete=index < current)
            for index, (_, label) in enumerate(stages)
        ]
    middle = (
        [("choose", "Item and tier")]
        if isinstance(configured, AugmentCarriedItem)
        else ([("choose", "Selection (if needed)")] if configured is None else [])
    )
    stages = (
        [("correct", "Choose tier")] if correction else [("start", "Outcome"), *middle]
    )
    stages += [("review", "Review"), ("done", "Completed")]
    current = next((index for index, (key, _) in enumerate(stages) if key == stage), 0)
    return [
        FlowStep(label, current=index == current, complete=index < current)
        for index, (_, label) in enumerate(stages)
    ]


def _record_or_404(fighter, key):
    try:
        return get_object_or_404(
            ActionRecord.objects.select_related("action", "outcome", "allowance"),
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


def _review_prices(record):
    return payment_figures(
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
    request, fighter, action, *, record=None, stage="start", correction=False, **context
):
    return render(
        request,
        "n26/action_flow.html",
        {
            "miniature": fighter,
            "gang": fighter.gang,
            "action": action,
            "record": record,
            "stage": stage,
            "correction": correction,
            "steps": _steps(record, action=action, stage=stage, correction=correction),
            "back": reverse("n26-edit-fighter", args=[fighter.pk]),
            "cancel_href": flow_url(fighter, record, "cancel")
            if _can_cancel(record)
            else "",
            "selection_summary": _selection_summary(record, stage),
            "outcome_href": flow_url(fighter, record, "outcome")
            if _can_cancel(record)
            and not correction
            and stage not in {"start", "done", "cancel"}
            else "",
            **context,
        },
    )


def _can_cancel(record):
    if record is None or record.state != ActionRecord.State.STARTED:
        return False
    advancement = getattr(record, "advancement_selection", None)
    return not advancement or not advancement.roll_event_id


def _selection_summary(record, stage):
    if record is None:
        return ""
    if stage == "review":
        target = record.review.get("target", {})
        selected = target.get("selection") if isinstance(target, dict) else None
        if selected:
            return f"{selected['item_name']}: {selected['candidate_tier']}. {selected['effect']}"
        if isinstance(target, dict) and target.get("result"):
            return (
                f"{target['result']}: {target['skill']}"
                if target.get("skill")
                else target["result"]
            )
    if stage == "done":
        selection = getattr(record, "augmentation_selection", None)
        if selection and selection.item_assignment and selection.intended_pick:
            return f"{selection.item_assignment.assignable}: {selection.intended_pick}."
        advancement = getattr(record, "advancement_selection", None)
        if advancement and advancement.intended_pick:
            skill = getattr(record, "skill_selection", None)
            return (
                f"{advancement.intended_pick}: {skill.selected_skill}."
                if skill
                and skill.selected_skill
                and skill.skill_assignment_id
                and not skill.skill_assignment.archived
                else str(advancement.intended_pick)
            )
    return ""


@login_required
def action_start(request, pk, action_id):
    fighter = _own_miniature_or_404(request, pk)
    gang = fighter.gang
    try:
        action = get_object_or_404(Action, pk=action_id)
    except ValidationError:
        raise Http404("No such action") from None
    if request.method == "POST":
        try:
            request_key = StartActionForm.base_fields["request_key"].clean(
                request.POST.get("request_key")
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
            return redirect(flow_url(fighter, existing, "resume"))
    allowances = list(
        ActionAllowance.objects.filter(fighter=fighter, action=action)
        .exclude(
            records__state__in=[
                ActionRecord.State.STARTED,
                ActionRecord.State.COMPLETED,
            ]
        )
        .order_by("created", "pk")
    )
    if not allowances and action.pk not in {
        access.action.pk for access in actions_for(fighter)
    }:
        raise Http404("No such action")
    outcomes = _outcomes(action)
    initial = {
        "request_key": uuid4(),
        "outcome": str(outcomes[0].pk) if len(outcomes) == 1 else "",
        "allowance": request.GET.get("allowance")
        or (str(allowances[0].pk) if allowances else ""),
    }
    form = StartActionForm(
        request.POST or None, initial=initial, outcomes=outcomes, allowances=allowances
    )
    if request.method == "POST" and form.is_valid():
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
            with operation(gang, actor=request.user) as op:
                record = op.start_action(
                    fighter,
                    action,
                    form.cleaned_data["request_key"],
                    allowance=allowance,
                )
                if record.state != ActionRecord.State.STARTED:
                    return redirect(flow_url(fighter, record, "done"))
                record = op.save_action_choices(record, outcome=outcome, terms={})
                if isinstance(outcome.operation, ApplyChanges):
                    record = op.review_action(
                        record, outcome=outcome, terms=record.terms
                    )
            return redirect(flow_url(fighter, record, "resume"))
        except Refusal as refusal:
            form.add_error(None, str(refusal))
    quote = quote_for(fighter, action)
    return _page(
        request,
        fighter,
        action,
        form=form,
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


@login_required
def action_flow(request, pk, record_id, step):
    fighter = _own_miniature_or_404(request, pk)
    record = _record_or_404(fighter, record_id)
    if record.state == ActionRecord.State.CANCELLED:
        messages.info(request, "This flow was cancelled.")
        return redirect("n26-edit-fighter", pk=fighter.pk)
    if step == "resume":
        next_step = (
            "done"
            if record.state == ActionRecord.State.COMPLETED
            else ("review" if record.review else "choose")
        )
        return redirect(flow_url(fighter, record, next_step))
    if step == "cancel":
        if request.method == "POST":
            try:
                with operation(fighter.gang, actor=request.user) as op:
                    op.cancel_action(record)
                messages.success(request, "Flow cancelled.")
            except Refusal as refusal:
                messages.error(request, str(refusal))
            return redirect("n26-edit-fighter", pk=fighter.pk)
        return _page(
            request,
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
            return redirect(flow_url(fighter, record, "resume"))
        can_correct = not isinstance(record.outcome.operation, ApplyChanges)
        return _page(
            request,
            fighter,
            record.action,
            record=record,
            stage="done",
            receipt=receipt_lines(record),
            correct_href=flow_url(fighter, record, "correct") if can_correct else "",
            correct_label="Choose tier"
            if isinstance(record.outcome.operation, AugmentCarriedItem)
            else "Correct result",
        )
    correction = record.state == ActionRecord.State.COMPLETED
    if step == "outcome" and not correction:
        return _choose_outcome(request, fighter, record)
    if step == "review":
        return _review(request, fighter, record, correction=correction)
    if step not in {"choose", "correct", "skill"}:
        raise Http404("No such flow step")
    if correction and step not in {"correct", "skill"}:
        return redirect(flow_url(fighter, record, "done"))
    configured = record.outcome.operation if record.outcome_id else None
    if isinstance(configured, AugmentCarriedItem):
        return _choose_augmentation(
            request, fighter, record, configured, correction=correction
        )
    if isinstance(configured, ApplyChanges):
        return redirect(flow_url(fighter, record, "review"))
    from n26.core.views.advancement_flows import advancement_step

    try:
        return advancement_step(
            request, fighter, record, step=step, correction=correction
        )
    except Refusal as refusal:
        form = EmptyActionForm({})
        form.add_error(None, str(refusal))
        return _page(
            request,
            fighter,
            record.action,
            record=record,
            form=form,
            stage="advancement",
            correction=correction,
        )


def _choose_outcome(request, fighter, record):
    outcomes = _outcomes(record.action)
    form = ActionOutcomeForm(
        request.POST or None,
        outcomes=outcomes,
        initial={"outcome": str(record.outcome_id)},
    )
    if request.method == "POST" and form.is_valid():
        outcome = next(
            item for item in outcomes if str(item.pk) == form.cleaned_data["outcome"]
        )
        try:
            with operation(fighter.gang, actor=request.user) as op:
                record = op.save_action_choices(record, outcome=outcome, terms={})
                if isinstance(outcome.operation, ApplyChanges):
                    record = op.review_action(
                        record, outcome=outcome, terms=record.terms
                    )
            return redirect(flow_url(fighter, record, "resume"))
        except Refusal as refusal:
            form.add_error(None, str(refusal))
    return _page(
        request,
        fighter,
        record.action,
        record=record,
        form=form,
        prices=payment_figures(quote_for(fighter, record.action)),
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


def _choose_augmentation(request, fighter, record, configured, *, correction):
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
    form = ActionSelectionForm(request.POST or None, choices=choices, initial=initial)
    if request.method == "POST" and form.is_valid():
        item, tier = form.cleaned_data["selection"].split("|")
        terms = {"item_assignment": item, "intended_pick": tier}
        try:
            with operation(fighter.gang, actor=request.user) as op:
                if correction:
                    record = op.review_action_correction(record, terms=terms)
                else:
                    record = op.save_action_choices(
                        record, outcome=record.outcome, terms=terms
                    )
                    record = op.review_action(
                        record, outcome=record.outcome, terms=record.terms
                    )
            return redirect(flow_url(fighter, record, "review"))
        except Refusal as refusal:
            form.add_error(None, str(refusal))
    return _page(
        request,
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


def _review(request, fighter, record, *, correction):
    if request.method != "POST" and not record.review:
        return redirect(
            flow_url(fighter, record, "correct" if correction else "outcome")
        )
    form = ConfirmActionForm(
        request.POST or None, initial={"review": _review_token(record)}
    )
    if request.method == "POST" and form.is_valid():
        try:
            reviewed = _submitted_review(record, form.cleaned_data["review"])
            correction = reviewed["review"].get("correction") is True
            with operation(fighter.gang, actor=request.user) as op:
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
            return redirect(flow_url(fighter, record, "done"))
        except Refusal as refusal:
            form.add_error(None, str(refusal))
    return _page(
        request,
        fighter,
        record.action,
        record=record,
        stage="review",
        correction=correction,
        form=form,
        prices=() if correction else _review_prices(record),
        outcome_description=_description(record.outcome),
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
