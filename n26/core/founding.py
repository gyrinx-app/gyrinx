"""Founding budgets — what one model may spend while the gang is new.

Some gangs let a model buy across every list it can reach on a single
allowance of Trade Points, but only as it joins: a Venator Hunt Leader
has 5 to spend over the list its Gang Legacy grants and the Trading Post
together, an Outcast Champion 3 over the affiliation's list, the Outcast
list and the post. The books call it a combined figure, and combined is
the whole of it — an equipment list counts Trade Points here where
nowhere else does.

The allowance belongs to the model, not to the gang, and it stands while
the gang's Found and equip gang action is open. So it is kept the way
everything else in this edition is kept: what a model may spend is a
counter reading off its computed card, which content raises and no
column stores, and what it has spent is the ledger's answer — every
purchase that recorded the founding action, on that model. A refund
returns to the same action because its event sits on the assignment the
purchase made; a sale returns nothing, as it never returns Trade Points.

Closing the action and starting it again gives a fresh figure, which is
what an owner wants after hiring somebody new: spend is counted per
action, so the old one's purchases stay on the old one.
"""

from dataclasses import dataclass


def budget_granted(computed):
    """What this model may spend at founding, read off its computed card.

    No query where nothing raises the counter, which is every model in
    every gang whose books grant no such allowance: the contributions are
    already on the card, and only one that names this counter is worth
    asking the library about.

    Pinned to the standard counter, as every reader of one is: counter
    names are unique per pack, so a homebrew pack's counter of the same
    name must not stand in for it. That is one query, and only where a
    contribution named the counter — a model with none pays nothing to
    find that out.
    """
    from n26.library.standard_content import founding_budget_counter

    if not _names_the_counter(computed):
        return 0
    standard = founding_budget_counter()
    if standard is None:
        return 0
    return _raised_by(computed, standard)


def _names_the_counter(computed):
    """Whether anything on this card raises the founding allowance, by
    the counter's name alone. Settled without a query, which is what
    keeps a model with no allowance costing what it always did."""
    from n26.library.standard_content import FOUNDING_BUDGET_COUNTER

    wanted = FOUNDING_BUDGET_COUNTER.casefold()
    return any(
        contribution.counter.name.casefold() == wanted
        for contribution in computed.counter_contributions
    )


def _raised_by(computed, standard):
    """What this card raises the standard counter by. Pinned to the row
    rather than the name: a homebrew pack's counter called the same thing
    is a different counter and grants nothing here."""
    return sum(
        contribution.amount
        for contribution in computed.counter_contributions
        if contribution.counter.pk == standard.pk
    )


@dataclass(frozen=True)
class FoundingBudget:
    """One model's founding allowance, as the figures it is read by.

    Built for the screen rather than stored: what the model may spend is
    what its card says, what it has spent is what the ledger says, and
    neither is a second copy of anything.

    ``action`` is the gang's open Found and equip gang action — the row
    a purchase on this screen records, so that what has gone can be
    summed back off it.
    """

    action: object
    granted: int
    spent: int

    @property
    def remaining(self):
        """What is left. Goes negative where the owner said they meant to
        overspend, which is what the question before such a purchase is
        for: Trade Points inform, and only credits are refused."""
        return self.granted - self.spent

    @property
    def facts(self):
        """The budget as a tally: what it holds, what has gone, what is
        left. Drawn by ``<c-n26.tally>``, which the Visit Trading Post
        card and the overspend question draw too — one arithmetic, one
        shape."""
        from n26.core.confirm import Fact

        return (
            Fact("Available", str(self.granted)),
            Fact("Spent", str(self.spent)),
            Fact("Remaining", str(self.remaining), ruled=True, strong=True),
        )


def budget_for(gang, miniature, computed):
    """This model's founding budget, or None where it has none.

    None covers both halves of "none": a model whose card raises the
    counter by nothing, and a gang whose founding action is complete. The
    first is settled without a query, so a screen for a model with no
    allowance asks exactly what it did before this existed.

    Three queries where there is one: the standard counter, so a
    homebrew one of the same name is not mistaken for it; which actions
    the gang has open — held on the gang, so a purchase on the same
    request reads it again for free — and what this model has already
    spent under the founding one.
    """
    from n26.core.models import Action
    from n26.core.reconcile import trade_points_spent_by

    granted = budget_granted(computed)
    if granted <= 0:
        return None
    action = gang.open_action(Action.Kind.FOUNDING)
    if action is None:
        return None
    return FoundingBudget(
        action=action,
        granted=granted,
        spent=trade_points_spent_by(action, miniature),
    )


def budgets_by_model(gang, computed):
    """Every model's founding budget under the open action, and nothing
    at all where no founding action is open or nobody on the roster has
    an allowance.

    ``computed`` is each member's fold, keyed by model id, off the card
    the roster was dealt from. What a model may spend is already in
    there; what it has spent is the ledger's. Keyed by the id written
    out, which is how a drawn card carries its model's — the two sides of
    this join arrive from different queries and only the written form is
    the same on both.

    A fixed cost for the whole roster rather than a query a fighter: the
    standard counter is asked for once, and what has gone is one sum
    grouped by whoever spent it. A gang whose books grant no such
    allowance pays for neither — nothing on any of its cards names the
    counter.
    """
    from n26.core.models import Action
    from n26.core.reconcile import trade_points_spent_by_model
    from n26.library.standard_content import founding_budget_counter

    named = {
        model_id: fold
        for model_id, fold in computed.items()
        if _names_the_counter(fold)
    }
    if not named:
        return {}
    action = gang.open_action(Action.Kind.FOUNDING)
    if action is None:
        return {}
    standard = founding_budget_counter()
    if standard is None:
        return {}
    spent = {
        str(model_id): total
        for model_id, total in trade_points_spent_by_model(action).items()
    }
    budgets = {}
    for model_id, fold in named.items():
        granted = _raised_by(fold, standard)
        if granted <= 0:
            continue
        budgets[str(model_id)] = FoundingBudget(
            action=action, granted=granted, spent=spent.get(str(model_id), 0)
        )
    return budgets
