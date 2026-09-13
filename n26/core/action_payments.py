"""Resolved action prices, before any balance is changed.

Library price components describe what a use asks for. A quote resolves each
one to the exact gang or counter assignment that would pay it, captures the
available value, and coalesces repeated references. The operation layer can
then compare the snapshot under the gang lock before writing payment events.
"""

from dataclasses import dataclass
from enum import StrEnum


class Resource(StrEnum):
    CREDITS = "credits"
    COUNTER = "counter"


@dataclass(frozen=True)
class Balance:
    """The exact stored balance one or more price components resolve to."""

    resource: Resource
    gang_id: str
    assignment_id: str | None = None

    def __post_init__(self):
        if self.resource == Resource.CREDITS and self.assignment_id is not None:
            raise ValueError("A credits balance belongs to the gang.")
        if self.resource == Resource.COUNTER and self.assignment_id is None:
            raise ValueError("A counter balance needs an assignment.")

    def snapshot(self):
        return {
            "resource": self.resource.value,
            "gang_id": self.gang_id,
            "assignment_id": self.assignment_id,
        }


@dataclass(frozen=True)
class QuotedLine:
    """One resolved debit, including the balance seen during review."""

    balance: Balance
    amount: int
    available: int
    position: int = 0
    name: str = ""

    def __post_init__(self):
        if self.amount <= 0:
            raise ValueError("A price component amount must be positive.")
        if self.available < 0:
            raise ValueError("An available balance cannot be negative.")
        if self.position < 0:
            raise ValueError("A price component position cannot be negative.")

    @property
    def after_payment(self):
        return self.available - self.amount

    def snapshot(self):
        return {
            **self.balance.snapshot(),
            "amount": self.amount,
            "available": self.available,
            "after_payment": self.after_payment,
            "position": self.position,
            "name": self.name,
        }


@dataclass(frozen=True)
class Quote:
    """Every required debit for one action use, in display order."""

    lines: tuple[QuotedLine, ...] = ()

    @classmethod
    def coalesce(cls, lines):
        """Combine repeated exact balances without losing their first order."""
        combined = {}
        for line in lines:
            previous = combined.get(line.balance)
            if previous is None:
                combined[line.balance] = line
                continue
            if previous.available != line.available:
                raise ValueError("Repeated price components disagree on the balance.")
            combined[line.balance] = QuotedLine(
                balance=line.balance,
                amount=previous.amount + line.amount,
                available=line.available,
                position=min(previous.position, line.position),
                name=previous.name or line.name,
            )
        return cls(tuple(sorted(combined.values(), key=lambda line: line.position)))

    @property
    def affordable(self):
        return all(line.after_payment >= 0 for line in self.lines)

    def snapshot(self):
        return [line.snapshot() for line in self.lines]

    def matches(self, snapshot):
        """Whether a submitted review is exactly the quote now available."""
        return self.snapshot() == snapshot
