"""Persist and resolve fighter advancement rolls and skill choices."""

from dataclasses import dataclass
from types import SimpleNamespace

from django.db import transaction

from n26.core.card import build_card, build_modifier_index, carriers
from n26.core.effects import compute
from n26.core.models import AdvancementSelection, Assignment, SkillSelection
from n26.core.operations import Refusal


@dataclass(frozen=True)
class AdvancementOption:
    id: str
    name: str
    rating: int
    gainable: bool
    needs_skill: bool
    skill_mode: str


def _validate_draft(op, record, configured):
    from n26.core.models import ActionRecord

    record = (
        ActionRecord.objects.select_for_update(of=("self",))
        .select_related("fighter__membership", "action")
        .filter(pk=record.pk, gang=op.gang, state=ActionRecord.State.STARTED)
        .first()
    )
    if record is None or record.fighter.membership.gang_id != op.gang.pk:
        raise Refusal("That advancement is no longer awaiting a roll.")
    if not record.action.outcomes.filter(
        outcome__resolve_advancement=configured
    ).exists():
        raise Refusal("That advancement does not belong to this action.")
    return record


def _computed(fighter):
    card = build_card(fighter, with_statlines=True)
    return card, compute(card, build_modifier_index(carriers(card)))


def _skill_offer(pickable):
    from n26.library.models import OffersChoice, Skill

    found = [
        modifier.effect
        for modifier in pickable.modifiers.all()
        if isinstance(modifier.effect, OffersChoice)
        and modifier.effect.of_kind.model_class() is Skill
    ]
    if len(found) > 1:
        raise ValueError(f"{pickable} offers more than one skill choice.")
    return found[0] if found else None


def _stat_gainable(fighter, pickable):
    from n26.core.render import build_model_card
    from n26.library.models import ChangesStat

    changes = [
        modifier.effect
        for modifier in pickable.modifiers.all()
        if isinstance(modifier.effect, ChangesStat)
    ]
    if not changes:
        return None
    card, computed = _computed(fighter)
    cells = build_model_card(fighter, card=card, computed=computed).statline.cells
    values = {cell.full_name: cell.value for cell in cells}
    for change in changes:
        shown = values.get(change.stat.full_name, "").rstrip('"+').lstrip("+")
        try:
            current = int(shown)
        except ValueError:
            continue
        direction = -change.amount if change.stat.is_inverted else change.amount
        if change.mode == change.Mode.WORSEN:
            direction = -direction
        moved = (
            change.amount
            if change.mode == change.Mode.SET
            else change.stat.shift(current, direction)
        )
        if moved != current:
            return True
    return False


def _listed_skills(record, offer):
    from n26.core.browse import offered_by, usability_for
    from n26.library.models import Skill

    _, computed = _computed(record.fighter)
    question = SimpleNamespace(slot=None, offer=offer, kind_label=offer.kind_label)
    listed = offered_by(question, computed)
    rows = listed.all_lines() if hasattr(listed, "all_lines") else listed
    fighter = usability_for(computed)
    owned = set(
        Assignment.objects.filter(
            miniature_root=record.fighter, archived=False, skill__isnull=False
        ).values_list("skill_id", flat=True)
    )
    return [
        getattr(row, "thing", row)
        for row in rows
        if isinstance(getattr(row, "thing", row), Skill)
        and getattr(row, "thing", row).pk not in owned
        and getattr(row, "thing", row).is_usable_by(fighter)
    ]


def _gainable(record, pickable):
    stat = _stat_gainable(record.fighter, pickable)
    if stat is not None:
        return stat
    offer = _skill_offer(pickable)
    return bool(_listed_skills(record, offer)) if offer else True


def record_action_roll(op, record, configured, request_key, *, rolled=None, rng=None):
    """Persist one 2D6 roll and its record-owned slot before any result pick."""
    record = _validate_draft(op, record, configured)
    selection, _ = AdvancementSelection.objects.select_for_update().get_or_create(
        action_record=record
    )
    if selection.roll_event_id:
        return selection
    anchor = op.assign(
        configured.slot,
        miniature=record.fighter,
        caused_by=record.fighter.membership,
        action_record=record,
    )
    event = op.roll(
        configured.slot,
        miniature=record.fighter,
        rolled=rolled,
        rng=rng,
        action_record=record,
    )
    selection.slot_assignment, selection.roll_event = anchor, event
    selection.save(update_fields=["slot_assignment", "roll_event", "modified"])
    record.terms = {**record.terms, "action_roll_request": str(request_key)}
    record.save(update_fields=["terms", "modified"])
    return selection


def advancement_options(record, configured):
    try:
        selection = record.advancement_selection
    except AdvancementSelection.DoesNotExist as error:
        raise Refusal("Roll 2D6 for this advancement first.") from error
    if not selection.roll_event_id:
        raise Refusal("Roll 2D6 for this advancement first.")
    members = list(configured.slot.picklist.members.select_related("pickable"))
    landed = configured.slot.picklist.landing(selection.roll_event.roll, members)
    gainable = [member for member in landed if _gainable(record, member.pickable)]
    offered = gainable or members
    return tuple(
        AdvancementOption(
            str(member.pickable_id),
            str(member.pickable),
            member.pickable.rating_contribution,
            _gainable(record, member.pickable),
            _skill_offer(member.pickable) is not None,
            (
                _skill_offer(member.pickable).mode
                if _skill_offer(member.pickable)
                else ""
            ),
        )
        for member in offered
    )


def skill_options(record, configured, pickable_id):
    if str(pickable_id) not in {
        option.id for option in advancement_options(record, configured)
    }:
        raise Refusal("That advancement result is not available for this roll.")
    pickable = configured.slot.picklist.members.get(pickable_id=pickable_id).pickable
    offer = _skill_offer(pickable)
    if offer is None:
        return {}
    grouped = {}
    for skill in _listed_skills(record, offer):
        grouped.setdefault(skill.category, []).append(skill)
    return grouped


def _skill_access(configured, pickable_id):
    pickable = configured.slot.picklist.members.get(pickable_id=pickable_id).pickable
    offer = _skill_offer(pickable)
    return "any" if offer.from_section_id is None else offer.from_section.name.lower()


def record_skill_roll(
    op,
    record,
    configured,
    request_key,
    *,
    pickable_id,
    skill_set_id,
    rolled=None,
    rng=None,
):
    record = _validate_draft(op, record, configured)
    options = skill_options(record, configured, pickable_id)
    category = next((row for row in options if str(row.pk) == str(skill_set_id)), None)
    if category is None:
        raise Refusal("That Skill Set is not available for this advancement.")
    selection, _ = SkillSelection.objects.select_for_update().get_or_create(
        action_record=record,
        defaults={"mode": "random", "access": _skill_access(configured, pickable_id)},
    )
    for attempt in selection.random_attempts:
        if attempt["request_key"] == str(request_key):
            return attempt
    from n26.library.models import Dice

    event = op.roll(
        configured.slot,
        miniature=record.fighter,
        rolled=rolled,
        rng=rng,
        dice=Dice.D6,
        action_record=record,
        note=str(category),
    )
    from n26.library.models import Skill

    rolled_skill = Skill.objects.filter(category=category, position=event.roll).first()
    available = next(
        (
            row
            for row in options[category]
            if row.pk == getattr(rolled_skill, "pk", None)
        ),
        None,
    )
    attempt = {
        "request_key": str(request_key),
        "event_id": str(event.pk),
        "skill_set_id": str(category.pk),
        "roll": event.roll,
        "skill_id": str(rolled_skill.pk) if rolled_skill else None,
        "result_name": str(rolled_skill) if rolled_skill else None,
        "is_available": available is not None,
        "unavailable_reason": (
            None
            if available is not None
            else "That result is already owned or unavailable."
        ),
    }
    selection.random_attempts = [*selection.random_attempts, attempt]
    selection.skill_set, selection.selected_skill = category, available
    selection.save()
    return attempt


def _resolved(record, configured, terms):
    pickable_id = str(terms.get("pickable_id", ""))
    if pickable_id not in {
        option.id for option in advancement_options(record, configured)
    }:
        raise Refusal("Choose an advancement result available for this roll.")
    pickable = configured.slot.picklist.members.get(pickable_id=pickable_id).pickable
    offer, skill = _skill_offer(pickable), None
    if offer is not None:
        options = skill_options(record, configured, pickable_id)
        if offer.mode == offer.Mode.RANDOM:
            selection = getattr(record, "skill_selection", None)
            skill = selection.selected_skill if selection else None
            if skill is None:
                raise Refusal("Roll D6 again for an available skill.")
        else:
            skill_id = str(terms.get("skill_id", ""))
            skill = next(
                (
                    row
                    for rows in options.values()
                    for row in rows
                    if str(row.pk) == skill_id
                ),
                None,
            )
            if skill is None:
                raise Refusal("Choose an available skill.")
    return pickable, offer, skill


def preview_advancement(record, configured, terms):
    pickable, offer, skill = _resolved(record, configured, terms)
    selection = record.advancement_selection
    return {
        "roll": selection.roll_event.roll,
        "roll_event_id": str(selection.roll_event_id),
        "slot_assignment_id": str(selection.slot_assignment_id),
        "pickable_id": str(pickable.pk),
        "result": str(pickable),
        "rating": pickable.rating_contribution,
        "skill_id": str(skill.pk) if skill else None,
        "skill": str(skill) if skill else None,
        "skill_mode": offer.mode if offer else None,
    }


@transaction.atomic
def apply_advancement(op, record, configured, terms):
    snapshot = preview_advancement(record, configured, terms)
    selection = record.advancement_selection
    if selection.pick_assignment_id:
        return snapshot
    pickable, offer, skill = _resolved(record, configured, terms)
    pick = op.choose(
        selection.slot_assignment,
        pickable,
        slot=configured.slot,
        roll=selection.roll_event,
        action_record=record,
    )
    selection.intended_pick, selection.pick_assignment = pickable, pick
    selection.save(update_fields=["intended_pick", "pick_assignment", "modified"])
    if skill is not None:
        skill_pick = op.choose(
            pick, skill, offer=offer, miniature=record.fighter, action_record=record
        )
        skill_selection, _ = SkillSelection.objects.get_or_create(
            action_record=record,
            defaults={
                "mode": offer.mode,
                "access": _skill_access(configured, pickable.pk),
            },
        )
        skill_selection.mode, skill_selection.access = (
            offer.mode,
            _skill_access(configured, pickable.pk),
        )
        skill_selection.skill_set, skill_selection.selected_skill = (
            skill.category,
            skill,
        )
        skill_selection.skill_assignment = skill_pick
        skill_selection.save()
    return snapshot


def correct_advancement(op, record, configured, terms):
    selection = record.advancement_selection
    old_pick = selection.pick_assignment
    old_skill = getattr(
        getattr(record, "skill_selection", None), "skill_assignment", None
    )
    if old_pick is None or old_pick.archived:
        raise Refusal("Later changes depend on this advancement.")
    dependent = old_pick.caused.filter(archived=False)
    if old_skill is not None:
        dependent = dependent.exclude(pk=old_skill.pk)
    if dependent.exists():
        raise Refusal("Later changes depend on this advancement.")
    snapshot = preview_advancement(record, configured, terms)
    pickable, offer, skill = _resolved(record, configured, terms)
    if old_skill is not None:
        op.remove(old_skill, action_record=record, before_pick=old_skill)
    replacement = op.replace_slot_pick(
        selection.slot_assignment,
        configured.slot,
        pickable,
        previous_pick=old_pick,
        miniature=record.fighter,
        action_record=record,
    )
    selection.intended_pick, selection.pick_assignment = pickable, replacement
    selection.save(update_fields=["intended_pick", "pick_assignment", "modified"])
    if skill is not None:
        skill_pick = op.choose(
            replacement,
            skill,
            offer=offer,
            miniature=record.fighter,
            action_record=record,
        )
        skill_selection, _ = SkillSelection.objects.get_or_create(
            action_record=record,
            defaults={
                "mode": offer.mode,
                "access": _skill_access(configured, pickable.pk),
            },
        )
        skill_selection.mode, skill_selection.access = (
            offer.mode,
            _skill_access(configured, pickable.pk),
        )
        skill_selection.skill_set, skill_selection.selected_skill = (
            skill.category,
            skill,
        )
        skill_selection.skill_assignment = skill_pick
        skill_selection.save()
    return snapshot
