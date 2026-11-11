"""Explicit editor props from the report's prepared forms and consequence plan."""

from django.urls import reverse
from django.utils import timezone
from django.utils.formats import date_format

from n26.core.campaigns import battle_stake, stake_came_from
from n26.core.post_battle_forms import (
    editor_models,
    mission_results,
    preview_display,
    toolbar_display,
)


def _counter(row):
    return {
        "id": str(row.change.assignment_id or ""),
        "name": row.change.name,
        "prefix": row.prefix,
        "listName": row.list_name,
        "entered": row.entered,
        "editable": row.editable,
        "before": row.start,
        "base": row.base,
        "after": row.change.after,
        "fromResults": row.change.from_results,
        "limit": row.limit,
        "minusLabel": row.minus_label,
        "plusLabel": row.plus_label,
    }


def _model(model):
    result = model.result
    return {
        "id": model.id,
        "name": model.name,
        "prefix": model.prefix,
        "profileName": model.profile_name,
        "ownedBy": result.owned_by,
        "participated": model.participated,
        "xp": model.xp,
        "xpAvailable": result.xp_available,
        "xpBefore": result.xp_before,
        "xpHelp": result.xp_blocked_message,
        "status": model.status,
        "statusLabel": result.status_label,
        "statusColour": model.status_colour,
        "statusOptions": [
            {"value": value, "label": label} for value, label in model.status_options
        ],
        "statusConflict": result.status_conflict,
        "statusChanges": model.status_changes,
        "finalStatusLabel": model.final_status_label,
        "finalStatusColour": model.final_status_colour,
        "equipment": model.equipment,
        "equipmentLabel": model.equipment_label,
        "equipmentApplies": result.equipment_applies,
        "equipmentChanged": result.equipment_changed,
        "equipmentDisposition": result.equipment_disposition,
        "equipmentNames": list(result.equipment_affected_names),
        "equipmentExclusions": list(result.equipment_exclusions),
        "addEffectLabel": model.add_effect_label,
        "effectGroups": [
            {
                "label": label,
                "options": [{"value": value, "label": text} for value, text in options],
            }
            for label, options in model.effect_groups
        ],
        "effects": [
            {
                "id": effect.id,
                "selected": effect.selected,
                "label": effect.label,
                "name": effect.name,
                "retainedOption": effect.retained_option,
                "retainedChoices": [
                    {"key": key, "selected": list(selected)}
                    for key, selected in effect.retained_choices
                ],
                "questions": [
                    {
                        "key": question.key,
                        "label": question.label,
                        "multiple": question.multiple,
                        "required": bool(question.min_picks),
                        "selected": list(question.selected),
                        "options": [
                            {"value": option.value, "label": option.text}
                            for option in question.options
                        ],
                    }
                    for question in effect.questions
                ],
            }
            for effect in model.effects
        ],
        "counters": [_counter(row) for row in model.counter_rows],
        "counterEffects": model.show_counter_effects,
        "note": model.note,
        "noteLabel": model.note_label,
        "noteHelp": model.note_help,
        "noteLimit": model.note_limit,
        "errors": list(result.errors),
    }


def territory_display(report, actor):
    stake = battle_stake(report.battle, actor)
    if not stake:
        return None
    applied = (
        bool(report.battle.stake_transfer_mark)
        or report.battle.result != report.battle.Result.NOT_RECORDED
    )
    if report.battle.stake_transfer_mark:
        source = stake_came_from(report.battle)
        outcome = (
            f"Moved from {source.name} to {stake.awarded_to}."
            if source
            else f"Moved to {stake.awarded_to}."
        )
    elif report.battle.result == report.battle.Result.NOT_RECORDED:
        outcome = "Outcome not recorded."
    else:
        outcome = stake.outcome
    return {
        "name": stake.name,
        "heading": stake.label,
        "outcome": outcome,
        "currentHolder": stake.held_by,
        "applied": applied,
        "note": "Already applied."
        if applied
        else "The campaign’s arbitrator records this outcome on Edit battle.",
    }


def editor_display(report, actor, payload, plan, *, show_errors=False, errors=()):
    """Project only authorised facts; both initial and command responses use this shape."""
    models = editor_models(plan, payload)
    mission = mission_results(plan, payload, show_errors=show_errors)
    breadcrumbs = []
    if report.battle_id:
        breadcrumbs.append(
            {
                "label": report.battle.title,
                "href": reverse(
                    "n26-battle", args=[report.battle.campaign_id, report.battle.pk]
                ),
            }
        )
    breadcrumbs.append(
        {"label": report.gang.name, "href": reverse("n26-gang", args=[report.gang_id])}
    )
    if not report.battle_id:
        breadcrumbs.append(
            {
                "label": "Post-battle",
                "href": reverse("n26-gang-post-battle", args=[report.gang_id]),
            }
        )
    breadcrumbs.append(
        {
            "label": "Post-battle results"
            if report.battle_id
            else report.reference or "Post-battle report"
        }
    )
    return {
        "reportId": str(report.pk),
        "title": "Post-battle results",
        "lead": (f"{report.battle.title} · " if report.battle_id else "")
        + date_format(report.date, "j M Y"),
        "breadcrumbs": breadcrumbs,
        "correcting": bool(report.latest_sequence),
        "receiptHref": reverse("n26-post-battle-receipt", args=[report.pk]),
        "generation": str(report.generation),
        "revision": report.draft_revision,
        "review": plan.review,
        "savedAt": timezone.localtime(report.modified).strftime("%H:%M:%S"),
        "payload": payload,
        "participationConfirmed": bool(payload.get("participation_confirmed")),
        "models": [_model(model) for model in models],
        "toolbar": toolbar_display(models),
        "mission": {
            "creditLines": [
                {
                    "id": line.id,
                    "amount": line.amount,
                    "reason": line.reason,
                    "amountErrors": list(line.amount_errors),
                    "reasonErrors": list(line.reason_errors),
                    "removeLabel": line.remove_label,
                }
                for line in mission.credit_rows
            ],
            "canAddLine": mission.can_add_line,
            "totalText": mission.total_text,
            "counters": [_counter(row) for row in mission.counter_rows],
            "counterEffects": mission.show_effects,
        },
        "territory": territory_display(report, actor),
        "preview": preview_display(plan, models),
        "errors": list(dict.fromkeys([*errors, *(plan.errors if show_errors else [])])),
        "showErrors": show_errors,
    }
