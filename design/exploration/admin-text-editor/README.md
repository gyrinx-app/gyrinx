# Staff-admin TinyMCE callout exploration

A runnable design exploration that extends TinyMCE in Django staff-admin flat pages. The original React/Tiptap replacement remains available for comparison. It uses the repository’s N26 theme and Cotton-derived controls inside shadow roots. It is a prototype: production widgets, page rendering and models are unchanged.

## Open the prototype

Requirements: Python 3.14, Node 22.12 or newer, npm and uv. Run these commands from this directory:

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements.txt
npm ci
bash start.sh
```

Open the one-click staff login URL printed by the server. It opens the TinyMCE version (`?editor=tinymce`). Use the comparison link above the editor to switch; save before switching. The default port is 8765; set `EDITOR_PORT=8766 bash start.sh` if it is occupied. The server binds to loopback only. All writes, including uploads, stay in this directory’s ignored local SQLite database and upload directory. The preview user has no usable password. No production credentials are needed.

Opening `index.html` displays these setup directions; the interactive editor needs its local Django server. Startup regenerates the Cotton recipes, installed Lucide icon manifest and theme CSS from this checkout, builds JavaScript and seeds a synthetic flat page. Restarts retain saved local pages.

## What to review

TinyMCE 7.8.0 comes from the application’s pinned `django-tinymce==5.0.0`. Callouts are protected blocks edited through native TinyMCE dialogs, with native inline rich-text fields, Undo transactions, copy/paste and paragraph dividers. Download and related-link fields use TinyMCE’s native file picker with the local staff-only upload endpoint.

The editor is mounted in Django’s ordinary flat-page admin form with URL, title, content, sites, advanced options, introduction and group visibility controls. Explore Edit, Preview and HTML views; formatting and text colours; file and image uploads; sticky toolbar behaviour; light/dark themes; and desktop/mobile layouts.

Text-colour swatches and callout choices use the same 18 named colours from `n26.core.colours.GANG_COLOURS`. Preparation generates their N26 token names; the text picker resolves actual `--color-<name>-500` values through the active theme, rather than using TinyMCE’s default palette. Callouts retain palette names and use the theme tokens directly, with neutral Gyrinx box styling by default.

The callout menu includes information, expanding information, FAQ carousel, download, related links, email and expandable example blocks. Their settings include the N26 palette, Lucide icons, optional stripes/glow and basic rich body formatting. Cards and links can be added or removed. Copy transfers a whole block; the bottom Plus divider inserts a blank paragraph below it.

The Square Code button inserts an HTML-source block. Copy/paste preserves its source, and preview renders supported markup through the N26 rich-text sanitiser. Scripts, event handlers and embedded frames are removed. Source is stored faithfully in the block rather than executed in the authoring textarea. There is no comment feature.

## Verify

Start the local server, then in a second terminal run:

```bash
npm run check
npm run format:check
.venv/bin/python check_callout_preview.py
.venv/bin/python check_uploads.py
```

Use the same `EDITOR_PORT` for the server and checks. Browser checks use Google Chrome on macOS by default. Elsewhere, set `CHROME_EXECUTABLE` to an installed Chromium browser or run `npx playwright install chromium` to use Playwright’s browser. Tests restore the seeded page or create/delete temporary pages and uploads; screenshots go to ignored `qa/`.

`check_tinymce.mjs` verifies the native palette against generated N26 token values, all seven callout types, legacy anchor/class preservation, native body formatting, FAQ/link editing, uploads, HTML blocks, HTML/plain clipboard transfer, native Undo, save/reload and reader preview.

Checks cover cursor insertion, formatting, private staff uploads and CSRF, save/reload, clipboard HTML/plain-text fallback, reader interactions, paragraph dividers, deletion/Undo, dark menus, sticky toolbars and responsive layouts. Python preview checks exercise configuration validation, field limits and sanitisation.

## Source map

- `src/tiny-editor.jsx`, `src/tiny-callout-dialog.jsx`, `src/tiny-callout-content.jsx`: native TinyMCE plugin, dialogs, protected blocks and serialization.
- `src/tiny-playground.jsx`: comparison shell, preview and Django textarea synchronisation.
- `src/colours.js`: shared N26 theme-palette resolution.
- `src/editor.jsx`: original replacement-editor toolbar and comparison selection.
- `src/controls.jsx`, `src/uploads.jsx`, `src/block-controls.jsx`: shared Cotton controls, uploads, Copy and paragraph dividers.
- `src/callouts.jsx`, `src/callout-model.js`, `src/callout-reader.jsx`: callout authoring, portable settings and reader UI.
- `src/html-block.jsx`: editable HTML-source blocks and clipboard parsing.
- `src/callout-rich.jsx`: restricted rich body editing and rendering.
- `prepare.py`: generates recipes and theme sources from this checkout.
- `server.py`, `lab/`, `callout_preview.py`: isolated demo admin, uploads and preview.

Generated assets, dependencies, login secrets, database files, uploads and screenshots are ignored. JavaScript dependencies are locked in `package-lock.json`; Python dependencies are pinned in `requirements.txt`.

## Before production integration

The comparison shell retains the shadow boundary; native TinyMCE runs in a staff-only same-origin iframe because TinyMCE does not support direct shadow-root mounting. Its content iframe receives the generated N26 styles. This extra frame isolates the playground from Django admin styles; a production plugin should register on the existing widget rather than copy this comparison-frame setup.

This exploration does not change Gyrinx’s existing `TinyMCEWithUpload`. An implementation must use the approved build/widget seams, production upload storage and permissions, and the existing flat-page presentation pipeline. The local sidecar models do not implement production audit history or public-page access enforcement.

The native TinyMCE version preserves untouched HTML and checks an edited legacy anchor/class fixture. Representative page copies still need compatibility tests for custom classes/styles, tables and embeds. The optional Tiptap comparison has a narrower schema and can discard unsupported markup. Live flat-page rendering permits some local iframe embeds while this preview removes them. Callout and HTML-source blocks need production rendering support before their saved metadata can be used on live pages. Heading IDs, contents navigation and both legacy/N26 presentation should be checked as part of that integration.
