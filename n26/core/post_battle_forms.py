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


def change_draft(payload, intent, *, previous=None):
    """Server-side form actions alter pending values, never the gang."""
    payload = deepcopy(payload)
    if previous and "bulk_undo" in previous and intent != "undo-xp":
        payload["bulk_undo"] = previous["bulk_undo"]
    if intent == "participation-xp":
        before = {}
        for model in payload["models"]:
            if model["participated"]:
                try:
                    amount = int(model["xp"] or 0)
                except TypeError, ValueError:
                    raise forms.ValidationError(
                        "Enter whole numbers for XP before adding participation XP."
                    ) from None
                before[model["id"]] = model["xp"]
                model["xp"] = str(amount + 1)
        payload["bulk_undo"] = before
    elif intent == "undo-xp":
        before = (previous or {}).get("bulk_undo", {})
        for model in payload["models"]:
            if model["id"] in before:
                try:
                    model["xp"] = str(int(model["xp"] or 0) - 1)
                except TypeError, ValueError:
                    raise forms.ValidationError(
                        "Enter whole numbers for XP before undoing the addition."
                    ) from None
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
                xp=values.get("xp", ""),
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
