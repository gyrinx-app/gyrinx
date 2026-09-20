"""Save working results, then apply one reviewed contribution to a gang's story.

Draft revisions protect concurrent editors. Applied revisions keep the submitted
contribution and its exact occurrences, so correcting XP or income never resets
the gang's later earnings or spending.
"""

import json
from collections import defaultdict
from contextlib import contextmanager
from copy import deepcopy
from dataclasses import asdict, dataclass, field, replace
from hashlib import sha256
from uuid import UUID, uuid4

from django.apps import apps
from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from n26.core.battle_permissions import may_record_gang
from n26.core.card import Node, build_gang_card, build_modifier_index, carriers
from n26.core.counter_tracking import is_active
from n26.core.effects import compute, compute_gang, counter_readings
from n26.core.models import Assignment, Battle, Campaign, Gang, LedgerEvent, Miniature
from n26.core.models.assignment import ASSIGNABLE_FIELDS
from n26.core.models.post_battle import PostBattleReport, PostBattleRevision
from n26.core.operations import Refusal, operation, subtree
from n26.core.owned import is_detachable, is_possession
from n26.core.render import build_choice_offer
from n26.core.status import Status, label_for
from n26.library.models import Counter, Pickable, Slot
from n26.library.models.modifier import OpChangesCounter, OpSetsStatus
from n26.library.standard_content import XP_COUNTER
from n26.write_pause import write_guard


@dataclass(frozen=True)
class Option:
    value: str
    label: str


@dataclass
class ChoiceQuestion:
    key: str
    label: str
    options: list[Option]
    selected: list[str]
    min_picks: int
    max_picks: int

    @property
    def multiple(self):
        return self.max_picks > 1


@dataclass
class EffectSlot:
    key: str
    label: str
    options: list[Option]


@dataclass
class EffectResult:
    id: str
    name: str
    slot: str
    pick: str
    questions: list[ChoiceQuestion] = field(default_factory=list)
    statuses: list[str] = field(default_factory=list)


@dataclass
class ModelResult:
    id: str
    name: str
    status: str
    status_label: str
    xp_before: int
    xp_after: int
    xp_change: int
    xp_assignment_id: str | None
    xp_available: bool
    is_vehicle: bool = False
    effect_slots: list[EffectSlot] = field(default_factory=list)
    effects: list[EffectResult] = field(default_factory=list)
    final_status: str = ""
    equipment_names: list[str] = field(default_factory=list)
    equipment_disposition: str = "keep"
    equipment_changed: bool = False
    equipment_affected_names: list[str] = field(default_factory=list)
    equipment_exclusions: list[str] = field(default_factory=list)
    errors: list[str] = field(default_factory=list)
    participated: bool = False


@dataclass
class PostBattlePlan:
    valid: bool
    errors: list[str]
    models: list[ModelResult]
    credits_before: int | None
    credits_after: int | None
    credits_change: int
    review: str
    inputs: dict
    # Resolved objects are private execution data, never template inputs.
    _writes: list = field(default_factory=list, repr=False)
    _removals: list = field(default_factory=list, repr=False)
    _status_writes: dict = field(default_factory=dict, repr=False)
    _equipment: dict = field(default_factory=dict, repr=False)
    _retained: dict = field(default_factory=dict, repr=False)


def can_edit_report(report, actor):
    return may_record_gang(
        gang=report.gang,
        actor=actor,
        campaign=report.battle.campaign if report.battle_id else None,
    ) and (
        not report.battle_id or report.battle.gangs.filter(pk=report.gang_id).exists()
    )


def _require_editor(report, actor):
    if not can_edit_report(report, actor):
        raise Refusal(
            "Only this gang's owner or its current arbitrator can record these results."
        )


@contextmanager
def _locked(gang, battle=None, report=None):
    """Use the same campaign, gang, battle order as campaign administration."""
    with transaction.atomic(), write_guard():
        if battle is not None:
            Campaign.objects.select_for_update(no_key=True).get(pk=battle.campaign_id)
        gang = Gang.objects.select_for_update().get(pk=gang.pk)
        if battle is not None:
            battle = (
                Battle.objects.select_for_update()
                .select_related("campaign")
                .get(pk=battle.pk)
            )
        if report is not None:
            report = PostBattleReport.objects.select_for_update().get(pk=report.pk)
            report.gang = gang
            report.battle = battle
        yield gang, battle, report


def _uuid(value, label):
    try:
        return UUID(str(value))
    except ValueError, TypeError, AttributeError:
        raise Refusal(
            f"{label} is missing or invalid. Reload this page and try again."
        ) from None


def _draft(payload):
    try:
        encoded = json.dumps(payload, allow_nan=False)
    except TypeError, ValueError:
        raise Refusal("This draft contains a value that cannot be saved.") from None
    if not isinstance(payload, dict) or len(encoded) > 262144:
        raise Refusal("This draft is too large or is not a report.")
    return deepcopy(payload)


def start_report(
    gang, *, actor, battle=None, request_key, date=None, reference="", payload=None
):
    request_key = _uuid(request_key, "The request reference")
    with _locked(gang, battle) as (gang, battle, _):
        candidate = PostBattleReport(gang=gang, battle=battle)
        _require_editor(candidate, actor)
        if battle is not None and not battle.gangs.filter(pk=gang.pk).exists():
            raise Refusal("This gang is not a participant in this battle.")
        existing = PostBattleReport.objects.filter(
            gang=gang, request_key=request_key
        ).first()
        if existing is not None:
            if existing.battle_id != (battle.pk if battle else None):
                raise Refusal("That request reference belongs to a different report.")
            return existing
        if battle is not None:
            existing = PostBattleReport.objects.filter(gang=gang, battle=battle).first()
            if existing is not None:
                return existing
        return PostBattleReport.objects.create(
            gang=gang,
            battle=battle,
            creator=actor,
            last_editor=actor,
            request_key=request_key,
            date=date or (battle.date if battle else timezone.localdate()),
            reference=str(reference).strip()[:200],
            draft=_draft(payload or {}),
        )


def _check_version(report, generation, revision):
    if report.state != PostBattleReport.State.DRAFT:
        raise Refusal(
            "These results have already been applied. Open a correction to change them."
        )
    if str(report.generation) != str(generation) or report.draft_revision != revision:
        raise Refusal(
            "This draft changed in another tab. Reload it before saving your changes."
        )


def save_draft(report, *, actor, generation, revision, payload):
    payload = _draft(payload)
    with _locked(report.gang, report.battle, report) as (_, _, report):
        _require_editor(report, actor)
        _check_version(report, generation, revision)
        report.draft = payload
        report.draft_revision += 1
        report.last_editor = actor
        report.save(
            update_fields=["draft", "draft_revision", "last_editor", "modified"]
        )
        return report


def start_correction(report, *, actor):
    with _locked(report.gang, report.battle, report) as (_, _, report):
        _require_editor(report, actor)
        if report.state == PostBattleReport.State.DRAFT:
            return report
        report.draft = deepcopy(
            report.revisions.get(sequence=report.latest_sequence).inputs
        )
        report.generation = uuid4()
        report.draft_revision = 0
        report.state = PostBattleReport.State.DRAFT
        report.last_editor = actor
        report.save(
            update_fields=[
                "draft",
                "generation",
                "draft_revision",
                "state",
                "last_editor",
                "modified",
            ]
        )
        return report


def _integer(value, label, errors):
    try:
        number = int(value or 0)
        if (
            isinstance(value, bool)
            or str(value or 0).strip() != str(number)
            or not 0 <= number <= 1000000
        ):
            raise ValueError
        return number
    except TypeError, ValueError:
        errors.append(f"Enter a whole number from 0 to 1,000,000 for {label}.")
        return 0


def _options(slot, computed):
    return {
        item.key: item
        for group in build_choice_offer(slot, computed).groups
        for item in group.options
        if item.thing is not None
    }


def _selected_content(raw_models):
    """Hydrate submitted identities in batches; eligibility is checked separately."""
    ids = defaultdict(set)
    allowed = {label.lower(): label for label in ASSIGNABLE_FIELDS.values()}
    for model in raw_models:
        for effect in model.get("effects", []):
            ids["library.pickable"].add(str(effect.get("pick", "")))
            answers = effect.get("choices") or {}
            for values in answers.values() if isinstance(answers, dict) else ():
                for value in values if isinstance(values, list) else ():
                    label, _, pk = str(value).partition(":")
                    if label in allowed:
                        ids[label].add(pk)
    things = []
    for label, values in ids.items():
        model = apps.get_model(allowed[label])
        valid = []
        for value in values:
            try:
                valid.append(model._meta.pk.to_python(value))
            except ValidationError, ValueError, TypeError:
                pass
        things.extend(model.objects.filter(pk__in=valid))
    return things


def _fields(obj):
    return {f.attname: str(getattr(obj, f.attname)) for f in obj._meta.concrete_fields}


def _effect_steps(thing, index, errors, facts, active):
    statuses = []
    for modifier, _ in index.for_thing(thing):
        effect = modifier.effect
        facts.append(
            [
                _fields(modifier),
                _fields(effect) if effect else None,
                _fields(modifier.scope),
            ]
        )
        if isinstance(effect, OpSetsStatus):
            statuses.append(effect.status)
        elif isinstance(effect, OpChangesCounter):
            if not active:
                errors.append(
                    "Counter tracking must be active before applying this lasting effect."
                )
        elif effect is not None and getattr(effect, "is_stored", False):
            errors.append(
                f"{thing} has a stored effect that cannot be recorded here. Resolve it separately before continuing."
            )
    return statuses


def _project_effect(
    card, computed, slot, thing, raw, result, index, writes, facts, active
):
    """Add hypothetical nodes and resolve only the questions this occurrence adds."""
    occurrence = result.id
    root_key = f"post-battle:{occurrence}"
    nodes = {root_key}
    card.roots.append(
        Node(
            thing,
            root_key,
            caused_by_key=slot.anchor.key,
            chosen_for_key=slot.anchor.key,
            chosen_for_slot_id=slot.slot.pk,
            acquired=timezone.now(),
        )
    )
    writes.append(
        (occurrence, root_key, slot.anchor.key, slot.slot, None, thing, card.miniature)
    )
    result.statuses.extend(
        _effect_steps(thing, index, result_errors := [], facts, active)
    )
    answers = raw.get("choices") or {}
    if not isinstance(answers, dict):
        result_errors.append("The choices for this lasting effect are invalid.")
        answers = {}
    asked = set()
    for _ in range(5):
        computed = compute(card, index)
        pending = [
            q
            for q in computed.choices
            if q.anchor.key in nodes and (q.anchor.key, q.identity.pk) not in asked
        ]
        if not pending:
            break
        for question in pending:
            asked.add((question.anchor.key, question.identity.pk))
            key = f"{question.anchor.key}:{question.identity._meta.model_name}:{question.identity.pk}"
            offered = _options(question, computed)
            chosen = answers.get(key, [])
            if not isinstance(chosen, list) or any(
                not isinstance(value, str) for value in chosen
            ):
                chosen = []
                result_errors.append("The choices for this lasting effect are invalid.")
            result.questions.append(
                ChoiceQuestion(
                    key,
                    question.kind_label,
                    [Option(k, v.name) for k, v in offered.items()],
                    chosen,
                    question.min_picks,
                    question.max_picks,
                )
            )
            if not question.min_picks <= len(chosen) <= question.max_picks:
                result_errors.append(
                    f"Choose {question.min_picks} to {question.max_picks} {question.kind_label.lower()} for {thing}."
                )
            if (
                question.slot
                and question.slot.assigned_to == Slot.WillBeAssignedTo.GANG
            ) or (question.offer and question.offer.will_be_assigned_to == "gang"):
                result_errors.append(
                    "This lasting effect asks for a gang-wide choice. Resolve it separately before continuing."
                )
                continue
            if (
                question.slot
                and not question.slot.slot_type.allows_repeats
                and len(set(chosen)) != len(chosen)
            ):
                result_errors.append(f"Choose different {question.kind_label.lower()}.")
            for number, selected in enumerate(chosen):
                option = offered.get(selected)
                if option is None:
                    result_errors.append(
                        f"Choose an available {question.kind_label.lower()} for {thing}."
                    )
                    continue
                node_key = f"{key}:{number}"
                nodes.add(node_key)
                card.roots.append(
                    Node(
                        option.thing,
                        node_key,
                        caused_by_key=question.anchor.key,
                        chosen_for_key=question.anchor.key,
                        chosen_for_slot_id=question.slot.pk if question.slot else None,
                        chosen_for_offer_id=question.offer.pk
                        if question.offer
                        else None,
                        acquired=timezone.now(),
                    )
                )
                writes.append(
                    (
                        occurrence,
                        node_key,
                        question.anchor.key,
                        question.slot,
                        question.offer,
                        option.thing,
                        card.miniature,
                    )
                )
                result.statuses.extend(
                    _effect_steps(option.thing, index, result_errors, facts, active)
                )
    else:
        result_errors.append(
            "This lasting effect has too many linked choices to record here."
        )
    known = {q.key for q in result.questions}
    if any(value for key, value in answers.items() if key not in known):
        result_errors.append(
            "Some choices no longer belong to this lasting effect. Check its choices again."
        )
    return result_errors


def _remove_nodes(nodes, removed):
    kept = []
    for node in nodes:
        if str(node.key) not in removed:
            node.children = _remove_nodes(node.children, removed)
            kept.append(node)
    return kept


def _project_counters(card, index, plan, result, facts):
    """Mirror the ordered stored tallies, without writing or hiding a clamp."""
    counters = {}
    by_assignment = {}
    for node in card.all_nodes():
        if (
            isinstance(node.assignable, Counter)
            and node.assignment
            and not node.broadcast
        ):
            value = getattr(node.assignment, "counter_value", None)
            held = [
                value.value if value else 0,
                str(node.assignment.pk),
                node.assignable,
            ]
            counters.setdefault(node.assignable.pk, []).append(held)
            by_assignment[str(node.assignment.pk)] = held
    xp_effect_delta = 0
    reversed_deltas = defaultdict(int)
    for _, _, events in plan._removals:
        for event in events:
            if event.kind == LedgerEvent.Kind.TALLIED and event.counter_delta:
                reversed_deltas[str(event.assignment_id)] -= event.counter_delta
    for key, delta in reversed_deltas.items():
        held = by_assignment.get(key)
        if held is not None:
            held[0] += delta
            if held[2].name.casefold() == XP_COUNTER.casefold():
                xp_effect_delta += delta
    if result.xp_assignment_id in by_assignment:
        by_assignment[result.xp_assignment_id][0] += result.xp_change
    if any(held[0] < 0 for held in by_assignment.values()):
        result.errors.append(
            "These corrections would take a counter below zero. Correct its later changes first."
        )
    for _, _, _, _, _, thing, miniature in plan._writes:
        if str(miniature.pk) != result.id:
            continue
        for modifier, _ in index.for_thing(thing):
            effect = modifier.effect
            if not isinstance(effect, OpChangesCounter):
                continue
            matches = counters.get(effect.counter_id, [])
            if len(matches) > 1:
                result.errors.append(
                    "This lasting effect has more than one matching counter. Resolve it separately."
                )
                continue
            if not matches:
                counter = effect.counter
                matches = [[0, None, counter]]
                counters[effect.counter_id] = matches
            held = matches[0]
            before = held[0]
            if effect.mode == OpChangesCounter.Mode.ADD:
                held[0] += effect.amount
            elif effect.mode == OpChangesCounter.Mode.SUBTRACT:
                held[0] = max(0, held[0] - effect.amount)
            else:
                held[0] = effect.amount
            facts.append(
                ["stored-counter", result.id, str(effect.pk), held[1], held[0] - before]
            )
            if held[2].name.casefold() == XP_COUNTER.casefold():
                xp_effect_delta += held[0] - before
    result.xp_after += xp_effect_delta


def _equipment_disposal(card, assignments):
    """Find complete equipment packages without crossing another holder's kit.

    Removal and movement follow both parent and cause links. The review uses
    those same links, including attached parts, before any package is moved.
    Computed equipment has no assignment to move or archive.
    """
    gear = {
        str(node.assignment.pk): node.assignment
        for node in card.all_nodes()
        if node.assignment is not None
        and not node.broadcast
        and is_possession(node.assignable)
    }
    children = defaultdict(set)
    for key, assignment in assignments.items():
        for parent in (assignment.parent_id, assignment.caused_by_id):
            if parent is not None:
                children[str(parent)].add(key)

    def descendants(key):
        found = set()
        pending = list(children[key])
        while pending:
            current = pending.pop()
            if current not in found:
                found.add(current)
                pending.extend(children[current])
        return found

    packages = {key: descendants(key) for key in gear}
    nested_gear = set().union(*packages.values()) if packages else set()
    roots = [key for key in gear if key not in nested_gear]
    exclusions = [
        f"{node.name} (provided by a rule)"
        for node in card.all_nodes()
        if node.assignment is None
        and not node.broadcast
        and not node.suppressed
        and is_possession(node.assignable)
    ]
    movable = []
    affected = set()
    for key in roots:
        assignment = gear[key]
        package = {key, *packages[key]}
        if not is_detachable(assignment.assignable):
            exclusions.append(f"{assignment.assignable} (part of another item)")
            continue
        if any(
            assignments[part].miniature_root_id != card.miniature.pk
            or assignments[part].gang_id is not None
            for part in package
        ):
            exclusions.append(
                f"{assignment.assignable} (also affects another model or the gang's equipment)"
            )
            continue
        movable.append(assignment)
        affected.update(package)
    names = [
        str(assignments[key].assignable)
        for key in sorted(affected)
        if is_possession(assignments[key].assignable)
    ]
    return movable, sorted(affected), names, exclusions


def preview_report(report, *, actor, payload=None):
    _require_editor(report, actor)
    payload = _draft(report.draft if payload is None else payload)
    errors = []
    raw_models = payload.get("models", [])
    if (
        not isinstance(raw_models, list)
        or len(raw_models) > 200
        or any(not isinstance(m, dict) for m in raw_models)
    ):
        raw_models = []
        errors.append("The model results are invalid.")
    for raw in raw_models:
        if (
            not isinstance(raw.get("effects", []), list)
            or len(raw.get("effects", [])) > 20
            or any(not isinstance(e, dict) for e in raw.get("effects", []))
        ):
            raw["effects"] = []
            errors.append("The lasting effects are invalid.")
    previous = (
        report.revisions.filter(sequence=report.latest_sequence).first()
        if report.latest_sequence
        else None
    )
    old = previous.inputs if previous else {}
    old_models = {m["id"]: m for m in old.get("models", [])}
    old_occurrences = previous.receipt.get("occurrences", {}) if previous else {}
    credits = _integer(payload.get("credits"), "credits", errors)
    reason = str(payload.get("reason", "")).strip()
    if (credits or old.get("credits", 0)) and not reason:
        errors.append("Add a reason for these credits.")
    if len(reason) > 255:
        errors.append("Keep the credits reason to 255 characters or fewer.")
    inputs = {
        "schema": 1,
        "credits": credits,
        "reason": reason,
        "participation_confirmed": payload.get("participation_confirmed") is True,
        "models": [],
    }
    if not inputs["participation_confirmed"]:
        errors.append("Confirm which models took part before applying these results.")
    change = credits - old.get("credits", 0)
    plan = PostBattlePlan(
        False,
        errors,
        [],
        report.gang.credits,
        report.gang.credits + change,
        change,
        "",
        inputs,
    )
    if not report.gang.credits_unlimited and plan.credits_after < 0:
        errors.append("The gang does not have enough credits to make this correction.")
    if report.gang.credits_unlimited:
        plan.credits_before = plan.credits_after = None
    gang_card = build_gang_card(report.gang)
    miniatures = {
        m.pk: m
        for m in Miniature.objects.filter(
            membership__gang=report.gang, membership__archived=False
        ).select_related("membership")
    }
    gang_card.members = {
        pk: card for pk, card in gang_card.members.items() if pk in miniatures
    }
    for pk, card in gang_card.members.items():
        card.miniature = miniatures[pk]
    selected = _selected_content(raw_models)
    index = build_modifier_index(
        [*carriers(gang_card, *gang_card.members.values()), *selected]
    )
    compute_gang(gang_card, index)
    submitted = {str(m.get("id")): m for m in raw_models}
    if len(submitted) != len(raw_models):
        errors.append("Each model can appear only once in a report.")
    if set(old_models) - set(submitted):
        errors.append(
            "Include every model from the applied report when making a correction."
        )
    current_ids = {str(pk) for pk in gang_card.members}
    if (set(submitted) | set(old_models)) - current_ids:
        errors.append(
            "A model in this report is no longer on this gang's roster. Restore it before correcting these results."
        )
    occurrences = set()
    facts = []
    choices_cache = {}
    active = is_active()
    assignments = {
        str(n.key): n.assignment
        for card in [gang_card, *gang_card.members.values()]
        for n in card.all_nodes()
        if n.assignment is not None
    }
    assignments.update(
        {
            str(node.key): node.assignment
            for root in gang_card.stash_roots
            for node in root.walk()
            if node.assignment is not None
        }
    )
    removed = set()
    all_specs = {str(e.get("id")): e for m in raw_models for e in m.get("effects", [])}
    for occurrence, held in old_occurrences.items():
        if all_specs.get(occurrence) == held["input"]:
            plan._retained[occurrence] = held
            continue
        root = assignments.get(held["root_id"])
        if (
            root is None
            or root.archived
            or str(root.miniature_root_id) != held["model_id"]
        ):
            errors.append(
                "A lasting effect being corrected has already been removed or moved. Correct it separately first."
            )
            continue
        descendants = {str(a.pk) for a in subtree(root) if not a.archived} | {
            str(root.pk)
        }
        if descendants != set(held["assignment_ids"]):
            errors.append(
                "A lasting effect being corrected has changed since it was recorded. Correct it separately first."
            )
            continue
        events = list(
            LedgerEvent.objects.filter(pk__in=held["event_ids"]).select_related(
                "assignment__counter_value"
            )
        )
        for event in events:
            if event.kind == LedgerEvent.Kind.TALLIED and event.counter_delta:
                counter = event.assignment
                value = getattr(counter, "counter_value", None) if counter else None
                if (
                    counter is None
                    or counter.archived
                    or str(counter.pk) in descendants
                    or value is None
                ):
                    errors.append(
                        "This lasting effect changed a counter that cannot be safely reversed. Correct that counter separately first."
                    )
        plan._removals.append((occurrence, root, events))
        removed.update(descendants)
        facts.append(["remove", occurrence, sorted(descendants)])
    for model_id, card in gang_card.members.items():
        model_id = str(model_id)
        miniature = card.miniature
        raw = submitted.get(model_id, {})
        before = old_models.get(model_id, {})
        model_errors = []
        card.roots = _remove_nodes(card.roots, removed)
        computed = compute(card, index)
        xp_nodes = [
            n
            for n in card.all_nodes()
            if isinstance(n.assignable, Counter)
            and n.assignable.name.casefold() == XP_COUNTER.casefold()
            and not n.broadcast
            and n.assignment is not None
            and not n.suppressed
        ]
        xp_assignment = xp_nodes[0].assignment if len(xp_nodes) == 1 else None
        xp_readings = [
            r.value
            for r in counter_readings(card, computed)
            if r.thing.name.casefold() == XP_COUNTER.casefold()
        ]
        xp_before = sum(xp_readings)
        xp = _integer(raw.get("xp"), f"{miniature.name}'s XP", model_errors)
        xp_change = xp - before.get("xp", 0)
        if xp_change and (xp_assignment is None or not active):
            model_errors.append(
                "This model needs one tracked XP counter before XP can be changed."
            )
        if xp_assignment is not None and xp_change < 0:
            held = getattr(xp_assignment, "counter_value", None)
            if (held.value if held else 0) + xp_change < 0:
                model_errors.append(
                    "This model no longer has enough XP to make this correction."
                )
        primary = next(
            (n.assignable for n in card.all_nodes() if n.is_primary_profile), None
        )
        vehicle = primary is not None and primary.profile_type.name == "Vehicle"
        result = ModelResult(
            model_id,
            miniature.name,
            miniature.status,
            label_for(miniature.status, vehicle),
            xp_before,
            xp_before + xp_change,
            xp_change,
            str(xp_assignment.pk) if xp_assignment else None,
            xp_assignment is not None and active,
            is_vehicle=vehicle,
            errors=model_errors,
            participated=raw.get("participated") is True,
        )
        plan.models.append(result)
        eligible = {}
        for slot in computed.choices:
            if (
                slot.slot is None
                or not slot.slot.slot_type.is_lasting_effect
                or slot.slot.assigned_to == Slot.WillBeAssignedTo.GANG
            ):
                continue
            anchor = slot.anchor.assignment
            if anchor is None:
                anchor = assignments.get(str(slot.anchor.key))
            if anchor is None:
                continue
            key = f"{anchor.pk}:{slot.slot.pk}"
            cache_key = str(slot.slot.pk)
            if cache_key not in choices_cache:
                choices_cache[cache_key] = _options(replace(slot, picks=[]), computed)
            options = choices_cache[cache_key]
            eligible[key] = (slot, options)
            result.effect_slots.append(
                EffectSlot(
                    key,
                    slot.kind_label,
                    [Option(str(v.thing.pk), v.name) for v in options.values()],
                )
            )
        normalized_effects = []
        implied = []
        new_counts = defaultdict(int)
        for raw_effect in raw.get("effects", []):
            try:
                occurrence = str(UUID(str(raw_effect.get("id"))))
            except ValueError, TypeError, AttributeError:
                model_errors.append(
                    "A lasting effect has an invalid reference. Remove it and add it again."
                )
                continue
            if occurrence in occurrences:
                model_errors.append("Each lasting effect needs its own reference.")
                continue
            occurrences.add(occurrence)
            spec = {
                "id": occurrence,
                "slot": str(raw_effect.get("slot", "")),
                "pick": str(raw_effect.get("pick", "")),
                "choices": raw_effect.get("choices") or {},
            }
            normalized_effects.append(spec)
            if occurrence in plan._retained:
                held = plan._retained[occurrence]
                if held["model_id"] != model_id:
                    model_errors.append(
                        "A recorded lasting effect cannot move to another model."
                    )
                questions = [
                    ChoiceQuestion(
                        **(
                            q
                            | {"options": [Option(**option) for option in q["options"]]}
                        )
                    )
                    for q in held.get("questions", [])
                ]
                result.effects.append(
                    EffectResult(
                        occurrence,
                        held["name"],
                        spec["slot"],
                        spec["pick"],
                        questions=questions,
                    )
                )
                continue
            slot, offered = eligible.get(spec["slot"], (None, {}))
            option = next(
                (v for v in offered.values() if str(v.thing.pk) == spec["pick"]), None
            )
            if slot is None or option is None or not isinstance(option.thing, Pickable):
                model_errors.append(
                    "Choose a lasting effect from one of this model's available tables."
                )
                continue
            new_counts[spec["slot"]] += 1
            if len(slot.picks) + new_counts[spec["slot"]] > slot.max_picks:
                model_errors.append(
                    f"There is no space for another {slot.kind_label.lower()}."
                )
            effect = EffectResult(occurrence, option.name, spec["slot"], spec["pick"])
            result.effects.append(effect)
            facts.append(["effect", model_id, spec])
            model_errors.extend(
                _project_effect(
                    card,
                    computed,
                    slot,
                    option.thing,
                    spec,
                    effect,
                    index,
                    plan._writes,
                    facts,
                    active,
                )
            )
            implied.extend(effect.statuses)
        explicit = str(raw.get("status", ""))
        if explicit and explicit not in Status.values:
            model_errors.append("Choose a valid final status.")
            explicit = ""
        removing_status = any(
            str(root.miniature_root_id) == model_id
            and any(e.kind == LedgerEvent.Kind.STATUS_SET for e in events)
            for _, root, events in plan._removals
        )
        existing_conflict = miniature.status != Status.ACTIVE and any(
            status != miniature.status for status in implied
        )
        if (
            len(set(implied)) > 1 or removing_status or existing_conflict
        ) and not explicit:
            model_errors.append(
                "Choose the final status to resolve these lasting effects."
            )
        status_changed = explicit and (
            not previous
            or explicit != before.get("status")
            or implied
            or removing_status
        )
        final_status = (
            explicit
            if status_changed
            else (implied[-1] if implied else miniature.status)
        )
        result.final_status = final_status
        if status_changed or implied or removing_status:
            plan._status_writes[model_id] = final_status
            facts.append(["status", model_id, miniature.status, final_status])
        disposition = str(raw.get("equipment", "keep"))
        if disposition not in {"keep", "stash", "lost"}:
            model_errors.append("Choose what happens to this model's equipment.")
            disposition = "keep"
        if (
            before.get("equipment", "keep") != "keep"
            and disposition != before["equipment"]
        ):
            model_errors.append(
                "Equipment already moved or lost cannot be reversed by this report. Correct it separately."
            )
        gear = [
            n.assignment
            for n in card.all_nodes()
            if n.assignment is not None
            and not n.broadcast
            and is_possession(n.assignable)
            and n.assignment.parent_id is None
        ]
        result.equipment_names = [str(a.assignable) for a in gear]
        result.equipment_disposition = disposition
        if disposition != "keep" and disposition != before.get("equipment", "keep"):
            if final_status != Status.DEAD:
                model_errors.append(
                    "Only a dead or destroyed model's equipment can be disposed of here."
                )
            else:
                movable, affected, names, exclusions = _equipment_disposal(
                    card, assignments
                )
                result.equipment_changed = True
                result.equipment_affected_names = names
                result.equipment_exclusions = exclusions
                plan._equipment[model_id] = (disposition, movable)
                facts.append(
                    [
                        "equipment",
                        model_id,
                        disposition,
                        affected,
                        exclusions,
                    ]
                )
        inputs["models"].append(
            {
                "id": model_id,
                "participated": result.participated,
                "xp": xp,
                "status": explicit,
                "equipment": disposition,
                "effects": normalized_effects,
            }
        )
        _project_counters(card, index, plan, result, facts)
        facts.append(["xp", model_id, result.xp_assignment_id])
        errors.extend(f"{miniature.name}: {error}" for error in model_errors)
    plan.review = sha256(
        json.dumps(facts, sort_keys=True, default=str).encode()
    ).hexdigest()
    plan.valid = not errors
    return plan


def apply_report(report, *, actor, generation, revision, submission_key, review):
    submission_key = _uuid(submission_key, "The submission reference")
    with _locked(report.gang, report.battle, report) as (gang, _, report):
        _require_editor(report, actor)
        existing = PostBattleRevision.objects.filter(
            submission_key=submission_key
        ).first()
        if existing is not None:
            if existing.report_id != report.pk:
                raise Refusal(
                    "That submission reference belongs to a different report."
                )
            return existing
        _check_version(report, generation, revision)
        plan = preview_report(report, actor=actor)
        if not plan.valid:
            raise Refusal(" ".join(plan.errors))
        if not review or review != plan.review:
            raise Refusal(
                "These results have changed. Check the changes again before applying them."
            )
        saved = PostBattleRevision.objects.create(
            report=report,
            sequence=report.latest_sequence + 1,
            submission_key=submission_key,
            actor=actor,
            inputs=plan.inputs,
        )
        assigned = {}
        roots = {}
        with operation(
            gang, actor=actor, batch=saved.batch, post_battle_revision=saved
        ) as op:
            op.receive_credits(
                plan.credits_change,
                plan.inputs["reason"] or "Post-battle income correction",
            )
            reversals = [
                (occurrence, event)
                for occurrence, _, events in plan._removals
                for event in events
                if event.kind == LedgerEvent.Kind.TALLIED and event.counter_delta
            ]
            # Restoring deductions first cannot clip a later reversed addition.
            for occurrence, event in sorted(
                reversals, key=lambda pair: pair[1].counter_delta
            ):
                op.post_battle_occurrence = UUID(occurrence)
                op.tally(
                    event.assignment,
                    -event.counter_delta,
                    note="Post-battle correction",
                    reversal_of=event,
                )
            for occurrence, root, _ in plan._removals:
                op.post_battle_occurrence = UUID(occurrence)
                op.remove(root, note="Post-battle correction")
            op.post_battle_occurrence = None
            for model in plan.models:
                if model.xp_change:
                    op.tally(
                        Assignment.objects.get(pk=model.xp_assignment_id),
                        model.xp_change,
                        note="Post-battle XP",
                    )
            for (
                occurrence,
                key,
                anchor_key,
                slot,
                offer,
                thing,
                miniature,
            ) in plan._writes:
                op.post_battle_occurrence = UUID(occurrence)
                anchor = assigned.get(anchor_key)
                if anchor is None:
                    anchor = Assignment.objects.get(
                        pk=anchor_key, archived=False, gang_root=gang
                    )
                assigned[key] = op.choose(
                    anchor, thing, slot=slot, offer=offer, miniature=miniature
                )
                roots.setdefault(occurrence, assigned[key])
            op.post_battle_occurrence = None
            for model_id, status in plan._status_writes.items():
                miniature = Miniature.objects.get(pk=model_id)
                op.set_status(miniature, status, note="Post-battle results")
            for disposition, gear in plan._equipment.values():
                for assignment in gear:
                    if disposition == "stash":
                        op.move(assignment, gang.stash, note="Post-battle equipment")
                    else:
                        op.remove(assignment, note="Equipment lost after battle")
            op.event(
                None, LedgerEvent.Kind.POST_BATTLE, note="Post-battle results recorded"
            )
        events = list(saved.ledger_events.order_by("created", "pk"))
        occurrences = deepcopy(plan._retained)
        specs = {
            e["id"]: (m["id"], e) for m in plan.inputs["models"] for e in m["effects"]
        }
        effects = {e.id: e for m in plan.models for e in m.effects}
        for occurrence, root in roots.items():
            occurrence_events = [
                e
                for e in events
                if str(e.post_battle_occurrence) == occurrence
                and e.created >= root.created
            ]
            model_id, spec = specs[occurrence]
            occurrences[occurrence] = {
                "input": spec,
                "name": effects[occurrence].name,
                "model_id": model_id,
                "questions": [asdict(q) for q in effects[occurrence].questions],
                "root_id": str(root.pk),
                "assignment_ids": [
                    str(a.pk) for a in [root, *subtree(root)] if not a.archived
                ],
                "event_ids": [str(e.pk) for e in occurrence_events],
            }
        gang.refresh_from_db()
        # A receipt freezes actual readings, including computed contributions
        # and counters a stored effect created while applying this report.
        final_card = build_gang_card(gang)
        final_index = build_modifier_index(
            carriers(final_card, *final_card.members.values())
        )
        compute_gang(final_card, final_index)
        final_statuses = dict(
            Miniature.objects.filter(pk__in=[m.id for m in plan.models]).values_list(
                "pk", "status"
            )
        )
        final_statuses = {str(pk): status for pk, status in final_statuses.items()}
        final_readings = {}
        for pk, card in final_card.members.items():
            computed = compute(card, final_index)
            final_readings[str(pk)] = sum(
                r.value
                for r in counter_readings(card, computed)
                if r.thing.name.casefold() == XP_COUNTER.casefold()
            )
        for model in plan.models:
            model.xp_after = final_readings.get(model.id, 0)
            model.final_status = final_statuses[model.id]
        receipt = {
            "gang": gang.name,
            "reference": report.reference,
            "date": str(report.date),
            "battle": report.battle.title if report.battle_id else "",
            "credits_before": plan.credits_before,
            "credits_after": None if gang.credits_unlimited else gang.credits,
            "credits_change": plan.credits_change,
            "reason": plan.inputs["reason"],
            "models": [
                {
                    "id": m.id,
                    "name": m.name,
                    "participated": m.participated,
                    "xp_before": m.xp_before,
                    "xp_after": m.xp_after,
                    "xp_change": m.xp_change,
                    "status_before": m.status,
                    "status_after": m.final_status,
                    "status_before_label": m.status_label,
                    "status_after_label": label_for(m.final_status, m.is_vehicle),
                    "effects": [e.name for e in m.effects],
                    "equipment_disposition": m.equipment_disposition,
                    "equipment_changed": m.equipment_changed,
                    "equipment_names": m.equipment_affected_names,
                    "equipment_exclusions": m.equipment_exclusions,
                }
                for m in plan.models
            ],
            "occurrences": occurrences,
            "event_ids": [str(e.pk) for e in events],
        }
        PostBattleRevision.objects.filter(pk=saved.pk, receipt={}).update(
            receipt=receipt
        )
        saved.receipt = receipt
        report.latest_sequence = saved.sequence
        report.state = PostBattleReport.State.APPLIED
        report.last_editor = actor
        report.save(
            update_fields=["latest_sequence", "state", "last_editor", "modified"]
        )
        return saved
