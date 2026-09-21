"""Resolve authored promotions as part of the earned advancement they consume."""

from types import SimpleNamespace

from n26.core.card import build_card, build_modifier_index, carriers
from n26.core.effects import compute
from n26.core.models import ActionRecord, AdvancementSelection
from n26.core.operations import Refusal


def _subtypes(card, computed):
    return {row.thing.pk for row in computed.subtypes} | {
        node.assignable.pk
        for node in card.all_nodes()
        if not node.suppressed
        and not node.broadcast
        and node.assignable._meta.label_lower == "library.subtype"
    }


def promotion_for(record, configured):
    selection = getattr(record, "advancement_selection", None)
    if selection is not None and (
        selection.roll_event_id or "promotion_rule" in record.terms
    ):
        return selection.promotion
    if record.allowance_id is None or record.allowance.threshold is None:
        return None
    rules = list(
        configured.promotions.filter(threshold__lte=record.allowance.threshold)
        .select_related("slot__picklist", "from_subtype")
        .order_by("-threshold")
    )
    if not rules:
        return None
    card = build_card(record.fighter)
    computed = compute(card, build_modifier_index(carriers(card)))
    subtypes = _subtypes(card, computed)
    present_rules = {row.thing.pk for row in computed.rules}
    present_rules.update(
        node.assignable.pk
        for node in card.all_nodes()
        if not node.suppressed
        and not node.broadcast
        and node.assignable._meta.label_lower == "library.rule"
    )
    return next(
        (
            rule
            for rule in rules
            if rule.from_subtype_id in subtypes
            and (
                rule.requires_rule_id is None or rule.requires_rule_id in present_rules
            )
        ),
        None,
    )


def may_decline(record, promotion):
    return bool(
        promotion
        and promotion.replaces_advancement
        and promotion.optional_profiles.filter(
            pk=record.fighter.membership.profile_id
        ).exists()
    )


def replaces_roll(record, configured):
    promotion = promotion_for(record, configured)
    selection = getattr(record, "advancement_selection", None)
    declined = bool(
        selection and selection.roll_event_id and record.terms.get("decline_promotion")
    )
    return bool(promotion and promotion.replaces_advancement and not declined)


def result_slot(record, configured):
    promotion = promotion_for(record, configured)
    if promotion and replaces_roll(record, configured):
        return promotion.slot
    return configured.slot


def promotion_state(record, configured):
    """Bind review to the promotion's effects and the model's current subtype."""
    promotion = promotion_for(record, configured)
    if promotion is None:
        return None
    from n26.core.advancements import _counterfactual_card, _roll_table

    card, _, _ = _counterfactual_card(record)
    computed = compute(card, build_modifier_index(carriers(card)))
    subtypes = sorted(str(pk) for pk in _subtypes(card, computed))
    if str(promotion.from_subtype_id) not in subtypes:
        raise Refusal("This model's rank changed. Review its promotion again.")
    _, table = _roll_table(
        SimpleNamespace(slot=promotion.slot, slot_id=promotion.slot_id)
    )
    return {
        "rule": str(promotion.pk),
        "modified": promotion.modified.isoformat(),
        "subtypes": subtypes,
        "table": table,
        "declined": bool(record.terms.get("decline_promotion")),
        "stash": [
            {
                "id": str(item.pk),
                "modified": item.modified.isoformat(),
                "name": str(item.assignable),
            }
            for item in weapons_to_stash(record, configured)
        ],
    }


def weapons_to_stash(record, configured):
    """Equipment removed by a promotion, evaluated before the new subtype applies."""
    if record.state == ActionRecord.State.COMPLETED:
        return []
    promotion = promotion_for(record, configured)
    if (
        not promotion
        or not replaces_roll(record, configured)
        or not promotion.stash_weapons_for.filter(
            pk=record.fighter.membership.profile_id
        ).exists()
    ):
        return []
    if promotion.keep_weapon_trait_id is None:
        raise Refusal("This promotion has no equipment rule configured.")
    from n26.library.models import Weapon

    card = build_card(record.fighter)
    computed = compute(card, build_modifier_index(carriers(card)))
    result = []
    for node in card.all_nodes():
        if node.suppressed or node.broadcast or not isinstance(node.assignable, Weapon):
            continue
        profiles = [
            child
            for child in node.children
            if child.is_weapon_profile and not child.suppressed
        ]
        if profiles and all(
            str(promotion.keep_weapon_trait) in computed.weapons[child.key].trait_names
            for child in profiles
        ):
            continue
        if node.assignment is None:
            raise Refusal(
                f"Remove this model's granted weapons without {promotion.keep_weapon_trait} before promoting it."
            )
        result.append(node.assignment)
    return result


def stash_promotion_weapons(op, record, configured):
    for weapon in weapons_to_stash(record, configured):
        op.move(weapon, op.gang.stash, note="Promotion", action_record=record)


def remove_unfinished_promotion(op, record, selection):
    """Remove the record-owned choice when it is cancelled or declined."""
    if (
        selection
        and selection.promotion_id
        and not selection.roll_event_id
        and selection.slot_assignment_id
    ):
        if selection.pick_assignment_id:
            raise Refusal("This promotion already has a result.")
        op.remove(selection.slot_assignment, action_record=record)


def prepare_promotion(op, record, configured):
    from n26.core.advancements import _validate_draft

    record = _validate_draft(op, record, configured)
    promotion = promotion_for(record, configured)
    if not replaces_roll(record, configured):
        raise Refusal("Roll for this advancement before choosing a result.")
    selection, _ = AdvancementSelection.objects.get_or_create(action_record=record)
    if selection.slot_assignment_id is None:
        selection.slot_assignment = op.assign(
            promotion.slot,
            miniature=record.fighter,
            caused_by=record.fighter.membership,
            action_record=record,
        )
        selection.promotion = promotion
        selection.save(update_fields=["slot_assignment", "promotion", "modified"])
    record.terms = {**record.terms, "promotion_rule": str(promotion.pk)}
    record.save(update_fields=["terms", "modified"])
    return record


def apply_bonus_promotion(op, record, selection, pick):
    promotion = selection.promotion
    if promotion is None or promotion.replaces_advancement:
        return
    choices = list(promotion.slot.picklist.members.select_related("pickable"))
    if len(choices) != 1:
        raise ValueError("A promotion after an advancement needs exactly one result.")
    anchor = op.assign(
        promotion.slot,
        miniature=record.fighter,
        caused_by=pick,
        action_record=record,
    )
    selection.promotion_assignment = op.choose(
        anchor,
        choices[0].pickable,
        slot=promotion.slot,
        miniature=record.fighter,
        action_record=record,
    )
    selection.save(update_fields=["promotion_assignment", "modified"])


def require_earliest_allowance(fighter, action, allowance):
    """Resolve earlier ranks before a promotion changes later rank behaviour."""
    if allowance is None or allowance.threshold is None:
        return
    configured = next(
        (
            row.outcome.operation
            for row in action.outcomes.select_related("outcome")
            if row.outcome.resolve_advancement_id
        ),
        None,
    )
    if (
        configured is None
        or promotion_for(
            SimpleNamespace(
                fighter=fighter,
                allowance=allowance,
                allowance_id=allowance.pk,
                terms={},
            ),
            configured,
        )
        is None
    ):
        return
    pending = fighter.action_allowances.filter(
        action=action,
        source=fighter.membership,
        threshold__lt=allowance.threshold,
    ).exclude(records__state=ActionRecord.State.COMPLETED)
    if pending.exists():
        raise Refusal("Complete the earlier earned advancement first.")
