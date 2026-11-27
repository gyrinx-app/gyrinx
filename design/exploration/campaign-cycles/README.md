# Campaign phases, cycles and dashboard exploration

An independent design prototype for campaign schedules and the campaign
reading experience. It uses rendered N26 Cotton components, theme tokens and
Lucide icons. It does not replace an application page or write application data.

## Run locally

Use Python 3.14 with this repository's locked Python dependencies and Node
22.12 or newer. Activate the repository environment, then:

```bash
cd design/exploration/campaign-cycles
npm ci
python prepare.py
npm run build
npm start
```

Open <http://127.0.0.1:8768/campaign/>. Its separate origin keeps this sample
independent of other demos. The optional Adobe Fonts stylesheet uses the
network; system fonts work offline. No database is required.

All campaign state lives in localStorage at this origin. The player/arbitrator
switch illustrates available controls; it is not authentication. Reset demo
replaces only this synthetic campaign. Unreadable saved data is preserved until
an explicit reset. Storage failures leave edits in memory and show a message.

## Explore

- Read the dashboard in player and arbitrator views, at phone, tablet and
  desktop widths. Long names wrap, actions move beside or below the title, and
  mobile Campaign information starts collapsed. Phase and cycle names link to
  the schedule. Status appears beside the arbitrator, with reduced-motion-aware
  dots. Completed campaigns show Post-campaign and the total cycles played.
- Edit phase descriptions, effects, entry credits and outcome rewards. Duplicate
  a phase, reorder phases, and add or move future finite cycles. Completed
  cycles keep their phase; cycles with battles cannot be deleted. Moving the
  current cycle to another phase applies that phase's entry grant once.
- End a cycle or reopen a completed campaign. New cycles store their actual
  start time; the dashboard does not substitute planned dates for that time.
  Rough dates on the schedule are indicative only.
- Switch to unlimited cycles. Future rows disappear and a repeating pattern can
  specify ordered phase/count steps. A new or edited pattern starts next cycle.
  An End cycle phase override consumes one pattern position, then resumes the
  pattern. Moving the current cycle does not consume a position. The expanded
  pattern strip marks the consumed position in bold.
- Enable Auto-change cycles with every 1–520 weeks or monthly timing, a weekday
  or month day, a local time and an IANA time zone. Week intervals start on the
  next selected weekday. Short months use their last day; subsequent months
  restore the chosen day. Repeated clock hours use the first occurrence and
  missing clock hours shift forward. The dashboard hides the time-zone label;
  the scheduling panel shows it. A manual end can skip one automatic boundary
  without consuming an extra pattern position.
- Record battles with a cycle, phase and result. Rewards, effects and period
  names are captured with the record. Later schedule edits preserve those
  snapshots. Entry credits go to each demo gang's stash when a phase changes,
  including re-entry, without repeating for consecutive same-phase cycles.

The browser checks timing while open and catches up missed boundaries on
reopening, in batches of 100. It cannot execute while all tabs are closed.
Web Locks serialize manual and automatic writes across tabs where supported;
without Web Locks, concurrent tab writes have no atomicity guarantee. A stale
End cycle dialog cannot end a cycle that began after the dialog opened.

## Sources and checks

Edit source and rebuild. Generated recipes, Cotton trees, theme files, bundles,
dependencies and screenshots are ignored. `reference/` preserves the ten campaign and navigation templates used by the sandbox (the
8 October archive, with four missing layout/include wrappers from its local
checkout). This keeps the explored composition reproducible after upstream
tables migrate to React. Other primitives and theme tokens come from this
checkout. Exported paths and hashes are checked by the browser suite. The
shadow boundary prevents host styles from overriding the demo.

| Source | Responsibility |
| --- | --- |
| `src/campaign-model.js`, `src/campaign-data.js` | Local domain operations, validation and synthetic data |
| `src/campaign-clock.js` | Calendar recurrences and time-zone conversion |
| `src/campaign-state.js` | Transactions, persistence, timing, navigation and guards |
| `src/campaign.jsx` | Page composition and dialogs |
| `src/campaign-view.jsx`, `src/campaign-cotton.jsx` | Cotton-backed dashboard and tables |
| `src/campaign-schedule.jsx`, `src/campaign-drag.js` | Schedule controls and temporary drag previews |
| `src/campaign-forms.jsx`, `src/campaign-ui.jsx` | Forms and campaign presentation |
| `src/controls.jsx`, `src/surface-controls.jsx`, `src/surface.css` | Native controls and Cotton-derived adapters |
| `campaign_templates.py`, `prepare.py` | Build-time Cotton trees, recipes and theme |

With the preview running:

```bash
npx playwright install chromium
npm run check
npm run format:check
```

Set `CHROME_PATH` to use installed Chrome. `CAMPAIGN_ORIGIN` overrides the test
origin. Tests use fresh browser contexts and preserve the interactive demo.
They cover model invariants, migrations, validation, calendar edges, grants,
patterns, drag previews, storage recovery, two-tab timing, stale forms, keyboard
use and 80 long-name/viewer/viewport combinations. Captures are written to `qa/`.

## Production integration

This exploration intentionally uses a local JavaScript model. Integration needs
server-enforced permissions, campaign operations and durable event records;
atomic and idempotent grants, battle rewards and scheduler runs; a policy for
backdated battles and linked ledger entries; and a server scheduler that runs
without a browser. Effects are descriptive only. Territory transfers and
per-gang post-cycle completion are outside the prototype. No production jobs,
notifications, gang ledgers or campaign records are changed.

Use the application's page shell, typed React adapters and operation pipeline
when implementing the agreed design. Browser storage, synthetic account names,
shadow mounting and local routing are exploration infrastructure.
