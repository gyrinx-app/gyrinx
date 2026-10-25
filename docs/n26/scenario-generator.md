# N26 Scenario Generator: what it does

The Scenario Generator is a quick way to set up a battle. For each of four
scenario tables, a player rolls a D6, chooses an entry, or leaves the table
out. They can then share the result, save it to a campaign log, or take it to
**Record a battle**.

## Where to find it

There are two ways in:

- **Inside a campaign.** Every campaign's **Battles** box has a **Generate
  scenario** button next to **Record battle**. Anyone who can read the
  campaign sees it. This generator belongs to that campaign: saving and
  recording use it directly.
- **From the menu.** **Scenario generator** is in the N26 menu, after
  **Campaigns**, at `/n26/scenario/`. Anyone signed in can use it, for
  campaign or skirmish play. It asks which campaign to use when saving or
  recording. See
  [Outside a campaign](#outside-a-campaign).

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

Include at least one component. Saving or cancelling a save keeps your
chosen and omitted components set for the next generation.

On a wide screen the choices sit on the left and the scenario on the right.
On a phone the choices come first.

Generating saves nothing. A player can generate a scenario, play the game,
and record the battle afterwards, or never record it.

## Doing something with the result

| Action | Who can use it | What it does |
| --- | --- | --- |
| **Share** | Everyone who can read the campaign | Copies a link to the scenario on a desktop, or opens the share sheet on a phone. Anyone who opens the link sees the same scenario. |
| **Print** | Everyone who can read the campaign | Opens a print page with the scenario laid out as on screen, one card per component, with the Deployment map. **Print** on that page opens the browser's print dialog, which can also save a PDF. **Back to scenario** returns to the campaign's generator. |
| **Save to log** | The arbitrator and accepted players | Opens **Save scenario**, which asks for a scenario name and adds one line to the campaign log. |
| **Record a battle** | The arbitrator and accepted players | Opens **Record a battle** with the scenario attached. The player names the battle and records it as usual. |

A saved scenario appears in the log like this:

> **Alex** saved the scenario **Vent ambush**: Deployment 3 (Stand Off),
> Objective 4 (Object Lesson), Crew 4 (Surprise Attack)

The line links back to the scenario. A recorded battle appears in the log in
the usual way, for example "recorded Vent ambush on 2026-10-12".

## Outside a campaign

The generator in the menu works the same way, without a campaign. Under the
result it offers:

| Action | Who can use it | What it does |
| --- | --- | --- |
| **Print** | Everyone | The same print page as inside a campaign. **Back to scenario** returns to this generator. |
| **Save to campaign** | Anyone who arbitrates a campaign or has accepted a place in one | Opens a dialog that asks for the campaign and a scenario name, then adds one line to that campaign's log. |
| **Record a battle** | The same people | Opens a dialog that asks for the campaign, then opens that campaign's **Record a battle** with the scenario attached. |

The campaign list shows only campaigns the player can record in. Archived
campaigns are left out. Someone with no such campaign sees **Share** and
**Print** only. A dialog that finds a problem reopens with the message and
keeps what was entered.

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

- The generator is in the menu as well as in each campaign, so it works for
  skirmish play. The campaign's Battles button is labelled **Record battle**
  so both buttons fit on one line on a small phone.
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
