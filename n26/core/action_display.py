"""JSON-native page facts for the complete model action workflow."""

from dataclasses import asdict
from urllib.parse import urlencode
from uuid import uuid4

from django.middleware.csrf import get_token
from django.urls import reverse
from django.utils.text import capfirst

from n26.core.action_workflow import BUSINESS_FIELDS


def page_data(request, page, target, *, errors=None, conflict=False):
    context = page.context
    fighter = context["miniature"]
    record = context.get("record")
    form = context.get("form")
    values = {name: "" for name in BUSINESS_FIELDS}
    values.update(
        {
            "command_key": str(uuid4()),
            "gang_id": str(fighter.gang.pk),
            "revision": str(record.revision) if record else "",
            "target_kind": target.kind,
            "target_id": target.key,
            "target_step": target.step,
            "target_allowance": target.allowance or "",
            "target_pick": target.pick or "",
            "target_allowance_present": "1" if target.allowance is not None else "0",
            "target_pick_present": "1" if target.pick is not None else "0",
            "submitted_summary": "",
        }
    )
    if form:
        for name in form.fields:
            value = form[name].value()
            values[name] = "" if value is None else str(value)
    if context.get("decline_promotion"):
        values["request_key"] = str(context["promotion_request_key"])
    # Preserve submitted business fields exactly on known rejections as well.
    if request.method == "POST":
        for name in values:
            if name in request.POST:
                values[name] = request.POST[name]
    scalar_names = (
        "stage",
        "correction",
        "earned_threshold",
        "back",
        "back_href",
        "back_label",
        "done_href",
        "cancel_href",
        "undo_href",
        "correct_href",
        "change_href",
        "selection_summary",
        "outcome_href",
        "tracking_unavailable",
        "submit_label",
        "submit_variant",
        "roll_value",
        "advancement_title",
        "roll_explanation",
        "threshold_roll",
        "promotion_description",
        "decline_promotion",
        "skill_random",
        "skill_resolved",
        "skill_selected",
        "skill_title",
        "skill_empty",
        "selected_pick",
        "show_outcome",
        "outcome_description",
        "retained_payment",
        "retained_roll",
        "hold_reason",
        "keeps_stashed_weapons",
        "recovery_only",
    )
    facts = {name: context.get(name) for name in scalar_names}
    facts.update(
        {
            "outcome": str(record.outcome) if record and record.outcome_id else "",
            "allowanceThreshold": bool(
                record and record.allowance_id and record.allowance.threshold
            ),
            "steps": [asdict(step) for step in context.get("steps", [])],
            "prices": [asdict(price) for price in context.get("prices", [])],
            "payments": [
                [asdict(fact) for fact in tally.facts]
                for tally in context.get("payment_tallies", [])
            ],
            "receipt": [asdict(fact) for fact in context.get("receipt", [])],
            "outcomes": context.get("outcomes", []),
            "items": [
                {
                    "key": row["key"],
                    "name": row["item"].item_name,
                    "current": row["item"].current_tier,
                    "tier": row["item"].candidate_tier,
                    "effect": row["item"].effect[:1].upper() + row["item"].effect[1:],
                    "before": row["item"].rating_before,
                    "after": row["item"].rating_after,
                }
                for row in context.get("item_options", [])
            ],
            "advancements": [
                {
                    "key": row["option"].id,
                    "name": row["option"].name,
                    "minimum": row["option"].roll_minimum,
                    "rating": row["option"].rating,
                    "forcedRandom": row["option"].forced_random,
                }
                for row in context.get("advancement_options", [])
            ],
            "roll": context.get("advancement_roll"),
            "skillRoll": context.get("skill_roll"),
            "skillGroups": context.get("skill_groups", []),
            "attempts": context.get("skill_attempts", []),
            "reviewChoice": context.get("review_choice"),
            "changes": context.get("change_preview", []),
        }
    )
    if facts["reviewChoice"]:
        facts["reviewChoice"] = {
            **facts["reviewChoice"],
            "description": capfirst(facts["reviewChoice"]["description"]),
        }
    draft_key = f"n26-action-draft:{request.user.pk}:{fighter.pk}:{target.kind}:{target.key}:{target.step}:{target.pick}:{target.allowance}"
    values["draft_key"] = draft_key
    here = request.path
    recovery_href = (
        here
        + "?"
        + urlencode({**target.query, "recover": "1", "gang_id": str(fighter.gang.pk)})
    )
    return {
        "title": str(context["action"]),
        "modelName": fighter.name,
        "gangName": fighter.gang.name,
        "gangHref": reverse("n26-gang", args=[fighter.gang.pk]),
        "modelHref": reverse("n26-edit-fighter", args=[fighter.pk]),
        "facts": facts,
        "values": values,
        "errors": errors
        if errors is not None
        else dict(form.errors)
        if form and form.is_bound
        else {},
        "initialConflict": conflict,
        "fields": list(form.fields) if form else [],
        "hiddenFields": [field.name for field in form.hidden_fields()] if form else [],
        "action": here + ("?" + request.GET.urlencode() if request.GET else ""),
        "commandHref": reverse("n26-action-command", args=[fighter.pk]),
        "displayHref": reverse("n26-action-display", args=[fighter.pk])
        + "?"
        + urlencode(
            {
                "target_kind": target.kind,
                "target_id": target.key,
                "target_step": target.step,
                "target_allowance": target.allowance or "",
                "target_pick": target.pick or "",
                "target_allowance_present": "1"
                if target.allowance is not None
                else "0",
                "target_pick_present": "1" if target.pick is not None else "0",
                **({"recover": "1"} if request.GET.get("recover") == "1" else {}),
            }
        ),
        "csrfToken": get_token(request),
        "recoveryKey": f"n26-action:{request.user.pk}:{fighter.gang.pk}:{fighter.pk}",
        "draftKey": draft_key,
        "draftScope": f"n26-action-draft:{request.user.pk}:{fighter.pk}:",
        "recoveryHref": recovery_href,
        "signInHref": reverse("account_login")
        + "?"
        + urlencode({"next": recovery_href}),
    }
