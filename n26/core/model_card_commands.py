"""Locked direct model-counter steps shared by native and React equipment controls."""

from dataclasses import dataclass
from uuid import UUID

from django.core.exceptions import ValidationError

from n26.core.equip_purchase import UnavailableEquipment

MOST_A_TALLY_MOVES = 1000


@dataclass
class CounterResult:
    assignment: object | None = None
    value: int | None = None
    change: int = 0
    name: str = ""
    refused: str = ""
    replayed: bool = False
    conflict: bool = False


def tally_step(gang, actor, assignment_key, data, *, require_key=False, model_key=""):
    """Apply a bounded recorded-counter delta once, rechecking access under the gang lock."""
    from n26.core.models import Assignment, EquipReceipt
    from n26.core.operations import Refusal, operation
    from n26.library.models import Counter

    try:
        change = int(data.get("change", ""))
    except ValueError, TypeError:
        raise UnavailableEquipment("Enter an amount to add or remove.") from None
    if not change or abs(change) > MOST_A_TALLY_MOVES:
        raise UnavailableEquipment(
            f"Enter a non-zero amount between {-MOST_A_TALLY_MOVES} and {MOST_A_TALLY_MOVES}."
        )
    try:
        key = UUID(data["request_key"]) if data.get("request_key") else None
    except ValueError, AttributeError:
        return CounterResult(refused="Reload this page before changing the counter.")
    if require_key and key is None:
        return CounterResult(refused="Reload this page before changing the counter.")
    payload = {
        "format": "counter-step-v1",
        "assignment": str(assignment_key),
        "change": change,
        "model": model_key,
    }
    try:
        with operation(gang, actor=actor) as op:
            gang.refresh_from_db()
            if not actor.is_authenticated or gang.owner_id != actor.pk or gang.archived:
                raise Refusal("You can no longer edit this gang.")
            if key:
                receipt = EquipReceipt.objects.filter(
                    gang=gang, request_key=key
                ).first()
                if receipt:
                    if receipt.actor_id != actor.pk or receipt.payload != payload:
                        return CounterResult(
                            refused="This form was already used for a different equipment change. Reload the page.",
                            conflict=True,
                        )
                    return CounterResult(
                        value=receipt.result["value"],
                        name=receipt.result["name"],
                        change=change,
                        replayed=True,
                    )
            try:
                assignment = Assignment.objects.select_related(
                    "counter", "miniature_root__membership"
                ).get(pk=assignment_key, gang_root=gang, archived=False)
            except Assignment.DoesNotExist, ValidationError:
                raise UnavailableEquipment(
                    "That counter is no longer available."
                ) from None
            if (
                not isinstance(assignment.assignable, Counter)
                or assignment.miniature_root is None
                or assignment.miniature_root.membership is None
                or assignment.miniature_root.membership.archived
                or assignment.miniature_root.membership.gang_id != gang.pk
            ):
                raise UnavailableEquipment("That counter is not on an active model.")
            if model_key and str(assignment.miniature_root_id) != model_key:
                raise UnavailableEquipment("That counter is not on this model.")
            name = str(assignment.assignable)
            value = op.tally(assignment, change)
            if key:
                op.record_equip_receipt(key, payload, {"value": value, "name": name})
            return CounterResult(
                assignment=assignment, value=value, change=change, name=name
            )
    except Refusal as error:
        gang.refresh_from_db()
        gang.forget_open_activities()
        return CounterResult(refused=error.public_message)
