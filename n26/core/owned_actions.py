"""Validated equipment actions shared by native and JSON command views."""

from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError

from n26.core.equip_purchase import (
    UnavailableEquipment,
    choices_picked,
    selection_keys,
    stable_choices,
)
from n26.core.owned import (
    can_unbolt,
    is_built_in_profile,
    is_detachable,
    is_possession,
    thing_key,
)


@dataclass(frozen=True)
class Touched:
    key: str
    miniature: object | None


def row_behind(assignment):
    node = assignment
    while node.parent_id is not None:
        node = node.parent
    return Touched(key=thing_key(node.assignable), miniature=node.miniature_root)


@dataclass
class OwnedResult:
    assignment: object | None = None
    touched: Touched | None = None
    also: str = ""
    message: str = ""
    tone: str = "success"
    refused: str = ""
    changed: bool = False
    verb: str = "update"
    facts: dict | None = None
    detached_to_stash: bool = False
    replayed: bool = False
    conflict: bool = False


def change(
    gang,
    user,
    action,
    assignment_key,
    data,
    *,
    include_staged=False,
    require_key=False,
):
    """Recheck access and the current possession under the gang's write lock."""
    from n26.core.models import Assignment, EquipReceipt
    from n26.core.operations import Refusal, operation

    raw_key = data.get("request_key", "")
    try:
        key = UUID(raw_key) if raw_key else None
    except ValueError, AttributeError:
        return OwnedResult(refused="Reload this page before changing equipment.")
    if key is None and require_key:
        return OwnedResult(refused="Reload this page before changing equipment.")
    payload = owned_payload(action, assignment_key, data)
    try:
        with operation(gang, actor=user) as op:
            gang.refresh_from_db()
            gang.forget_open_activities()
            if not user.is_authenticated or gang.owner_id != user.pk or gang.archived:
                raise Refusal("You can no longer equip this gang.")
            if key is not None:
                previous = EquipReceipt.objects.filter(
                    gang=gang, request_key=key
                ).first()
                if previous is not None:
                    if previous.actor_id != user.pk or previous.payload != payload:
                        return OwnedResult(
                            refused="This form was already used for a different equipment change. Reload the page.",
                            conflict=True,
                        )
                    return recall_owned(previous.result)
            try:
                assignment = Assignment.objects.select_related(
                    "ledger_entry",
                    "miniature_root",
                    "parent",
                    "gang_root",
                ).get(pk=assignment_key, gang_root=gang, archived=False)
            except Assignment.DoesNotExist, ValidationError:
                raise UnavailableEquipment("No such possession") from None
            if not is_possession(assignment.assignable):
                raise UnavailableEquipment("Not something the gang owns")
            result = OwnedResult(
                assignment=assignment,
                touched=row_behind(assignment),
                facts={
                    "gang_id": str(gang.pk),
                    "miniature_id": str(assignment.miniature_root_id)
                    if assignment.miniature_root_id
                    else None,
                    "thing": str(assignment.assignable),
                    "action": action,
                },
            )
            if action in {"sell", "refund", "remove"} and is_built_in_profile(
                assignment
            ):
                parent = (
                    str(assignment.parent.assignable)
                    if assignment.parent_id
                    else "the weapon"
                )
                name = assignment.assignable.name or str(assignment.assignable)
                raise Refusal(
                    f"You cannot {action} {name} on its own. It comes with {parent}."
                )
            if action == "sell":
                _sell(op, assignment, data, result)
            elif action == "reassign":
                _reassign(op, assignment, data, result)
            elif action == "rechoose":
                _rechoose(op, assignment, data, result)
            elif action == "accessorise":
                _accessorise(
                    op, assignment, data, result, include_staged=include_staged
                )
            elif action in {"remove", "refund"}:
                _remove(op, assignment, action, result)
            else:
                raise UnavailableEquipment("No such equipment action")
            if key is not None:
                op.record_equip_receipt(key, payload, owned_record(result))
            return result
    except Refusal as error:
        gang.refresh_from_db()
        gang.forget_open_activities()
        return OwnedResult(refused=error.public_message)


def _sell(op, assignment, data, result):
    from n26.core.operations import detachable_children

    name = str(assignment.assignable)
    stash = getattr(op.gang, "stash", None)
    keeping = (
        []
        if data.get("accessories") == "sell" or stash is None
        else detachable_children(assignment)
    )
    for child in keeping:
        op.move(child, stash)
    proceeds = op.sell(assignment)
    if proceeds is None:
        result.message = f"{name} was already removed."
        result.tone = "info"
        return
    result.changed = True
    result.verb = "archive"
    result.facts.update(proceeds=proceeds, stashed=len(keeping))
    kept = ", ".join(str(child.assignable) for child in keeping)
    result.message = f"Sold {name} for {proceeds}¢."
    if kept:
        result.message += f" {kept} went to the stash."


def _reassign(op, assignment, data, result):
    from n26.core.models import Assignment, Miniature
    from n26.core.operations import Refusal

    name = str(assignment.assignable)
    came_from = assignment.miniature_root
    off = str(assignment.parent.assignable) if assignment.parent_id else ""
    stays_on = (
        f"You cannot take {name} off {off}. Only a bought accessory can come off."
    )
    if (
        assignment.parent_id is not None
        and assignment.caused_by_id is not None
        and is_detachable(assignment.assignable)
    ):
        raise Refusal(stays_on)
    wanted = data.get("to")
    if wanted == "stash":
        destination = getattr(op.gang, "stash", None)
    elif wanted == "held":
        if assignment.parent_id is None:
            destination = None
        elif not can_unbolt(assignment):
            raise Refusal(stays_on)
        else:
            destination = came_from or getattr(op.gang, "stash", None)
    elif wanted == "weapon":
        try:
            destination = (
                Assignment.objects.filter(
                    pk=data.get("weapon", ""),
                    gang_root=op.gang,
                    archived=False,
                )
                .exclude(weapon=None)
                .exclude(pk=assignment.pk)
                .exclude(pk=assignment.parent_id)
                .first()
            )
        except ValidationError:
            destination = None
    else:
        try:
            destination = Miniature.objects.filter(
                pk=data.get("miniature", ""),
                membership__gang=op.gang,
                membership__archived=False,
            ).first()
        except ValidationError:
            destination = None
    if destination is None:
        raise Refusal(f"There is nowhere to move {name} to.")
    if wanted == "held":
        result.also = thing_key(assignment.assignable)
    elif isinstance(destination, Assignment):
        landed = row_behind(destination)
        if landed.miniature == result.touched.miniature:
            result.also = landed.key
    op.reassign(assignment, destination)
    result.changed = True
    result.facts["to"] = wanted if wanted in {"stash", "weapon", "held"} else "model"
    if wanted == "stash":
        result.message = f"Moved {name} to the stash."
    elif wanted == "weapon":
        result.message = f"Fitted {name} to {destination.assignable}."
    elif wanted == "held":
        result.message = f"Took {name} off {off}."
        if came_from is None:
            result.message += " It is in the stash."
            result.detached_to_stash = True
    else:
        result.message = f"Moved {name} to {destination.name}."


def _rechoose(op, assignment, data, result):
    from n26.core.browse import offered_choices
    from n26.library.models.assignable import Optioned

    thing = assignment.assignable
    if not isinstance(thing, Optioned) or not thing.offers_a_choice:
        raise UnavailableEquipment("Nothing to choose")
    picked = (
        stable_choices(data["selection"], offered_choices(thing))
        if "selection" in data
        else choices_picked(data, thing_key(thing), offered_choices(thing))
    )
    taken = {row.default_set_id for row in assignment.chosen_options.all()}
    entry = getattr(assignment, "ledger_entry", None)
    before = entry.paid if entry is not None else 0
    try:
        op.rechoose(assignment, option=[option.default_set for option in picked])
    except ValueError:
        raise UnavailableEquipment("Choose the equipment options again.") from None
    if entry is not None:
        entry.refresh_from_db()
    after = entry.paid if entry is not None else 0
    result.facts["delta"] = after - before
    now = {row.default_set_id for row in assignment.chosen_options.all()}
    if now == taken:
        result.message = f"{thing}'s options are unchanged."
        return
    result.changed = True
    holds = ", ".join(option.name for option in thing.options_taken(now))
    settled = (
        f" — {after - before}¢ more."
        if after > before
        else f" — {before - after}¢ back."
        if after < before
        else "."
    )
    result.message = f"{thing} now has {holds}{settled}"


def _accessorise(op, assignment, data, result, *, include_staged):
    from n26.core.operations import Refusal
    from n26.library.models import Weapon, WeaponAccessory

    if not isinstance(assignment.assignable, Weapon):
        raise UnavailableEquipment("Not a weapon")
    try:
        accessory = WeaponAccessory.objects.selectable(
            include_staged=include_staged
        ).get(pk=data.get("accessory", ""))
    except WeaponAccessory.DoesNotExist, ValidationError, ValueError:
        raise Refusal("That accessory does not fit this weapon.") from None
    bought = op.buy(assignment, thing=accessory)
    result.assignment = bought
    result.changed = True
    result.verb = "create"
    result.facts.update(
        thing=accessory.name, onto=str(assignment.assignable), paid=bought.rating
    )
    result.message = f"Fitted {accessory.name} to {assignment.assignable} — {bought.ledger_entry.paid}¢."


def _remove(op, assignment, action, result):
    from n26.core.operations import refund_of, trade_points_in

    name = str(assignment.assignable)
    if action == "refund":
        refunding, paid = refund_of(assignment)
        points = trade_points_in(refunding)
        if op.gang.credits_unlimited and not points:
            action = "remove"
    removed = op.refund(assignment) if action == "refund" else op.remove(assignment)
    if removed is None:
        result.message = f"{name} was already removed."
        result.tone = "info"
        return
    result.changed = True
    result.verb = "archive"
    result.facts["action"] = action
    if action == "refund":
        result.facts.update(refunded=paid, trade_points=points)
        result.message = (
            f"Refunded {name} — {refund_words(op.gang, paid, points)} back."
        )
    else:
        result.message = f"Removed {name}."


def refunded_credits(gang, paid):
    """Return recorded credit payment only when the gang tracks a credit budget."""
    return 0 if gang.credits_unlimited else paid


def refund_words(gang, paid, trade_points):
    """Describe refundable credits and founding trade points, omitting unused resources."""
    from django.template.defaultfilters import pluralize

    credits = refunded_credits(gang, paid)
    if not trade_points:
        return f"{credits}¢"
    points = f"{trade_points} trade point{pluralize(trade_points)}"
    return f"{credits}¢ and {points}" if credits else points


def removal_words(gang, paid, trade_points):
    """Explain that removal returns nothing and identify any available refund alternative."""
    if not gang.credits_unlimited:
        return "No credits are returned. Use Refund instead to recover the amount paid."
    if trade_points:
        return (
            "No trade points are returned. Use Refund instead to recover "
            f"{refund_words(gang, paid, trade_points)}."
        )
    return "Removal does not refund the purchase."


def owned_payload(action, assignment_key, data):
    names = {"accessories", "to", "weapon", "miniature", "accessory"}
    if "selection" in data:
        return {
            "version": 2,
            "action": action,
            "assignment": str(assignment_key),
            "selection": sorted(selection_keys(data["selection"])),
            "fields": {
                name: data.getlist(name) for name in sorted(names) if name in data
            },
        }
    return {
        "version": 1,
        "action": action,
        "assignment": str(assignment_key),
        "fields": {
            name: data.getlist(name)
            for name in sorted(data)
            if name in names or ":option:" in name
        },
    }


def owned_record(result):
    return {
        "touched": {
            "key": result.touched.key,
            "miniature": str(result.touched.miniature.pk)
            if result.touched.miniature
            else "",
        },
        "also": result.also,
        "message": result.message,
        "tone": result.tone,
        "changed": result.changed,
        "detachedToStash": result.detached_to_stash,
    }


def recall_owned(record):
    from n26.core.models import Miniature

    miniature = (
        Miniature.objects.filter(pk=record["touched"]["miniature"]).first()
        if record["touched"]["miniature"]
        else None
    )
    return OwnedResult(
        touched=Touched(record["touched"]["key"], miniature),
        also=record["also"],
        message=record["message"],
        tone=record["tone"],
        changed=record["changed"],
        detached_to_stash=record["detachedToStash"],
        replayed=True,
    )
