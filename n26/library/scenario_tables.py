"""The scenario generator's tables, each rolled on a D6: Deployment,
Objective and Crew, then any number of side jobs, up to
``SIDE_JOB_LIMIT``, each from a set of side jobs the reader picks.

These are game content, original to Gyrinx, and fixed: they ship with
the code rather than being authored in the library's pages, so they are
constants here. ``n26.core.scenarios`` reads them to roll, check and
describe a scenario.

Each table's ``key``, each side job set's ``key`` and each entry's
``roll`` are what links and saved battles name, so they must not change.
Names and text can be revised; a battle shows its entries as they read
now. Text between asterisks, ``*like this*``, is drawn in bold.
"""

import re
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

    def parts(self):
        """The text as ``(words, bold)`` pairs, split at the asterisks."""
        return [
            (words, index % 2 == 1)
            for index, words in enumerate(_BOLD.split(self.text))
            if words
        ]

    @property
    def plain(self):
        """The text without the asterisks that mark bold."""
        return self.text.replace("*", "")


_BOLD = re.compile(r"\*([^*]+)\*")


@dataclass(frozen=True)
class ScenarioTable:
    """One table. ``key`` is what URLs and stored battles use; ``name`` is
    what a reader sees. A side job in a scenario is drawn from a table for
    its place, "Side job 2", whose ``side_job_set`` is the set it came
    from."""

    key: str
    name: str
    entries: tuple[ScenarioEntry, ...]
    side_job_set: SideJobSet | None = None

    def entry(self, roll):
        """The entry a roll lands on, or None for a roll off the table."""
        for entry in self.entries:
            if entry.roll == roll:
                return entry
        return None


@dataclass(frozen=True)
class SideJobSet:
    """A set of six side jobs to roll on, such as the Escher ones. ``key``
    is what links and stored battles use, with the roll: "escher-3"."""

    key: str
    name: str
    entries: tuple[ScenarioEntry, ...]

    @property
    def label(self):
        """The set as the generator's menu names it."""
        return f"{self.name} side jobs"

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
                'Roll-Off Winner chooses a board edge. Opponent takes the opposite. Both gangs may deploy anywhere in their deployment zone but no closer than 12" from the board’s centre line, so that both gangs start no closer than 24" from each other.'
            ),
            image="n26/scenarios/deployment-1.png",
        ),
        ScenarioEntry(
            roll=2,
            name="Face Off:",
            text=(
                'Roll-Off Winner chooses a board edge. Opponent takes the opposite. Both gangs may deploy anywhere in their deployment zone but no closer than 9" from the board’s centre line, so that both gangs start no closer than 18" from each other.'
            ),
            image="n26/scenarios/deployment-2.png",
        ),
        ScenarioEntry(
            roll=3,
            name="Stand Off:",
            text=(
                'Roll-Off Winner chooses a board edge. Opponent takes the opposite. Both gangs may deploy anywhere in their deployment zone but no closer than 6" from the board’s centre line, so that both gangs start no closer than 12" from each other.'
            ),
            image="n26/scenarios/deployment-3.png",
        ),
        ScenarioEntry(
            roll=4,
            name="Ambush",
            text=(
                'The Defender deploys anywhere on the battlefield within 6" from the centre point of the battlefield. The Attacker deploys anywhere in a ring around the Defender at least 12" from the centre of the board.'
            ),
            image="n26/scenarios/deployment-4.png",
        ),
        ScenarioEntry(
            roll=5,
            name="Free For All:",
            text=(
                'Roll-Off Winner chooses a board quarter. Opponent takes the quarter opposite. Each gang deploys anywhere in their board quarter, no closer than 9" from the board centre.'
            ),
            image="n26/scenarios/deployment-5.png",
        ),
        ScenarioEntry(
            roll=6,
            name="Chance Encounter:",
            text=(
                'Roll-Off Winner chooses a corner. They may deploy anywhere within 9" of that board corner and the opposite board corner. The opponent deploys within 9" of the other 2 corners. Both players should spread their gangs equally between their deployment corners where possible.'
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
                "Place a suitable objective/marker at the centre of the board. This objective is worth 1 VP if held during the Check For Victory step of each turn’s End Phase. The Winner is the first player to reach 3 VP. If only one player has a model left on the board, they are the winner. If no players have any models left on the board, the battle is a draw."
            ),
        ),
        ScenarioEntry(
            roll=2,
            name="Turf War: ",
            text=(
                'Starting with Round 3 — If only one player has models that are not Seriously Injured/Damaged within 9" of the centre of the board during the Check For Victory step of the End Phase, they are the winner. If only one player has a model left on the board, they are the winner. If no players have any models left on the board, the battle is a draw.'
            ),
        ),
        ScenarioEntry(
            roll=3,
            name="Tunnel Clash:",
            text=(
                'Place a suitable objective/marker at the centre of the board. Then starting with the player that wins a roll-off; players take turns to place another objective marker at least 6" away from any other marker and at least 6" away from any board edge. During the Check For Victory step of the End Phase, if a player controls two objectives, they score 1 VP. The winner is the first to reach 3 VP. If only one player has a model left on the board, they are the winner. If no players have any models left on the board, the battle is a draw.'
            ),
        ),
        ScenarioEntry(
            roll=4,
            name="Object Lesson:",
            text=(
                "Both gangs earn 1 VP for each enemy model that went OoA in that round. An additional 1 VP is earned for a Leader/Champ/Brute, and an additional 1 VP if they are taken OoA as part of a Fight/CdeG/Sabotage action. The winner is the first to 10 VP. If only one player has a model left on the board, they are the winner. If no players have any models left on the board, the battle is a draw."
            ),
        ),
        ScenarioEntry(
            roll=5,
            name="Flank ‘em:",
            text=(
                'The Attacker places an objective/marker at the centre of one board edge, 6" onto the board. The Defender places an objective/marker in the same position from the opposite board edge. During the Check For Victory step of the End Phase, if a gang controls both objectives they score 1 VP. The Winner is the first player to score 3 VP. If only one player has a model left on the board, they are the winner. If no players have any models left on the board, the battle is a draw.'
            ),
        ),
        ScenarioEntry(
            roll=6,
            name="Burn Them Out:",
            text=(
                'The Defender places an objective/marker in the Attacker’s deployment zone, then the Attacker places one in the Defender’s deployment zone. They take turns until each has placed 3 objectives. Each objective must be 6" from all other objectives — where possible. During the Check For Victory step of the End Phase, if a gang controls an objective in the opponent’s deployment zone they score 1 VP and remove the objective. The winner is the first to 2 VP. If both players have 2 VP or no players have any models left on the board, the battle is a draw.'
            ),
        ),
    ),
)
GENERAL_SIDE_JOBS = SideJobSet(
    key="general",
    name="General",
    entries=(
        ScenarioEntry(
            roll=1,
            name="Stitch ‘em Up: ",
            text=(
                "Your Fighters may plant evidence on a Seriously Injured enemy model instead of making the usual Strength checks to take the fighter OoA. If at least one enemy Fighter had evidence planted on them in this way by the end of the battle (even if they are no longer on the board), your gang has accomplished this Side Job."
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
                "After both starting Crews have deployed, randomly select one of your opponent’s models (who is not the Leader) — declare them your target. During the Check For Victory step of the End Phase of any round: If the target model had been taken OoA or left the board for any reason, then your gang has accomplished this Side Job."
            ),
        ),
        ScenarioEntry(
            roll=4,
            name="Crippling Strike:",
            text=(
                "During the Check For Victory step of the End Phase of any round — if at least half of your opponent’s models left on the board are Seriously Injured/Damaged or Engaged, then your gang has accomplished this Side Job."
            ),
        ),
        ScenarioEntry(
            roll=5,
            name="Spread Unrest:",
            text=(
                'Any Active Fighter (without the Beast Subtype) from your gang may perform the Graffiti (Double) action if they are within your opponent’s deployment zone (or 6" from the centre of the board if there isn’t a DZ). If at least one Fighter performed this action during the battle (even if they are no longer on the board), your gang has accomplished this Side Job.'
            ),
        ),
        ScenarioEntry(
            roll=6,
            name="Protect the Future:",
            text=(
                "After both crews are deployed — randomly select one of your Prospects who is on the board to be ‘protected’ and announce they have been selected. If the selected Fighter is still on the board at the end of the battle, your gang has accomplished this Side Job. (If you have no Prospects, select a Ganger; if you have no Gangers, generate a new Side Job)."
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
                "Both players use Hybrid (3+D3) for their Starting Crew. Both gangs use the Reinforcements (5) rule — D3 Reinforcements arrive each round starting from the 1st."
            ),
        ),
        ScenarioEntry(
            roll=2,
            name="Hold Nothing Back:",
            text=("Both players use Custom (10) to determine their Starting Crew."),
        ),
        ScenarioEntry(
            roll=3,
            name="Patrol:",
            text=("Both gangs use Hybrid (3+4) to determine their Starting Crew."),
        ),
        ScenarioEntry(
            roll=4,
            name="Surprise Attack:",
            text=(
                "The Attacker uses Hybrid (4+4) to determine their Starting Crew. Defender uses Custom (3). The Defender uses Reinforcements (7) rule — D3 Reinforcements arriving each round starting with the 1st."
            ),
        ),
        ScenarioEntry(
            roll=5,
            name="Strike Force:",
            text=(
                "Attacker and Defender both use Custom (5) to determine their Starting Crew."
            ),
        ),
        ScenarioEntry(
            roll=6,
            name="Scouting Force:",
            text=("Both gangs use Hybrid (D3+5) to determine their Starting Crew."),
        ),
    ),
)

ESCHER_SIDE_JOBS = SideJobSet(
    key="escher",
    name="Escher",
    entries=(
        ScenarioEntry(
            roll=1,
            name="Chemical Reign:",
            text=(
                "Keep count of each time an enemy Fighter loses a wound to a weapon with the Toxic (X) trait. If, during the Check For Victory step of any round, this count is at least 3, you have accomplished this Side Job."
            ),
        ),
        ScenarioEntry(
            roll=2,
            name="Maiden, Mother, Matriarch:",
            text=(
                'If, during the Check For Victory step of any round, you have a Prospect, a Ganger AND a Leader or Champion, each Active or Suppressed, all within 6" of the centre of the battlefield, you have accomplished this Side Job.'
            ),
        ),
        ScenarioEntry(
            roll=3,
            name="Hunt Together:",
            text=(
                "If a friendly Fighter and a pet both performed a Charge or Engage action against the same enemy Fighter in the same round, you have accomplished this Side Job in the Check For Victory step of that round."
            ),
        ),
        ScenarioEntry(
            roll=4,
            name="Cut Off the Head:",
            text=(
                "If every enemy Leader and Champion is Out of Action or Seriously Injured during the Check For Victory step of any round, you have accomplished this Side Job."
            ),
        ),
        ScenarioEntry(
            roll=5,
            name="Experimental Chem:",
            text=(
                'At the start of the battle, after all Fighters are deployed, choose one of your Fighters to carry 3 doses of an experimental Stimm. They can use a dose with the *Administer Dose* action. Roll a D6 for the effect: 1 – they suffer an L1 wound that ignores saves; 2 – they are Suppressed; 3+ – their Move increases by 1" for the rest of the battle. If all 3 doses are used, you have accomplished this Side Job.'
            ),
        ),
        ScenarioEntry(
            roll=6,
            name="Murder Run:",
            text=(
                "If, during the Check For Victory step of any round, 3 enemy Fighters are Out of Action or Seriously Injured, you have accomplished this Side Job."
            ),
        ),
    ),
)
GOLIATH_SIDE_JOBS = SideJobSet(
    key="goliath",
    name="Goliath",
    entries=(
        ScenarioEntry(
            roll=1,
            name="Pit Fight:",
            text=(
                "Randomly select one of your deployed Fighters. If that Fighter *only* uses weapons with the *Melee* trait for the entire battle, you have accomplished this Side Job."
            ),
        ),
        ScenarioEntry(
            roll=2,
            name="Personal Vendetta:",
            text=(
                "Pick your Leader or one of your Champions, and the enemy Leader or one of their Champions (or any other Fighter if neither is available). If, at the end of the battle, your Fighter has taken that enemy Fighter Out of Action, you have accomplished this Side Job."
            ),
        ),
        ScenarioEntry(
            roll=3,
            name="Wreck the Place:",
            text=(
                'Any Active Fighter in your gang within the enemy’s deployment zone (or within 6" of the centre of the board if there is no DZ) may perform the Vandalise (Single) action: roll a D6 and add their Strength. On a total of 6 or more, they have vandalised the area. If your gang does this twice or more by the end of the battle, you have accomplished this Side Job.'
            ),
        ),
        ScenarioEntry(
            roll=4,
            name="Maximum Force:",
            text=(
                "If, by the end of the battle, your gang has taken 3 enemy Fighters Out of Action with Fight actions, you have accomplished this Side Job."
            ),
        ),
        ScenarioEntry(
            roll=5,
            name="Hold the Forge:",
            text=(
                'Select a piece of terrain at least 12" from your deployment zone (or any piece if you have no DZ). If, at the end of the battle, there are no enemy models within 3" of it, you have accomplished this Side Job.'
            ),
        ),
        ScenarioEntry(
            roll=6,
            name="Prove Your Worth!:",
            text=(
                "If, during any round, a friendly Fighter was Engaged by *two* enemy Fighters *at the same time*, and at the end of that round is still on the board and not Seriously Injured, you have accomplished this Side Job."
            ),
        ),
    ),
)

#: The tables every scenario may use, in the order the generator shows
#: them. Side jobs come after them.
TABLES = (DEPLOYMENT, OBJECTIVE, CREW)

#: The side job sets, in the order the generator's menu lists them.
SIDE_JOB_SETS = (GENERAL_SIDE_JOBS, ESCHER_SIDE_JOBS, GOLIATH_SIDE_JOBS)

#: The most side jobs one scenario may have.
SIDE_JOB_LIMIT = 6


def side_job_key(place):
    """The key a scenario's side job is stored under, by its place from 1:
    "side_job" for the first, as before there could be more, then
    "side_job_2" and on."""
    return "side_job" if place == 1 else f"side_job_{place}"


#: Every side job key, first to last.
SIDE_JOB_KEYS = tuple(side_job_key(place) for place in range(1, SIDE_JOB_LIMIT + 1))


def side_job_set(key):
    """The side job set with this key, or None."""
    for found in SIDE_JOB_SETS:
        if found.key == key:
            return found
    return None


def side_job_table(place, found):
    """The table a scenario's side job at ``place`` is drawn from: the
    entries of the set ``found``, named for the place."""
    return ScenarioTable(
        key=side_job_key(place),
        name=f"Side job {place}",
        entries=found.entries,
        side_job_set=found,
    )


def table(key):
    """The table with this key, or None."""
    for found in TABLES:
        if found.key == key:
            return found
    return None
