"""Preview and apply item tier augmentations for fighter actions."""

from __future__ import annotations

from copy import copy
from dataclasses import asdict, dataclass, is_dataclass

from django.db.models import Q
from django.utils import timezone

from n26.core.card import Node, build_card, build_modifier_index, carriers, node_for
from n26.core.effects import compute
from n26.core.models import Assignment, SlotSelection
from n26.core.operations import Refusal
from n26.core.render import build_model_card
from n26.library.models import PicklistMember, Slot, Wargear, Weapon


@dataclass(frozen=True)
class AugmentationCandidate:
    """One carried item's next effective tier, ready for a review screen."""

    item_assignment_id: str
    item_name: str
    current_level: int
    current_tier: str
    candidate_level: int
    candidate_tier: str
    candidate_pick_id: str
    effect: str
    rating_before: int
    rating_after: int


@dataclass(frozen=True)
class AugmentationPreview:
    """Every valid item choice for one fighter and augmentation kind."""

    candidates: tuple[AugmentationCandidate, ...]


@dataclass(frozen=True)
class _Ladder:
    item: Assignment
    slot: Assignment
    current: Assignment | None
    members: tuple[PicklistMember, ...]


def _refuse(message):
    raise Refusal(message)


def _project_counters(card, projected):
    """Apply reviewed post-payment counter values to an in-memory card."""
    if not projected:
        return card

    def project(nodes):
        for node in nodes:
            assignment = node.assignment
            value = (
                projected.get(str(assignment.pk)) if assignment is not None else None
            )
            counter = (
                getattr(assignment, "counter_value", None)
                if assignment is not None
                else None
            )
            if value is not None and counter is not None:
                assignment = copy(assignment)
                assignment._state = copy(assignment._state)
                assignment._state.fields_cache = dict(assignment._state.fields_cache)
                counter = copy(counter)
                counter.value = value
                assignment._state.fields_cache["counter_value"] = counter
                node.assignment = assignment

    project(card.all_nodes())
    if card.gang_card is not None:
        project(card.gang_card.all_nodes())
        card.gang_card.acquired = None
    return card


def _copy_node(node):
    cloned = copy(node)
    cloned.children = [_copy_node(child) for child in node.children]
    return cloned


def _copy_card(card):
    """Copy mutable card state while retaining its hydrated ORM objects."""
    cloned = copy(card)
    cloned.roots = [_copy_node(node) for node in card.roots]
    cloned.granted = [_copy_node(node) for node in card.granted]
    cloned.removals = list(card.removals)
    cloned.holdings = list(card.holdings)
    if card.gang_card is not None:
        cloned.gang_card = copy(card.gang_card)
        cloned.gang_card.roots = [_copy_node(node) for node in card.gang_card.roots]
        cloned.gang_card.stash_roots = [
            _copy_node(node) for node in card.gang_card.stash_roots
        ]
        cloned.gang_card.granted = [_copy_node(node) for node in card.gang_card.granted]
        cloned.gang_card.holdings = list(card.gang_card.holdings)
    return cloned


def _ladders(record, configured, *, card=None, projected=None):
    """Resolve exact carried items and their single configured ladder."""
    card = card or build_card(record.fighter, with_statlines=True)
    if projected:
        card = _project_counters(_copy_card(card), projected)
    effective = _copy_card(card)
    compute(effective, build_modifier_index(carriers(effective)))
    nodes = list(effective.all_nodes())
    items = [
        node.assignment
        for node in nodes
        if node.assignment is not None
        and not node.assignment.archived
        and not node.suppressed
        and node.assignment.miniature_root_id == record.fighter_id
        and isinstance(node.assignable, (Weapon, Wargear))
    ]
    slots_by_item = {}
    for node in nodes:
        assignment = node.assignment
        if (
            assignment is not None
            and not assignment.archived
            and not node.suppressed
            and assignment.miniature_root_id == record.fighter_id
            and assignment.slot_id is not None
            and assignment.slot.slot_type_id == configured.slot_type_id
            and assignment.slot.mode == Slot.Mode.TIER_LADDER
            and assignment.slot.assigned_to == Slot.WillBeAssignedTo.BEARER
            and assignment.caused_by_id is not None
        ):
            slots_by_item.setdefault(assignment.caused_by_id, []).append(assignment)

    relevant = [(item, slots_by_item.get(item.pk, [])) for item in items]
    ambiguous = [item for item, slots in relevant if len(slots) > 1]
    if ambiguous:
        _refuse(f"{ambiguous[0].assignable} has more than one matching tier ladder.")

    slots = [found[0] for _, found in relevant if found]
    members = PicklistMember.objects.filter(
        picklist_id__in={slot.slot.picklist_id for slot in slots}
    ).select_related("pack", "pickable", "pickable__pack")
    members_by_list = {}
    for member in members:
        members_by_list.setdefault(member.picklist_id, []).append(member)

    live_picks = [
        node.assignment
        for node in nodes
        if node.assignment is not None
        and node.assignment.pickable_id is not None
        and not node.assignment.archived
        and node.assignment.miniature_root_id == record.fighter_id
    ]
    picks_by_slot = {}
    for pick in live_picks:
        picks_by_slot.setdefault(pick.chosen_for_id, []).append(pick)

    resolved = []
    for item, found in relevant:
        if not found:
            continue
        slot = found[0]
        picks = picks_by_slot.get(slot.pk, [])
        if len(picks) > 1:
            _refuse(f"{item.assignable} has more than one current augmentation tier.")
        ladder_members = tuple(members_by_list.get(slot.slot.picklist_id, ()))
        if any(member.level is None for member in ladder_members):
            _refuse(f"{item.assignable}'s tier ladder has a tier without a level.")
        resolved.append(
            _Ladder(item, slot, picks[0] if picks else None, ladder_members)
        )
    return card, tuple(resolved)


def _level(ladder, pick):
    if pick is None:
        return 0
    member = next(
        (member for member in ladder.members if member.pickable_id == pick.pickable_id),
        None,
    )
    if member is None:
        _refuse(f"{pick.assignable} is not on {ladder.slot.assignable}'s tier ladder.")
    return member.level


def _render(card, index=None):
    card = _copy_card(card)
    if index is None:
        index = build_modifier_index(carriers(card))
    computed = compute(card, index)
    return build_model_card(card.miniature, card=card, computed=computed, brought_in={})


def _effect_state(value):
    """Comparable game effects, excluding prices and presentation metadata."""
    value = asdict(value) if is_dataclass(value) else value
    if isinstance(value, dict):
        return {
            key: _effect_state(item)
            for key, item in value.items()
            if key
            not in {
                "assignment_id",
                "back",
                "brought_in",
                "choices",
                "full_name",
                "held_at",
                "href",
                "id",
                "modified_by",
                "profile_name",
                "provenance",
                "questions",
                "rating",
                "remarks",
                "row_questions",
                "short_name",
            }
        }
    if isinstance(value, (list, tuple)):
        return [_effect_state(item) for item in value]
    return value


def _newly_capped(before, after):
    """Whether this candidate affected a characteristic already at its ceiling."""
    before = asdict(before) if is_dataclass(before) else before
    after = asdict(after) if is_dataclass(after) else after
    if isinstance(before, dict) and isinstance(after, dict):
        if (
            after.get("held_at") == "maximum"
            and before.get("value") == after.get("value")
            and before.get("modified_by") != after.get("modified_by")
        ):
            return True
        return any(
            key in before and _newly_capped(before[key], child)
            for key, child in after.items()
        )
    if isinstance(before, (list, tuple)) and isinstance(after, (list, tuple)):
        return any(
            _newly_capped(left, right)
            for left, right in zip(before, after, strict=False)
        )
    return False


def _replace_node(card, key, replacement):
    """Replace one stored line in a copied card, preserving its position."""

    def replace(nodes):
        for position, node in enumerate(nodes):
            if node.key == key:
                replacement.children = node.children
                nodes[position] = replacement
                return True
            if replace(node.children):
                return True
        return False

    return replace(card.roots)


def _remove_node(card, key):
    """Remove one stored line from a copied card."""

    def remove(nodes):
        for position, node in enumerate(nodes):
            if node.key == key:
                nodes.pop(position)
                return True
            if remove(node.children):
                return True
        return False

    return remove(card.roots)


def _preview_node(ladder, member):
    """Describe the assignment that replacing this tier would create."""
    return Node(
        assignable=member.pickable,
        key=("augmentation-preview", ladder.slot.pk, member.pickable_id),
        rating=member.pickable.rating_contribution,
        caused_by_key=ladder.slot.pk,
        chosen_for_key=ladder.slot.pk,
        chosen_for_slot_id=ladder.slot.slot_id,
        acquired=timezone.now(),
    )


def _render_with_pick(card, ladder, member, index):
    """Render one temporary replacement with the identity of a new pick."""
    card = _copy_card(card)
    replacement = _preview_node(ladder, member)
    old_rating = ladder.current.rating if ladder.current is not None else 0
    if ladder.current is None:
        card.roots.append(replacement)
    elif not _replace_node(card, ladder.current.pk, replacement):
        _refuse("The current augmentation tier is no longer on this fighter.")
    card.full_rating += member.pickable.rating_contribution - old_rating
    return _render(card, index)


def _restored_card(card, ladder, previous_pick):
    """Return the completed card as it stood immediately before this action."""
    card = _copy_card(card)
    old_rating = ladder.current.rating
    if previous_pick is None:
        if not _remove_node(card, ladder.current.pk):
            _refuse("The original augmentation tier is no longer on this fighter.")
        card.full_rating -= old_rating
    else:
        restored = node_for(previous_pick)
        if not _replace_node(card, ladder.current.pk, restored):
            _refuse("The original augmentation tier is no longer on this fighter.")
        card.full_rating += restored.rating - old_rating
    return card


def _selectable(member):
    return not (
        member.archived
        or member.staged
        or member.pack.archived
        or member.pickable.archived
        or member.pickable.staged
        or member.pickable.pack.archived
    )


def _candidate(card, ladder, index=None, before=None):
    def supported_modifiers(member):
        modifiers = tuple(index.for_thing(member.pickable))
        if any(
            getattr(modifier.effect, "is_stored", False)
            for modifier, _source in modifiers
        ):
            return None
        return modifiers

    current_level = _level(ladder, ladder.current)
    ordered = sorted(ladder.members, key=lambda member: member.level)
    next_members = [
        member
        for member in ordered
        if member.level > current_level and _selectable(member)
    ]
    member = next_members[0] if next_members else None
    if member is None:
        return None

    candidate_modifiers = supported_modifiers(member)
    if candidate_modifiers is None:
        return None

    before = before or _render(card, index)
    after = _render_with_pick(card, ladder, member, index)
    # A capped characteristic may make the immediate rung do nothing. The
    # rule permits looking exactly one rung farther, never an arbitrary jump.
    same_effects = _effect_state(before) == _effect_state(after)
    if same_effects and _newly_capped(before, after):
        member = next_members[1] if len(next_members) > 1 else None
        if member is None:
            return None
        candidate_modifiers = supported_modifiers(member)
        if candidate_modifiers is None:
            return None
        after = _render_with_pick(card, ladder, member, index)
        if _effect_state(before) == _effect_state(after):
            return None
    elif same_effects and before.rating == after.rating:
        return None

    return AugmentationCandidate(
        item_assignment_id=str(ladder.item.pk),
        item_name=str(ladder.item.assignable),
        current_level=current_level,
        current_tier=(
            next(
                member.label
                for member in ladder.members
                if ladder.current is not None
                and member.pickable_id == ladder.current.pickable_id
            )
            if ladder.current
            else "None"
        ),
        candidate_level=member.level,
        candidate_tier=member.label,
        candidate_pick_id=str(member.pickable_id),
        effect=(
            "; ".join(str(modifier.effect) for modifier, _ in candidate_modifiers)
            or f"Select {member.label}."
        ),
        rating_before=before.rating,
        rating_after=after.rating,
    )


def _original_selection(record, *, lock=False):
    query = SlotSelection.objects
    if lock:
        query = query.select_for_update(of=("self",))
    try:
        selection = query.select_related(
            "item_assignment",
            "slot_assignment__slot",
            "previous_pick__ledger_entry",
            "new_pick",
        ).get(action_record=record)
    except SlotSelection.DoesNotExist:
        return None
    return selection


def _correction_baseline(record, configured, *, lock=False, projected=None):
    selection = _original_selection(record, lock=lock)
    card, ladders = _ladders(record, configured, projected=projected)
    if selection is None or record.state != record.State.COMPLETED:
        return card, ladders, None
    live = Assignment.objects.filter(
        chosen_for=selection.slot_assignment_id,
        pickable__isnull=False,
        archived=False,
    )
    if lock:
        live = live.select_for_update()
    live = list(live)
    if (
        selection.item_assignment is None
        or selection.item_assignment.archived
        or selection.item_assignment.gang_root_id != record.gang_id
        or selection.item_assignment.miniature_root_id != record.fighter_id
        or selection.slot_assignment is None
        or selection.slot_assignment.archived
        or selection.slot_assignment.gang_root_id != record.gang_id
        or selection.slot_assignment.miniature_root_id != record.fighter_id
        or selection.new_pick is None
        or selection.new_pick.archived
        or live != [selection.new_pick]
    ):
        _refuse(
            "The original item or tier has changed. "
            "Review the change before continuing."
        )
    if Assignment.objects.filter(
        Q(parent=selection.new_pick) | Q(caused_by=selection.new_pick)
    ).exists():
        _refuse(
            "The original tier has dependent changes. Review them before continuing."
        )
    original = next(
        (
            ladder
            for ladder in ladders
            if ladder.slot.pk == selection.slot_assignment_id
        ),
        None,
    )
    if (
        original is None
        or selection.new_pick_id is None
        or original.current is None
        or original.current.pk != selection.new_pick_id
    ):
        _refuse(
            "The original item or tier has changed. "
            "Review the change before continuing."
        )
    card = _restored_card(card, original, selection.previous_pick)
    card, ladders = _ladders(record, configured, card=card)
    ladders = tuple(
        _Ladder(row.item, row.slot, selection.previous_pick, row.members)
        if row.slot.pk == original.slot.pk
        else row
        for row in ladders
    )
    return card, ladders, selection


def augmentation_options(record, configured):
    """List effective next tiers for the fighter's carried items."""
    card, ladders, _selection = _correction_baseline(record, configured)
    preview_carriers = [*carriers(card)]
    preview_carriers.extend(
        member.pickable for ladder in ladders for member in ladder.members
    )
    index = build_modifier_index(preview_carriers)
    before = _render(card, index)
    current_ids = [ladder.current.pk for ladder in ladders if ladder.current]
    blocked = set(
        Assignment.objects.filter(
            Q(parent_id__in=current_ids) | Q(caused_by_id__in=current_ids)
        ).values_list("parent_id", "caused_by_id")
    )
    blocked_ids = {value for pair in blocked for value in pair if value is not None}
    return AugmentationPreview(
        tuple(
            candidate
            for ladder in ladders
            if ladder.current is None or ladder.current.pk not in blocked_ids
            if (candidate := _candidate(card, ladder, index, before))
        )
    )


def preview_augmentation(record, configured, terms, *, projected=None):
    """Return the exact target-state fingerprint stored with a review."""
    ladder, _member, candidate, selection, before, after = _selected(
        record, configured, terms, projected=projected
    )
    snapshot = {
        "selection": asdict(candidate),
        "item_assignment": str(ladder.item.pk),
        "item_modified": ladder.item.modified.isoformat(),
        "slot_assignment": str(ladder.slot.pk),
        "slot_modified": ladder.slot.modified.isoformat(),
        "current_pick": str(ladder.current.pk) if ladder.current else None,
        "current_pick_modified": (
            ladder.current.modified.isoformat() if ladder.current else None
        ),
        "effects_before": before,
        "effects_after": after,
    }
    if selection is not None:
        snapshot["original_result"] = {
            "item_assignment": str(selection.item_assignment_id),
            "item_modified": selection.item_assignment.modified.isoformat(),
            "slot_assignment": str(selection.slot_assignment_id),
            "slot_modified": selection.slot_assignment.modified.isoformat(),
            "new_pick": str(selection.new_pick_id),
            "new_pick_modified": selection.new_pick.modified.isoformat(),
            "previous_pick": (
                str(selection.previous_pick_id) if selection.previous_pick_id else None
            ),
            "previous_pick_modified": (
                selection.previous_pick.modified.isoformat()
                if selection.previous_pick_id
                else None
            ),
        }
    return snapshot


def _selected(record, configured, terms, *, lock=False, projected=None):
    item_id = terms.get("item_assignment")
    intended_id = terms.get("intended_pick")
    if not item_id or not intended_id:
        _refuse("Choose an item and augmentation tier before continuing.")
    card, ladders, selection = _correction_baseline(
        record, configured, lock=lock, projected=projected
    )
    ladder = next((row for row in ladders if str(row.item.pk) == str(item_id)), None)
    if ladder is None:
        _refuse("That item is no longer carried by this fighter.")
    index = build_modifier_index(
        [*carriers(card), *(member.pickable for member in ladder.members)]
    )
    candidate = _candidate(card, ladder, index)
    if candidate is None or candidate.candidate_pick_id != str(intended_id):
        _refuse("That augmentation is no longer the next effective tier.")
    if (
        ladder.current is not None
        and Assignment.objects.filter(
            Q(parent=ladder.current) | Q(caused_by=ladder.current)
        ).exists()
    ):
        _refuse(
            "The current tier has dependent changes. Review them before continuing."
        )
    member = next(
        row
        for row in ladder.members
        if str(row.pickable_id) == candidate.candidate_pick_id
    )
    before = _render(card, index)
    after = _render_with_pick(card, ladder, member, index)
    return (
        ladder,
        member,
        candidate,
        selection,
        _effect_state(before),
        _effect_state(after),
    )


def apply_augmentation(op, record, configured, terms):
    """Apply a reviewed augmentation and record its exact assignments."""
    ladder, member, candidate, _selection, _before, _after = _selected(
        record, configured, terms
    )
    new_pick = op.replace_slot_pick(
        ladder.slot,
        ladder.slot.slot,
        member.pickable,
        previous_pick=ladder.current,
        miniature=record.fighter,
        action_record=record,
    )
    SlotSelection.objects.update_or_create(
        action_record=record,
        defaults={
            "item_assignment": ladder.item,
            "slot_assignment": ladder.slot,
            "previous_pick": ladder.current,
            "intended_pick": member.pickable,
            "new_pick": new_pick,
        },
    )
    return {"augmentation": asdict(candidate), "new_pick": str(new_pick.pk)}


def _live_pick(slot):
    return list(
        Assignment.objects.select_for_update().filter(
            chosen_for=slot, pickable__isnull=False, archived=False
        )
    )


def correct_augmentation(op, record, configured, terms):
    """Reverse a completed result and apply its replacement without repayment."""
    ladder, member, candidate, selection, _before, _after = _selected(
        record, configured, terms, lock=True
    )
    if selection is None:
        _refuse("This action has no augmentation result to correct.")
    if selection.new_pick is None or selection.new_pick.archived:
        _refuse("The original augmentation has changed. Review it before continuing.")
    if Assignment.objects.filter(
        Q(parent=selection.new_pick) | Q(caused_by=selection.new_pick)
    ).exists():
        _refuse(
            "The original tier has dependent changes. Review them before continuing."
        )
    if (
        selection.item_assignment is None
        or selection.slot_assignment is None
        or selection.item_assignment.miniature_root_id != record.fighter_id
        or selection.slot_assignment.miniature_root_id != record.fighter_id
        or _live_pick(selection.slot_assignment) != [selection.new_pick]
    ):
        _refuse(
            "The original item or tier has changed. "
            "Review the change before continuing."
        )

    restored_pick = None
    if selection.previous_pick is None:
        op.replace_slot_pick(
            selection.slot_assignment,
            selection.slot_assignment.slot,
            None,
            previous_pick=selection.new_pick,
            miniature=record.fighter,
            action_record=record,
        )
    else:
        restored_pick = op.restore_slot_pick(
            selection.slot_assignment,
            selection.slot_assignment.slot,
            restore_pick=selection.previous_pick,
            replacing=selection.new_pick,
            miniature=record.fighter,
            action_record=record,
        )
    current = (
        restored_pick
        if restored_pick is not None and ladder.slot.pk == selection.slot_assignment_id
        else ladder.current
    )
    new_pick = op.replace_slot_pick(
        ladder.slot,
        ladder.slot.slot,
        member.pickable,
        previous_pick=current,
        miniature=record.fighter,
        action_record=record,
    )
    selection.item_assignment = ladder.item
    selection.slot_assignment = ladder.slot
    selection.previous_pick = current
    selection.intended_pick = member.pickable
    selection.new_pick = new_pick
    selection.save()
    return {"augmentation": asdict(candidate), "new_pick": str(new_pick.pk)}
