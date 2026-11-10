# N26 database exploration

A standalone, read-only design prototype for finding N26 content without creating a gang. This draft preserves the latest database design for continued work. It does not add an application route or connect to application data.

## Run from another checkout

Use Python 3.14, [uv](https://docs.astral.sh/uv/) and Node 22.12 or newer. From the repository root:

```bash
cd design/exploration/database
uv venv --python 3.14 .venv
uv pip sync --python .venv/bin/python requirements.txt
.venv/bin/python prepare.py
npm ci
npm run build
npm start
```

Open [the database](http://127.0.0.1:8772/database/). The separate loopback origin does not share the editor demo's data. No application server, PostgreSQL setup, credentials, cloud folder or original sandbox is required. Adobe Fonts is optional; system fonts work offline. Stop the preview with Ctrl+C.

The standalone Python environment pins the Cotton versions used by this design. It imports template helpers from this checkout, but does not initialise application models or access a database. `prepare.py` is needed after changing reference templates; rebuild after changing JavaScript or styles. Do not edit generated recipes, presentation trees or compiled CSS.

## Explore

- The initial view shows a search prompt. Search suggestions support Up/Down, Enter and Escape. Command/Ctrl+K focuses the search field.
- Search names, sets, ammunition names, traits or modifier characteristics. Try Agility, Toxin, Shotgun or Strength. Results are grouped by category.
- Browse profiles, weapons, weapon accessories, gear, injuries, skills, built-in territories, powers and ranks. A filtered category has a single heading, set filtering and live counts.
- Read model cards and compact weapon cards using the striped, bevelled New style frame, torn nameplate, paper body and price panel. Weapons have a parent line with named profiles indented beneath them, including additional prices and traits.
- Skills show their set and dice-face result; injury D66 results use two dice faces. Expand a skill's built-in profiles and follow links back and forth between skills and model cards.
- Injury, gear and relevant accessory cards show structured modifier examples and their scope. Roll targets use improves/worsens, rather than treating a higher number as universally better.
- Query, category and linked entry are shareable URL state with Back/Forward support. Set filtering and open disclosures are temporary. Nothing is stored in browser storage.

All 64 entries, relationships, prices, characteristics, injury results and modifiers are **illustrative**. The fixtures are not an authoritative N26 content export or rules pack. The prototype contains names and structured display facts, not copied rulebook prose.

## Sources and regeneration

| Source | Responsibility |
| --- | --- |
| `src/database.jsx` | Search, category browsing, cards, relationship links and URL navigation |
| `src/database-data.js` | Independent fixtures and search matching |
| `src/cotton-tree.jsx`, `src/controls.jsx` | Inert Cotton tree renderer and small native React control adapters |
| `src/model-name.jsx`, `src/nameplate-edge.js` | Wrapped card names and deterministic torn nameplates |
| `src/cards.css` | Focused New style frame, header, price panel and paper styling |
| `src/database.css`, `src/surface.css` | Database-specific layout and shared page surface |
| `prepare.py`, `cotton_templates.py` | Render real Cotton templates into presentation trees and control recipes |
| `reference/` | Frozen design inputs and provenance, independent of later application template migrations |

The [reference notes](reference/README.md) identify the captured inputs. They are build inputs, not a second application implementation. Generated `src/presentation.json`, `src/cotton.json`, `public/theme.css`, `dist/`, dependency trees and `qa/` captures are ignored. The shadow boundary isolates the preview stylesheet.

## Initial redundancy review

- Removed the campaign tree exporter and full campaign JSON dependency. This prototype now renders only its own page shell, sections, statlines and cards.
- Removed unused full-model/weapon card exports and the superseded standalone weapon-statline export. The model body is rendered directly rather than generating a full card and discarding its header.
- Removed obsolete weapon-profile CSS, unused modal/upload/input adapters, pet/status name helpers and unrelated editor/history styling.
- Reduced the borrowed card/callout styling to the frame, nameplate, name wrapping, rating and paper rules used here. Source hashes and retained byte counts are recorded in `reference/style-provenance.json`.
- Kept intentional design inputs separate from authored behaviour. There is one search implementation, one shared model/weapon frame and one representation of fixture relationships.

This is an initial cleanup, not a production architecture review. Production should use the application's typed React adapters, assets and page shell rather than preserve this exploration's isolated renderer and frozen theme.

## Verify

With the preview running:

```bash
npx playwright install chromium
npm run check
npm run format:check
```

`CHROME_PATH` selects an installed Chrome executable. `DATABASE_ORIGIN` overrides the default test origin. Tests use fresh browser contexts, and write captures to ignored `qa/`. They cover the search prompt, suggestions and keyboard controls, category headings, set filters, nested weapon profiles, shared frames, dice faces, injury/gear modifiers, reciprocal profile/skill links, empty states, URL reload and Back, five viewport widths and dark mode.

## Production work remaining

Replace fixtures with authorised, JSON-safe display props from the N26 content library. Use the standard content pack and its staged/archived visibility policy; do not query every pack or expose staged content to public readers. Add bounded server-side search and per-category pagination, query-growth checks and batched related-content loading.

Resolve default skills through built-in grants, not selectable skill sets. Preserve each weapon profile's parent, applicability, traits and price. Express stat changes from the real `ChangesStat` scope, mode, amount and stat direction; the fixture summaries do not execute effects. Define discovery and detail read permissions and real deep links before mounting this in the application. There are no production endpoints, migrations, player-data operations or production connections in this draft.
