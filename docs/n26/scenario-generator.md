# N26 Scenario Generator: what it does

The Scenario Generator gives an N26 campaign a quick way to set up a battle.
It rolls a D6 on four scenario tables, shows the results, and lets the
players share them, save them to the campaign log, or carry them into the
battle record.

Status: built and tested locally on the branch `feat/n26-scenario-generator`.
It is not yet in a pull request.

## Where to find it

Every campaign's **Battles** box has a **Generate scenario** button, next to
**Record a battle**. Anyone who can read the campaign sees it. The **Record a
battle** page also has a **Generate scenario** button beside the Scenario
name.

## The four tables

Each table has six entries, one for each face of a D6. Each entry has a name
and a paragraph of text.

| Table | What it decides |
| --- | --- |
| Deployment | Where each gang sets up. Each entry also has a map image. |
| Objective | How the battle is won. |
| Side Job | An extra goal a gang can complete. |
| Crew | How each gang picks its starting crew. |

All the table wording and the Deployment maps are original content written
for Gyrinx.

## Generating a scenario

The page offers three options:

- **Generate full scenario** rolls once on each of the four tables.
- **Generate scenario components** rolls only on the tables the reader ticks.
- **Choose my own** shows all four tables and lets the reader pick an entry
  from each. They then press **Use these options**.

The results appear in a **Results** box under the controls, with a die for
each roll. Pressing the button again replaces the results.

Generating saves nothing. A player can roll a scenario, play the game, and
record the battle afterwards, or never record it.

## Doing something with the result

| Button | Who sees it | What it does |
| --- | --- | --- |
| **Copy scenario** | Everyone | Copies a link to the result on desktop, or opens the share sheet on a phone. Whoever opens the link sees the same result. |
| **Save to campaign log** | Accepted players | Asks for a scenario name, then adds one line to the campaign log for the arbitrator to review. |
| **Record result** | The arbitrator and accepted players | Opens **Record a battle** with the four results attached. The reader names the battle and records it as usual. |

Hovering over **Copy scenario** or **Save to campaign log** on a desktop
browser shows a short note about what the button does.

### What the campaign log shows

A saved scenario reads like this:

> **Alex** rolled a scenario for **Grudge match at the sump**: Deployment 1
> (Sniping Range), Objective 6 (Burn Them Out), Side Job 5 (Spread Unrest),
> Crew 3 (Patrol)

A battle recorded from the generator reads like this:

> **Alex** recorded a scenario for **Grudge match at the sump** on 7 October:
> Deployment 6 (Chance Encounter), Objective 5 (Flank 'em), …

Each line links back to the scenario or to the battle.

### Rolled or chosen

The log says **rolled** only when Gyrinx made the rolls. A result picked with
**Choose my own** says **chose**. So does a link whose numbers someone has
edited, because each rolled link carries a hidden check that editing breaks.
The arbitrator can therefore trust a "rolled" line.

The log does not show rolls that a player discarded before saving.

## The battle record

A battle recorded from the generator keeps its four results. The battle's
page shows them in a **Scenario** section, with the Deployment map.

## Recording the outcome later

Most battles are recorded before they are played, so the outcome is added
afterwards:

- **The arbitrator** uses **Edit battle** or **Record outcome**, as before.
- **A player whose gang fought the battle** now gets **Record outcome** while
  no outcome is recorded. It offers only the outcome and the winning gangs.
  Once an outcome is recorded, only the arbitrator can change it.

This changes an existing team rule, under which only the arbitrator could
change a battle after it was recorded. The pull request should ask the
maintainers to agree to it.

## Decisions made

- Generating a scenario saves nothing. Players save it or record it only when
  they want to.
- A saved scenario takes up one log line, not one line for every roll.
- Battles store which entries came up, not a copy of their text. If the table
  wording is revised later, older battles show the new wording.
- The labels follow N26 style: sentence-case buttons, and "log" rather than
  "history".

## Before release

1. Run the project's copy review on the new interface text.
2. Open a pull request. Call out the change that lets players record
   outcomes, so the team can agree to it.
