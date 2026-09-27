"""The report form preserves incomplete values separately from gameplay validation."""

from copy import deepcopy
from dataclasses import dataclass, field
from uuid import uuid4

from django import forms
from django.utils import timezone

from n26.core.status import Status, label_for


class StartReportForm(forms.Form):
    date = forms.DateField(initial=timezone.localdate)
    reference = forms.CharField(max_length=200, required=False, label="Reference")
    request_key = forms.UUIDField(widget=forms.HiddenInput)

    @property
    def date_value(self):
        value = self["date"].value()
        return value.isoformat() if hasattr(value, "isoformat") else value or ""


class ReportVersionForm(forms.Form):
    generation = forms.UUIDField(widget=forms.HiddenInput)
    revision = forms.IntegerField(min_value=0, widget=forms.HiddenInput)
    submission_key = forms.UUIDField(widget=forms.HiddenInput)
    review = forms.CharField(required=False, widget=forms.HiddenInput)


MAX_MODELS = 200
MAX_EFFECTS = 20


def posted_payload(data):
    """Read values without cleaning them: an unfinished draft is still saveable."""
    models = []
    seen = set()
    for model_id in data.getlist("model_id")[:MAX_MODELS]:
        if model_id in seen:
            continue
        seen.add(model_id)
        prefix = f"model-{model_id}"
        effects = []
        for occurrence in data.getlist(f"{prefix}-effect")[:MAX_EFFECTS]:
            effect_prefix = f"effect-{occurrence}"
            selected = data.get(f"{effect_prefix}-pick", "")
            slot, _, pick = selected.partition("|")
            choices = {
                key: selected
                for key in data.getlist(f"{effect_prefix}-question")[:MAX_EFFECTS]
                if (
                    selected := [
                        value
                        for value in data.getlist(f"{effect_prefix}-choice-{key}")
                        if value
                    ]
                )
            }
            effects.append(
                {"id": occurrence, "slot": slot, "pick": pick, "choices": choices}
            )
        models.append(
            {
                "id": model_id,
                "participated": data.get(f"{prefix}-participated") == "on",
                "xp": data.get(f"{prefix}-xp", ""),
                "status": data.get(f"{prefix}-status", ""),
                "equipment": data.get(f"{prefix}-equipment", "keep"),
                "effects": effects,
            }
        )
    return {
        "schema": 1,
        "credits": data.get("credits", ""),
        "reason": data.get("reason", ""),
        "participation_confirmed": data.get("participation_confirmed") == "on",
        "models": models,
    }


XP_STEPS = {"xp-step:+1": 1, "xp-step:-1": -1}


def change_draft(payload, intent, *, xp_eligible=frozenset()):
    """Server-side form actions alter pending values, never the gang."""
    payload = deepcopy(payload)
    payload.pop("bulk_undo", None)
    if intent in XP_STEPS:
        step = XP_STEPS[intent]
        for model in payload["models"]:
            if not model["participated"] or model["id"] not in xp_eligible:
                continue
            try:
                amount = int(model["xp"] or 0)
            except TypeError, ValueError:
                raise forms.ValidationError(
                    "Enter whole numbers for XP before changing XP for the selected models."
                ) from None
            model["xp"] = str(max(0, amount + step))
    elif intent.startswith("add-effect:"):
        target = intent.removeprefix("add-effect:")
        for model in payload["models"]:
            if model["id"] == target and len(model["effects"]) < MAX_EFFECTS:
                model["effects"].append(
                    {"id": str(uuid4()), "slot": "", "pick": "", "choices": {}}
                )
    elif intent.startswith("remove-effect:"):
        target = intent.removeprefix("remove-effect:")
        for model in payload["models"]:
            model["effects"] = [
                effect for effect in model["effects"] if effect["id"] != target
            ]
    elif intent.startswith("clear-choices:"):
        target = intent.removeprefix("clear-choices:")
        for model in payload["models"]:
            for effect in model["effects"]:
                if effect["id"] == target:
                    effect["choices"] = {}
    return payload


def keep_recorded_xp(payload, plan):
    """Put back the recorded award on models that cannot take XP.

    Returns the payload and whether anything changed. Drafts saved before
    blocked models were skipped can hold XP those models cannot take.
    """
    blocked = {
        str(model.id): str(model.xp_recorded or "")
        for model in plan.models
        if not model.xp_available
    }
    changed = False
    payload = deepcopy(payload)
    for model in payload.get("models", []):
        if not isinstance(model, dict):
            continue
        recorded = blocked.get(str(model.get("id")))
        if recorded is not None and str(model.get("xp") or "") != recorded:
            model["xp"] = recorded
            changed = True
    return payload, changed


@dataclass
class ReportEffect:
    id: str
    selected: str
    questions: list = field(default_factory=list)
    name: str = ""
    retained_choices: list = field(default_factory=list)


@dataclass
class ReportModel:
    id: str
    name: str
    prefix: str
    result: object
    participated: bool
    xp: str
    status: str
    equipment: str
    effect_options: list
    effects: list
    status_options: list

    @property
    def xp_attrs(self):
        return {} if self.result.xp_available else {"disabled": True}

    @property
    def final_status_label(self):
        return label_for(self.result.final_status, self.result.is_vehicle)


def editor_models(plan, payload):
    """Plain field values and the domain's options, without database reads."""
    raw = {str(model.get("id")): model for model in payload.get("models", [])}
    models = []
    for model in plan.models:
        model_id = str(model.id)
        values = raw.get(model_id, {})
        proposed = {str(effect.id): effect for effect in model.effects}
        options = [
            (f"{slot.key}|{option.value}", f"{slot.label} · {option.label}")
            for slot in model.effect_slots
            for option in slot.options
        ]
        effects = []
        for effect in values.get("effects", []):
            found = proposed.get(str(effect.get("id")))
            selected = f"{effect.get('slot', '')}|{effect.get('pick', '')}"
            if selected == "|":
                selected = ""
            effects.append(
                ReportEffect(
                    id=str(effect.get("id", "")),
                    selected=selected,
                    questions=found.questions if found else [],
                    name=found.name if found else "",
                    retained_choices=[
                        (key, selected)
                        for key, selected in (effect.get("choices") or {}).items()
                        if key
                        not in {
                            question.key
                            for question in (found.questions if found else [])
                        }
                    ],
                )
            )
        vehicle = model.is_vehicle
        models.append(
            ReportModel(
                id=model_id,
                name=model.name,
                prefix=f"model-{model_id}",
                result=model,
                participated=bool(values.get("participated", model.participated)),
                # A model that cannot take XP keeps its recorded award, so
                # an old or stray value never blocks the rest of the report.
                xp=(
                    values.get("xp", "")
                    if model.xp_available
                    else str(model.xp_recorded or "")
                ),
                status=values.get("status", ""),
                equipment=values.get("equipment", "keep"),
                effect_options=options,
                effects=effects,
                status_options=[
                    (value, label_for(value, vehicle)) for value in Status.values
                ],
            )
        )
    return models


def _plural(count, one, many):
    return (one if count == 1 else many).replace("{n}", str(count))


@dataclass
class XpToolbar:
    """The selected-models bar. The page script redraws it from the templates."""

    selected: int
    blocked_names: list
    minus_disabled: bool
    plus_disabled: bool

    count_one = count_many = "{n} selected"
    plus_one = "Add 1 XP to the selected model"
    plus_many = "Add 1 XP to the {n} selected models"
    minus_one = "Remove 1 XP from the selected model"
    minus_many = "Remove 1 XP from the {n} selected models"
    blocked_one = "1 selected model cannot take XP: {names}."
    blocked_many = "{n} selected models cannot take XP: {names}."

    @property
    def minus_attrs(self):
        return {"disabled": True} if self.minus_disabled else {}

    @property
    def plus_attrs(self):
        return {"disabled": True} if self.plus_disabled else {}

    @property
    def count_label(self):
        return _plural(self.selected, self.count_one, self.count_many)

    @property
    def plus_label(self):
        return _plural(self.selected, self.plus_one, self.plus_many)

    @property
    def minus_label(self):
        return _plural(self.selected, self.minus_one, self.minus_many)

    @property
    def blocked_message(self):
        if not self.blocked_names:
            return ""
        return _plural(
            len(self.blocked_names), self.blocked_one, self.blocked_many
        ).replace("{names}", ", ".join(self.blocked_names))


def xp_toolbar(models):
    selected = [model for model in models if model.participated]
    eligible = [model for model in selected if model.result.xp_available]

    def entered(model):
        try:
            return int(model.xp or 0)
        except TypeError, ValueError:
            return 1

    return XpToolbar(
        selected=len(selected),
        blocked_names=[m.name for m in selected if not m.result.xp_available],
        minus_disabled=all(entered(model) <= 0 for model in eligible),
        plus_disabled=not eligible,
    )
