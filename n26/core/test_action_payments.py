import pytest

from n26.core.action_payments import Balance, Quote, QuotedLine, Resource


def counter_balance(assignment="counter-1"):
    return Balance(Resource.COUNTER, gang_id="gang-1", assignment_id=assignment)


def test_quote_coalesces_repeated_exact_balances():
    quote = Quote.coalesce(
        [
            QuotedLine(counter_balance(), amount=3, available=5, position=2),
            QuotedLine(counter_balance(), amount=2, available=5, position=1),
        ]
    )

    assert len(quote.lines) == 1
    assert quote.lines[0].amount == 5
    assert quote.lines[0].position == 1
    assert quote.affordable


def test_quote_checks_affordability_after_coalescing():
    quote = Quote.coalesce(
        [
            QuotedLine(counter_balance(), amount=3, available=5),
            QuotedLine(counter_balance(), amount=3, available=5),
        ]
    )

    assert not quote.affordable
    assert quote.lines[0].after_payment == -1


def test_quote_keeps_different_counter_assignments_separate():
    quote = Quote.coalesce(
        [
            QuotedLine(counter_balance("counter-1"), amount=2, available=4),
            QuotedLine(counter_balance("counter-2"), amount=3, available=7),
        ]
    )

    assert [line.amount for line in quote.lines] == [2, 3]


def test_quote_requires_every_resource_in_a_mixed_price():
    quote = Quote.coalesce(
        [
            QuotedLine(
                Balance(Resource.CREDITS, gang_id="gang-1"),
                amount=50,
                available=50,
            ),
            QuotedLine(counter_balance(), amount=4, available=3),
        ]
    )

    assert not quote.affordable


def test_unlimited_credits_are_affordable_and_preserved_in_snapshot():
    quote = Quote.coalesce(
        [
            QuotedLine(
                Balance(Resource.CREDITS, gang_id="gang-1"),
                amount=100,
                available=None,
            ),
            QuotedLine(counter_balance(), amount=2, available=2),
        ]
    )

    assert quote.affordable
    assert quote.lines[0].after_payment is None
    assert quote.snapshot()[0]["available"] is None
    assert quote.snapshot()[0]["after_payment"] is None


def test_counter_balance_cannot_be_unlimited():
    with pytest.raises(ValueError, match="Only a credits balance"):
        QuotedLine(counter_balance(), amount=1, available=None)


def test_quote_snapshot_records_exact_balance_and_review_values():
    quote = Quote.coalesce(
        [
            QuotedLine(
                Balance(Resource.CREDITS, gang_id="gang-1"),
                amount=100,
                available=140,
                name="Credits",
            )
        ]
    )

    assert quote.snapshot() == [
        {
            "resource": "credits",
            "gang_id": "gang-1",
            "assignment_id": None,
            "amount": 100,
            "available": 140,
            "after_payment": 40,
            "position": 0,
            "name": "Credits",
        }
    ]


@pytest.mark.parametrize("amount", [0, -1])
def test_price_component_amount_must_be_positive(amount):
    with pytest.raises(ValueError, match="amount must be positive"):
        QuotedLine(counter_balance(), amount=amount, available=5)
