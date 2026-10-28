# N26 Scenario Generator: what it does

The Scenario Generator is a quick way to set up a battle. For each of three
scenario tables, and for each side job, a player rolls a D6, chooses an entry,
or leaves it out. They can then share the result, save it to a campaign log, or take it to
**Record a battle**.

## Where to find it

There are two ways in:

- **From a battle.** Battle creation offers optional inline generation. A
  saved battle offers **Generate scenario** or **Generate again** inline,
  attaching each generated result immediately.
- **From the menu.** **Scenario generator** is in the N26 menu, after
  **Campaigns**, at `/n26/scenario/`. Anyone signed in can use it, for
  campaign or skirmish play. It asks which campaign to use when connecting a scenario or
  creating a battle. See
  [Outside a campaign](#outside-a-campaign).

## The tables

Each table has six entries, one for each face of a D6. Each entry has a name
and a description.

| Table | What it decides |
| --- | --- |
| Deployment | Where each gang sets up. Each entry also has a map. |
| Objective | How the battle is won. |
| Crew | How each gang picks its starting crew. |

### Side jobs

A side job is an extra goal a gang can complete. Side jobs come in sets of six:

| Set | For |
| --- | --- |
| General side jobs | Any gang. These are the side jobs from before there were sets. |
| Escher side jobs | Escher gangs. |
| Goliath side jobs | Goliath gangs. |

A scenario can have up to six side jobs, each from any set. Within a set, a
rolled side job is never the same as another one in the scenario, unless every
job in that set is already taken. Side jobs are numbered in order: Side job 1,
Side job 2 and so on.

Some side jobs have words in bold, such as **only** or **at the same time**.
The bold shows on the page, on the battle and in the print.

The table wording, the side jobs and the Deployment maps are original content
written for Gyrinx.

## Generating a scenario

The page has one drop-down list for each table. Each list offers:

- **Roll a D6**, the default
- **Leave out**, for a component the players already have covered
- any of the table's six entries, chosen by name

The side job lists come last, after Crew. A side job's list first offers:

- **Choose a side job set**, the default, which adds no side job
- **Leave out**
- **General side jobs**, **Escher side jobs** and **Goliath side jobs**

Once a set is picked, the same list shows **Roll a D6**, that set's six jobs
and, at the bottom, **Change set**, which goes back to the list of sets.

**Add side job** below the last list adds another, up to six. Each side job
list after the first has a **−** button that removes it; the later side jobs
move up. Without JavaScript, picking a set and pressing **Generate scenario**
rolls on that set.

**Generate scenario** shows the result. The result gives each component its
name, its number, its full description and, for Deployment, its map. Your
choices stay set, and the button changes to **Generate again**. Pressing it
rolls again for every table still set to **Roll a D6**.

Include at least one component. Saving or cancelling a save keeps your
chosen and omitted components set for the next generation.

On a wide screen the choices sit on the left and the scenario on the right.
On a phone the choices come first.

Standalone generation and battle-creation previews save nothing. A player can generate a scenario, play the game,
and record the battle afterwards, or never record it.

## Actions in the campaign-specific generator

| Action | Who can use it | What it does |
| --- | --- | --- |
| **Share** | Everyone who can read the campaign | Copies a link to the scenario on a desktop, or opens the share sheet on a phone. Anyone who opens the link sees the same scenario. |
| **Print** | Everyone who can read the campaign | Opens a print page with the scenario laid out as on screen, one card per component, with the Deployment map. **Print** on that page opens the browser's print dialog, which can also save a PDF. **Back to scenario** returns to the campaign's generator. |
| **Save to log** | The arbitrator and accepted players | Opens **Save scenario**, which asks for a scenario name and adds one line to the campaign log. |
| **Record a battle** | The arbitrator and accepted players | Opens **Record a battle** with the scenario attached. The player names the battle and records it as usual. |

A saved scenario appears in the log like this:

> **Alex** saved the scenario **Vent ambush**: Deployment 3 (Stand Off),
> Objective 4 (Object Lesson), Crew 4 (Surprise Attack),
> Side job 1: Escher 3 (Hunt Together), Side job 2: Goliath 1 (Pit Fight)

Battles and log lines saved before there were sets show their one side job as
Side job 1 from the General set.

The line links back to the scenario. A recorded battle appears in the log in
the usual way, for example "recorded Vent ambush on 2026-10-12".

## Outside a campaign

The generator is available from the N26 menu and the swords shortcut on wide screens.
The compact header share control and **Share result** beside **Print** both share
an address containing the exact generated components. No identifier or saved
record is needed to reproduce that result.

| Action | Who can use it | What it does |
| --- | --- | --- |
| **Share result** and **Print** | Anyone signed in | Share the exact result or open its print page. |
| **Connect to battle** | Campaign arbitrators | Select a campaign, then one of its active battles. Connects the components without changing the battle's name, participants or outcome. |
| **Create a battle** | Arbitrators and accepted players | Select a campaign and open its battle form with the result attached. |

The connection dialog loads battles only after a campaign is selected. Archived
campaigns and battles are excluded. Replacing an attached scenario shows a warning.
The server checks the campaign, battle and permissions again, and refuses a stale
battle revision. Connecting appends a battle-edit event; repeating an unchanged
connection adds no duplicate event. Names belong to battles, so the dialog has no
scenario-name field. A successful connection opens the selected battle page.

## The battle record

The creation form has an optional **Name**. A blank name becomes **Battle #N**,
where N counts the campaign's battles, including archived battles. Naming and
creation occur under the campaign lock.

**Generate scenario** produces an optional compact preview without submitting the
battle or clearing the name, date or participants. **Table options** offers the
same choices as the main generator, including the side job sets, **Add side
job** and **−**. The preview can be regenerated
or removed, and its full result can be opened in another tab. The server validates
the hidden components when the battle is saved.

The battle page puts Outcome first and places the compact scenario beside it on
wide screens. The scenario offers expandable details, **Print** and **View
scenario**. The full-result link opens the standalone
generator with the exact components. Arbitrators can generate or regenerate directly on the battle page using the
same options as battle creation. Each generated result is
attached immediately, without leaving the page or requiring a separate save.
The battle revision is checked so a concurrent edit cannot be overwritten; a
refused attachment leaves the displayed saved result intact.
