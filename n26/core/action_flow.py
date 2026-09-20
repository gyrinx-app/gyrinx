"""Read-only presentation values for a model's action flows.

Access, earned uses and previous uses are read together for the Edit page.
No allowance is granted and no draft is opened while rendering a page.
"""

from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime

from django.db.models import F, Window
from django.db.models.functions import RowNumber

from n26.core.access import actions_for
from n26.core.action_payments import Balance, Quote, QuotedLine, Resource
from n26.core.confirm import Fact
from n26.core.flow import PaymentFigures
from n26.core.models import ActionAllowance, ActionRecord, Assignment
from n26.library.models import Action


@dataclass(frozen=True)
class ActionUseLink:
    key: str
    label: str
    href: str = ""
    detail: str = ""
    when: datetime | None = None


@dataclass
class ActionPanel:
    action_id: str
    name: str
    timing: str
    prices: tuple[PaymentFigures, ...] = ()
    allowance_id: str = ""
    available_uses: int | None = None
    problem: str = ""
    start_href: str = ""
    drafts: list[ActionUseLink] = field(default_factory=list)
    completed: list[ActionUseLink] = field(default_factory=list)


@dataclass(frozen=True)
class ReceiptLine:
    label: str
    value: str


@dataclass(frozen=True)
class PaymentTally:
    """One reviewed payment resource, arranged as a receipt."""

    facts: tuple[Fact, ...]


def payment_figures(quote):
    """Format the same resolved prices used by final checkout."""

    def display(line, value):
        if value is None:
            return "Unlimited"
        suffix = "¢" if line.balance.resource == Resource.CREDITS else ""
        return f"{value}{suffix}"

    return tuple(
        PaymentFigures(
            label="" if line.balance.resource == Resource.CREDITS else line.name,
            available=display(line, line.available),
            price=display(line, line.amount),
            remaining=display(line, line.after_payment),
        )
        for line in quote.lines
    )


def payment_tallies(quote):
    """Stack the reviewed balance, payment and remainder like a receipt."""

    def with_unit(value, label):
        return f"{value} {label}" if label else value

    return tuple(
        PaymentTally(
            (
                Fact("Available", with_unit(figures.available, figures.label)),
                Fact("This action", with_unit(figures.price, figures.label)),
                Fact(
                    "Remaining",
                    with_unit(figures.remaining, figures.label),
                    ruled=True,
                    strong=True,
                ),
            )
        )
        for figures in payment_figures(quote)
    )


def action_panels(fighter, *, card, computed, counter_tracking_active=True):
    """The effective actions and retained earned uses, with bounded reads."""
    access = actions_for(fighter, card=card, computed=computed)
    allowances = list(
        ActionAllowance.objects.filter(fighter=fighter)
        .exclude(
            records__state__in=(
                ActionRecord.State.STARTED,
                ActionRecord.State.COMPLETED,
            )
        )
        .order_by("created", "pk")
    )
    drafts = list(
        ActionRecord.objects.filter(fighter=fighter, state=ActionRecord.State.STARTED)
        .select_related("outcome")
        .order_by("-created", "-pk")
    )
    completed = list(
        ActionRecord.objects.filter(fighter=fighter, state=ActionRecord.State.COMPLETED)
        .annotate(
            action_position=Window(
                expression=RowNumber(),
                partition_by=F("action_id"),
                order_by=(F("created").desc(), F("pk").desc()),
            )
        )
        .filter(action_position__lte=3)
        .select_related("outcome")
        .order_by("-created", "-pk")
    )
    records = [*drafts, *completed]
    available = defaultdict(list)
    for allowance in allowances:
        available[allowance.action_id].append(allowance)
    effective_ids = {found.action.pk for found in access}
    action_ids = (
        effective_ids | set(available) | {record.action_id for record in records}
    )
    if not action_ids:
        return []
    actions = list(
        Action.objects.filter(pk__in=action_ids)
        .select_related("recruitment_allowance_rule", "rank_allowance_rule")
        .prefetch_related("use_price__counter")
        .order_by("name", "pk")
    )
    balances = defaultdict(list)
    for assignment in Assignment.objects.filter(
        gang_root=fighter.gang, counter__isnull=False, archived=False, removes=False
    ).select_related("counter_value", "counter"):
        payer = "fighter" if assignment.miniature_root_id == fighter.pk else "gang"
        if payer == "gang" and assignment.gang_id != fighter.gang.pk:
            continue
        if hasattr(assignment, "counter_value"):
            balances[(payer, assignment.counter_id)].append(assignment)
    credits = fighter.gang.recompute_credits()
    by_action = defaultdict(list)
    for record in records:
        by_action[record.action_id].append(record)
    panels = []
    for action in actions:
        granted = available[action.pk]
        panel = ActionPanel(
            action_id=str(action.pk),
            name=str(action),
            timing=action.get_timing_display(),
            allowance_id=str(granted[0].pk) if granted else "",
            available_uses=len(granted) if action.allowance_rule else None,
        )
        lines = []
        for component in action.use_price.all():
            if component.resource == component.Resource.CREDITS:
                balance = Balance(Resource.CREDITS, str(fighter.gang.pk))
                held = credits
                name = "Credits"
            else:
                matches = balances[(component.payer, component.counter_id)]
                if len(matches) != 1:
                    panel.problem = f"This model needs one {component.counter} counter."
                    break
                assignment = matches[0]
                balance = Balance(
                    Resource.COUNTER, str(fighter.gang.pk), str(assignment.pk)
                )
                held = assignment.counter_value.value
                name = str(component.counter)
            lines.append(
                QuotedLine(balance, component.amount, held, component.position, name)
            )
        if not panel.problem:
            quote = Quote.coalesce(lines)
            panel.prices = payment_figures(quote)
            if not quote.affordable:
                shortfalls = [
                    f"{line.amount - line.available} more {line.name}"
                    for line in quote.lines
                    if line.available is not None and line.amount > line.available
                ]
                panel.problem = f"This flow needs {' and '.join(shortfalls)}."
        if action.pk not in effective_ids and not granted:
            panel.problem = "This model cannot start another flow."
        elif not counter_tracking_active and not panel.problem:
            panel.problem = "This flow is temporarily unavailable."
        for record in by_action[action.pk]:
            if record.state == ActionRecord.State.STARTED:
                panel.drafts.append(
                    ActionUseLink(str(record.pk), f"Resume {action} flow")
                )
            elif (
                record.state == ActionRecord.State.COMPLETED
                and len(panel.completed) < 3
            ):
                panel.completed.append(
                    ActionUseLink(
                        str(record.pk),
                        str(record.outcome or action),
                        detail=_completed_detail(record),
                        when=record.created,
                    )
                )
        panels.append(panel)
    return panels


def _completed_detail(record):
    """Describe a completed choice from its immutable review snapshot."""
    target = record.review.get("target", {})
    if not isinstance(target, dict):
        return ""
    selection = target.get("selection")
    if selection:
        effect = selection.get("effect", "")
        detail = f"{selection['item_name']}: {selection['candidate_tier']}"
        return f"{detail}. {effect[:1].upper()}{effect[1:]}" if effect else detail
    result = target.get("result")
    if result:
        skill = target.get("skill")
        return f"{result}: {skill}" if skill else str(result)
    return ""


def receipt_lines(record):
    """Read what the action's own ledger moved, including later corrections."""
    from n26.core.action_records import action_changes

    changes = action_changes(record)
    lines = [
        ReceiptLine(movement.name, f"{movement.before} → {movement.after}")
        for movement in changes.counters
        if movement.before != movement.after
    ]
    if changes.credits_paid:
        lines.append(ReceiptLine("Credits paid", f"{changes.credits_paid}¢"))
    if changes.rating_delta:
        lines.append(ReceiptLine("Rating", f"{changes.rating_delta:+}¢"))
    return tuple(lines)
