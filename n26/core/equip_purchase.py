"""Equipment selection, payment and purchase decisions shared by HTTP adapters."""

import json
from dataclasses import asdict, dataclass, replace
from uuid import UUID, uuid4

from django.template.defaultfilters import pluralize

from n26.core.confirm import CONFIRM_FIELD, Confirmation, carried
from n26.core.listing import choice_field as _choice_field
from n26.core.listing import parts_field as _parts_field
from n26.core.listing import price_field as _price_field
from n26.core.owned import thing_key
from n26.core.prices import BadPrice
from n26.core.prices import price_typed as parse_price
from n26.errors import UserFacingError


class UnavailableEquipment(UserFacingError):
    """A catalogue selection cannot be resolved."""


def parts_picked(data, key, line):
    """Resolve submitted part indices against the current line and retain their positions.

    Reject duplicates, negative values and out-of-range indices. Positions also
    identify each part's submitted price field.
    """
    picked, seen = [], set()
    for value in data.getlist(_parts_field(key)):
        # Reject negative indices before Python can index from the end.
        if not value.isdigit():
            raise UnavailableEquipment("No such option")
        index = int(value)
        if index >= len(line.parts) or index in seen:
            raise UnavailableEquipment("No such option")
        seen.add(index)
        picked.append((index, line.parts[index]))
    return picked


def choices_picked(data, key, groups):
    """Resolve alternative indices against the supplied offer groups.

    Reject duplicate or invalid indices. Empty values select no member of an
    optional group. Reuse this parser for purchases and changes to owned options.
    """
    picked = []
    for index, group in enumerate(groups):
        seen = set()
        for value in data.getlist(_choice_field(key, index)):
            if value == "":
                continue
            # Reject negative indices before Python can index from the end.
            if not value.isdigit():
                raise UnavailableEquipment("No such option")
            position = int(value)
            if position >= len(group.options) or position in seen:
                raise UnavailableEquipment("No such option")
            seen.add(position)
            picked.append(group.options[position])
    return picked


def selection_keys(raw):
    try:
        keys = json.loads(raw)
    except ValueError, TypeError:
        raise UnavailableEquipment("Choose the equipment options again.") from None
    if (
        not isinstance(keys, list)
        or any(not isinstance(key, str) or not key for key in keys)
        or len(keys) != len(set(keys))
    ):
        raise UnavailableEquipment("Choose the equipment options again.")
    return keys


def stable_choices(raw, groups):
    offered = {
        option.option_key: option for group in groups for option in group.options
    }
    try:
        return [offered[key] for key in selection_keys(raw)]
    except KeyError:
        raise UnavailableEquipment("Choose the equipment options again.") from None


def selected_parts(raw):
    try:
        parts = json.loads(raw)
    except ValueError, TypeError:
        raise UnavailableEquipment("Choose the weapon profiles again.") from None
    if (
        not isinstance(parts, list)
        or any(
            not isinstance(part, dict)
            or set(part) != {"key", "paid"}
            or not isinstance(part["key"], str)
            or not part["key"]
            or not isinstance(part["paid"], str)
            for part in parts
        )
        or len(parts) != len({part["key"] for part in parts})
    ):
        raise UnavailableEquipment("Choose the weapon profiles again.")
    return parts


def price_typed(data, field, line):
    return parse_price(data, field, line.credits, line.name)


#: Use the same rating checkbox field and value as hiring.
RATE_FIELD, RATE_AT_PAID = "rate", "paid"


def full_price(line, surcharge=0):
    """Use the greater of listing and reference price, plus option surcharges.

    For negatively priced content, retain the listing price as its rating basis.
    """
    if line.credits < 0:
        return line.credits + surcharge
    return max(line.credits, line.thing.reference_price()) + surcharge


def charge(line, paid, surcharge=0, *, rate_at_paid=False):
    """Build recorded payment, list price and discount for one purchase line.

    Add option surcharge to both payment and full price. Normally rating follows
    full price; rate_at_paid adds an explicit lower rating only when payment is
    below full price. Preserve list price for purchase-history interpretation.
    """
    full = full_price(line, surcharge)
    paid = paid + surcharge
    charge = {"paid": paid, "list_price": full, "discount": full - paid}
    if rate_at_paid and paid < full:
        # Preserve full list price: history uses zero list price to identify free bundled profiles.
        charge["rating"] = paid
    return charge


def rating_box(data, charges):
    """Ask whether to rate discounted lines at their actual payment.

    Include only underpriced lines and omit the question after confirmation.
    """
    from n26.core.confirm import Checkbox

    if data.get(CONFIRM_FIELD):
        return None
    below = [
        (line.name, line_paid + surcharge, full_price(line, surcharge))
        for line, line_paid, surcharge in charges
    ]
    below = [(name, paid, full) for name, paid, full in below if paid < full]
    if not below:
        return None
    # Identify every discounted line separately because only selected parts may need lower ratings.
    names = " and ".join(name for name, _, _ in below)
    paid = sum(paid for _, paid, _ in below)
    full = sum(full for _, _, full in below)
    return Checkbox(
        name=RATE_FIELD,
        value=RATE_AT_PAID,
        label="Match rating to price",
        description=(
            f"The full rating for {names} is {full}¢. You pay {paid}¢. "
            "Leave unticked to keep the full rating. "
            f"If your group agrees, tick to use the {paid}¢ payment as the rating."
        ),
    )


def rating_question(data, action, line, spent, checkbox, back):
    """Build a separate rating confirmation when no overspend confirmation already carries it."""
    from n26.core.confirm import Confirmation, carried

    return Confirmation(
        title="Choose the rating",
        lead=f"{line.name} — {spent}¢.",
        heading="You are paying less than the full price",
        body=(
            "Choose whether this equipment keeps its full rating or "
            "uses the price you pay."
        ),
        variant="info",
        checkbox=checkbox,
        confirm_label=f"Buy {line.name}",
        action=action,
        cancel_url=back,
        carry=carried(data, leave_out={RATE_FIELD}),
        confirm_value="1",
    )


def trade_points_asked(line, picked):
    """Sum trade points charged by this line and selected parts.

    Options are credit surcharges only. Lines with no trade-point price charge
    zero points even when their collection uses Trading Post terms.
    """
    asked = line.trade_points if line.charges_trade_points else 0
    return (asked or 0) + sum(
        part.trade_points or 0 for _, part in picked if part.charges_trade_points
    )


def counted_against(gang, line, budget=None):
    """Attribute trade-point purchases to a personal allowance or the gang's open visit.

    Credit-only purchases have no activity. Personal founding allowances take
    precedence over a simultaneous visit.
    """
    if not line.charges_trade_points:
        return None
    return budget.activity if budget is not None else gang.open_visit


def overspend(data, action, gang, line, asked, back, budget=None, holder=""):
    """Ask for confirmation when trade points exceed the current allowance.

    Use personal-budget figures when supplied, otherwise the open visit.
    Without an activity, warn that points will be recorded against none.
    An explicitly confirmed overspend remains permitted.
    """
    from n26.core.confirm import Aside, Fact, carried

    if not asked or data.get(CONFIRM_FIELD) == "tp-overspend":
        return None
    visit = None if budget is not None else gang.open_visit
    open_activity = budget is not None or visit is not None
    if budget is not None:
        brought, spent = budget.granted, budget.spent
    elif visit is not None:
        # Read visit spend once so spent and remaining figures use the same value.
        brought, spent = (visit.trade_points or 0), gang.trade_points_spent
    else:
        brought, spent = 0, 0
    left = brought - spent
    if asked <= left:
        return None
    # Use the model as the personal allowance holder and the gang for an open visit.
    whose = holder if budget is not None and holder else gang.name
    if budget is not None:
        left_over = (
            f"What {whose} has left goes below zero, and stays there until "
            "the action is finished."
        )
    elif visit is not None:
        left_over = (
            "What the action has left goes below zero, and stays there "
            "until it is finished."
        )
    else:
        left_over = (
            "The purchase records trade points without linking them to an action."
        )
    return Confirmation(
        title="Not enough trade points",
        lead=f"{line.name} — {asked} trade point{pluralize(asked)}.",
        heading="Not enough trade points for this purchase",
        body=(
            f"{line.name} uses {asked} trade point{pluralize(asked)}, and "
            f"{whose} has {left}."
        ),
        aside=Aside(lead="You can buy it anyway.", rest=left_over),
        facts=(
            Fact(
                "Available",
                str(brought),
                sub="" if open_activity else "no action open",
            ),
            Fact("Spent", str(spent)),
            Fact("Remaining", str(left), ruled=True, strong=True),
            Fact("This purchase", str(asked)),
            Fact("Remaining after", str(left - asked), ruled=True, strong=True),
        ),
        confirm_label=f"Buy {line.name} anyway",
        action=action,
        cancel_url=back,
        carry=carried(data),
        confirm_value="tp-overspend",
    )


@dataclass(frozen=True)
class PurchaseCatalogue:
    """Fresh offers and allowance for one equipment destination."""

    holder: object
    view: object
    into: str
    collection: str
    budget: object | None = None


@dataclass
class PurchaseResult:
    key: str = ""
    assignment: object | None = None
    confirmation: Confirmation | None = None
    refused: str = ""
    message: str = ""
    facts: dict | None = None
    replayed: bool = False
    conflict: bool = False


def purchase(
    gang,
    user,
    data,
    catalogue,
    *,
    action,
    back,
    activity_seen=None,
    identity=None,
    require_key=False,
):
    """Resolve current offers under the gang lock, then ask or purchase.

    ``catalogue`` reloads the destination and its offers after access is checked.
    A confirmation changes no holdings; the next submission rechecks its figures.
    """
    from n26.core.models import EquipReceipt
    from n26.core.operations import Refusal, operation

    raw_key = data.get("request_key", "")
    try:
        key = UUID(raw_key) if raw_key else None
    except ValueError, AttributeError:
        return PurchaseResult(refused="Reload this page before buying.")
    if key is None and require_key:
        return PurchaseResult(refused="Reload this page before buying.")
    payload = purchase_payload(data, identity or {})
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
                        return PurchaseResult(
                            refused="This form was already used for a different equipment change. Reload the page.",
                            conflict=True,
                        )
                    return recall_purchase(previous.result, action=action, back=back)
            current = catalogue()
            result = _purchase(
                op, current, data, action=action, back=back, activity_seen=activity_seen
            )
            if key is not None and not result.refused:
                if result.confirmation is not None:
                    question = result.confirmation
                    result.confirmation = replace(
                        question,
                        carry=(
                            *(
                                (name, value)
                                for name, value in question.carry
                                if name != "request_key"
                            ),
                            ("request_key", str(uuid4())),
                        ),
                    )
                op.record_equip_receipt(key, payload, purchase_record(result))
            return result
    except (Refusal, BadPrice) as error:
        gang.refresh_from_db()
        gang.forget_open_activities()
        return PurchaseResult(refused=error.public_message)


def _purchase(op, current, data, *, action, back, activity_seen=None):
    from n26.core.models import Miniature

    gang = op.gang
    holder, view, budget = current.holder, current.view, current.budget
    if isinstance(holder, Miniature) and (
        holder.membership.archived or holder.membership.gang_id != gang.pk
    ):
        return PurchaseResult(refused="This model is no longer in the gang.")
    key = data.get("thing", "")
    line = (
        next(
            (line for line in view.all_lines() if thing_key(line.thing) == key),
            None,
        )
        if view is not None
        else None
    )
    if line is None:
        return PurchaseResult(refused="That item is not on this list.")
    if "selection" in data or "parts" in data:
        picks = stable_choices(data.get("selection", ""), line.choices)
        parts = selected_parts(data.get("parts", ""))
        offered_parts = {
            thing_key(part.thing): (index, part)
            for index, part in enumerate(line.parts)
        }
        try:
            picked = [offered_parts[part["key"]] for part in parts]
        except KeyError:
            raise UnavailableEquipment("Choose the weapon profiles again.") from None
        surcharge = sum(option.surcharge for option in picks)
        paid = (
            parse_price(data, "paid", line.credits, line.name, adjustment=surcharge)
            - surcharge
        )
        paid_for = [
            (part, price_typed({"paid": submitted["paid"]}, "paid", part))
            for submitted, (_, part) in zip(parts, picked, strict=True)
        ]
    else:
        picked = parts_picked(data, key, line)
        picks = choices_picked(data, key, line.choices)
        paid = price_typed(data, _price_field(key), line)
        paid_for = [
            (part, price_typed(data, _price_field(key, index), part))
            for index, part in picked
        ]
    surcharge = sum(option.surcharge for option in picks)
    rate_at_paid = data.get(RATE_FIELD) == RATE_AT_PAID
    payment = charge(line, paid, surcharge, rate_at_paid=rate_at_paid)
    asked = trade_points_asked(line, picked)
    expected_personal = data.get("personal_activity")
    current_activity = str(budget.activity.pk) if budget is not None else ""
    observed = current_activity if activity_seen is None else activity_seen
    if asked and (
        (expected_personal is not None and expected_personal != observed)
        or (observed and observed != current_activity)
    ):
        return PurchaseResult(
            refused="This spending action has changed. Reload the page before buying."
        )
    checkbox = rating_box(
        data,
        [(line, paid, surcharge), *((part, amount, 0) for part, amount in paid_for)],
    )
    question = overspend(data, action, gang, line, asked, back, budget, current.into)
    if question is not None:
        if budget is not None:
            question = replace(
                question,
                carry=(
                    *carried(data, leave_out={"personal_activity"}),
                    ("personal_activity", current_activity),
                ),
            )
        return PurchaseResult(
            confirmation=replace(
                question,
                checkbox=checkbox,
                carry=tuple(
                    (name, value)
                    for name, value in question.carry
                    if checkbox is None or name != RATE_FIELD
                ),
            )
        )
    spent = payment["paid"] + sum(amount for _, amount in paid_for)
    if checkbox is not None:
        return PurchaseResult(
            confirmation=rating_question(
                data,
                action,
                line,
                spent,
                checkbox,
                back,
            )
        )
    try:
        bought = op.buy(
            holder,
            line=line,
            option=[option.default_set for option in picks],
            activity=counted_against(gang, line, budget),
            **payment,
        )
        for part, amount in paid_for:
            op.buy(
                bought,
                line=part,
                activity=counted_against(gang, part, budget),
                **charge(part, amount, rate_at_paid=rate_at_paid),
            )
    except ValueError:
        raise UnavailableEquipment("No such option") from None
    extras = [
        *(option.name for option in picks),
        *(part.thing.name for part, _ in paid_for),
    ]
    price = f"{spent}¢" + (f" and {asked} TP" if asked else "")
    description = f"{line.name} with {', '.join(extras)}" if extras else line.name
    return PurchaseResult(
        key=key,
        assignment=bought,
        message=f"Bought {description} for {current.into} — {price}.",
        facts={
            "gang_id": str(gang.pk),
            "thing": line.name,
            "collection": current.collection,
            "paid": spent,
            "trade_points": asked,
            "parts": len(paid_for),
            "options": len(picks),
        },
    )


def purchase_payload(data, identity):
    """Bind a command to its destination, offer scope and submitted payment.

    Catalogue positions remain part of the native input format. Credentials and
    navigation do not change the command's business meaning.
    """
    from django.utils.text import slugify

    if "selection" in data or "parts" in data:
        return {
            "version": 2,
            "action": "buy",
            "identity": identity,
            "thing": data.get("thing", ""),
            "paid": data.get("paid", ""),
            "selection": sorted(selection_keys(data.get("selection", ""))),
            "parts": sorted(
                selected_parts(data.get("parts", "")), key=lambda part: part["key"]
            ),
            "rate": data.get("rate", ""),
            "confirmed": data.get("confirmed", ""),
            "personalActivity": data.get("personal_activity", ""),
        }
    prefix = f"{slugify(data.get('thing', ''))}:"
    names = {"thing", "rate", "confirmed", "personal_activity"}
    return {
        "version": 1,
        "action": "buy",
        "identity": identity,
        "fields": {
            name: data.getlist(name)
            for name in sorted(data)
            if name in names or name.startswith(prefix)
        },
    }


def purchase_record(result):
    return {
        "key": result.key,
        "assignment": str(result.assignment.pk)
        if result.assignment is not None
        else "",
        "message": result.message,
        "facts": result.facts,
        "confirmation": asdict(result.confirmation) if result.confirmation else None,
    }


def recall_purchase(record, *, action, back):
    """Recall a decision without consulting mutable equipment or offer records."""
    from n26.core.confirm import Aside, Checkbox, Fact

    raw = record.get("confirmation")
    question = None
    if raw is not None:
        question = Confirmation(
            **{
                **raw,
                "action": action,
                "cancel_url": back,
                "facts": tuple(Fact(**fact) for fact in raw["facts"]),
                "aside": Aside(**raw["aside"]) if raw["aside"] else None,
                "checkbox": Checkbox(**raw["checkbox"]) if raw["checkbox"] else None,
                "carry": tuple(tuple(field) for field in raw["carry"]),
            }
        )
    return PurchaseResult(
        key=record["key"],
        confirmation=question,
        message=record["message"],
        facts=record["facts"],
        replayed=True,
    )
