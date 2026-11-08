"""Validation, editor preparation and commands shared by schedule transports."""

from dataclasses import asdict, dataclass
from urllib.parse import urlencode
from uuid import uuid4

from django import forms
from django.http import Http404
from django.urls import reverse

from n26.core import cycles
from n26.core import schedule as s
from n26.core.cycle_data import (
    phase_details_from_data,
    ref_data,
    ref_from_data,
    steps_from_data,
)
from n26.core.cycle_display import editor_url, schedule_url
from n26.core.fields import to_ulid
from n26.core.operations import Refusal


class StructuredJSONField(forms.JSONField):
    empty_values = [None, ""]


FIELDS = {
    "setup": ("template_id", "mode", "current_number"),
    "cycle": (
        "target",
        "phase_id",
        "custom_name",
        "starts_on",
        "ends_on",
        "description",
        "effects",
    ),
    "phase": ("phase_id", "name", "description", "effects", "rewards"),
    "duplicate-phase": ("phase_id", "name"),
    "delete-phase": ("phase_id",),
    "plan": ("mode", "steps"),
    "template": ("template_id", "mode"),
    "save-template": ("name",),
    "start": ("expected_current",),
    "advance": ("expected_current",),
    "finish": ("expected_current",),
}
HEADINGS = {
    "setup": "Set up campaign cycles",
    "cycle": "Edit cycle",
    "phase": "Edit phase",
    "duplicate-phase": "Duplicate phase",
    "delete-phase": "Delete phase",
    "plan": "Edit future plan",
    "template": "Apply schedule template",
    "save-template": "Save schedule template",
    "start": "Start campaign",
    "advance": "Advance cycle",
    "finish": "Finish campaign",
}


class CycleEditorForm(forms.Form):
    request_key = forms.UUIDField()
    expected_revision = forms.IntegerField(min_value=0)
    template_id = forms.CharField(max_length=26)
    mode = forms.ChoiceField(choices=[("fixed", "Fixed"), ("repeating", "Repeating")])
    current_number = forms.IntegerField(min_value=1, max_value=1000)
    target = StructuredJSONField()
    phase_id = forms.CharField(max_length=26)
    name = forms.CharField(max_length=200)
    custom_name = forms.CharField(max_length=200, required=False)
    starts_on = forms.DateField(required=False)
    ends_on = forms.DateField(required=False)
    description = forms.CharField(required=False, strip=False, max_length=32000)
    effects = forms.CharField(required=False, strip=False, max_length=32000)
    rewards = StructuredJSONField(required=False)
    steps = StructuredJSONField()
    expected_current = forms.CharField(max_length=26)

    def clean_phase_id(self):
        value = self.cleaned_data["phase_id"]
        try:
            to_ulid(value)
        except ValueError:
            raise forms.ValidationError("Select a valid phase.") from None
        return value

    def __init__(self, action, *args, **kwargs):
        super().__init__(*args, **kwargs)
        keep = set(FIELDS[action]) | {"request_key"}
        if action != "setup":
            keep.add("expected_revision")
        self.fields = {
            name: field for name, field in self.fields.items() if name in keep
        }


@dataclass
class PreparedEditor:
    action: str
    heading: str
    lead: str
    initial: dict
    context: dict
    query: dict
    target: s.CycleRef | None = None


def prepare(campaign, action, query):
    if action not in FIELDS:
        raise Http404("No such schedule action")
    state = cycles.load(campaign)
    if (action == "setup") != (state is None):
        raise Http404("This schedule action is not available")
    initial = {"request_key": str(uuid4())}
    context, canonical, target = {}, {}, None
    lead = ""
    if state is not None:
        initial["expected_revision"] = state.revision
        context["currentName"] = state.current.name
    if action in ("setup", "template"):
        initial.update(template_id="", mode="fixed")
        if action == "setup":
            initial["current_number"] = ""
            lead = "Choose the current cycle. Earlier cycles will be saved without recorded start or end times."
            context["activates"] = campaign.status == "in_progress"
        else:
            lead = f"The new plan begins after Cycle {len(state.cycles)}. Saved cycles keep their identities and order."
    elif action == "cycle":
        try:
            target = (
                s.SavedCycleRef(query["cycle"])
                if query.get("cycle")
                else s.ProjectedCycleRef(
                    s.PlannedPosition(query["plan"], int(query["position"]))
                )
            )
            cycles._bounded_target(state, target)
            selected = s._selected(state, target)
        except KeyError, ValueError, s.ScheduleError, Refusal:
            raise Http404("No such cycle") from None
        canonical = (
            {"cycle": target.cycle_id}
            if isinstance(target, s.SavedCycleRef)
            else {"plan": target.position.plan_id, "position": target.position.index}
        )
        details = (
            selected.details
            if isinstance(selected, s.Cycle)
            else s.CycleDetails(selected.phase_id)
        )
        initial.update(asdict(details), target=ref_data(target))
        initial["custom_name"] = details.custom_name or ""
        for field in ("starts_on", "ends_on"):
            initial[field] = initial[field].isoformat() if initial[field] else ""
        preview = s.preview_cycle_edit(state, target, details)
        if preview.creates:
            first, last = preview.creates[0].order, preview.creates[-1].order
            lead = f"This edit saves Cycle {first} through Cycle {last}. The current cycle remains {state.current.name}."
        else:
            lead = f"Editing {selected.name}. Dates keep its saved position in the schedule."
    elif action in ("phase", "duplicate-phase", "delete-phase"):
        phase_id = query.get("phase")
        phase = next((p for p in state.phases if p.id == phase_id), None)
        if phase is None:
            raise Http404("No such phase")
        canonical = {"phase": phase.id}
        initial["phase_id"] = phase.id
        if action == "phase":
            initial.update(asdict(phase.details))
            lead = "Rewards are stored as settings. Saving them does not give credits or reputation."
        elif action == "duplicate-phase":
            initial["name"] = f"{phase.details.name} copy"[:200]
            lead = "The copy keeps these settings. Existing cycles remain assigned to their phases."
        else:
            lead = f"Delete {phase.details.name}. A phase referenced by saved history cannot be deleted."
    elif action == "plan":
        initial.update(
            mode=state.plan.mode,
            steps=[asdict(step) for step in s.editable_steps(state)],
        )
        lead = f"This plan begins after Cycle {len(state.cycles)}. Changes affect the projected continuation."
    elif action == "save-template":
        initial["name"] = ""
        lead = "Save this plan and its phases as a private reusable template."
    else:
        initial["expected_current"] = state.current_cycle_id
        if action == "advance":
            try:
                preview = s.preview_advance(state)
            except s.ScheduleError:
                raise Http404("This schedule action is not available") from None
            if preview.finishes:
                raise Http404("Finish the campaign after its final cycle")
            context["ending"] = state.current.name
            context["starting"] = preview.following.name
            context["savesNext"] = isinstance(preview.following, s.ProjectedCycle)
            lead = f"End {state.current.name} and start {preview.following.name}. Accepted players will be notified."
        elif action == "start":
            lead = f"Start {state.current.name} and notify accepted players."
        else:
            lead = f"End {state.current.name} and finish the campaign. Its final cycle will remain recorded."
    return PreparedEditor(
        action, HEADINGS[action], lead, initial, context, canonical, target
    )


def recovery_editor(campaign, action, query):
    """Keep the original form shape available for an authorised retained command."""
    state = cycles.load(campaign)
    return PreparedEditor(
        action,
        HEADINGS[action],
        "This action is no longer available. Retry an earlier unconfirmed save, or review the current schedule.",
        {
            "request_key": str(uuid4()),
            "expected_revision": state.revision if state else 0,
            "expected_current": state.current_cycle_id if state else "",
        },
        {"unavailable": True},
        {
            key: query[key]
            for key in ("cycle", "plan", "position", "phase")
            if key in query
        },
    )


@dataclass
class Submission:
    form: CycleEditorForm
    result: cycles.CommandResult | None = None
    conflict: bool = False
    key_conflict: bool = False
    current: dict | None = None


def _query_target(query):
    try:
        return (
            s.SavedCycleRef(query["cycle"])
            if query.get("cycle")
            else s.ProjectedCycleRef(
                s.PlannedPosition(query["plan"], int(query["position"]))
            )
        )
    except KeyError, ValueError:
        raise Refusal("Select a cycle from this campaign schedule.") from None


def perform(campaign, actor, action, data, query):
    form = CycleEditorForm(action, data)
    submitted = Submission(form)
    if not form.is_valid():
        return submitted
    values = form.cleaned_data
    common = {"actor": actor, "request_key": values["request_key"]}
    if action != "setup":
        common["expected_revision"] = values["expected_revision"]
    try:
        if action == "setup":
            result = cycles.configure(
                campaign,
                **common,
                template_id=values["template_id"],
                current_position=values["current_number"] - 1,
                mode=values["mode"],
            )
        elif action == "cycle":
            target = ref_from_data(values["target"])
            expected = _query_target(query)
            if target != expected:
                raise Refusal("The selected cycle changed. Reload the editor.")
            result = cycles.edit_cycle(
                campaign,
                **common,
                target=target,
                details=s.CycleDetails(
                    values["phase_id"],
                    values["custom_name"] or None,
                    values["starts_on"],
                    values["ends_on"],
                    values["description"],
                    values["effects"],
                ),
            )
        elif action in ("phase", "duplicate-phase", "delete-phase"):
            if values["phase_id"] != query.get("phase"):
                raise Refusal("The selected phase changed. Reload the editor.")
            if action == "phase":
                details = phase_details_from_data(
                    {
                        name: (values[name] or {})
                        if name == "rewards"
                        else values[name]
                        for name in ("name", "description", "effects", "rewards")
                    }
                )
                result = cycles.edit_phase(
                    campaign, **common, phase_id=values["phase_id"], details=details
                )
            elif action == "duplicate-phase":
                result = cycles.duplicate_phase(
                    campaign, **common, phase_id=values["phase_id"], name=values["name"]
                )
            else:
                result = cycles.delete_phase(
                    campaign, **common, phase_id=values["phase_id"]
                )
        elif action == "plan":
            result = cycles.replace_plan(
                campaign,
                **common,
                steps=steps_from_data(values["steps"]),
                mode=values["mode"],
            )
        elif action == "template":
            result = cycles.apply_template(
                campaign,
                **common,
                template_id=values["template_id"],
                mode=values["mode"],
            )
        elif action == "save-template":
            result = cycles.save_template(campaign, **common, name=values["name"])
        else:
            command = {
                "advance": cycles.advance,
                "start": cycles.start,
                "finish": cycles.finish,
            }[action]
            result = command(
                campaign, **common, expected_current=values["expected_current"]
            )
        submitted.result = result
    except cycles.CycleKeyConflict as exc:
        submitted.key_conflict = True
        form.add_error(None, exc.public_message)
    except cycles.CycleConflict as exc:
        submitted.conflict = True
        state = cycles.load(campaign)
        submitted.current = {
            "revision": state.revision if state else None,
            "cycle": state.current.name if state else "Cycles are not configured",
            "phase": state.current_phase.details.name if state else "",
        }
        form.add_error(None, exc.public_message)
    except Refusal as exc:
        form.add_error(None, exc.public_message)
    except s.ScheduleError as exc:
        form.add_error(None, str(exc))
    return submitted


def next_url(campaign, action, submitted):
    if submitted.result.cycle_id:
        return reverse(
            "n26-campaign-cycle", args=[campaign.pk, submitted.result.cycle_id]
        )
    url = schedule_url(campaign)
    if action in ("phase", "duplicate-phase"):
        return url + "#phase-" + submitted.form.cleaned_data["phase_id"]
    return url


def editor_props(
    campaign, actor, prepared, form, *, csrf_token, conflict=False, current=None
):
    query = urlencode(prepared.query)
    suffix = "?" + query if query else ""
    values = {}
    for name in form.fields:
        value = form[name].value()
        values[name] = "" if value is None else str(value)
    return {
        "kind": prepared.action,
        "heading": prepared.heading,
        "lead": prepared.lead,
        "context": prepared.context,
        "values": values,
        "errors": {name: list(messages) for name, messages in form.errors.items()},
        "initialConflict": conflict,
        "current": current,
        "templates": [
            {"id": str(t.pk), "name": t.name} for t in cycles.templates_for(actor)
        ],
        "action": editor_url(campaign, prepared.action, **prepared.query),
        "commandHref": reverse("n26-cycle-command", args=[campaign.pk, prepared.action])
        + suffix,
        "csrfToken": csrf_token,
        "recoveryKey": f"cycles:{actor.pk}:{campaign.pk}:{prepared.action}:{query}",
        "back": schedule_url(campaign),
    }
