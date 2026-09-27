"""The report form preserves incomplete values separately from gameplay validation."""

import json
from copy import deepcopy
from dataclasses import dataclass, field
from uuid import uuid4

from django import forms
from django.utils import timezone

from n26.core.counter_changes import LIMIT as COUNTER_LIMIT
from n26.core.post_battle import MAX_CREDIT_LINES, normalise
from n26.core.status import Status, label_for, status_colour


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
MAX_COUNTERS = 50


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
    lines = [
        {
            "id": line,
            "amount": data.get(f"credit-{line}-amount", ""),
            "reason": data.get(f"credit-{line}-reason", ""),
        }
        for line in dict.fromkeys(data.getlist("credit_line")[:MAX_CREDIT_LINES])
    ]
    counters = {
        key: data.get(f"gang-counter-{key}", "")
        for key in dict.fromkeys(data.getlist("gang_counter")[:MAX_COUNTERS])
    }
    return {
        "schema": 2,
        "credit_lines": lines,
        "gang_counters": counters,
        "participation_confirmed": data.get("participation_confirmed") == "on",
        "models": models,
    }


XP_STEPS = {"xp-step:+1": 1, "xp-step:-1": -1}


def _step_counter(values, key, step):
    """Move one entered counter change by ``step``, within the limit."""
    try:
        amount = int(str(values.get(key) or 0).strip())
    except ValueError:
        raise forms.ValidationError(
            "Enter a whole number for the counter change before you use −1 or +1."
        ) from None
    values[key] = str(max(-COUNTER_LIMIT, min(COUNTER_LIMIT, amount + step)))


def change_draft(payload, intent, *, xp_eligible=frozenset()):
    """Server-side form actions alter pending values, never the gang."""
    payload = normalise(payload)
    payload.pop("bulk_undo", None)
    if intent == "add-credit-line":
        if len(payload["credit_lines"]) < MAX_CREDIT_LINES:
            payload["credit_lines"].append(
                {"id": str(uuid4()), "amount": "", "reason": ""}
            )
    elif intent.startswith("remove-credit-line:"):
        target = intent.removeprefix("remove-credit-line:")
        payload["credit_lines"] = [
            line for line in payload["credit_lines"] if line.get("id") != target
        ]
    elif intent.startswith("counter-step:"):
        key, _, step = intent.removeprefix("counter-step:").rpartition(":")
        if step in {"+1", "-1"} and key in payload["gang_counters"]:
            _step_counter(payload["gang_counters"], key, int(step))
    elif intent in XP_STEPS:
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
    #: The field's label: the table's own word and a number, "Damage 2".
    label: str = ""
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
    #: ``(table label, [(value, text), ...])`` per table, for optgroups.
    effect_groups: list = field(default_factory=list)
    #: "Add Lasting Injury", "Add Damage" — the tables' own words.
    add_effect_label: str = ""
    #: Where an in-place update posts. Empty draws plain form controls.
    refresh_url: str = ""

    @property
    def refresh_attrs(self):
        """A control whose change redraws this model's module in place."""
        if not self.refresh_url:
            return {}
        return {
            "hx-post": self.refresh_url,
            "hx-trigger": "change",
            "hx-vals": json.dumps({"intent": f"refresh-model:{self.id}"}),
        }

    @property
    def status_attrs(self):
        """The Final status select: redraws the module, and points at the
        conflict that asks for a choice."""
        if not self.result.status_conflict:
            return self.refresh_attrs
        return self.refresh_attrs | {
            "aria-describedby": f"{self.prefix}-status-conflict",
            "aria-invalid": "true",
        }

    @property
    def button_attrs(self):
        """A button inside the module: htmx posts its own intent."""
        return {"hx-post": self.refresh_url} if self.refresh_url else {}

    @property
    def xp_why_label(self):
        return f"Why {self.name} cannot take XP"

    @property
    def current_xp_label(self):
        return f"Current XP: {self.result.xp_before}"

    @property
    def status_colour(self):
        return status_colour(self.result.status)

    @property
    def final_status_label(self):
        return label_for(self.result.final_status, self.result.is_vehicle)

    @property
    def final_status_colour(self):
        return status_colour(self.result.final_status)

    @property
    def status_changes(self):
        """Whether the status changes. Never while the results conflict:
        until the player chooses, there is no final status to name."""
        return (
            not self.result.status_conflict
            and self.result.final_status != self.result.status
        )

    @property
    def xp_changes(self):
        return self.result.xp_after != self.result.xp_before

    @property
    def named_effects(self):
        """The results picked so far. An empty slot records nothing."""
        return [effect for effect in self.effects if effect.name]

    @property
    def ends_in_recovery(self):
        return self.status_changes and self.result.final_status == Status.RECOVERY

    @property
    def changes(self):
        """Whether the summary lists this model: something it records."""
        return bool(
            self.xp_changes
            or self.named_effects
            or self.status_changes
            or self.result.status_conflict
            or self.result.equipment_changed
        )

    @property
    def equipment_label(self):
        return f"What happens to {self.name}'s equipment"


def _effect_label(labels):
    """One phrase for a model's tables, in their authored words: "Lasting
    Injury", or "Lasting Injury or Damage" where a model has both."""
    return " or ".join(dict.fromkeys(labels))


def refreshes_mission(intent):
    """Whether an in-place update redraws the Mission results section."""
    return intent == "add-credit-line" or intent.startswith(
        ("remove-credit-line:", "counter-step:")
    )


def refreshed_model(payload, intent):
    """The model whose module an in-place update redraws, if any."""
    kind, _, target = intent.partition(":")
    if kind in {"refresh-model", "add-effect"}:
        return target
    if kind in {"remove-effect", "clear-choices"}:
        for model in payload.get("models", []):
            if any(effect.get("id") == target for effect in model["effects"]):
                return model["id"]
    return None


def editor_models(plan, payload, refresh_url=""):
    """Plain field values and the domain's options, without database reads."""
    raw = {str(model.get("id")): model for model in payload.get("models", [])}
    models = []
    for model in plan.models:
        model_id = str(model.id)
        values = raw.get(model_id, {})
        proposed = {str(effect.id): effect for effect in model.effects}
        slot_labels = {slot.key: slot.label for slot in model.effect_slots}
        groups = [
            (
                slot.label,
                [
                    (f"{slot.key}|{option.value}", option.text)
                    for option in slot.options
                ],
            )
            for slot in model.effect_slots
            if slot.options
        ]
        options = [option for _, grouped in groups for option in grouped]
        default_label = next(iter(slot_labels.values()), "")
        effects = []
        for number, effect in enumerate(values.get("effects", []), start=1):
            found = proposed.get(str(effect.get("id")))
            selected = f"{effect.get('slot', '')}|{effect.get('pick', '')}"
            if selected == "|":
                selected = ""
            label = slot_labels.get(effect.get("slot", ""), default_label)
            effects.append(
                ReportEffect(
                    id=str(effect.get("id", "")),
                    selected=selected,
                    label=f"{label} {number}".strip(),
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
                effect_groups=groups,
                add_effect_label=(
                    f"Add {_effect_label(label for label, _ in groups)}"
                    if groups
                    else ""
                ),
                refresh_url=refresh_url,
            )
        )
    return models


@dataclass
class CreditRow:
    id: str
    amount: str
    reason: str
    number: int

    @property
    def prefix(self):
        return f"credit-{self.id}"

    @property
    def remove_label(self):
        return f"Remove credits line {self.number}"


@dataclass
class CounterRow:
    """One gang counter in Mission results: now, the change, and after."""

    change: object
    entered: str
    #: htmx's attributes for the step buttons; empty draws plain buttons.
    button_attrs: dict = field(default_factory=dict)

    @property
    def prefix(self):
        return f"gang-counter-{self.change.assignment_id}"

    @property
    def intent(self):
        return f"counter-step:{self.change.assignment_id}"

    @property
    def base(self):
        """Where the counter lands with nothing entered, for the page
        script to add a typed change to."""
        return self.change.after - self.change.manual

    @property
    def minus_attrs(self):
        if self.change.after <= 0 or self.change.manual <= -COUNTER_LIMIT:
            return {"disabled": True}
        return self.button_attrs

    @property
    def plus_attrs(self):
        if self.change.manual >= COUNTER_LIMIT:
            return {"disabled": True}
        return self.button_attrs

    @property
    def minus_label(self):
        return f"Remove 1 from {self.change.name}"

    @property
    def plus_label(self):
        return f"Add 1 to {self.change.name}"


@dataclass
class MissionResults:
    """The gang's results from the battle: credits and gang counters."""

    credit_rows: list
    counter_rows: list
    total: int
    #: Whether any result moves a gang counter; the column shows only then.
    show_effects: bool
    can_add_line: bool
    refresh_url: str = ""

    @property
    def total_text(self):
        return f"{self.total:+d}¢"

    @property
    def button_attrs(self):
        return {"hx-post": self.refresh_url} if self.refresh_url else {}


def mission_results(plan, payload, refresh_url=""):
    """The Mission results section's rows, from the draft and the plan.

    A report always shows at least one line of credits to type into; a
    new line has a fresh reference until the draft saves it.
    """
    lines = payload.get("credit_lines") or [
        {"id": str(uuid4()), "amount": "", "reason": ""}
    ]
    entered = payload.get("gang_counters") or {}
    button_attrs = {"hx-post": refresh_url} if refresh_url else {}
    return MissionResults(
        credit_rows=[
            CreditRow(
                id=str(line.get("id", "")),
                amount=str(
                    line.get("amount") if line.get("amount") is not None else ""
                ),
                reason=str(line.get("reason") or ""),
                number=number,
            )
            for number, line in enumerate(lines, start=1)
        ],
        counter_rows=[
            CounterRow(
                change=change,
                entered=str(entered.get(change.assignment_id) or ""),
                button_attrs=button_attrs,
            )
            for change in plan.gang_counters
        ],
        total=plan.credits_total,
        show_effects=plan.gang_counter_effects,
        can_add_line=len(lines) < MAX_CREDIT_LINES,
        refresh_url=refresh_url,
    )


def receipt_mission(receipt):
    """The receipt's lines of credits and gang counters.

    A receipt written before lines of credits holds one reason for the
    whole adjustment, and shows it as it was.
    """
    return {
        "credit_lines": receipt.get("credit_lines", []),
        "reason": "" if "credit_lines" in receipt else receipt.get("reason", ""),
        "gang_counters": receipt.get("gang_counters", []),
    }


def receipt_models(receipt):
    """The receipt's models that took part or changed, with what changed
    and each status's badge colour."""
    models = []
    for model in receipt.get("models", []):
        changed = {
            "xp_changed": model.get("xp_before") != model.get("xp_after")
            or bool(model.get("xp_change")),
            "status_changed": model.get("status_before") != model.get("status_after"),
        }
        if not (
            model.get("participated")
            or changed["xp_changed"]
            or changed["status_changed"]
            or model.get("effects")
            or model.get("equipment_changed")
        ):
            continue
        models.append(
            model
            | changed
            | {
                "status_before_colour": status_colour(model.get("status_before")),
                "status_after_colour": status_colour(model.get("status_after")),
            }
        )
    return models


def _plural(count, one, many):
    return (one if count == 1 else many).replace("{n}", str(count))


@dataclass
class XpToolbar:
    """The selected-models bar. The page script redraws it from the templates."""

    selected: int
    minus_disabled: bool
    plus_disabled: bool

    count_one = "1 model took part"
    count_many = "{n} models took part"
    plus_one = "Add 1 XP to the model that took part"
    plus_many = "Add 1 XP to each of the {n} models that took part"
    minus_one = "Remove 1 XP from the model that took part"
    minus_many = "Remove 1 XP from each of the {n} models that took part"

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
        minus_disabled=all(entered(model) <= 0 for model in eligible),
        plus_disabled=not eligible,
    )
