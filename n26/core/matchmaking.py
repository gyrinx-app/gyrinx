"""Random matchups of a campaign's gangs, proposed for battles not yet fought.

The arbitrator ticks the gangs to match and chooses pairs or larger battles.
Every ticked gang must play, so the number of matchups follows from the
number of gangs. When uneven sides are allowed, one spare gang joins the
matchup that holds the highest-rated gang.

Two gangs are a rematch when one of either gang's recent battles included
the other and the new battle has no more gangs than that one, so gangs may
always meet in a larger battle. How many recent battles count is the
lookback: 1 (the latest battle only) unless rematches are allowed, when the
arbitrator chooses it, and 0 checks nothing.

A gang is unavailable while it is in a battle with no result yet, or in a
battle dated after today. It is shown but cannot be ticked.
"""

import random
from dataclasses import dataclass, replace

from django.core import signing

from n26.core.models import Battle, Gang

MIN_WAYS = 2
MAX_WAYS = 8
MAX_LOOKBACK = 10
TITLE_LENGTH = 200
DRAW_SALT = "n26.campaign-matchmaker-draw"

# Bounds the search when the rematch rule leaves very few combinations, so a
# large selection cannot stall a request.
SEARCH_STEPS = 50_000


class Mode:
    PAIRS = "pairs"
    MORE = "more"
    CHOICES = [(PAIRS, "Match pairs"), (MORE, "Match more")]


class NoMatchup(Exception):
    """The selected gangs cannot be matched under the chosen rules."""


@dataclass(frozen=True)
class Entrant:
    """A gang offered to the matchmaker."""

    id: str
    name: str
    rating: int
    #: (opponent ids, gangs in the battle) for each recent battle, newest first.
    recent: tuple[tuple[frozenset[str], int], ...] = ()
    unavailable: str = ""

    @property
    def available(self):
        return not self.unavailable

    @property
    def last_opponents(self):
        return self.recent[0][0] if self.recent else frozenset()

    @property
    def last_size(self):
        return self.recent[0][1] if self.recent else 0


@dataclass(frozen=True)
class Matchup:
    """One proposed battle."""

    gangs: tuple[Entrant, ...]

    def title(self, number, mode):
        """The battle's scenario name until the arbitrator chooses a scenario."""
        if mode == Mode.PAIRS:
            label = " vs ".join(gang.name for gang in self.gangs)
        else:
            label = f"{len(self.gangs)}-way match"
        title = f"Matchup {number}: {label}"
        if len(title) > TITLE_LENGTH:
            title = title[: TITLE_LENGTH - 1].rstrip() + "…"
        return title


def campaign_entrants(campaign, today):
    """The campaign's playing gangs by name, with availability and recent battles."""
    gangs = Gang.objects.filter(
        campaign_memberships__campaign=campaign,
        campaign_memberships__left__isnull=True,
        archived=False,
    ).order_by("name")
    busy, history, players = {}, {}, {}
    taken = (
        Battle.gangs.through.objects.filter(
            battle__campaign=campaign, battle__archived=False
        )
        .order_by("-battle__date", "-battle__created")
        .values_list("gang_id", "battle_id", "battle__date", "battle__result")
    )
    for gang_id, battle_id, date, result in taken:
        if result == Battle.Result.NOT_RECORDED:
            busy[gang_id] = "In a battle with no result yet"
        elif date > today:
            busy.setdefault(gang_id, "In a battle dated after today")
        history.setdefault(gang_id, []).append(battle_id)
        players.setdefault(battle_id, set()).add(gang_id)
    return [
        Entrant(
            id=str(gang.pk),
            name=gang.name,
            rating=gang.rating,
            unavailable=busy.get(gang.pk, ""),
            recent=tuple(
                (
                    frozenset(
                        str(other) for other in players[battle] if other != gang.pk
                    ),
                    len(players[battle]),
                )
                for battle in history.get(gang.pk, ())[:MAX_LOOKBACK]
            ),
        )
        for gang in gangs
    ]


def matchup_sizes(count, ways, *, allow_uneven):
    """How many gangs play in each matchup, largest first.

    Raises `NoMatchup` when `count` gangs cannot be split into battles of
    `ways`, with at most one spare gang when uneven sides are allowed.
    """
    if count < MIN_WAYS:
        raise NoMatchup("Select at least 2 gangs.")
    matchups, spare = divmod(count, ways)
    if matchups == 0:
        raise NoMatchup(f"Select at least {ways} gangs for battles of {ways}.")
    if spare == 0:
        return [ways] * matchups
    if spare == 1 and allow_uneven:
        return [ways + 1] + [ways] * (matchups - 1)
    lower, upper = matchups * ways, (matchups + 1) * ways
    if spare == 1:
        raise NoMatchup(
            f"Select {lower} or {upper} gangs, or tick Allow uneven sides "
            "to add a spare gang."
        )
    if allow_uneven:
        raise NoMatchup(
            f"Select {lower}, {lower + 1} or {upper} gangs for battles of {ways}."
        )
    raise NoMatchup(f"Select {lower} or {upper} gangs for battles of {ways}.")


def rematch(a, b, size, lookback=1):
    """Whether a battle of `size` gangs repeats one of either gang's recent battles.

    Only the latest `lookback` battles of each gang count, and a battle with
    more gangs than the earlier one is never a rematch.
    """

    def met(gang, other):
        return any(
            other.id in opponents and size <= played
            for opponents, played in gang.recent[:lookback]
        )

    return met(a, b) or met(b, a)


def make_matchups(
    gangs,
    *,
    ways,
    allow_uneven=False,
    lookback=1,
    avoid=frozenset(),
    rng=None,
):
    """Shuffle `gangs` into battles of `ways`.

    `lookback` is how many of each gang's recent battles rule out a rematch;
    0 allows any. `avoid` holds sets of gang ids that must not be proposed
    again as a matchup. Raises `NoMatchup` when no combination meets the rules.
    """
    rng = rng or random.SystemRandom()
    gangs = list(gangs)
    sizes = matchup_sizes(len(gangs), ways, allow_uneven=allow_uneven)
    rng.shuffle(gangs)
    if sizes[0] > ways:
        # The spare gang joins the highest-rated gang, which fills the larger
        # first matchup.
        top = max(gangs, key=lambda gang: gang.rating)
        gangs.remove(top)
        gangs.insert(0, top)

    def compatible(group, gang, size):
        return not lookback or not any(
            rematch(gang, other, size, lookback) for other in group
        )

    steps = 0

    def fill(remaining, sizes):
        nonlocal steps
        if not sizes:
            return []
        # Each matchup starts with the first gang left, so the search never
        # tries the same grouping in a different order.
        anchor, rest = remaining[0], remaining[1:]
        for group in _groups([anchor], rest, sizes[0], compatible):
            steps += 1
            if steps > SEARCH_STEPS:
                return None
            if frozenset(gang.id for gang in group) in avoid:
                continue
            chosen = {gang.id for gang in group}
            others = fill([g for g in rest if g.id not in chosen], sizes[1:])
            if others is not None:
                return [Matchup(tuple(group))] + others
        return None

    found = fill(gangs, sizes)
    if found is None:
        if avoid:
            raise NoMatchup("Select more results to rematch.")
        if lookback > 1:
            raise NoMatchup(
                f"Every way to match these gangs is a rematch within {lookback} "
                "past matches. Enter a lower number, or select different gangs."
            )
        raise NoMatchup(
            "Every way to match these gangs is a rematch. "
            "Tick Allow rematches, or select different gangs."
        )
    return found


def _groups(group, candidates, size, compatible):
    """Yield every group of `size` that extends `group` from `candidates`."""
    if len(group) == size:
        yield group
        return
    for index, gang in enumerate(candidates):
        if len(group) + len(candidates) - index < size:
            return
        if compatible(group, gang, size):
            yield from _groups(
                group + [gang], candidates[index + 1 :], size, compatible
            )


@dataclass(frozen=True)
class Draw:
    """Proposed matchups and the rules they were drawn under."""

    mode: str
    ways: int
    allow_uneven: bool
    lookback: int
    matchups: tuple[Matchup, ...]

    def titled(self):
        """(number, title, matchup) for each matchup, numbered from 1."""
        return [
            (number, matchup.title(number, self.mode), matchup)
            for number, matchup in enumerate(self.matchups, start=1)
        ]

    def sign(self, campaign):
        """A token that carries this draw unchanged to the next request."""
        return signing.dumps(
            {
                "campaign": str(campaign.pk),
                "mode": self.mode,
                "ways": self.ways,
                "allow_uneven": self.allow_uneven,
                "lookback": self.lookback,
                "matchups": [
                    [gang.id for gang in matchup.gangs] for matchup in self.matchups
                ],
            },
            salt=DRAW_SALT,
            compress=True,
        )

    @classmethod
    def read(cls, campaign, token, entrants):
        """The draw a token carries, with each gang as it is now.

        Raises `NoMatchup` when the token is not this campaign's, or when a
        gang can no longer be matched.
        """
        try:
            data = signing.loads(token, salt=DRAW_SALT)
        except signing.BadSignature:
            raise NoMatchup(
                "These results are out of date. Make the matchup again."
            ) from None
        if data.get("campaign") != str(campaign.pk):
            raise NoMatchup("These results are out of date. Make the matchup again.")
        by_id = {entrant.id: entrant for entrant in entrants}
        matchups = []
        for ids in data["matchups"]:
            gangs = []
            for gang_id in ids:
                entrant = by_id.get(gang_id)
                if entrant is None or not entrant.available:
                    raise NoMatchup(
                        "A gang in these matchups can no longer be matched. "
                        "Make the matchup again."
                    )
                gangs.append(entrant)
            matchups.append(Matchup(tuple(gangs)))
        return cls(
            mode=data["mode"],
            ways=data["ways"],
            allow_uneven=data["allow_uneven"],
            lookback=data["lookback"],
            matchups=tuple(matchups),
        )

    def chosen(self, values):
        """The positions named by the submitted ``selected`` values.

        Raises `NoMatchup` for a value that names no matchup here.
        """
        chosen = set()
        for value in values:
            if not value.isdigit() or not 1 <= int(value) <= len(self.matchups):
                raise NoMatchup("Select matchups from these results.")
            chosen.add(int(value) - 1)
        return chosen

    def redraw(self, chosen, *, rng=None):
        """Draw the chosen matchups again from their own gangs.

        The other matchups stay where they are. No chosen matchup is proposed
        again, so one matchup on its own cannot be redrawn.
        """
        if not chosen:
            raise NoMatchup("Select more results to rematch.")
        picked = [self.matchups[index] for index in sorted(chosen)]
        fresh = iter(
            make_matchups(
                [gang for matchup in picked for gang in matchup.gangs],
                ways=self.ways,
                allow_uneven=self.allow_uneven,
                lookback=self.lookback,
                avoid={frozenset(gang.id for gang in m.gangs) for m in picked},
                rng=rng,
            )
        )
        return replace(
            self,
            matchups=tuple(
                next(fresh) if index in chosen else matchup
                for index, matchup in enumerate(self.matchups)
            ),
        )
