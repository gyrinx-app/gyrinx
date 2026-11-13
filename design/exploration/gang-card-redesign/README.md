# Gang card redesign

A standalone React gallery for reviewing the redesigned N26 model cards.
It contains model cards only: no gang stash, campaign or available-action boxes,
Card Manager, gang-page layout, or application routes are changed.

## Run locally

Use this checkout's Python environment and Node 22.12 or newer. From the
repository root, export the recipes from the actual Cotton templates:

```bash
.codex/run.sh python design/exploration/gang-card-redesign/prepare.py
cd design/exploration/gang-card-redesign
npm ci
npm run build
npm start
```

Open <http://127.0.0.1:8768/>. The gallery has its own npm lockfile and loads no
editor or campaign bundles. It needs a server for module imports; it is not a
`file://` preview. The optional Adobe Fonts stylesheet needs internet access;
N26's system-font fallback works offline. `npm run preview` serves the production
build on the same loopback port after stopping the development server.

## Review the design

- Change Gang colour to compare the 18 N26 gang colours. The `colour` query
  parameter retains the chosen colour on reload. Theme switches between light
  and dark mode.
- Inspect leaders, champions, pets, long names, status badges, a vehicle, and
  a model with extra details and six weapons. Longer content grows naturally.
- Switch between Card, Lore and Notes using the mouse or arrow/Home/End keys.
  Light-mode panels and their active tabs share one continuous paper texture.
- Open the model menus, portrait previews and action prompts. Edit, Equip,
  clone, refund and delete open preview dialogs; they do not change real models.
  Mark as changes only the current card's local status.
- Click a camera to choose an image, resize the 4:5 crop and apply it. Cancel
  preserves the card. Applying restores focus to the new portrait button.
  Invalid files and files above 10 MB show a recoverable error. Cropped JPEGs
  are capped at 1600px. Blob URLs are revoked on unmount.

All sample names, profiles, equipment and actions are display fixtures, not a
complete rules dataset. Pictures and status changes live only in React memory
until reload. There is no localStorage, database, authentication or upload API.
No application or production data is read or written.

## Sources and rebuilds

Edit the sources, then rerun `prepare.py` and `npm run build`.

| Source | Purpose |
| --- | --- |
| `src/gallery.jsx`, `src/gallery.css` | Minimal colour/theme controls and model gallery |
| `src/model-card.jsx` | Header, tabs, characteristics, weapons and preview actions |
| `src/models.js`, `src/gang-sheet-data.js` | Fixed example models and display data |
| `src/model-name.jsx`, `src/nameplate-edge.js` | Two-line name layout and deterministic ragged edge |
| `src/model-picture-upload.jsx`, `src/picture-crop-dialog.jsx` | Native chooser and lazy-loaded Cropper.js dialog |
| `src/card-content.css`, `src/card-layout.css` | Shared model-card content and layout |
| `src/new-cards.css`, `src/frame.css` | Redesign theme and shared bevel/strip geometry |
| `src/controls.jsx` | Cotton-derived buttons, Lucide icons and modal lifecycle |
| `prepare.py`, `build-shadow-theme.mjs` | Cotton recipes and N26 theme within the shadow boundary |
| `check.mjs` | Model-card browser regressions and review captures |

Generated recipes, theme inputs, CSS, bundles, dependencies and QA screenshots
are ignored. Do not hand-edit or commit them. The generator reads this
checkout's N26 sources, including the gang-colour registry and picture-input
recipes. Controls use Lucide at 1.7 stroke weight. The classic paper artwork and
three dog portraits are the existing design sandbox's decorative assets;
`public/static/cards/` contains only those fixtures, never user uploads.

The card layer keeps the existing design: bevelled frame, neutral striped top
band, black ragged nameplate in light mode, tinted nameplate in dark mode,
neutral attribute labels, and a gang-coloured second statline heading row.
Dark-mode ratings use full gang colour and automatically contrasting text;
light-mode ratings use white on black. The tint for the dark second heading
row reuses the nameplate token. Texture alignment uses one ResizeObserver per
card, observes all tab buttons, and skips unchanged pixel writes.

## Validation

With the gallery running:

```bash
npx playwright install chromium
npm run check
npm run format:check
```

To use installed Chrome, set `CHROME_PATH` to its executable. `CARDS_ORIGIN`
overrides the default origin. Checks use an isolated browser, cover all 18
colours in both themes, 1512/390/320px viewports, texture and border joins,
keyboard tabs and menus, action dialogs, cropping, focus restoration, invalid
and oversized images, and assert that no network writes occur. Captures are
written to the ignored `qa/` directory. Run the repository formatters before
submitting changes.

## Production integration limits

This workflow is already React in the prototype. Application integration is
**deferred**: these cards have synthetic props, simulated actions and temporary
portraits. It needs a typed model-card adapter, real read props, permission-aware
commands through Django operations, durable image storage, authoritative rating
calculation, and parity checks against actual model and vehicle profiles.
The standalone shadow boundary is prototype infrastructure, not a new app shell.

The agreed bright active-tab colours are preserved. Several do not meet 4.5:1
small-text contrast on light paper; production needs an accessible tab-colour
treatment. Attribute labels already use neutral text, and rating text is checked
for 4.5:1 contrast across the palette. The CSS `corner-shape: bevel` geometry
needs cross-browser review; unsupported browsers retain rounded corners.
This draft does not change production templates, dependencies, APIs or routes.
