"""The scenario generator's four tables: Deployment, Objective, Side Job
and Crew, each rolled on a D6.

A scenario is one entry from each table. The tables are fixed text that
ships with the code rather than library content an author edits, so they
live here as constants. A battle records which entry each table landed
on by table key and roll, so an entry's text can be revised without
rewriting any battle.

The entry text is placeholder copy until the real tables are supplied.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ScenarioEntry:
    """One result on one table: the roll that lands on it, its name, a
    paragraph saying what it means, and an optional image under the
    static root."""

    roll: int
    name: str
    text: str
    image: str = ""

    @property
    def label(self):
        """The name as a line of text says it. A name may end in a colon
        or spaces when written as a heading; a sentence leaves them off."""
        return self.name.strip().rstrip(":").strip()


@dataclass(frozen=True)
class ScenarioTable:
    """One of the four tables. ``key`` is what URLs and stored battles
    use; ``name`` is what a reader sees."""

    key: str
    name: str
    entries: tuple[ScenarioEntry, ...]

    def entry(self, roll):
        """The entry a roll lands on, or None for a roll off the table."""
        for entry in self.entries:
            if entry.roll == roll:
                return entry
        return None


DEPLOYMENT = ScenarioTable(
    key="deployment",
    name="Deployment",
    entries=(
        ScenarioEntry(
            roll=1,
            name="Sniping Range:",
            text=(
                'Roll-Off Winner chooses a board edge. Opponent takes the opposite. Both gangs may deploy anywhere in their deployment zone but no closer than 12" from the board’s centre line, so that both gangs start no closer than 24" from each other'
            ),
            image="n26/scenarios/deployment-1.png",
        ),
        ScenarioEntry(
            roll=2,
            name="Face off:",
            text=(
                'Roll-Off Winner chooses a board edge. Opponent takes the opposite. Both gangs may deploy anywhere in their deployment zone but no closer than 9" from the board’s centre line, so that both gangs start no closer than 18" from each other'
            ),
            image="n26/scenarios/deployment-2.png",
        ),
        ScenarioEntry(
            roll=3,
            name="Stand Off:",
            text=(
                'Roll-Off Winner chooses a board edge. Opponent takes the opposite. Both gangs may deploy anywhere in their deployment zone but no closer than 6" from the board’s centre line, so that both gangs start no closer than 12" from each other'
            ),
            image="n26/scenarios/deployment-3.png",
        ),
        ScenarioEntry(
            roll=4,
            name="Ambush!",
            text=(
                'The Defender deploys anywhere on the battlefield within 6" from the centre point of the battlefield. The attacker deploys anywhere in a ring around the defender at least 12" from the centre of the board.'
            ),
            image="n26/scenarios/deployment-4.png",
        ),
        ScenarioEntry(
            roll=5,
            name="Free For All:",
            text=(
                'Roll-Off Winner chooses a board quarter. Opponent takes the quarter opposite. Each gang deploys anywhere in their board quarter, no closer than 9" from the board centre '
            ),
            image="n26/scenarios/deployment-5.png",
        ),
        ScenarioEntry(
            roll=6,
            name="Chance Encounter:",
            text=(
                'Roll-Off Winner chooses a corner. They may deploy anywhere within 9" of that board corner and the opposite board corner. The opponent  deploys within 9" of the other 2 corners. Both players should spread their gang’s equally between their deployment corner where possible. '
            ),
            image="n26/scenarios/deployment-6.png",
        ),
    ),
)
OBJECTIVE = ScenarioTable(
    key="objective",
    name="Objective",
    entries=(
        ScenarioEntry(
            roll=1,
            name="King of the Hive: ",
            text=(
                "Place a suitable objective/marker at the centre of the board. This objective is worth 1 VP if held during the Check For Victory step of each turn's End Phase. The Winner is the first player to reach 3 VP. If only one player has a model left on the board, they are the winner. If no players have any models left on the board, the battle is a draw"
            ),
        ),
        ScenarioEntry(
            roll=2,
            name="Turf War: ",
            text=(
                'Starting with Round 3 – If only one player has models that are not SI/Damaged within 9" of the centre of the board during the Check For Victory step of the End Phase, they are the winner. If only one player has a model left on the board, they are the winner. If no players have any models left on the board, the battle is a draw'
            ),
        ),
        ScenarioEntry(
            roll=3,
            name="Tunnel Clash:",
            text=(
                'Place a suitable objective/marker at the centre of the board. Then starting with the player that wins a roll-off; players take turns to place another objective marker at least 6" away from any other marker and at least 6" away from any board edge. During the Check For Victory step of the End Phase, if a player controls two objectives, they score 1 VP. The winner is the first to reach 3 VP. If only one player has a model left on the board, they are the winner. If no players have any models left on the board, the battle is a draw'
            ),
        ),
        ScenarioEntry(
            roll=4,
            name="Object Lesson:",
            text=(
                "Both gangs earn 1 VP for each enemy model that went OoA in that round. An additional 1 VP is earned for a Leader/Champ/Brute, and an additional 1 VP if they are taken OoA as part of a Fight/CdeG/Sabotage action. The winner is the first to 10 VP. If only one player has a model left on the board, they are the winner. If no players have any models left on the board, the battle is a draw"
            ),
        ),
        ScenarioEntry(
            roll=5,
            name="Flank ‘em:",
            text=(
                'The attacker places an objective/marker at the centre of one board edge, 6" onto the board. The Defender places an objective/marker in the same position from the opposite board edge. During the Check For Victory step of the End Phase, if a gang controls both objectives they score 1 VP. The Winner is the first player to score 3 VP. If only one player has a model left on the board, they are the winner. If no players have any models left on the board, the battle is a draw'
            ),
        ),
        ScenarioEntry(
            roll=6,
            name="Burn Them Out:",
            text=(
                'The Defender places and objective/marker in the Attackers deployment zone, then the Attacker places one in the Defenders deployment zone. They take turns until each have each placed 3 objectives. Each objective must be 6" from all other objectives – where possible. During the Check For Victory step of the End Phase, if a gang controls an objective in the opponents deployment zone they score 1 VP and remove the objective. The winner is the first to 2 VP.  If both players have 2 VP or no players have any models left on the board, the battle is a draw.'
            ),
        ),
    ),
)
SIDE_JOB = ScenarioTable(
    key="side_job",
    name="Side Job",
    entries=(
        ScenarioEntry(
            roll=1,
            name="Stitch ‘em Up: ",
            text=(
                "Your Fighters may plant evidence on a SI enemy model instead of making the usual Strength checks to take the fighter OoA. If at least one enemy Fighter had evidence planyed on them in this way by the end of the battle (even if they are no longer on the board), your gang has accomplished this Side Job."
            ),
        ),
        ScenarioEntry(
            roll=2,
            name="The Package:",
            text=(
                "At the start of the battle, after both starting Crews have deployed, choose 1 of your Fighters who is on the board and give them a marker representing The Package. If –during the Check For Victory step of the End Phase of round 3, or any round after– the Fighter carrying the package is in base-contact with a board edge in your opponent’s deployment zone (or the centre of the zone if it has no edges), they may remove the marker and your gang has accomplished this Side Job."
            ),
        ),
        ScenarioEntry(
            roll=3,
            name="Settle a Score:",
            text=(
                "After both starting Crews have deployed, randomly select one of your opponent’s models (who is not the Leader) – declare them your target. During the Check For Victory step of the End Phase of any round: If the target model had been taken OoA or left the board for any reason, then your gang has accomplished this Side Job."
            ),
        ),
        ScenarioEntry(
            roll=4,
            name="Crippling Strike:",
            text=(
                "During the Check For Victory step of the End Phase of any round – if at least half of your opponents models left on the board are SI/Damaged Engaged, then your gang has accomplished this Side Job."
            ),
        ),
        ScenarioEntry(
            roll=5,
            name="Spread Unrest:",
            text=(
                'Any Active Fighter (without the Beast Subtype) from your gang may perform the Graffiti (Double) action If they are within your opponents deployment zone (or 6" from the centre of the board if there isn’t a DZ). If at least one Fighter performed this action during the battle (even if they are no longer on the board), your gang has accomplished this Side Job.'
            ),
        ),
        ScenarioEntry(
            roll=6,
            name="Protect the Future:",
            text=(
                "After both crews are deployed – randomly select on of your Prospects who is on the board to be ‘protected’ and announce they have been selected. If the selected Figher is still on the board at the end of the battle  your gang has accomplished this Side Job. (If you have no Prospects, select a Ganger, if you have no Gangers, generate a new Side Job)."
            ),
        ),
    ),
)
CREW = ScenarioTable(
    key="crew",
    name="Crew",
    entries=(
        ScenarioEntry(
            roll=1,
            name="Escalating Engagement:",
            text=(
                "Both players use Hybrid(3+D3 method for their Starting Crew. Both gangs user Reinforcements (5) rule – D3 Reinforcements arrive each round starting from the 1st."
            ),
        ),
        ScenarioEntry(
            roll=2,
            name="Hold Nothing Back!:",
            text=("Both players use Custom(10) to determine their Starting Crew."),
        ),
        ScenarioEntry(
            roll=3,
            name="Patrol:",
            text=("Both Gangs use Hybrid(3 + 4) to determine their Starting Crew."),
        ),
        ScenarioEntry(
            roll=4,
            name="Surprise Attack!:",
            text=(
                "The Attacker uses Hybrid(4+4) to determine their Starting Crew. Defender uses Custom(3). The Defender uses Reinforcements(7) rule – D3 Reinforcements arriving each round starting with the 1st."
            ),
        ),
        ScenarioEntry(
            roll=5,
            name="Strike Force:",
            text=(
                "Attacker and Defender both use Custom(5) to determine their Starting Crew."
            ),
        ),
        ScenarioEntry(
            roll=6,
            name="Scouting Force:",
            text=("Both gangs use Hybrid(D3+5) to determine their Starting Crew."),
        ),
    ),
)

#: Every table, in the order the generator shows them.
TABLES = (DEPLOYMENT, OBJECTIVE, SIDE_JOB, CREW)


def table(key):
    """The table with this key, or None."""
    for found in TABLES:
        if found.key == key:
            return found
    return None


@dataclass(frozen=True)
class ScenarioResult:
    """What one table landed on, for drawing: the table, the roll and its
    entry."""

    table: ScenarioTable
    roll: int
    entry: ScenarioEntry

    @property
    def face(self):
        """The roll as the die component takes it, a string."""
        return str(self.roll)


def roll(keys, rng=None):
    """A D6 roll for each named table, as ``{key: roll}`` in table order.
    ``rng`` is anything with ``randint``, so a test can seed it."""
    from n26.library.models import Dice

    return {found.key: Dice.roll(Dice.D6, rng) for found in TABLES if found.key in keys}


def results(rolls):
    """The result for each table a mapping of ``{key: roll}`` names, in
    table order. A key or roll that is not on a table is skipped, so a
    hand-edited address draws what it can rather than failing."""
    found = []
    for each in TABLES:
        try:
            rolled = int(rolls.get(each.key, ""))
        except ValueError:
            continue
        entry = each.entry(rolled)
        if entry is not None:
            found.append(ScenarioResult(table=each, roll=rolled, entry=entry))
    return found


@dataclass(frozen=True)
class ChoosableEntry:
    """One entry offered to choose by hand, and whether it is the one
    picked on its table."""

    entry: ScenarioEntry
    picked: bool


@dataclass(frozen=True)
class ChoosableTable:
    """One table offered to choose by hand."""

    table: ScenarioTable
    entries: tuple[ChoosableEntry, ...]


def choosable(rolls):
    """Every table with every entry, marking the one a mapping of
    ``{key: roll}`` names on each table, so a result can be adjusted."""
    picked = {result.table.key: result.roll for result in results(rolls)}
    return [
        ChoosableTable(
            table=each,
            entries=tuple(
                ChoosableEntry(entry=entry, picked=picked.get(each.key) == entry.roll)
                for entry in each.entries
            ),
        )
        for each in TABLES
    ]


# --- Proving a roll was made here ---------------------------------------------
#
# A result lives only in its address, and anybody can edit an address. So a
# roll the generator makes carries a stamp: a signature over the campaign and
# the rolls, made with the site's secret key. An address whose rolls were
# edited no longer matches its stamp, and a result chosen by hand never has
# one. Either way it reads, and saves, as chosen rather than rolled.

STAMP_SALT = "n26.core.scenarios.stamp"


def _signed_value(campaign_id, rolls):
    """The campaign and its rolls as one string, the same for the same
    rolls whatever order they arrive in."""
    return f"{campaign_id}:" + ",".join(f"{key}={rolls[key]}" for key in sorted(rolls))


def stamp(campaign_id, rolls):
    """The stamp for these rolls in this campaign."""
    from django.core.signing import Signer

    return Signer(salt=STAMP_SALT).signature(_signed_value(campaign_id, rolls))


def is_stamped(campaign_id, rolls, check):
    """Whether ``check`` is the stamp these rolls were made with."""
    from django.utils.crypto import constant_time_compare

    return bool(rolls and check) and constant_time_compare(
        stamp(campaign_id, rolls), check
    )


def rolls_of(found):
    """``{key: roll}`` for a list of results."""
    return {result.table.key: result.roll for result in found}


# --- Saving a scenario to the campaign's log ---------------------------------
#
# The log stores no sentence, only a note the reader turns into one. A saved
# scenario's note is whether it was rolled, each table's key and roll, then
# the name the player gave it: "rolled deployment=6,objective=2 Dust Up".
# Entry names are looked up when the log is drawn, so the note stays short
# and a renamed entry reads as it is now, as a battle's scenario does.

ROLLED = "rolled"
CHOSE = "chose"


def history_note(rolled, rolls, name=""):
    """The note a saved scenario's log entry stores."""
    word = ROLLED if rolled else CHOSE
    pairs = ",".join(f"{key}={value}" for key, value in rolls.items())
    return f"{word} {pairs} {name}".strip()


def read_history_note(note):
    """``(rolled, rolls, name)`` from a saved scenario's note. A note that
    does not parse gives no rolls, and one saved without a name gives an
    empty name."""
    word, _, rest = note.partition(" ")
    pairs, _, name = rest.partition(" ")
    rolls = {}
    for pair in pairs.split(","):
        key, _, value = pair.partition("=")
        if key and value:
            rolls[key] = value
    return word == ROLLED, rolls, name.strip()


def generator_query(campaign_id, rolled, rolls):
    """The generator's query string for a known result, as a dict for
    ``urlencode(..., doseq=True)``. A rolled result carries its stamp,
    and the mode is the one that would have rolled those tables."""
    if not rolled:
        query = {"mode": "choose"}
    elif len(rolls) == len(TABLES):
        query = {"mode": "full"}
    else:
        query = {"mode": "components", "tables": list(rolls)}
    query.update(rolls)
    if rolled:
        query["check"] = stamp(campaign_id, rolls)
    return query


def describe(found):
    """A list of results as the log says it: each table and roll with the
    entry's name, "Deployment 6 (Chance Encounter)"."""
    return ", ".join(
        f"{result.table.name} {result.roll} ({result.entry.label})" for result in found
    )
