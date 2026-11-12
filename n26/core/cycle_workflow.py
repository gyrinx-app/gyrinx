"""Validation, editor preparation and commands shared by schedule transports."""

import json
from dataclasses import asdict, dataclass
from datetime import timedelta
from urllib.parse import urlencode
from uuid import uuid4

from django import forms
from django.http import Http404
from django.urls import reverse
from django.utils import timezone

from n26.core import cycles
from n26.core import schedule as s
from n26.core.cycle_data import (
    phase_details_from_data,
    ref_data,
    ref_from_data,
    steps_from_data,
    template_data,
)
from n26.core.cycle_display import editor_url, schedule_url
from n26.core.fields import to_ulid
from n26.core.operations import Refusal


class StructuredJSONField(forms.JSONField):
    empty_values = [None, ""]


CALENDAR_FIELDS = ("date_start", "cycle_interval", "cycle_unit")
DATE_FIELDS = (*CALENDAR_FIELDS, "date_version", "date_mode")
RETIRED_FIELDS = {"template": ("template_id", "mode"), "save-template": ("name",)}
FIELDS = {
    "setup": (
        "template_id",
        "setup_definition",
        "mode",
        "current_number",
        "no_current",
        *DATE_FIELDS,
    ),
    "cycle": (
        "target",
        "phase_id",
        "custom_name",
        "starts_on",
        "ends_on",
        "description",
        "effects",
        "date_version",
        "shift_later",
    ),
    "phase": ("phase_id", "name", "description", "effects", "rewards"),
    "add-phase": ("name", "description", "effects", "rewards"),
    "duplicate-phase": ("phase_id", "name"),
    "delete-phase": ("phase_id", "current_choice"),
    "delete-cycle": ("target", "current_choice"),
    "plan": ("mode", "steps", *DATE_FIELDS),
    "start": ("expected_current",),
    "advance": ("expected_current",),
    "finish": ("expected_current",),
}
HEADINGS = {
    "template": "Confirm earlier template change",
    "save-template": "Confirm earlier template save",
    "setup": "Set up campaign phases & cycles",
    "cycle": "Edit cycle",
    "phase": "Edit phase",
    "add-phase": "Add phase",
    "duplicate-phase": "Duplicate phase",
    "delete-phase": "Delete phase",
    "delete-cycle": "Delete cycle",
    "plan": "Schedule settings",
    "start": "Start campaign",
    "advance": "Advance cycle",
    "finish": "Finish campaign",
}


class CycleEditorForm(forms.Form):
    request_key = forms.UUIDField()
    expected_revision = forms.IntegerField(min_value=0)
    template_id = forms.CharField(max_length=26)
    setup_definition = StructuredJSONField(required=False)
    mode = forms.ChoiceField(choices=[("fixed", "Fixed"), ("repeating", "Repeating")])
    current_number = forms.IntegerField(min_value=1, max_value=1000, required=False)
    no_current = forms.BooleanField(required=False)
    target = StructuredJSONField()
    phase_id = forms.CharField(max_length=26)
    name = forms.CharField(max_length=200)
    custom_name = forms.CharField(max_length=200, required=False)
    starts_on = forms.DateField(required=False)
    ends_on = forms.DateField(required=False)
    shift_later = forms.BooleanField(required=False)
    date_start = forms.DateField(required=False)
    cycle_interval = forms.IntegerField(min_value=1, max_value=520, required=False)
    cycle_unit = forms.ChoiceField(
        choices=[("weeks", "Weeks"), ("months", "Calendar months")], required=False
    )
    date_mode = forms.ChoiceField(
        choices=[("manual", "No planned dates"), ("planned", "Plan cycle dates")],
        required=False,
    )
    # Version 2 lets an empty date pair clear saved dates; older commands preserve them.
    date_version = forms.ChoiceField(choices=[("1", "1"), ("2", "2")], required=False)
    description = forms.CharField(required=False, strip=False, max_length=32000)
    effects = forms.CharField(required=False, strip=False, max_length=32000)
    rewards = StructuredJSONField(required=False)
    steps = StructuredJSONField()
    expected_current = forms.CharField(max_length=26, required=False)
    current_choice = forms.CharField(required=False, max_length=200)

    def clean_current_number(self):
        return self.cleaned_data.get("current_number") or 1

    def clean_phase_id(self):
        value = self.cleaned_data["phase_id"]
        try:
            to_ulid(value)
        except ValueError:
            raise forms.ValidationError("Select a valid phase.") from None
        return value

    def __init__(self, action, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.action = action
        keep = set(FIELDS.get(action, RETIRED_FIELDS.get(action, ()))) | {"request_key"}
        if action != "setup":
            keep.add("expected_revision")
        self.fields = {
            name: field for name, field in self.fields.items() if name in keep
        }
        if action == "setup":
            self.fields["template_id"].required = False
        if (
            action in ("setup", "plan")
            and self.is_bound
            and self.data.get("date_mode") == "manual"
        ):
            for name in CALENDAR_FIELDS:
                self.fields[name].disabled = True
        if (
            action == "setup"
            and self.is_bound
            and forms.BooleanField(required=False).clean(self.data.get("no_current"))
        ):
            self.fields["current_number"].disabled = True

    def clean(self):
        values = super().clean()
        if (
            self.action == "setup"
            and not values.get("template_id")
            and values.get("setup_definition") is None
            and "setup_definition" not in self.errors
        ):
            self.add_error(
                "setup_definition", "Add a phase and a step to your custom schedule."
            )
        required = ()
        if self.action == "cycle":
            if values.get("date_version") == "1" or (
                values.get("date_version") == "2"
                and bool(values.get("starts_on")) != bool(values.get("ends_on"))
            ):
                required = ("starts_on", "ends_on")
        elif self.action in ("setup", "plan"):
            if values.get("date_mode") == "manual":
                for name in CALENDAR_FIELDS:
                    values[name] = None
            elif (
                values.get("date_mode") == "planned"
                or values.get("date_version") == "1"
                or any(values.get(name) for name in CALENDAR_FIELDS)
            ):
                required = CALENDAR_FIELDS
        for name in required:
            if not values.get(name) and name not in self.errors:
                self.add_error(name, "This field is required.")
        return values


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
    heading = HEADINGS[action]
    context, canonical, target = {}, {}, None
    lead = ""
    if state is not None:
        initial["expected_revision"] = state.revision
        context["currentName"] = (
            state.current.name if state.current else "No current cycle"
        )
    if action == "setup":
        initial.update(
            template_id="",
            setup_definition=template_data(
                s.ScheduleTemplate(
                    "Custom",
                    (s.Phase("phase-1", s.PhaseDetails("Phase 1")),),
                    (s.PlanStep("step-1", "phase-1", 1),),
                )
            ),
            mode="fixed",
        )
        context["customDefinition"] = initial["setup_definition"]
        initial["current_number"] = "1"
        initial["no_current"] = False
        initial.update(
            date_start=timezone.localdate().isoformat(),
            cycle_interval=1,
            cycle_unit="weeks",
            date_version="1",
            date_mode="manual",
        )
        lead = "Choose the current cycle and add planning dates if you need them. You advance each cycle when the campaign is ready."
        context["activates"] = campaign.status == "in_progress"
    elif action in ("cycle", "delete-cycle"):
        if query.get("fields") not in (None, "dates"):
            raise Http404("No such cycle editor")
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
        if query.get("fields") == "dates":
            canonical["fields"] = "dates"
            context["datesOnly"] = True
            heading = "Edit cycle dates"
        details = (
            selected.details
            if isinstance(selected, s.Cycle)
            else s.CycleDetails(
                selected.phase_id,
                starts_on=selected.starts_on,
                ends_on=selected.ends_on,
            )
        )
        initial["date_version"] = "2"
        initial["shift_later"] = False
        if state.calendar and details.ends_on:
            context["shiftLater"] = {
                "endsOn": details.ends_on.isoformat(),
            }
        initial.update(asdict(details), target=ref_data(target))
        initial["custom_name"] = details.custom_name or ""
        for field in ("starts_on", "ends_on"):
            initial[field] = initial[field].isoformat() if initial[field] else ""
        preview = s.preview_cycle_edit(state, target, details)
        if preview.creates:
            first, last = preview.creates[0].order, preview.creates[-1].order
            lead = f"This edit saves Cycle {first} through Cycle {last}. " + (
                f"The current cycle remains {state.current.name}."
                if state.current
                else "No cycle will be started."
            )
        else:
            lead = f"Editing {selected.name}. Changing dates does not reorder saved cycles."
        if action == "delete-cycle":
            victims = [selected.id] if isinstance(selected, s.Cycle) else []
            _prepare_deletion(campaign, state, initial, context, victims)
            context["savedCount"] = 1
            context["projectedPrefix"] = len(preview.creates)
            lead = f"Delete {selected.name}."
    elif action == "add-phase":
        initial.update(asdict(s.PhaseDetails("New phase")))
        lead = "Add a phase, then choose its cycles in Schedule settings."
    elif action in ("phase", "duplicate-phase", "delete-phase"):
        phase_id = query.get("phase")
        phase = next(
            (p for p in state.phases if p.id == phase_id and not p.archived), None
        )
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
            victims = [
                c.id
                for c in state.cycles
                if not c.archived and c.details.phase_id == phase.id
            ]
            _prepare_deletion(
                campaign, state, initial, context, victims, phase_id=phase.id
            )
            context["futureCount"] = sum(
                step.count
                for step in s.editable_steps(state)
                if step.phase_id == phase.id
            )
            context["repeating"] = state.plan.mode == "repeating"
            lead = f"Delete {phase.details.name} and all its cycles from the campaign schedule, including every future occurrence."
    elif action == "plan":
        initial.update(
            mode=state.plan.mode,
            steps=[asdict(step) for step in s.editable_steps(state)],
        )
        calendar = state.calendar
        initial.update(
            date_version="1",
            date_mode="planned" if calendar else "manual",
            cycle_interval=calendar.interval if calendar else 1,
            cycle_unit=calendar.unit if calendar else "weeks",
            date_start=calendar.dates_for(len(state.cycles) + 1)[0].isoformat()
            if calendar
            else "",
        )
        if calendar:
            latest_end = max(
                (
                    cycle.details.ends_on
                    for cycle in state.cycles
                    if cycle.details.ends_on
                ),
                default=None,
            )
            initial["date_start"] = max(
                calendar.dates_for(len(state.cycles) + 1)[0],
                latest_end + timedelta(days=1)
                if latest_end
                else calendar.dates_for(len(state.cycles) + 1)[0],
            ).isoformat()
        context["needsDates"] = calendar is None
        context["nextCycleNumber"] = len(state.cycles) + 1
        context["patternSteps"] = [asdict(step) for step in state.plan.steps]
        context["fixedSteps"] = [asdict(step) for step in s.fixed_steps(state)]
        context["startsAfterOrder"] = len(state.cycles)
        lead = "The steps below set future cycles. Existing cycles keep their dates and phases."
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
            lead = f"End {state.current.name} and start {preview.following.name}. This will send notifications to players participating in the campaign."
        elif action == "start":
            if state.status == "in_progress" and state.current is None:
                heading = "Start first cycle"
            first = state.current or next(
                (c for c in state.cycles if not c.archived), None
            )
            lead = f"Start {first.name if first else 'Cycle 1'}. This will send notifications to players participating in the campaign."
        else:
            lead = (
                f"End {state.current.name} and finish the campaign. Its final cycle will remain recorded."
                if state.current
                else "Finish the campaign without starting a cycle."
            )
    return PreparedEditor(action, heading, lead, initial, context, canonical, target)


def _prepare_deletion(campaign, state, initial, context, victims, *, phase_id=None):
    from n26.core.models import Battle

    initial["current_choice"] = ""
    context["savedCount"] = len(victims)
    context["battleCount"] = Battle.objects.filter(
        campaign=campaign, cycle_id__in=victims
    ).count()
    context["replacesCurrent"] = state.current_cycle_id in victims
    choices = []
    if context["replacesCurrent"]:
        for cycle in (*state.cycles, *s.project(state, limit=12)):
            saved = isinstance(cycle, s.Cycle)
            cycle_phase = cycle.details.phase_id if saved else cycle.phase_id
            if (
                saved and (cycle.archived or cycle.id in victims)
            ) or cycle_phase == phase_id:
                continue
            choices.append(
                {
                    "value": json.dumps(
                        ref_data(s.SavedCycleRef(cycle.id) if saved else cycle.ref)
                    ),
                    "label": f"{cycle.name} · {s._phase(state, cycle_phase).details.name}",
                }
            )
    context["currentChoices"] = choices


def recovery_editor(campaign, action, query):
    """Keep the original form shape available for an authorised retained command."""
    state = cycles.load(campaign)
    return PreparedEditor(
        action,
        "Edit cycle dates"
        if action == "cycle" and query.get("fields") == "dates"
        else HEADINGS[action],
        "This action is no longer available. Retry an earlier unconfirmed save, or review the current schedule.",
        {
            "request_key": str(uuid4()),
            "expected_revision": state.revision if state else 0,
            "expected_current": state.current_cycle_id if state else "",
        },
        {
            "unavailable": True,
            "datesOnly": action == "cycle" and query.get("fields") == "dates",
        },
        {
            key: query[key]
            for key in ("cycle", "plan", "position", "phase", "fields")
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


def _deletion_choice(values):
    choice = values.get("current_choice", "")
    if not choice:
        return {}
    if choice == "none":
        return {"no_current": True}
    try:
        return {"replacement": ref_from_data(json.loads(choice))}
    except ValueError, s.ScheduleError:
        raise Refusal(
            "Choose a replacement current cycle or No current cycle."
        ) from None


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
        calendar = (
            s.CycleCalendar(
                values["date_start"], values["cycle_interval"], values["cycle_unit"]
            )
            if values.get("date_start")
            else None
        )
        if action == "setup":
            result = cycles.configure(
                campaign,
                **common,
                template_id=values["template_id"],
                current_position=None
                if values["no_current"]
                else values["current_number"] - 1,
                mode=values["mode"],
                calendar=calendar,
                definition=values["setup_definition"],
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
                shift_later=values["shift_later"],
                clear_dates=values.get("date_version") == "2"
                and not values["starts_on"]
                and not values["ends_on"],
            )
        elif action == "add-phase":
            details = phase_details_from_data(
                {
                    name: values[name] or {} if name == "rewards" else values[name]
                    for name in ("name", "description", "effects", "rewards")
                }
            )
            result = cycles.add_phase(campaign, **common, details=details)
        elif action == "delete-cycle":
            target = ref_from_data(values["target"])
            if target != _query_target(query):
                raise Refusal("The selected cycle changed. Reload the confirmation.")
            result = cycles.delete_cycle(
                campaign, **common, target=target, **_deletion_choice(values)
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
                    campaign,
                    **common,
                    phase_id=values["phase_id"],
                    **_deletion_choice(values),
                )
        elif action in RETIRED_FIELDS:
            inputs = (
                {"name": values["name"]}
                if action == "save-template"
                else {"template": values["template_id"], "mode": values["mode"]}
            )
            result = cycles.replay_template_command(
                campaign,
                actor=actor,
                kind="save_template" if action == "save-template" else "apply_template",
                inputs=inputs,
                expected_revision=values["expected_revision"],
                request_key=values["request_key"],
            )
        elif action == "plan":
            result = cycles.replace_plan(
                campaign,
                **common,
                steps=steps_from_data(values["steps"]),
                mode=values["mode"],
                calendar=calendar,
                clear_calendar=values.get("date_mode") == "manual",
                future_dates=values.get("date_mode") == "planned",
            )
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
            "cycle": state.current.name
            if state and state.current
            else "No current cycle"
            if state
            else "Cycles are not configured",
            "phase": state.current_phase.details.name
            if state and state.current_phase
            else "",
        }
        form.add_error(None, exc.public_message)
    except Refusal as exc:
        form.add_error(None, exc.public_message)
    except s.ScheduleError as exc:
        form.add_error(None, str(exc))
    return submitted


def next_url(campaign, action, submitted):
    if submitted.result.cycle_id:
        from n26.core.cycle_display import SAVED_PAGE_SIZE
        from n26.core.models import CampaignCycle

        order = CampaignCycle.objects.values_list("order", flat=True).get(
            campaign=campaign, pk=submitted.result.cycle_id
        )
        ordinal = CampaignCycle.objects.filter(
            campaign=campaign, archived=False, order__lte=order
        ).count()
        page = (ordinal - 1) // SAVED_PAGE_SIZE + 1
        return (
            schedule_url(campaign) + f"?page={page}#cycle-" + submitted.result.cycle_id
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
            {"id": str(t.pk), "name": t.name, "definition": t.definition}
            for t in cycles.templates_for(actor)
        ]
        if prepared.action == "setup"
        else [],
        "action": editor_url(campaign, prepared.action, **prepared.query),
        "commandHref": reverse("n26-cycle-command", args=[campaign.pk, prepared.action])
        + suffix,
        "csrfToken": csrf_token,
        "recoveryKey": f"cycles:{actor.pk}:{campaign.pk}:{prepared.action}:{query}",
        "back": schedule_url(campaign),
    }
