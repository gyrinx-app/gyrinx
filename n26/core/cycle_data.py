"""Translate schedule definitions and editable values at the storage boundary."""

from dataclasses import asdict
from datetime import date

from n26.core import schedule as s


def calendar_data(calendar):
    if calendar is None:
        return {}
    data = {**asdict(calendar), "starts_on": calendar.starts_on.isoformat()}
    if not calendar.days_offset:
        data.pop("days_offset")
    return data


def calendar_from_data(data):
    if data == {}:
        return None
    data = _object(
        data, {"starts_on", "interval", "unit", "starts_after_order", "days_offset"}
    )
    try:
        start = date.fromisoformat(data["starts_on"])
        return s.CycleCalendar(
            start,
            data["interval"],
            data["unit"],
            data["starts_after_order"],
            data.get("days_offset", 0),
        )
    except (KeyError, TypeError, ValueError) as exc:
        raise s.ScheduleError("Enter a valid start date and cycle interval.") from exc


def _object(data, fields):
    if not isinstance(data, dict) or data.keys() - fields:
        raise s.ScheduleError("The schedule contains unsupported fields.")
    return data


def _array(data):
    if not isinstance(data, list):
        raise s.ScheduleError("The schedule entries must be a list.")
    return data


def _text(data, field, default=""):
    value = data.get(field, default)
    if not isinstance(value, str):
        raise s.ScheduleError(f"Enter text for {field.replace('_', ' ')}.")
    return value


def credits_from_data(data):
    data = _object(data, {"fixed", "dice"})
    dice = data.get("dice")
    if dice is not None:
        dice = s.DiceAmount(**_object(dice, {"count", "sides", "multiplier"}))
    return s.CreditAmount(fixed=data.get("fixed", 0), dice=dice)


def rewards_from_data(data):
    data = _object(data, {"win", "draw", "loss", "entry_credits"})
    outcomes = {}
    for name in ("win", "draw", "loss"):
        reward = _object(data.get(name, {}), {"credits", "reputation"})
        outcomes[name] = s.Reward(
            credits_from_data(reward.get("credits", {})), reward.get("reputation", 0)
        )
    return s.RewardSettings(
        **outcomes, entry_credits=credits_from_data(data.get("entry_credits", {}))
    )


def phase_details_from_data(data):
    data = _object(data, {"name", "description", "effects", "rewards"})
    return s.PhaseDetails(
        _text(data, "name"),
        _text(data, "description"),
        _text(data, "effects"),
        rewards_from_data(data.get("rewards", {})),
    )


def steps_from_data(data):
    steps = []
    for item in _array(data):
        item = _object(item, {"id", "phase_id", "count"})
        identity, phase = _text(item, "id"), _text(item, "phase_id")
        if not identity or not phase:
            raise s.ScheduleError(
                "Every plan step must identify its phase and position."
            )
        if len(identity) > 26:
            raise s.ScheduleError("A plan step identity cannot exceed 26 characters.")
        steps.append(s.PlanStep(identity, phase, item.get("count")))
    return tuple(steps)


def template_from_data(name, data):
    data = _object(data, {"phases", "steps"})
    phases = []
    for item in _array(data.get("phases", [])):
        item = _object(item, {"id", "details"})
        identity = _text(item, "id")
        if not identity:
            raise s.ScheduleError("Every template phase must have an identity.")
        phases.append(
            s.Phase(identity, phase_details_from_data(item.get("details", {})))
        )
    return s.ScheduleTemplate(
        name, tuple(phases), steps_from_data(data.get("steps", []))
    )


def template_data(template):
    return {
        "phases": [
            {"id": p.id, "details": asdict(p.details)}
            for p in template.phases
            if not p.archived
        ],
        "steps": [asdict(step) for step in template.steps],
    }


def cycle_details_data(details):
    data = asdict(details)
    for field in ("starts_on", "ends_on"):
        value = data[field]
        data[field] = value.isoformat() if value else None
    return data


def cycle_details_from_data(data):
    data = _object(
        data,
        {"phase_id", "custom_name", "starts_on", "ends_on", "description", "effects"},
    )
    dates = {}
    for field in ("starts_on", "ends_on"):
        value = data.get(field)
        try:
            dates[field] = (
                date.fromisoformat(value) if value not in (None, "") else None
            )
        except TypeError, ValueError:
            raise s.ScheduleError("Enter dates in YYYY-MM-DD format.") from None
    custom_name = data.get("custom_name")
    if custom_name is not None and not isinstance(custom_name, str):
        raise s.ScheduleError("Enter text for the custom name.")
    return s.CycleDetails(
        phase_id=_text(data, "phase_id"),
        custom_name=custom_name or None,
        description=_text(data, "description"),
        effects=_text(data, "effects"),
        **dates,
    )


def ref_from_data(data):
    if isinstance(data, dict) and set(data) == {"cycle_id"}:
        return s.SavedCycleRef(_text(data, "cycle_id"))
    if isinstance(data, dict) and set(data) == {"plan_id", "index"}:
        return s.ProjectedCycleRef(
            s.PlannedPosition(_text(data, "plan_id"), data["index"])
        )
    raise s.ScheduleError("Select a saved or projected cycle.")


def ref_data(ref):
    if isinstance(ref, s.SavedCycleRef):
        return {"cycle_id": ref.cycle_id}
    return asdict(ref.position)
