"""Actions on screen — what a gang has open, and how to start one.

An ``n26.core.models.Action`` is the state: which act is open, and the two
events that bracket it. This module is the other half — the plain
structures a template draws them by, so that every action reads the same
way whatever it is. Founding and equipping the gang and a trip to the
trading post are the same shape on screen: a title, where the act stands,
a sentence of help, and one button that moves it on.

``ActionsSquare`` gathers them into the one place a gang's page reports
them: a square in the same grid as the stash and the models, so what is
open is read beside what it is being spent on. It carries the gang's
last few acts too — what has been done is the other half of what is
open, and a reader deciding what to do next wants both in one place.

What the square costs is the gang's open actions and the last stretch
of its story. Nothing here knows HTML.
"""

from dataclasses import dataclass

#: What the button on an open action says. The same for every kind: the
#: card has already named which action it is, so the button need not.
COMPLETE = "Complete action"

#: What the owner is waiting for before they complete the founding.
FOUNDING_HELP = "Click when you have finished hiring and equipping the gang."

#: What being part-way through the founding lets an owner do, under the
#: title. The help beside the button says when to finish; this says what
#: finishing takes away, which is the half a reader needs before they do.
FOUNDING_ABOUT = (
    "While this action is open, fighters with founding Trade Points can spend "
    "them on their equipment lists and at the Trading Post."
)

#: The same, for a trip to the trading post — where the book also has
#: something to say about what completing it takes away.
VISIT_HELP = (
    "Click when you have finished at the Trading Post. Unspent Trade "
    "Points are lost when you complete the action."
)

#: How many acts the square prints. Enough to say what has been going on
#: without becoming the history page, which is one click away.
SNAPSHOT = 5


@dataclass(frozen=True)
class ActionCard:
    """One open action as a screen draws it.

    ``facts`` is the tally under the title, where the action has figures
    to show — what it brought, what has gone, what is left. An action
    with none is drawn without one rather than with a row of zeroes.

    ``act`` is what the button posts, so one field says which control was
    clicked and the card carries the value for the act it offers.

    ``about`` is a sentence under the title saying what the action lets its
    owner do while it stands open — the other half of ``help``, which says
    when to end it. An action with nothing to explain carries none.

    ``marked`` says the founding mark is drawn beside the title: the same
    shape that stands beside every founding Trade Point figure, so a reader
    meets one feature rather than four unrelated screens.
    """

    title: str
    action: str
    help: str = ""
    about: str = ""
    facts: tuple = ()
    button_label: str = COMPLETE
    act: str = "finish"
    marked: bool = False


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
class HistoryLine:
    """One act from the gang's story, as the square prints it.

    ``told`` is the sentence with the actor left off, so a screen can
    draw who did it apart from what they did the way the history page
    does. The sentence is the history's own — the square tells nothing a
    second way.
    """

    when: object
    actor: str
    told: str


@dataclass(frozen=True)
class ActionsSquare:
    """What a gang has open, and the ways to start something.

    Drawn as one square in the roster grid, ahead of the stash. It is
    there whether or not anything is open: a square that came and went
    would move every card after it, and "nothing is open" is worth
    saying to a reader deciding what to do next.

    ``start_founding`` is where the start form posts, and is empty while
    a founding action is open.

    ``history`` is the gang's last few acts, newest first, and is empty
    for a gang nothing has been done to yet. The square says so rather
    than drawing a heading over nothing.
    """

    founding: ActionCard | None = None
    visit: VisitLine | None = None
    history: tuple = ()
    start_founding: str = ""
    history_href: str = ""

    @property
    def anything_open(self):
        return self.founding is not None or self.visit is not None


def open_card(kind, at, *, help="", about="", facts=(), marked=False):
    """One open action's card. The name comes from the kind, so a screen
    cannot call an action something the ledger does not."""
    return ActionCard(
        title=kind.label,
        action=at,
        help=help,
        about=about,
        facts=facts,
        marked=marked,
    )


def founding_card(gang, at):
    """The gang's open Found and equip gang action, or None.

    The gang reads all its open actions in one query and holds them, so
    a page drawing this beside the visit's figure pays for one.
    """
    from n26.core.models import Action

    kind = Action.Kind.FOUNDING
    if gang.open_action(kind) is None:
        return None
    return open_card(kind, at, help=FOUNDING_HELP, about=FOUNDING_ABOUT, marked=True)


def founding_blocks_visit(gang, seen):
    """Whether the way into a Trading Post visit is shut for now.

    A gang holds one action of each kind and performs them one at a
    time, so a control that would start a visit beside an open founding
    is a control that would be refused. It is drawn dead with a reason
    rather than led to a page that says no.

    ``seen`` is whether the founding reaches this reader at all. Every
    gang carries an open founding action, and a reader the feature has
    not opened to is given no way to close one — shutting the button for
    them would take visits away with nothing offered in its place.

    Reads the gang's open actions, which a screen drawing this has
    normally asked for already.
    """
    from n26.core.models import Action

    return bool(seen and gang.open_action(Action.Kind.FOUNDING) is not None)


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


def history_lines(gang, viewer=None, limit=SNAPSHOT):
    """The gang's last few acts as the square prints them, newest first.

    The sentences are built by the history's own builder, so the square
    and the history page cannot describe one act two ways.
    """
    from n26.core import history

    return tuple(
        HistoryLine(
            when=act.when,
            actor=act.actor,
            told="".join(span.text for span in act.spans),
        )
        for act in history.latest(gang, limit=limit, viewer=viewer)
    )


def actions_square(gang, sheet, *, founding_at, visit_at, history_at, viewer=None):
    """The gang page's Actions square: what is open, what has been done,
    and what may start.

    The visit is read off the sheet rather than the gang, because what an
    open one has left is a ledger query and the sheet has already asked
    it. The founding action costs nothing beyond that: the gang read
    every action it has open in one go, and the sheet already asked. The
    story is the one thing here that is nobody else's reading, and it is
    bounded — the last stretch of events, whatever the gang's age.
    """
    founding = founding_card(gang, founding_at)
    visit = None
    if sheet.visiting_trading_post:
        visit = VisitLine(trade_points_left=sheet.trade_points_left, href=visit_at)
    return ActionsSquare(
        founding=founding,
        visit=visit,
        history=history_lines(gang, viewer=viewer),
        start_founding="" if founding is not None else founding_at,
        history_href=history_at,
    )
