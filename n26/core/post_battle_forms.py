"""The report form preserves incomplete values separately from gameplay validation."""

import json
from copy import deepcopy
from dataclasses import dataclass, field
from uuid import uuid4

from django import forms
from django.utils import timezone

from n26.core.counter_changes import LIMIT as COUNTER_LIMIT
from n26.core.post_battle import MAX_CREDIT_LINES, MAX_NOTE, normalise, signed
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
                "counters": {
                    key: data.get(f"{prefix}-counter-{key}", "")
                    for key in dict.fromkeys(
                        data.getlist(f"{prefix}-counter")[:MAX_COUNTERS]
                    )
                },
                # A browser counts a line break as one character and posts
                # two; the note is kept with one, as its limit counts it.
                "note": data.get(f"{prefix}-note", "").replace("\r\n", "\n"),
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


def _model_counter_step(intent):
    """``model-counter-step:<model>:<counter>:<step>`` in its three parts."""
    target, _, rest = intent.removeprefix("model-counter-step:").partition(":")
    key, _, step = rest.rpartition(":")
    return target, key, step if step in {"+1", "-1"} else "0"


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
    elif intent.startswith("model-counter-step:"):
        target, key, step = _model_counter_step(intent)
        for model in payload["models"]:
            counters = model.get("counters")
            if model["id"] == target and isinstance(counters, dict) and key in counters:
                _step_counter(counters, key, int(step))
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
    counter_rows: list = field(default_factory=list)
    note: str = ""

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
            or self.result.moving_counters
            or self.result.note_appends
        )

    @property
    def equipment_label(self):
        return f"What happens to {self.name}'s equipment"

    @property
    def summary_counters(self):
        """The counters this report moves, with where each change came from."""
        return [
            (change, counter_parts(change.delta, change.effect))
            for change in self.result.moving_counters
        ]

    @property
    def show_counter_effects(self):
        return self.result.counter_effects

    @property
    def counters_heading_id(self):
        return f"{self.prefix}-counters-heading"

    @property
    def note_label(self):
        return f"Add to {self.name}'s notes (optional)"

    @property
    def note_help(self):
        # Typing does not redraw the module, so the help cannot depend on
        # whether the note has changed: once a note is in the model's
        # notes, say where it is, whatever is typed next.
        if self.result.note_recorded:
            return f"The earlier note stays in {self.name}'s notes. Edit it there."
        return f"Added to the end of {self.name}'s notes when you apply these results."

    @property
    def note_limit(self):
        return MAX_NOTE


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
    if kind == "model-counter-step":
        return _model_counter_step(intent)[0]
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
                counter_rows=_model_counter_rows(model, values.get("counters")),
                note=str(values.get("note") or ""),
            )
        )
    return models


def _model_counter_rows(model, entered):
    entered = entered if isinstance(entered, dict) else {}
    prefix = f"model-{model.id}"
    return [
        CounterRow(
            change=change,
            entered=str(entered.get(change.assignment_id) or ""),
            list_name=f"{prefix}-counter",
            field_prefix=f"{prefix}-counter",
            step_intent=f"model-counter-step:{model.id}",
        )
        for change in model.counters
    ]


@dataclass
class CreditRow:
    id: str
    amount: str
    reason: str
    number: int
    amount_errors: list = field(default_factory=list)
    reason_errors: list = field(default_factory=list)

    @property
    def prefix(self):
        return f"credit-{self.id}"

    @property
    def remove_label(self):
        return f"Remove line of credits {self.number}"

    def _error_attrs(self, name, errors):
        if not errors:
            return {}
        return {
            "aria-invalid": "true",
            "aria-describedby": f"{self.prefix}-{name}-error",
        }

    @property
    def amount_attrs(self):
        return self._error_attrs("amount", self.amount_errors)

    @property
    def reason_attrs(self):
        return self._error_attrs("reason", self.reason_errors)


@dataclass
class CounterRow:
    """One counter's row, the gang's or a model's: now, the change, and after."""

    change: object
    entered: str
    #: The name the form lists each counter under; each counter's field
    #: is this name, a dash and the counter's id.
    list_name: str = "gang_counter"
    field_prefix: str = "gang-counter"
    step_intent: str = "counter-step"

    @property
    def editable(self):
        """A counter a result creates has no change to enter yet."""
        return bool(self.change.assignment_id)

    @property
    def prefix(self):
        return f"{self.field_prefix}-{self.change.assignment_id}"

    @property
    def intent(self):
        return f"{self.step_intent}:{self.change.assignment_id}"

    @property
    def base(self):
        """Where the counter lands with nothing entered, for the page
        script to add a typed change to."""
        return self.change.after - self.change.manual

    @property
    def start(self):
        """The Before column: the reading before this report, so Before,
        the change and what results add sum to After."""
        return self.change.start

    @property
    def limit(self):
        return COUNTER_LIMIT

    def _step_attrs(self, step, disabled):
        """The page script steps the field in place; without scripts the
        button posts the form."""
        attrs = {"data-counter-step": self.prefix, "data-step": step}
        return (attrs | {"disabled": True}) if disabled else attrs

    @property
    def minus_attrs(self):
        return self._step_attrs(
            "-1", self.change.after <= 0 or self.change.manual <= -COUNTER_LIMIT
        )

    @property
    def plus_attrs(self):
        return self._step_attrs("+1", self.change.manual >= COUNTER_LIMIT)

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
        return f"{signed(self.total)}¢"

    @property
    def button_attrs(self):
        return {"hx-post": self.refresh_url} if self.refresh_url else {}


def mission_results(plan, payload, refresh_url="", show_errors=False):
    """The Mission results section's rows, from the draft and the plan.

    A report always shows at least one line of credits to type into; a
    new line has a fresh reference until the draft saves it. With
    ``show_errors``, each line carries its own errors to show by its
    fields.
    """
    field_errors = plan.credit_field_errors if show_errors else {}
    lines = payload.get("credit_lines") or [
        {"id": str(uuid4()), "amount": "", "reason": ""}
    ]
    entered = payload.get("gang_counters") or {}
    return MissionResults(
        credit_rows=[
            CreditRow(
                id=str(line.get("id", "")),
                amount=str(
                    line.get("amount") if line.get("amount") is not None else ""
                ),
                reason=str(line.get("reason") or ""),
                number=number,
                amount_errors=field_errors.get(f"{line.get('id', '')}-amount", []),
                reason_errors=field_errors.get(f"{line.get('id', '')}-reason", []),
            )
            for number, line in enumerate(lines, start=1)
        ],
        counter_rows=[
            CounterRow(
                change=change,
                entered=str(entered.get(change.assignment_id) or ""),
            )
            for change in plan.gang_counters
        ],
        total=plan.credits_total,
        show_effects=plan.gang_counter_effects,
        can_add_line=len(lines) < MAX_CREDIT_LINES,
        refresh_url=refresh_url,
    )


def receipt_mission(receipt, revision=None):
    """The receipt's lines of credits and gang counters.

    The credits from this battle are the lines' total. A correction also
    names its change from the version before. A receipt written before
    lines of credits holds one reason for the whole adjustment, and shows
    it as it was.
    """
    total = receipt.get("credits_total")
    if total is None and revision is not None:
        total = revision.inputs.get("credits")
    if total is None:
        total = receipt.get("credits_change", 0)
    correction = revision is not None and revision.sequence > 1
    change = receipt.get("credits_change", 0)
    return {
        "total_text": f"{signed(int(total or 0))}¢",
        "change_text": f"{signed(int(change or 0))}¢" if correction else "",
        "credit_lines": [
            line | {"amount_text": f"{signed(int(line.get('amount') or 0))}¢"}
            for line in receipt.get("credit_lines", [])
        ],
        "reason": "" if "credit_lines" in receipt else receipt.get("reason", ""),
        "gang_counters": receipt.get("gang_counters", []),
    }


def counter_parts(manual, effect):
    """Where a counter's change came from: "+1 entered, +1 from results"."""
    parts = []
    if manual:
        parts.append(f"{manual:+d} entered")
    if effect:
        parts.append(f"{effect:+d} from results")
    return ", ".join(parts)


def receipt_models(receipt):
    """The receipt's models that took part or changed, with what changed,
    each status's badge colour and where each counter's change came from."""
    models = []
    for model in receipt.get("models", []):
        changed = {
            "xp_changed": model.get("xp_before") != model.get("xp_after")
            or bool(model.get("xp_change")),
            "status_changed": model.get("status_before") != model.get("status_after"),
            "counters": [
                line
                | {
                    "parts": counter_parts(
                        line["manual"] - line["recorded"], line["effect"]
                    )
                }
                for line in model.get("counters", [])
            ],
        }
        if not (
            model.get("participated")
            or changed["xp_changed"]
            or changed["status_changed"]
            or model.get("effects")
            or model.get("equipment_changed")
            or changed["counters"]
            or model.get("note_appended")
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
