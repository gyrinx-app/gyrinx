# Gang card manager

An independent React design exploration for ordering the cards on an N26 gang
page. It uses synthetic gang data, standard model cards and Cotton-derived
controls. It does not replace the application gang page or write application data.

## Run locally

Use this repository's Python environment and Node 22.12 or newer:

```bash
cd design/exploration/gang-card-manager
npm ci
python prepare.py
npm run build
npm start
```

Open <http://127.0.0.1:8776/gang/>. No database or sign-in is required. The optional
Adobe Fonts stylesheet and logo use the network; system fonts work offline.
`GYRINX_SOURCE` can point `prepare.py` at a separate Gyrinx source tree.
Rebuild after editing source. Vite emits hashed scripts; the preview serves the
current build without the sandbox's Django asset-version workaround.

## Explore

- Open Card Manager to edit a draft. Select cards with All/None or checkboxes,
  move them with arrows, or drag one or several selected cards by a handle.
  Adjacent selected cards retain their order. Pets always follow their owner.
- Hold over a card for 650 ms to group cards. Drag a group to move it or merge
  it with another card or group. Drag a child out to remove it from its group.
  Use the name to rename a group, its colour dot to choose from the N26 palette,
  or Unlink to ungroup it. Groups cannot nest.
- Pin cards or groups to the top or bottom. Pins on children act within their
  group. Extracting a child removes its inherited pin. Panels and dead/destroyed
  models start grouped and pinned at the top and bottom respectively.
- Group by type applies to selected cards, or every card when nothing is selected.
  It confirms before replacing affected groups. Sorting respects pins, sorts
  group contents, then uses each group's first card to order the groups.
  Default restores the established order; there is no reverse default.
- Refund, archive and delete queue changes until Save. Their first confirmation
  marks the affected models; Undo restores them. A final Save confirmation lists
  each action and its models. **These actions are simulated:** they remove sample
  cards from the preview, without changing credits or application records.
- Cancel, Exit, Escape and page unload guard unsaved changes. Save stays disabled
  until the layout or pending actions change. Reordering animates only displaced
  cards, and respects reduced motion. Selection and arrows provide a keyboard
  alternative to pointer dragging.

Long leader, champion and vehicle names are included by default; `?names=short`
provides a compact comparison. Grouping, pins, colours and names persist under
`gyrinx-card-manager-v1` in localStorage at this origin. Saved layouts are validated
before rendering. Invalid or unreadable storage is preserved and the preview
runs in memory with a visible message. A failed write also reports that the
layout lasts for this visit only. This origin is separate from other design demos.

The toolbar moves controls into More options in stages as available space narrows.
Refund, archive, delete and reset stay in that dropdown. Group headings use 12px
text and icons; colour dots, Unlink and drag handles retain larger click targets.

## Sources and verification

`src/card-manager.jsx` owns the draft and dialog interactions;
`src/card-manager-model.js` owns ordering, grouping, pins, sorting and storage
validation. `src/gang-sheet.jsx` provides standard sample cards and panels.
`prepare.py` renders the repository's Cotton button, input, native select, dialog,
card and segmented-tab recipes and builds a shadow-scoped N26 theme. React owns
the tab behaviour; no Alpine markup is executed. Generated output is ignored.
The parallel model-card artwork, image upload and theme experiments are excluded.

With the preview running:

```bash
npm run check
npm run format:check
```

The model and Chrome checks cover ordering invariants, selections, pins within
groups, grouping and type regrouping, drag extraction/merging, stable DOM identity,
targeted animation, colour and rename controls, staged actions, confirmation,
persistence, malformed/unavailable storage, keyboard and reduced motion. They
exercise the toolbar and dropdown at widths from 320 to 1,000 pixels, plus long
names and light/dark layouts. Screenshots are written to ignored `qa/`.
`BASE_URL` overrides the test origin; `CHROME_PATH` selects a different Chrome
executable. The default Chrome path is the macOS Google Chrome installation.

## Production integration

This is a design prototype. Production needs server-prepared gang/card identifiers,
owner permissions, transactional layout storage and version/conflict handling.
Every refund/archive/delete must use the existing N26 operations and ledger rules,
including founding Trade Points, free/granted gear, paid equipment sent to stash,
attached pets, and campaign restrictions. Client values cannot authorise actions
or calculate refunds. Replace the simulated action boundary with those existing
contracts and test permissions and concurrent writes before enabling it.

Browser layout storage has no cross-tab transaction guarantee. The sample sheet
and statlines are display fixtures rather than authoritative rules data. The
prototype adds no server scheduler, application routes, migrations or production
API. Assistive-technology and cross-browser testing remain required before release.
