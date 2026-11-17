"""Validation, editor preparation and commands shared by schedule transports."""

import json
from collections import Counter
from dataclasses import asdict, dataclass, replace
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
    template_from_data,
)
from n26.core.cycle_display import editor_url, schedule_url
from n26.core.fields import to_ulid
from n26.core.operations import Refusal


class StructuredJSONField(forms.JSONField):
    empty_values = [None, ""]


CALENDAR_FIELDS = ("date_start", "cycle_interval", "cycle_unit")
DATE_FIELDS = (*CALENDAR_FIELDS, "date_mode")
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
        "shift_later",
    ),
    "add-cycle": (
        "occurrence_id",
        "after_cycle_id",
        "custom_name",
        "starts_on",
        "ends_on",
        "description",
        "effects",
    ),
    "move-cycle": ("cycle_id", "occurrence_id", "after_cycle_id"),
    "duplicate-cycle": ("cycle_id", "occurrence_id", "after_cycle_id", "clear_dates"),
    "move-phase": ("occurrence_id", "after_occurrence_id"),
    "phase": ("phase_id", "name", "description", "effects", "rewards"),
    "add-phase": ("name", "description", "effects", "rewards", "after_occurrence_id"),
    "duplicate-phase": ("phase_id", "name", "after_occurrence_id", "clear_dates"),
    "delete-phase": ("phase_id", "current_choice"),
    "delete-cycle": ("target", "current_choice"),
    "plan": ("mode", "steps", *DATE_FIELDS),
    "pattern": ("steps",),
    "plan-cycles": ("pattern_count",),
    "start": ("expected_current", "start_target"),
    "advance": ("expected_current",),
    "finish": ("expected_current",),
}
HEADINGS = {
    "template": "Confirm earlier template change",
    "save-template": "Confirm earlier template save",
    "setup": "Set up campaign phases & cycles",
    "cycle": "Edit cycle",
    "add-cycle": "Add cycle",
    "move-cycle": "Move cycle",
    "duplicate-cycle": "Duplicate cycle",
    "move-phase": "Move phase",
    "phase": "Edit phase",
    "add-phase": "Add phase",
    "duplicate-phase": "Duplicate phase",
    "delete-phase": "Delete phase",
    "delete-cycle": "Delete cycle",
    "plan": "Settings",
    "pattern": "Edit repeating pattern",
    "plan-cycles": "Add cycles from pattern",
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
    occurrence_id = forms.CharField(max_length=26)
    cycle_id = forms.CharField(max_length=26)
    after_cycle_id = forms.CharField(max_length=26, required=False)
    after_occurrence_id = forms.CharField(max_length=26, required=False)
    clear_dates = forms.BooleanField(required=False)
    pattern_count = forms.IntegerField(min_value=1, max_value=1000)
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
    )
    description = forms.CharField(required=False, strip=False, max_length=32000)
    effects = forms.CharField(required=False, strip=False, max_length=32000)
    rewards = StructuredJSONField(required=False)
    steps = StructuredJSONField()
    expected_current = forms.CharField(max_length=26, required=False)
    current_choice = forms.CharField(required=False, max_length=200)
    start_target = StructuredJSONField(required=False)

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
        for name in (
            "occurrence_id",
            "cycle_id",
            "after_cycle_id",
            "after_occurrence_id",
        ):
            if values.get(name):
                try:
                    to_ulid(values[name])
                except ValueError:
                    self.add_error(name, "Choose an entry from this campaign timeline.")
        required = ()
        if self.action in ("setup", "plan"):
            if values.get("date_mode") == "manual":
                for name in CALENDAR_FIELDS:
                    values[name] = None
            elif values.get("date_mode") == "planned":
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


def _occurrence(state, identity):
    active = [o for o in state.occurrences if not o.archived]
    selected = next((o for o in active if o.id == identity), None)
    if selected is None:
        # Earlier links used the definition identity rather than a block identity.
        matches = [o for o in active if o.phase_id == identity]
        selected = matches[0] if len(matches) == 1 else None
    if selected is None:
        raise Http404("No such phase block")
    return selected


def _timeline_context(state):
    return [
        {
            "id": occurrence.id,
            "number": occurrence.position,
            "name": s._phase(state, occurrence.phase_id).details.name,
            "cycles": [
                {"id": c.id, "name": c.name, "order": c.order}
                for c in state.cycles
                if not c.archived and c.occurrence_id == occurrence.id
            ],
        }
        for occurrence in state.occurrences
        if not occurrence.archived
    ]


def _used_cycle(state, cycle):
    return cycle.id in state.protected_cycle_ids or bool(
        state.current and cycle.order <= state.current.order
    )


def _selected_cycle_context(cycle):
    return {
        "id": cycle.id,
        "name": cycle.name,
        "order": cycle.order,
        "occurrenceId": cycle.occurrence_id,
    }


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
        context["timelineOccurrences"] = _timeline_context(state)
        context["definitionPhases"] = [
            {
                "id": phase.id,
                "phaseId": phase.id,
                "name": phase.details.name,
                "description": phase.details.description,
                "effects": phase.details.effects,
                "rewards": asdict(phase.details.rewards),
                "count": 0,
                "editHref": "",
                "duplicateHref": "",
                "deleteHref": "",
            }
            for phase in state.phases
            if not phase.archived
        ]
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
            date_mode="manual",
        )
        lead = "Choose phases and plan their cycles."
        context["activates"] = campaign.status == "in_progress"
    elif action == "plan-cycles":
        if state.plan.mode != "repeating":
            raise Http404("This schedule has no repeating pattern")
        upcoming = s.project(replace(state, calendar=None), limit=1)[0]
        step = next(
            step for step in state.plan.steps if step.id == upcoming.source.step_id
        )
        initial["pattern_count"] = min(
            cycles.MAX_PREFIX, step.count - upcoming.source.offset
        )
        context["firstUpcoming"] = {
            "name": f"Cycle {sum(not c.archived for c in state.cycles) + 1}",
            "phase": s._phase(state, upcoming.phase_id).details.name,
        }
        lead = "Add upcoming cycles from the repeating pattern to your timeline."
    elif action == "add-cycle":
        occurrence = _occurrence(state, query.get("phase"))
        canonical = {"phase": occurrence.id}
        children = [
            c
            for c in state.cycles
            if not c.archived and c.occurrence_id == occurrence.id
        ]
        initial.update(
            occurrence_id=occurrence.id,
            after_cycle_id=children[-1].id if children else "",
            custom_name="",
            starts_on="",
            ends_on="",
            description="",
            effects="",
        )
        context["definitionPhaseId"] = occurrence.phase_id
        lead = "Add a cycle to this phase block. Saving does not start it."
    elif action in ("move-cycle", "duplicate-cycle"):
        selected = next(
            (c for c in state.cycles if not c.archived and c.id == query.get("cycle")),
            None,
        )
        if selected is None:
            raise Http404("No such cycle")
        canonical = {"cycle": selected.id}
        context["selectedCycle"] = _selected_cycle_context(selected)
        siblings = [
            c
            for c in state.cycles
            if not c.archived and c.occurrence_id == selected.occurrence_id
        ]
        index = siblings.index(selected)
        initial.update(
            cycle_id=selected.id,
            occurrence_id=selected.occurrence_id,
            after_cycle_id=selected.id
            if action == "duplicate-cycle"
            else siblings[index - 1].id
            if index
            else "",
        )
        if action == "duplicate-cycle":
            initial["clear_dates"] = True
            lead = f"Copy {selected.name}. You can change the copy separately."
        else:
            lead = f"Move {selected.name}. Its dates and other settings are kept."
    elif action == "move-phase":
        occurrence = _occurrence(state, query.get("phase"))
        canonical = {"phase": occurrence.id}
        ordered = [o for o in state.occurrences if not o.archived]
        index = ordered.index(occurrence)
        initial.update(
            occurrence_id=occurrence.id,
            after_occurrence_id=ordered[index - 1].id if index else "",
        )
        lead = "Move this phase block together with its cycles. Existing dates must fit the new position."
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
        if isinstance(selected, s.Cycle):
            context["selectedCycle"] = _selected_cycle_context(selected)
        initial["shift_later"] = False
        initial.update(asdict(details), target=ref_data(target))
        initial["custom_name"] = details.custom_name or ""
        for field in ("starts_on", "ends_on"):
            initial[field] = initial[field].isoformat() if initial[field] else ""
        preview = s.preview_cycle_edit(state, target, details)
        if preview.following_on:
            context["shiftLater"] = {
                "endsOn": details.ends_on.isoformat() if details.ends_on else "",
                "followingOn": preview.following_on.isoformat(),
            }
        lead = f"Edit the dates and details for {selected.name}."
        if action == "delete-cycle":
            victims = [selected.id] if isinstance(selected, s.Cycle) else []
            _prepare_deletion(campaign, state, initial, context, victims)
            context["savedCount"] = 1
            context["projectedPrefix"] = len(preview.creates)
            lead = f"Delete {selected.name}."
    elif action == "add-phase":
        initial.update(asdict(s.PhaseDetails("New phase")))
        ordered = [o for o in state.occurrences if not o.archived]
        if "after" in query:
            after = query["after"]
            if not any(o.id == after for o in ordered):
                raise Http404("No such insertion point")
            canonical = {"after": after}
            initial["after_occurrence_id"] = after
        else:
            initial["after_occurrence_id"] = ordered[-1].id if ordered else ""
        lead = "Add a phase block, then add its cycles to the timeline."
    elif action in ("phase", "duplicate-phase", "delete-phase"):
        raw_identity = query.get("phase")
        occurrence = _occurrence(state, raw_identity)
        phase = s._phase(state, occurrence.phase_id)
        canonical = {"phase": raw_identity}
        initial["phase_id"] = raw_identity
        context["definitionPhaseId"] = phase.id
        children = [
            c
            for c in state.cycles
            if not c.archived and c.occurrence_id == occurrence.id
        ]
        if action == "phase":
            frontier = max(
                (c.order for c in children if _used_cycle(state, c)), default=0
            )
            used = [c for c in children if c.order <= frontier]
            future = [c for c in children if c.order > frontier]
            current_block = next(
                (
                    o
                    for o in state.occurrences
                    if state.current and o.id == state.current.occurrence_id
                ),
                None,
            )
            if (used and not future) or (
                not children
                and current_block
                and occurrence.position <= current_block.position
            ):
                raise Http404("This phase has no unused future cycles to edit")
            initial.update(asdict(phase.details))
            context["splitOccurrence"] = bool(used)
            lead = (
                "Changes apply to the unused future cycles in this phase. Recorded cycles keep their rules."
                if used
                else "Rewards are stored as settings. Saving them does not give credits or reputation."
            )
        elif action == "duplicate-phase":
            initial["name"] = f"{phase.details.name} copy"[:200]
            ordered = [o for o in state.occurrences if not o.archived]
            initial["after_occurrence_id"] = ordered[-1].id if ordered else ""
            initial["clear_dates"] = True
            lead = "The copy is added after the last phase block, with its own rules and cycles."
        else:
            _prepare_deletion(
                campaign, state, initial, context, [c.id for c in children]
            )
            context.update(futureCount=0, repeating=False, occurrenceOnly=True)
            lead = f"Delete this {phase.details.name} phase block and its unused cycles from the campaign schedule."
    elif action == "pattern":
        if state.plan.mode != "repeating":
            raise Http404("This campaign has a fixed plan")
        initial["steps"] = [asdict(step) for step in state.plan.steps]
        lead = "Choose the cycle steps to repeat after the cycles on your timeline."
    elif action == "plan":
        frontier = s.calendar_boundary(state)
        initial.update(
            mode=state.plan.mode,
            steps=[asdict(step) for step in s.editable_steps(state)],
        )
        calendar = state.calendar
        first_default = s.calendar_defaults_start(state)
        first_date = first_default.isoformat() if first_default else ""
        initial.update(
            date_mode="planned" if calendar else "manual",
            cycle_interval=calendar.interval if calendar else 1,
            cycle_unit=calendar.unit if calendar else "weeks",
            date_start=first_date,
        )
        context["needsDates"] = calendar is None
        context["nextCycleNumber"] = frontier + 1
        context["patternSteps"] = [asdict(step) for step in state.plan.steps]
        context["fixedSteps"] = [asdict(step) for step in s.fixed_steps(state)]
        context["startsAfterOrder"] = frontier
        context["savedStepCounts"] = dict(
            Counter(cycle.source.step_id for cycle in state.cycles)
        )
        context["originalMode"] = state.plan.mode
        remaining = (
            (state.plan.length - state.next_position % state.plan.length)
            % state.plan.length
            if state.next_position
            else state.plan.length
        )
        context["fixedEndpoint"] = sum(not c.archived for c in state.cycles) + (
            remaining
            if state.plan.mode == "repeating"
            else state.plan.length - state.next_position
        )
        lead = "Set the campaign length and default cycle dates. Edit phases and cycles on the timeline."
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
            if state.current is None and (
                any(c.archived for c in state.cycles)
                or any(p.archived for p in state.phases)
            ):
                heading = "Start cycle"
                context["selectStart"] = True
                context["startChoices"] = _available_cycle_choices(state)
                lead = "Choose the cycle to start. This will send notifications to players participating in the campaign."
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
    context["currentChoices"] = (
        _available_cycle_choices(state, victims, phase_id=phase_id)
        if context["replacesCurrent"]
        else []
    )


def _available_cycle_choices(state, victims=(), *, phase_id=None):
    choices = []
    continuation = s.PlanContinuation(
        state.plan,
        state.next_position,
        saved_count=sum(not c.archived for c in state.cycles),
    )
    for cycle in (*state.cycles, *s.project(continuation, limit=cycles.MAX_PREFIX)):
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
    return choices


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
            for key in ("cycle", "plan", "position", "phase", "fields", "after")
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
            )
        elif action in ("add-cycle", "move-cycle", "duplicate-cycle", "move-phase"):
            operation = {
                "add-cycle": "insert_cycle",
                "move-cycle": "move_cycle",
                "duplicate-cycle": "duplicate_cycle",
                "move-phase": "move_occurrence",
            }[action]
            arguments = {}
            if action == "move-phase":
                if values["occurrence_id"] != query.get("phase"):
                    raise Refusal("The selected phase changed. Reload the editor.")
                arguments.update(
                    occurrence_id=values["occurrence_id"],
                    after_occurrence_id=values["after_occurrence_id"] or None,
                )
            else:
                arguments["occurrence_id"] = values["occurrence_id"]
                if action == "add-cycle":
                    if values["occurrence_id"] != query.get("phase"):
                        raise Refusal("The selected phase changed. Reload the editor.")
                    arguments["details"] = s.CycleDetails(
                        values["occurrence_id"],
                        values["custom_name"] or None,
                        values["starts_on"],
                        values["ends_on"],
                        values["description"],
                        values["effects"],
                    )
                else:
                    if values["cycle_id"] != query.get("cycle"):
                        raise Refusal("The selected cycle changed. Reload the editor.")
                    arguments["cycle_id"] = values["cycle_id"]
                if action != "duplicate-cycle" or "after_cycle_id" in data:
                    arguments["after_cycle_id"] = values["after_cycle_id"] or None
                if action == "duplicate-cycle" and "clear_dates" in data:
                    arguments["clear_dates"] = values["clear_dates"]
            result = cycles.author_timeline(
                campaign, **common, action=operation, **arguments
            )
        elif action == "add-phase":
            if "after" in query and values["after_occurrence_id"] != query["after"]:
                raise Refusal("The insertion point changed. Reload the editor.")
            details = phase_details_from_data(
                {
                    name: (values[name] or {}) if name == "rewards" else values[name]
                    for name in ("name", "description", "effects", "rewards")
                }
            )
            placement = (
                {"after_occurrence_id": values["after_occurrence_id"] or None}
                if "after_occurrence_id" in data
                else {}
            )
            result = cycles.author_timeline(
                campaign,
                **common,
                action="insert_occurrence",
                details=details,
                receipt_inputs={
                    "details": asdict(details),
                    **(
                        {"after_occurrence": placement["after_occurrence_id"]}
                        if placement
                        else {}
                    ),
                },
                **placement,
            )
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
            arguments = {"occurrence_id": values["phase_id"]}
            if action == "phase":
                operation = "edit_occurrence"
                arguments["details"] = phase_details_from_data(
                    {
                        name: (values[name] or {})
                        if name == "rewards"
                        else values[name]
                        for name in ("name", "description", "effects", "rewards")
                    }
                )
            elif action == "duplicate-phase":
                operation = "duplicate_occurrence"
                arguments["name"] = values["name"]
                if "after_occurrence_id" in data:
                    arguments["after_occurrence_id"] = (
                        values["after_occurrence_id"] or None
                    )
                if "clear_dates" in data:
                    arguments["clear_dates"] = values["clear_dates"]
            else:
                operation = "remove_occurrence"
                choice = _deletion_choice(values)
                arguments["receipt_inputs"] = {
                    "phase": values["phase_id"],
                    **cycles._deletion_inputs(
                        choice.get("replacement"), choice.get("no_current", False)
                    ),
                }
            if action == "phase":
                arguments["receipt_inputs"] = {
                    "phase": values["phase_id"],
                    "details": asdict(arguments["details"]),
                }
            elif action == "duplicate-phase":
                arguments["receipt_inputs"] = {
                    "phase": values["phase_id"],
                    "name": values["name"],
                    **(
                        {"after_occurrence": arguments["after_occurrence_id"]}
                        if "after_occurrence_id" in arguments
                        else {}
                    ),
                    **(
                        {"clear_dates": arguments["clear_dates"]}
                        if "clear_dates" in arguments
                        else {}
                    ),
                }
            result = cycles.author_timeline(
                campaign, **common, action=operation, **arguments
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
        elif action == "pattern":
            result = cycles.replace_plan(
                campaign,
                **common,
                steps=steps_from_data(values["steps"]),
                mode="repeating",
            )
        elif action == "plan-cycles":
            result = cycles.plan_cycles(
                campaign, **common, count=values["pattern_count"]
            )
        elif action == "plan":
            result = cycles.replace_plan(
                campaign,
                **common,
                steps=steps_from_data(values["steps"]),
                mode=values["mode"],
                calendar=calendar,
                clear_calendar=values.get("date_mode") == "manual",
            )
        else:
            command = {
                "advance": cycles.advance,
                "start": cycles.start,
                "finish": cycles.finish,
            }[action]
            result = command(
                campaign,
                **common,
                expected_current=values["expected_current"],
                **(
                    {"target": ref_from_data(values["start_target"])}
                    if action == "start" and values.get("start_target")
                    else {}
                ),
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


PHASE_ACTIONS = {"phase", "add-phase", "duplicate-phase", "delete-phase", "move-phase"}


def editor_back(campaign, action):
    return schedule_url(campaign)


def next_url(campaign, action, submitted):
    if action == "move-phase":
        from n26.core.cycle_display import SAVED_PAGE_SIZE
        from n26.core.models import CampaignCycle

        occurrence_id = submitted.form.cleaned_data["occurrence_id"]
        saved = CampaignCycle.objects.filter(campaign=campaign, archived=False)
        first_order = (
            saved.filter(phase_occurrence_id=occurrence_id)
            .order_by("order")
            .values_list("order", flat=True)
            .first()
        )
        ordinal = saved.filter(order__lte=first_order).count() if first_order else 1
        page = (ordinal - 1) // SAVED_PAGE_SIZE + 1
        return schedule_url(campaign) + f"?page={page}#phase-{occurrence_id}"
    if action in PHASE_ACTIONS:
        return editor_back(campaign, action)
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
        "context": {
            **prepared.context,
            **(
                {"planRecoveryKey": f"cycles:{actor.pk}:{campaign.pk}:plan:"}
                if prepared.action == "delete-phase"
                else {}
            ),
        },
        "values": values,
        "errors": {name: list(messages) for name, messages in form.errors.items()},
        "initialConflict": conflict,
        "current": current,
        "templates": [
            {
                "id": str(t.pk),
                "name": t.name,
                "definition": template_data(template_from_data(t.name, t.definition)),
            }
            for t in cycles.templates_for(actor)
        ]
        if prepared.action == "setup"
        else [],
        "action": editor_url(campaign, prepared.action, **prepared.query),
        "commandHref": reverse("n26-cycle-command", args=[campaign.pk, prepared.action])
        + suffix,
        "csrfToken": csrf_token,
        "recoveryKey": f"cycles:{actor.pk}:{campaign.pk}:{prepared.action}:{query}",
        "back": editor_back(campaign, prepared.action),
    }
