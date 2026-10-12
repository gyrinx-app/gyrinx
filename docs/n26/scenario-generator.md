# N26 Scenario Generator: what it does

The Scenario Generator gives an N26 campaign a quick way to set up a battle.
For each of four scenario tables, a player rolls a D6, chooses an entry, or
leaves the table out. They can then share the result, save it to the
campaign log, or take it to **Record a battle**.

## Where to find it

Every campaign's **Battles** box has a **Generate scenario** button next to
**Record a battle**. Anyone who can read the campaign sees it.

## The four tables

Each table has six entries, one for each face of a D6. Each entry has a name
and a description.

| Table | What it decides |
| --- | --- |
| Deployment | Where each gang sets up. Each entry also has a map. |
| Objective | How the battle is won. |
| Side job | An extra goal a gang can complete. |
| Crew | How each gang picks its starting crew. |

The table wording and the Deployment maps are original content written for
Gyrinx.

## Generating a scenario

The page has one drop-down list for each table. Each list offers:

- **Roll a D6**, the default
- **Leave out**, for a component the players already have covered
- any of the table's six entries, chosen by name

**Generate scenario** shows the result. The result gives each component its
name, its number, its full description and, for Deployment, its map. Your
choices stay set, and the button changes to **Generate again**. Pressing it
rolls again for every table still set to **Roll a D6**.

On a wide screen the choices sit on the left and the scenario on the right.
On a phone the choices come first.

Generating saves nothing. A player can generate a scenario, play the game,
and record the battle afterwards, or never record it.

## Doing something with the result

| Action | Who can use it | What it does |
| --- | --- | --- |
| **Share** | Everyone who can read the campaign | Copies a link to the scenario on a desktop, or opens the share sheet on a phone. Anyone who opens the link sees the same scenario. |
| **Save to log** | The arbitrator and accepted players | Opens **Save scenario**, which asks for a scenario name and adds one line to the campaign log. |
| **Record a battle** | The arbitrator and accepted players | Opens **Record a battle** with the scenario attached. The player names the battle and records it as usual. |

A saved scenario appears in the log like this:

> **Alex** saved the scenario **Vent ambush**: Deployment 3 (Stand Off),
> Objective 4 (Object Lesson), Crew 4 (Surprise Attack!)

The line links back to the scenario. A recorded battle appears in the log in
the usual way, for example "recorded Vent ambush on 2026-10-12".

## The battle record

On **Record a battle**, a **Scenario components** box lists each component
under the scenario name. **View scenario details** opens the full
descriptions and the map. If the form shows an error, the scenario and
everything else already entered stay in place.

The battle keeps its scenario, and the battle's page shows it in a
**Scenario** section.

## Checks

- **Saving** needs a scenario name of up to 200 characters, the same rule as
  a battle's scenario.
- **A component that is not on its table is refused.** For example, a link
  naming Deployment 7 is not used, even if its other components are valid.
  A component that was left out is fine.
- **Archived campaigns** cannot have scenarios saved to them.

## Decisions

- Generating a scenario saves nothing. Players save a scenario or record a
  battle only when they want to.
- A saved scenario adds one line to the log.
- Battles and saved scenarios store which entries came up, not a copy of
  their text. If the table wording is revised, older records show the new
  wording.
- Rolled and chosen results are treated the same. A link does not prove who
  rolled a scenario, or how many times they rolled.
- Letting players record a battle's outcome later is a separate change with
  its own pull request.
