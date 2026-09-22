"""The roll and skill forms within a generic fighter action flow."""

from urllib.parse import urlencode
from uuid import uuid4

from django.shortcuts import redirect

from n26.core.action_forms import (
    ActionRollForm,
    AdvancementForm,
    EmptyActionForm,
    SkillRollForm,
    SkillSelectionForm,
)
from n26.core.operations import Refusal, operation


def advancement_step(request, fighter, record, *, step="choose", correction=False):
    from n26.core.advancements import advancement_options, skill_options
    from n26.core.promotions import (
        may_decline,
        prepare_promotion,
        promotion_for,
        replaces_roll,
    )
    from n26.core.views.action_flows import _page, flow_url

    configured = record.outcome.operation
    selection = getattr(record, "advancement_selection", None)
    promotion = promotion_for(record, configured)
    replacement = replaces_roll(record, configured)
    if (
        replacement
        and request.method == "POST"
        and request.POST.get("decline_promotion")
    ):
        form = ActionRollForm(request.POST)
        if form.is_valid():
            try:
                with operation(fighter.gang, actor=request.user) as op:
                    op.record_action_roll(
                        record,
                        configured,
                        form.cleaned_data["request_key"],
                        decline_promotion=True,
                    )
            except Refusal as refusal:
                from n26.core.views.action_flows import _refusal_page

                return _refusal_page(
                    request, fighter, record.action, refusal, record=record
                )
            return redirect(flow_url(fighter, record, "choose"))
    if not replacement and (selection is None or selection.roll_event_id is None):
        if correction:
            raise Refusal("This advancement has no recorded roll to correct.")
        form = ActionRollForm(request.POST or None, initial={"request_key": uuid4()})
        if request.method == "POST" and form.is_valid():
            try:
                with operation(fighter.gang, actor=request.user) as op:
                    op.record_action_roll(
                        record, configured, form.cleaned_data["request_key"]
                    )
                return redirect(flow_url(fighter, record, "choose"))
            except Refusal as refusal:
                form.add_error(None, str(refusal))
        return _page(
            request,
            fighter,
            record.action,
            record=record,
            stage="roll",
            form=form,
            submit_label="Roll 2D6",
            submit_variant="primary",
        )

    options = tuple(
        option for option in advancement_options(record, configured) if option.gainable
    )
    if step == "skill":
        pick_id = (
            request.GET.get("pick") if correction else record.terms.get("pickable_id")
        )
        chosen = next((option for option in options if option.id == str(pick_id)), None)
        if chosen is None:
            return redirect(
                flow_url(fighter, record, "correct" if correction else "choose")
            )
        groups = skill_options(record, configured, chosen.id)
        return _skill_step(
            request, fighter, record, configured, chosen, groups, correction=correction
        )

    form = AdvancementForm(
        request.POST or None,
        options=options,
        initial={"pickable_id": record.terms.get("pickable_id")},
    )
    if request.method == "POST" and form.is_valid():
        chosen = next(
            option
            for option in options
            if option.id == form.cleaned_data["pickable_id"]
        )
        terms = {"pickable_id": chosen.id}
        try:
            if chosen.needs_skill:
                if not correction:
                    with operation(fighter.gang, actor=request.user) as op:
                        if replacement:
                            record = prepare_promotion(op, record, configured)
                        op.save_action_choices(
                            record, outcome=record.outcome, terms=terms
                        )
                tail = "?" + urlencode({"pick": chosen.id}) if correction else ""
                return redirect(flow_url(fighter, record, "skill") + tail)
            with operation(fighter.gang, actor=request.user) as op:
                if replacement and not correction:
                    record = prepare_promotion(op, record, configured)
                if correction:
                    op.review_action_correction(record, terms=terms)
                else:
                    record = op.save_action_choices(
                        record, outcome=record.outcome, terms=terms
                    )
                    op.review_action(record, outcome=record.outcome, terms=record.terms)
            return redirect(flow_url(fighter, record, "review"))
        except Refusal as refusal:
            form.add_error(None, str(refusal))
    return _page(
        request,
        fighter,
        record.action,
        record=record,
        stage="advancement",
        correction=correction,
        form=form,
        roll_value=selection.roll_event.roll
        if selection and selection.roll_event_id
        else None,
        advancement_title="Choose a promotion"
        if replacement
        else "Choose an advancement",
        promotion_description=(
            "Choose one result instead of rolling this advancement."
            if replacement
            else ""
        ),
        decline_promotion=not correction
        and replacement
        and may_decline(record, promotion),
        promotion_request_key=uuid4(),
        advancement_options=[
            {"option": option, "checked": str(form["pickable_id"].value()) == option.id}
            for option in options
        ],
        submit_label="Continue" if options else "",
        submit_variant="primary",
    )


def _skill_step(request, fighter, record, configured, chosen, groups, *, correction):
    from n26.core.advancements import recorded_skill
    from n26.core.views.action_flows import _page, flow_url

    selection = getattr(record, "skill_selection", None)
    attempts = selection.random_attempts if selection else []
    random = chosen.skill_mode == "random"
    selected = recorded_skill(record, configured, chosen.id) if random else None
    resolved = selected is not None
    if (
        random
        and resolved
        and request.method == "POST"
        and "request_key" in request.POST
    ):
        return redirect(flow_url(fighter, record, "skill"))
    if random and not resolved and not correction:
        form = SkillRollForm(
            request.POST or None,
            groups=groups,
            initial={
                "request_key": uuid4(),
                "skill_set_id": str(selection.skill_set_id)
                if selection and selection.skill_set_id
                else "",
            },
        )
        submit_label = "Roll D6 again" if attempts else "Roll D6"
    elif random:
        form = EmptyActionForm(request.POST or None)
        submit_label = "Review" if resolved else ""
    else:
        form = SkillSelectionForm(
            request.POST or None,
            groups=groups,
            initial={"skill_id": record.terms.get("skill_id")},
        )
        submit_label = "Review"
    if request.method == "POST" and form.is_valid():
        terms = {"pickable_id": chosen.id}
        try:
            with operation(fighter.gang, actor=request.user) as op:
                if random and not resolved and not correction:
                    op.record_skill_roll(
                        record,
                        configured,
                        form.cleaned_data["request_key"],
                        pickable_id=chosen.id,
                        skill_set_id=form.cleaned_data["skill_set_id"],
                    )
                    return redirect(flow_url(fighter, record, "skill"))
                if not random:
                    terms["skill_id"] = form.cleaned_data["skill_id"]
                if correction:
                    op.review_action_correction(record, terms=terms)
                else:
                    record = op.save_action_choices(
                        record, outcome=record.outcome, terms=terms
                    )
                    op.review_action(record, outcome=record.outcome, terms=record.terms)
            return redirect(flow_url(fighter, record, "review"))
        except Refusal as refusal:
            form.add_error(None, str(refusal))
    return _page(
        request,
        fighter,
        record.action,
        record=record,
        stage="skill",
        correction=correction,
        form=form,
        skill_random=random,
        skill_resolved=resolved,
        skill_selected=str(selected) if resolved else "",
        skill_attempts=attempts,
        skill_groups=[
            {
                "key": str(group.pk),
                "name": str(group),
                "checked": "skill_set_id" in form.fields
                and str(form["skill_set_id"].value()) == str(group.pk),
                "skills": [
                    {
                        "key": str(skill.pk),
                        "name": str(skill),
                        "checked": "skill_id" in form.fields
                        and str(form["skill_id"].value()) == str(skill.pk),
                    }
                    for skill in skills
                ],
            }
            for group, skills in groups.items()
        ],
        submit_label=submit_label,
        submit_variant="primary",
    )
