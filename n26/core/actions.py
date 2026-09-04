"""Actions on screen — how a gang reads the one it has open.

An ``n26.core.models.Action`` is the state: which act is open, and the two
events that bracket it. This module is the other half — the plain
structure a template draws it by, so that every action reads the same way
whatever it is. Founding and equipping the gang and a trip to the trading
post are the same shape on screen: a title, where the act stands, a
sentence of help, and one button that moves it on.

Nothing here queries beyond asking the gang for its open action, and
nothing here knows HTML.
"""

from dataclasses import dataclass

#: What the button on an open action says. The same for every kind: the
#: card has already named which action it is, so the button need not.
COMPLETE = "Complete action"

#: What the owner is waiting for before they complete the founding.
FOUNDING_HELP = "Click when you have finished hiring and equipping the gang."

#: The same, for a trip to the trading post — where the book also has
#: something to say about what completing it takes away.
VISIT_HELP = (
    "Click when you have finished at the Trading Post. Any unused TP will be discarded."
)


@dataclass(frozen=True)
class ActionCard:
    """One action as a screen draws it.

    ``facts`` is the tally under the title, where the action has figures
    to show — what it brought, what has gone, what is left. An action
    with none is drawn without one rather than with a row of zeroes.

    ``act`` is what the button posts, so one field says which of the two
    controls was clicked and the card carries the value for the state it
    is in.
    """

    title: str
    action: str
    help: str = ""
    facts: tuple = ()
    is_open: bool = True
    button_label: str = COMPLETE
    act: str = "finish"


def card_for(kind, at, *, is_open, help="", facts=()):
    """One action's card, in whichever state it is in.

    The two states are one function because they are one control in two
    positions: open, the button completes the action; closed, it starts
    another. The name comes from the kind either way, so a screen cannot
    call an action something the ledger does not.
    """
    label = kind.label
    if not is_open:
        return ActionCard(
            title=label,
            action=at,
            is_open=False,
            button_label=f"Start the {label} action",
            act="start",
        )
    return ActionCard(title=label, action=at, help=help, facts=facts)


def founding_card(gang, at):
    """The Found and equip gang action for this gang, open or not.

    Drawn on the gang page: open, it offers the button that completes it;
    closed, the control that starts it again. One query — the gang's own
    open action of that kind.
    """
    from n26.core.models import Action

    kind = Action.Kind.FOUNDING
    return card_for(
        kind, at, is_open=gang.open_action(kind) is not None, help=FOUNDING_HELP
    )


def visit_card(receipt, at):
    """The open Visit Trading Post action, as its own page draws it.

    Takes the receipt rather than the gang: what the visit brought and
    what it has left is one arithmetic (``n26.core.trading``), and a card
    that worked it out a second way could disagree with the page it sits on.
    """
    from n26.core.models import Action

    return card_for(
        Action.Kind.TRADING_POST_VISIT,
        at,
        is_open=True,
        help=VISIT_HELP,
        facts=receipt.facts,
    )
