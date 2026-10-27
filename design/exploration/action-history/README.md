# Action history exploration

A working design prototype for gang histories and shared campaign activity.
It explores retained undo/redo branches, dated restoration, snapshots, private
highlights and cloning from a point in time.

**Design status: this does not yet properly match Gyrinx N26’s design
specifications. Further work is required to resolve its appearance before
production integration.** Cotton-derived recipes and N26 theme tokens are used,
but the page composition, spacing, typography, menus and timeline presentation
still need review against the [N26 gallery](https://gyrinx.app/n26/design/).

## Run locally

Requirements: Python 3.14 with this repository’s locked Python dependencies,
Node 22.12 or newer, and npm. This exploration has a separate npm lockfile;
it does not change the application’s frontend dependencies.

From the repository root, activate its environment, then:

```bash
cd design/exploration/action-history
npm ci
python prepare.py
npm run build
npm start
```

Open <http://127.0.0.1:8766/history/> for the gang example or
<http://127.0.0.1:8766/history/campaign/> for the campaign. The separate origin
keeps sample history independent of other local demos. The optional Adobe Fonts
stylesheet requires internet access; system fonts work offline.

All sample history lives in this browser’s localStorage. The viewer switch is a
simulation of Louis owning Nightshade and Mira owning Iron Vultures, not
application authentication. No application database or production data is used.
Clearing localStorage at this origin resets the demo. Sample actions cover
17–22 October 2026 and include undo sequences and restorations. The demo-only
“Generate demo actions” control adds more activity for layout testing.

## Try the behaviour

- Undo an action, generate another, then undo and choose a retained redo branch.
  Abandoned history remains visible rather than being deleted.
- Use an ordinary action’s menu to highlight it, link to it, inspect its static
  snapshot, restore that snapshot, or clone a gang from it. Highlight is the
  second menu option and is only visible to its owner. Cloning adds no activity.
- Restore an older snapshot, then undo the restoration. Restore records have no
  per-action controls. Restoration keeps the current page and records the dated
  target, while cloning opens the copied gang’s page.
- Open Timeline to explore branches, dated dividers and restore connections.
  Hover or click nodes for details. Undone restores move below the canonical
  track and use a dotted connection instead of a return arrow. Follow a node’s
  deep link: it scrolls into view without automatically opening its details.
- Switch to the campaign. Activity stays flat, including undone actions; there
  are no side rails, indentation or Timeline mode. Each owner can use their own
  gang’s controls within the shared activity log.
- Filter by date, gang, player or action type; there is no pagination. Log a dice
  roll and inspect the Lucide dice faces.

## Sources and rebuilds

Edit the sources, then rerun `python prepare.py` and `npm run build`.
Generated recipes, theme inputs, bundles, screenshots and dependencies are
ignored. Do not edit those generated files.

| Source | Responsibility |
| --- | --- |
| `src/history.jsx` | Routing, filters, action dialogs and persistence |
| `src/history-model.js` | Immutable snapshots, ownership and retained history |
| `src/history-demo.js` | Sample data and compatible localStorage migrations |
| `src/history-graph.js` | Branch layout, lane reuse and restore connections |
| `src/history-timeline.jsx` | Nested log, flat campaign log and timeline diagram |
| `src/history-entry.jsx` | Shared action content, nodes and menus |
| `src/history-ui.jsx`, `src/controls.jsx` | Shared presentation and controls |
| `src/history-format.js`, `src/history.css` | Dates, links and scoped styling |
| `prepare.py` | Cotton recipe export and shadow theme generation from this checkout |
| `build-shadow-theme.mjs` | Tailwind property defaults inside the shadow boundary |
| `check.mjs` | Model invariants and browser regression checks |

`public/static/history/` contains synthetic-example icon assets from Gyrinx’s
house, badge and brand assets. Icons in controls use Lucide at 1.7 stroke weight.
The shadow boundary keeps prototype styles isolated from page styles.

## Validation

With the preview server running:

```bash
npx playwright install chromium
npm run check
npm run format:check
```

To use an installed Chrome instead, set `CHROME_PATH` to its executable.
`HISTORY_ORIGIN` overrides the default test origin of `http://127.0.0.1:8766`.
The browser check uses a fresh browser context and synthetic data, exercising
ownership, retained branches, exact snapshots, date filtering, deep links,
restore/clone navigation, timeline interactions, mobile and dark layouts.
It writes review captures to `qa/`.

## Production integration still required

This is a design exploration, not a replacement for N23 or N26 history pages.
The model simulates snapshots and permissions in JavaScript. Production work
must define durable snapshot/history storage, server-enforced ownership and
private highlights, atomic operations, concurrent writes, and the effects of
restoration on related campaign records. Browser-local cloning and restoring do
not exercise Django operations or real gang reconstruction.

Reuse the application’s page shell, Cotton primitives and typed React adapters
when integrating the agreed behaviour. The standalone shadow root and custom
routing are prototype infrastructure. Resolve the N26 visual mismatch above,
and validate against real action types and representative large histories.
