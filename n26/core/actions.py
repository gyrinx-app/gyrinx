"""Actions on screen — what a gang has open, and how to start one.

An ``n26.core.models.Action`` is the state: which act is open, and the two
events that bracket it. This module is the other half — the plain
structures a template draws them by, so that every action reads the same
way whatever it is. Founding and equipping the gang and a trip to the
trading post are the same shape on screen: a title, where the act stands,
a sentence of help, and one button that moves it on.

``ActionsSquare`` gathers them into the one place a gang's page reports
them: a square in the same grid as the stash and the models, so what is
open is read beside what it is being spent on.

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
    "Click when you have finished at the Trading Post. Unspent Trade "
    "Points are lost when you complete the action."
)


@dataclass(frozen=True)
class ActionCard:
    """One open action as a screen draws it.

    ``facts`` is the tally under the title, where the action has figures
    to show — what it brought, what has gone, what is left. An action
    with none is drawn without one rather than with a row of zeroes.

    ``act`` is what the button posts, so one field says which control was
    clicked and the card carries the value for the act it offers.
    """

    title: str
    action: str
    help: str = ""
    facts: tuple = ()
    button_label: str = COMPLETE
    act: str = "finish"


@dataclass(frozen=True)
class VisitLine:
    """An open Visit Trading Post action, in one line.

    A line rather than a card: what the visit is worth is decided and
    spent on its own page, and this says only that it is open and how
    much is left before a reader goes anywhere.
    """

    trade_points_left: int
    href: str


@dataclass(frozen=True)
class ActionsSquare:
    """What a gang has open, and the ways to start something.

    Drawn as one square in the roster grid, ahead of the stash. It is
    there whether or not anything is open: a square that came and went
    would move every card after it, and "nothing is open" is worth
    saying to a reader deciding what to do next.

    ``start_founding`` is where the start form posts, and is empty while
    a founding action is open — the menu then offers the visit alone.
    """

    founding: ActionCard | None = None
    visit: VisitLine | None = None
    start_founding: str = ""
    visit_href: str = ""

    @property
    def anything_open(self):
        return self.founding is not None or self.visit is not None


def open_card(kind, at, *, help="", facts=()):
    """One open action's card. The name comes from the kind, so a screen
    cannot call an action something the ledger does not."""
    return ActionCard(title=kind.label, action=at, help=help, facts=facts)


def founding_card(gang, at):
    """The gang's open Found and equip gang action, or None.

    The gang reads all its open actions in one query and holds them, so
    a page drawing this beside the visit's figure pays for one.
    """
    from n26.core.models import Action

    kind = Action.Kind.FOUNDING
    if gang.open_action(kind) is None:
        return None
    return open_card(kind, at, help=FOUNDING_HELP)


def visit_card(receipt, at):
    """The open Visit Trading Post action, as its own page draws it.

    Takes the receipt rather than the gang: what the visit brought and
    what it has left is one arithmetic (``n26.core.trading``), and a card
    that worked it out a second way could disagree with the page it sits on.
    """
    from n26.core.models import Action

    return open_card(
        Action.Kind.TRADING_POST_VISIT, at, help=VISIT_HELP, facts=receipt.facts
    )


def actions_square(gang, sheet, *, founding_at, visit_at):
    """The gang page's Actions square: what is open, and what may start.

    The visit is read off the sheet rather than the gang, because what an
    open one has left is a ledger query and the sheet has already asked
    it. The founding action costs nothing beyond that: the gang read
    every action it has open in one go, and the sheet already asked.
    """
    founding = founding_card(gang, founding_at)
    visit = None
    if sheet.visiting_trading_post:
        visit = VisitLine(trade_points_left=sheet.trade_points_left, href=visit_at)
    return ActionsSquare(
        founding=founding,
        visit=visit,
        start_founding="" if founding is not None else founding_at,
        visit_href=visit_at,
    )
