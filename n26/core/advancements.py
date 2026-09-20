"""Persist and resolve fighter advancement rolls and skill choices."""

from dataclasses import dataclass
from types import SimpleNamespace

from django.db import transaction
from django.db.models import Q

from n26.core.card import Node, build_card, build_modifier_index, carriers
from n26.core.effects import compute
from n26.core.models import (
    ActionRecord,
    AdvancementSelection,
    Assignment,
    SkillSelection,
)
from n26.core.operations import Refusal


@dataclass(frozen=True)
class AdvancementOption:
    id: str
    name: str
    rating: int
    gainable: bool
    needs_skill: bool
    skill_mode: str
    effect: str = ""


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


def _correction_result(record, *, lock=False):
    """Return and validate the completed result being counterfactually removed."""
    if record.state != ActionRecord.State.COMPLETED:
        return None, None
    query = AdvancementSelection.objects
    if lock:
        query = query.select_for_update(of=("self",))
    try:
        selection = query.select_related("pick_assignment").get(action_record=record)
    except AdvancementSelection.DoesNotExist as error:
        raise Refusal("This action has no advancement result to correct.") from error
    skill_selection = (
        SkillSelection.objects.select_related("skill_assignment")
        .filter(action_record=record)
        .first()
    )
    old_pick = selection.pick_assignment
    old_skill = skill_selection.skill_assignment if skill_selection else None
    if (
        old_pick is None
        or old_pick.archived
        or old_pick.miniature_root_id != record.fighter_id
        or old_pick.chosen_for_id != selection.slot_assignment_id
        or (
            old_skill is not None
            and (
                old_skill.archived
                or old_skill.miniature_root_id != record.fighter_id
                or old_skill.caused_by_id != old_pick.pk
            )
        )
    ):
        raise Refusal("Later changes depend on this advancement.")
    protected = [old_pick.pk]
    if old_skill is not None:
        protected.append(old_skill.pk)
    dependent = Assignment.objects.filter(
        Q(parent_id__in=protected) | Q(caused_by_id__in=protected),
        archived=False,
    )
    if old_skill is not None:
        dependent = dependent.exclude(pk=old_skill.pk)
    if dependent.exists():
        raise Refusal("Later changes depend on this advancement.")
    return selection, skill_selection


def _counterfactual_card(record):
    card = build_card(record.fighter, with_statlines=True)
    selection, skill_selection = _correction_result(record)
    if selection is None:
        return card, None, None
    hidden = {selection.pick_assignment_id}
    if skill_selection and skill_selection.skill_assignment_id:
        hidden.add(skill_selection.skill_assignment_id)

    def without_hidden(nodes):
        kept = []
        for node in nodes:
            if node.assignment is not None and node.assignment.pk in hidden:
                continue
            node.children = without_hidden(node.children)
            kept.append(node)
        return kept

    card.roots = without_hidden(card.roots)
    card.granted = without_hidden(card.granted)
    return card, selection, skill_selection


def _fighter_state(record, additions=()):
    """JSON target facts that can change advancement availability or effects."""
    from n26.core.render import build_model_card

    card, _selection, _skill_selection = _counterfactual_card(record)
    profile = next(node for node in card.all_nodes() if node.is_primary_profile)
    nodes = [
        Node(
            assignable=thing,
            key=("advancement-target", position, thing.pk),
            rating=getattr(thing, "rating_contribution", 0),
            caused_by_key=profile.key,
            chosen_for_key=profile.key,
        )
        for position, thing in enumerate(additions)
    ]
    profile.children.extend(nodes)
    computed = compute(card, build_modifier_index([*carriers(card), *additions]))
    rendered = build_model_card(record.fighter, card=card, computed=computed)
    stored_skills = {
        str(node.assignable.pk)
        for node in card.all_nodes()
        if not node.suppressed
        and node.assignment is not None
        and getattr(node.assignable._meta, "label_lower", "") == "library.skill"
    }
    return {
        "stats": [cell.value for cell in rendered.statline.cells],
        "skills": sorted(
            stored_skills
            | {
                str(contribution.thing.pk)
                for contribution in computed.skills
                if getattr(contribution.thing, "pk", None) is not None
            }
        ),
        "placements": sorted(
            [str(row.category.pk), str(row.section.pk)] for row in computed.placements
        ),
    }


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


def _stat_gainable(fighter, pickable, *, evaluation=None):
    from n26.core.render import build_model_card
    from n26.library.models import ChangesStat

    changes = [
        modifier.effect
        for modifier in pickable.modifiers.all()
        if isinstance(modifier.effect, ChangesStat)
    ]
    if not changes:
        return None
    if evaluation is None:
        card = build_card(fighter, with_statlines=True)
        index = build_modifier_index([*carriers(card), pickable])
        before = build_model_card(fighter, card=card, computed=compute(card, index))
    else:
        card, index, before = evaluation
    node = Node(
        assignable=pickable,
        key=("advancement-preview", pickable.pk),
        rating=pickable.rating_contribution,
    )
    profile = next(line for line in card.all_nodes() if line.is_primary_profile)
    node.caused_by_key = profile.key
    node.chosen_for_key = profile.key
    profile.children.append(node)
    try:
        after = build_model_card(
            fighter,
            card=card,
            computed=compute(card, index),
        )
    finally:
        profile.children.remove(node)
    return [cell.value for cell in before.statline.cells] != [
        cell.value for cell in after.statline.cells
    ]


def _listed_skills(record, offer, *, computed=None, owned=None):
    from n26.core.browse import offered_by, usability_for
    from n26.library.models import Skill
    from n26.library.models.assignable import USABLE_BY_LISTS

    card = None
    if computed is None or owned is None:
        card, _selection, _skill_selection = _counterfactual_card(record)
    if computed is None:
        computed = compute(card, build_modifier_index(carriers(card)))
    question = SimpleNamespace(slot=None, offer=offer, kind_label=offer.kind_label)
    listed = offered_by(question, computed)
    rows = listed.all_lines() if hasattr(listed, "all_lines") else listed
    fighter = usability_for(computed)
    if owned is None:
        owned = {
            node.assignable.pk
            for node in card.all_nodes()
            if node.assignment is not None
            and getattr(node.assignable._meta, "label_lower", "") == "library.skill"
        }
        owned.update(
            contribution.thing.pk
            for contribution in computed.skills
            if getattr(contribution.thing, "pk", None) is not None
        )
    ids = [
        getattr(row, "thing", row).pk
        for row in rows
        if isinstance(getattr(row, "thing", row), Skill)
        and getattr(row, "thing", row).pk not in owned
    ]
    hydrated = {
        skill.pk: skill
        for skill in Skill.objects.filter(pk__in=ids)
        .select_related("category")
        .prefetch_related(*USABLE_BY_LISTS)
    }
    return [
        hydrated[pk]
        for pk in ids
        if pk in hydrated and hydrated[pk].is_usable_by(fighter)
    ]


def _gainable(record, pickable, *, evaluation=None, skills_for=None):
    stat = _stat_gainable(record.fighter, pickable, evaluation=evaluation)
    if stat is not None:
        return stat
    offer = _skill_offer(pickable)
    return (
        bool(skills_for(offer) if skills_for else _listed_skills(record, offer))
        if offer
        else True
    )


def _roll_table(configured):
    """Return active members and the semantic table state bound to a roll."""
    from n26.core.browse import picklist_lines

    members = list(
        picklist_lines(configured.slot.picklist)
        .select_related("pickable")
        .prefetch_related(
            "pickable__modifiers__offers_choice",
            "pickable__modifiers__changes_stat",
        )
    )
    state = {
        "slot_id": str(configured.slot_id),
        "slot_modified": configured.slot.modified.isoformat(),
        "picklist_id": str(configured.slot.picklist_id),
        "picklist_modified": configured.slot.picklist.modified.isoformat(),
        "members": [
            {
                "id": str(member.pk),
                "modified": member.modified.isoformat(),
                "pickable_id": str(member.pickable_id),
                "pickable_modified": member.pickable.modified.isoformat(),
                "roll_low": member.roll_low,
                "roll_high": member.roll_high,
                "modifiers": sorted(
                    [str(modifier.pk), modifier.modified.isoformat()]
                    for modifier in member.pickable.modifiers.all()
                ),
            }
            for member in members
        ],
    }
    return members, state


def record_action_roll(op, record, configured, request_key, *, rolled=None, rng=None):
    """Persist one 2D6 roll and its record-owned slot before any result pick."""
    requested_record = record
    record = _validate_draft(op, record, configured)
    selection, _ = AdvancementSelection.objects.select_for_update().get_or_create(
        action_record=record
    )
    if selection.roll_event_id:
        return selection
    _members, table_state = _roll_table(configured)
    slots_owned_by_other_drafts = (
        AdvancementSelection.objects.filter(
            action_record__state=ActionRecord.State.STARTED,
            slot_assignment__isnull=False,
        )
        .exclude(action_record=record)
        .values("slot_assignment_id")
    )
    bound = list(
        Assignment.objects.select_for_update()
        .filter(
            miniature_root=record.fighter,
            slot=configured.slot,
            caused_by=record.fighter.membership,
            archived=False,
        )
        .exclude(pk__in=slots_owned_by_other_drafts)
        .exclude(caused__pickable__isnull=False, caused__archived=False)[:2]
    )
    if len(bound) > 1:
        raise Refusal("This advancement has more than one available result slot.")
    anchor = (
        bound[0]
        if bound
        else op.assign(
            configured.slot,
            miniature=record.fighter,
            caused_by=record.fighter.membership,
            action_record=record,
        )
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
    record.terms = {
        **record.terms,
        "action_roll_request": str(request_key),
        "advancement_table": table_state,
    }
    record.save(update_fields=["terms", "modified"])
    requested_record.terms = record.terms
    return selection


def advancement_options(record, configured):
    from n26.library.prose import sentence_for

    try:
        selection = record.advancement_selection
    except AdvancementSelection.DoesNotExist as error:
        raise Refusal("Roll 2D6 for this advancement first.") from error
    if not selection.roll_event_id:
        raise Refusal("Roll 2D6 for this advancement first.")
    members, table_state = _roll_table(configured)
    if record.terms.get("advancement_table") != table_state:
        raise Refusal("This advancement table changed after the roll was recorded.")
    landed = configured.slot.picklist.landing(selection.roll_event.roll, members)
    card, _selection, _skill_selection = _counterfactual_card(record)
    index = build_modifier_index(
        [*carriers(card), *(member.pickable for member in members)]
    )
    computed = compute(card, index)
    from n26.core.render import build_model_card

    evaluation = (
        card,
        index,
        build_model_card(record.fighter, card=card, computed=computed),
    )
    owned = {
        node.assignable.pk
        for node in card.all_nodes()
        if node.assignment is not None
        and getattr(node.assignable._meta, "label_lower", "") == "library.skill"
    }
    owned.update(
        contribution.thing.pk
        for contribution in computed.skills
        if getattr(contribution.thing, "pk", None) is not None
    )
    skill_cache = {}

    def skills_for(offer):
        if offer.pk not in skill_cache:
            skill_cache[offer.pk] = _listed_skills(
                record, offer, computed=computed, owned=owned
            )
        return skill_cache[offer.pk]

    offers = {member.pk: _skill_offer(member.pickable) for member in members}
    from n26.core.models import ActionRecord

    gainable = {}
    for member in members:
        offer = offers[member.pk]
        can_gain = _gainable(
            record,
            member.pickable,
            evaluation=evaluation,
            skills_for=skills_for,
        )
        if (
            can_gain
            and record.state == ActionRecord.State.COMPLETED
            and offer is not None
            and offer.mode == offer.Mode.RANDOM
        ):
            recorded = recorded_skill(record, configured, member.pickable_id)
            can_gain = recorded is not None and any(
                skill.pk == recorded.pk for skill in skills_for(offer)
            )
        gainable[member.pk] = can_gain

    gainable_members = [member for member in landed if gainable[member.pk]]
    offered = gainable_members or members
    return tuple(
        AdvancementOption(
            str(member.pickable_id),
            str(member.pickable),
            member.pickable.rating_contribution,
            gainable[member.pk],
            offers[member.pk] is not None,
            offers[member.pk].mode if offers[member.pk] else "",
            " ".join(
                sentence_for(modifier, thing=member.pickable).text
                for modifier, _ in index.for_thing(member.pickable)
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


def recorded_skill(record, configured, pickable_id):
    """Return the immutable random result only when it belongs to this choice."""
    pickable = configured.slot.picklist.members.get(pickable_id=pickable_id).pickable
    offer = _skill_offer(pickable)
    if offer is None or offer.mode != offer.Mode.RANDOM:
        return None
    selection = getattr(record, "skill_selection", None)
    if selection is None:
        return None
    access = _skill_access(configured, pickable_id)
    if record.state != ActionRecord.State.COMPLETED:
        if selection.mode != offer.Mode.RANDOM:
            return None
        skill = selection.selected_skill
        if (
            skill is None
            or selection.access != access
            or selection.skill_set_id != skill.category_id
        ):
            return None
        accepted = any(
            attempt.get("is_available")
            and attempt.get("pickable_id") == str(pickable.pk)
            and attempt.get("skill_id") == str(skill.pk)
            and attempt.get("skill_set_id") == str(skill.category_id)
            for attempt in selection.random_attempts
        )
        return skill if accepted else None
    accepted = next(
        (
            attempt
            for attempt in reversed(selection.random_attempts)
            if attempt.get("is_available")
            and attempt.get("pickable_id") == str(pickable.pk)
            and attempt.get("skill_id")
            and attempt.get("skill_set_id")
            and attempt.get("access", selection.access) == access
        ),
        None,
    )
    if accepted is None:
        return None
    from n26.library.models import Skill

    return Skill.objects.filter(
        pk=accepted["skill_id"], category_id=accepted["skill_set_id"]
    ).first()


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
    from n26.core.browse import picklist_lines

    member = (
        picklist_lines(configured.slot.picklist).filter(pickable_id=pickable_id).first()
    )
    if member is None:
        raise Refusal("That advancement result is not available for this roll.")
    offer = _skill_offer(member.pickable)
    if offer is None or offer.mode != offer.Mode.RANDOM:
        raise Refusal("That advancement result does not use a random skill roll.")
    selection, _ = SkillSelection.objects.select_for_update().get_or_create(
        action_record=record,
        defaults={"mode": "random", "access": _skill_access(configured, pickable_id)},
    )
    for attempt in selection.random_attempts:
        if attempt["request_key"] == str(request_key):
            if attempt.get("pickable_id") != str(pickable_id) or attempt.get(
                "skill_set_id"
            ) != str(skill_set_id):
                raise Refusal(
                    "That request was already used for a different skill roll."
                )
            return attempt
    options = skill_options(record, configured, pickable_id)
    category = next((row for row in options if str(row.pk) == str(skill_set_id)), None)
    if category is None:
        raise Refusal("That skill set is not available for this advancement.")
    access = _skill_access(configured, pickable_id)
    latest = selection.random_attempts[-1] if selection.random_attempts else None
    matching = [
        attempt
        for attempt in selection.random_attempts
        if attempt.get("skill_set_id") == str(category.pk)
        and (
            attempt.get("access") == access
            or (
                "access" not in attempt
                and selection.access == access
                and selection.skill_set_id == category.pk
            )
        )
    ]
    accepted = next(
        (attempt for attempt in reversed(matching) if attempt.get("is_available")),
        None,
    )
    if accepted is not None:
        from n26.library.models import Skill

        selection.access = access
        selection.skill_set = category
        selection.selected_skill = Skill.objects.get(pk=accepted["skill_id"])
        selection.save()
        return accepted
    from n26.library.models import Dice

    if (
        latest is not None
        and not matching
        and (selection.access != access or selection.skill_set_id != category.pk)
    ):
        event_id, result = latest["event_id"], latest["roll"]
    else:
        event = op.roll(
            configured.slot,
            miniature=record.fighter,
            rolled=rolled,
            rng=rng,
            dice=Dice.D6,
            action_record=record,
            note=str(category),
        )
        event_id, result = str(event.pk), event.roll
    from n26.library.models import Skill

    rolled_skill = Skill.objects.filter(category=category, position=result).first()
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
        "pickable_id": str(pickable_id),
        "event_id": event_id,
        "access": access,
        "skill_set_id": str(category.pk),
        "roll": result,
        "skill_id": str(rolled_skill.pk) if rolled_skill else None,
        "result_name": str(rolled_skill) if rolled_skill else None,
        "is_available": available is not None,
        "unavailable_reason": (
            None if available is not None else "No available skill was rolled."
        ),
    }
    selection.random_attempts = [*selection.random_attempts, attempt]
    selection.access = access
    selection.skill_set, selection.selected_skill = category, available
    selection.save()
    return attempt


def _resolved(record, configured, terms):
    pickable_id = str(terms.get("pickable_id", ""))
    options_by_id = {
        option.id: option for option in advancement_options(record, configured)
    }
    if pickable_id not in options_by_id or not options_by_id[pickable_id].gainable:
        raise Refusal("Choose an advancement result available for this roll.")
    pickable = configured.slot.picklist.members.get(pickable_id=pickable_id).pickable
    offer, skill = _skill_offer(pickable), None
    if offer is not None:
        options = skill_options(record, configured, pickable_id)
        if offer.mode == offer.Mode.RANDOM:
            skill = recorded_skill(record, configured, pickable_id)
            available = {row.pk for rows in options.values() for row in rows}
            if skill is None or skill.pk not in available:
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
    snapshot = {
        "roll": selection.roll_event.roll,
        "roll_event_id": str(selection.roll_event_id),
        "slot_assignment_id": str(selection.slot_assignment_id),
        "pickable_id": str(pickable.pk),
        "result": str(pickable),
        "rating": pickable.rating_contribution,
        "skill_id": str(skill.pk) if skill else None,
        "skill": str(skill) if skill else None,
        "skill_mode": offer.mode if offer else None,
        "skill_from_section_id": str(offer.from_section_id) if offer else None,
        "skill_will_be_assigned_to": offer.will_be_assigned_to if offer else None,
        "fighter_state": _fighter_state(record),
        "result_state": _fighter_state(
            record, [pickable, *([skill] if skill is not None else [])]
        ),
    }
    original, original_skill = _correction_result(record)
    if original is not None:
        snapshot["original_result"] = {
            "pick_assignment_id": str(original.pick_assignment_id),
            "pick_modified": original.pick_assignment.modified.isoformat(),
            "pickable_id": str(original.intended_pick_id),
            "skill_assignment_id": (
                str(original_skill.skill_assignment_id)
                if original_skill and original_skill.skill_assignment_id
                else None
            ),
            "skill_modified": (
                original_skill.skill_assignment.modified.isoformat()
                if original_skill and original_skill.skill_assignment_id
                else None
            ),
        }
    return snapshot


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
    selection, skill_selection = _correction_result(record, lock=True)
    old_pick = selection.pick_assignment
    old_skill = skill_selection.skill_assignment if skill_selection else None
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
        roll=selection.roll_event,
    )
    selection.intended_pick, selection.pick_assignment = pickable, replacement
    selection.save(update_fields=["intended_pick", "pick_assignment", "modified"])
    if skill_selection is not None:
        skill_selection.skill_set = None
        skill_selection.selected_skill = None
        skill_selection.skill_assignment = None
        skill_selection.save(
            update_fields=[
                "skill_set",
                "selected_skill",
                "skill_assignment",
                "modified",
            ]
        )
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
