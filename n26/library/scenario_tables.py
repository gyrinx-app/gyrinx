"""The scenario generator's four tables: Deployment, Objective, Side job
and Crew, each rolled on a D6.

These are game content, original to Gyrinx, and fixed: they ship with
the code rather than being authored in the library's pages, so they are
constants here. ``n26.core.scenarios`` reads them to roll, check and
describe a scenario.

Each table's ``key`` and each entry's ``roll`` are what links and saved
battles name, so they must not change. Names and text can be revised;
a battle shows its entries as they read now.
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
SIDE_JOB = ScenarioTable(
    key="side_job",
    name="Side job",
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

#: Every table, in the order the generator shows them.
TABLES = (DEPLOYMENT, OBJECTIVE, SIDE_JOB, CREW)


def table(key):
    """The table with this key, or None."""
    for found in TABLES:
        if found.key == key:
            return found
    return None
