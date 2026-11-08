"""Build display structures for open activities and available next steps.

Activity records hold their state and opening or closing events. These
dataclasses describe titles, balances, help and controls without HTML.

``ActivitiesSquare`` occupies the roster's first cell beside the stash,
including when no activity is open. It links to history without listing
events. Reads use the gang's cached open activities.
"""

from dataclasses import dataclass

#: What the button on an open action says. The same for every kind: the
#: card has already named which action it is, so the button need not.
COMPLETE = "Complete action"

#: What the owner is waiting for before they complete the founding.
FOUNDING_HELP = "Complete when you have finished hiring and equipping the gang. Unspent Trade Points become unavailable."

#: Explain the allowance available while founding remains open.
FOUNDING_ABOUT = (
    "While this action is open, fighters with founding Trade Points can spend "
    "them at the Trading Post."
)

#: The same, for a trip to the trading post — where the book also has
#: something to say about what completing it takes away.
VISIT_HELP = "Complete when you have finished at the Trading Post. Unspent Trade Points are lost."

POST_BATTLE_HELP = "Record XP, credits and each model's results after a battle."

#: Maximum entries in the compact history read.
SNAPSHOT = 5


@dataclass(frozen=True)
class ActivityCard:
    """An open activity's title, facts and completion control.

    ``facts`` contains available balance figures. ``act`` identifies the command.
    ``about`` explains the open activity; ``help`` explains completion.
    ``marked`` displays the shared founding allowance symbol.
    """

    title: str
    action: str
    help: str = ""
    about: str = ""
    facts: tuple = ()
    button_label: str = COMPLETE
    act: str = "finish"
    marked: bool = False
    activity_id: str = ""


@dataclass(frozen=True)
class VisitLine:
    """An open Trading Post visit's remaining points and destination."""

    trade_points_left: int
    href: str


@dataclass(frozen=True)
class HistoryLine:
    """A history entry with actor and sentence separated for display.

    Reuse the history renderer's wording.
    """

    when: object
    actor: str
    told: str


@dataclass(frozen=True)
class Step:
    """An available task with description and control.

    Exactly one of ``href`` and ``post`` is set, selecting navigation or
    immediate submission.
    """

    told: str
    verb: str
    href: str = ""
    post: str = ""


@dataclass(frozen=True)
class ActivitiesSquare:
    """Open activities, ordered next steps and starting controls for the roster.

    Required tasks precede optional workflows. Display the empty state only
    when neither an activity nor next step exists. ``start_founding`` is
    empty while founding is open; ``history_href`` links to the history.
    """

    founding: ActivityCard | None = None
    visit: VisitLine | None = None
    start_founding: str = ""
    history_href: str = ""
    #: Ransoms first, then Clean House, then optional post-battle recording.
    to_do: tuple = ()

    @property
    def anything_open(self):
        return self.founding is not None or self.visit is not None


def open_card(kind, at, *, help="", about="", facts=(), marked=False, activity_id=""):
    """Build an activity card using its canonical kind label."""
    return ActivityCard(
        title=kind.label,
        action=at,
        help=help,
        about=about,
        facts=facts,
        marked=marked,
        activity_id=activity_id,
    )


def founding_card(gang, at):
    """Return the open founding activity using the gang's cached activity read."""
    from n26.core.models import Activity

    kind = Activity.Kind.FOUNDING
    activity = gang.open_activity(kind)
    if activity is None:
        return None
    return open_card(
        kind,
        at,
        help=FOUNDING_HELP,
        about=FOUNDING_ABOUT,
        marked=True,
        activity_id=str(activity.pk),
    )


def founding_blocks_visit(gang, seen):
    """Whether open founding should disable a new Trading Post visit.

    ``seen`` means the viewer can close founding. Only disable the visit for
    those viewers, who have an available way to finish the blocking activity.
    Use cached open activities when already loaded.
    """
    from n26.core.models import Activity

    return bool(seen and gang.open_activity(Activity.Kind.FOUNDING) is not None)


def visit_card(receipt, at):
    """Build a Trading Post card from the receipt's existing balance calculation."""
    from n26.core.models import Activity

    return open_card(
        Activity.Kind.TRADING_POST_VISIT, at, help=VISIT_HELP, facts=receipt.facts
    )


def history_lines(gang, viewer=None, limit=SNAPSHOT):
    """Build recent entries through the same renderer as the full history."""
    from n26.core import history

    return tuple(
        HistoryLine(
            when=act.when,
            actor=act.actor,
            told="".join(span.text for span in act.spans),
        )
        for act in history.latest(gang, limit=limit, viewer=viewer)
    )


def activities_square(
    gang,
    sheet,
    *,
    founding_at,
    visit_at,
    history_at,
    clean_house_at="",
    ransoms=(),
    post_battle_at="",
):
    """Build the roster's open activities and starting controls from existing reads.

    Reuse the sheet's visit balance and the gang's cached open activities.
    """
    # Empty destinations withhold the corresponding controls and state.
    # Opening the panel for another feature must not open founding access.
    founding = founding_card(gang, founding_at) if founding_at else None
    visit = None
    if visit_at and sheet.visiting_trading_post:
        visit = VisitLine(trade_points_left=sheet.trade_points_left, href=visit_at)
    completed = gang.founding_completed_at() if founding_at else None
    available = getattr(sheet, "has_founding_tp", True)
    return ActivitiesSquare(
        founding=founding,
        visit=visit,
        start_founding=founding_at
        if founding is None and completed is None and available
        else "",
        history_href=history_at,
        to_do=steps_waiting(
            sheet,
            clean_house_at=clean_house_at,
            ransoms=ransoms,
            post_battle_at=post_battle_at,
        ),
    )


def steps_waiting(sheet, *, clean_house_at="", ransoms=(), post_battle_at=""):
    """Return authorised required tasks before optional post-battle recording.

    Ransoms precede Clean House because unpaid ransom can kill the model at
    the cycle's end. Empty URLs suppress individual controls.
    """
    from n26.core.status import Status

    steps = [
        Step(told=f"{name} is held for ransom.", verb="Pay ransom", href=at)
        for name, at in ransoms
        if at
    ]
    in_recovery = sum(1 for model in sheet.models if model.status == Status.RECOVERY)
    if in_recovery and clean_house_at:
        models = "model" if in_recovery == 1 else "models"
        steps.append(
            Step(
                told=f"{in_recovery} {models} In Recovery until the cycle ends.",
                verb="Clean House",
                post=clean_house_at,
            )
        )
    if post_battle_at:
        steps.append(
            Step(told=POST_BATTLE_HELP, verb="Post-battle", href=post_battle_at)
        )
    return tuple(steps)
