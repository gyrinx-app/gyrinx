# Logged-out homepage exploration

Runnable design prototype for Gyrinx's logged-out homepage, using the checkout's N26 tokens and rendered Cotton components. It preserves the wide banner, adds a login area alongside Latest updates, and presents the three introduction callouts as a mobile carousel. The application homepage, authentication and database are unchanged.

## Open

Requirements: Python 3.14, uv, Node 22.12 or newer, and npm. From this directory:

```bash
uv venv --python 3.14 .venv
uv pip install --python .venv/bin/python -r requirements.txt
npm ci
bash start.sh
```

Open <http://127.0.0.1:8766/homepage/>. Set `HOMEPAGE_PORT` to use another port. No PostgreSQL, demo database, staff account or production credentials are required. Opening `index.html` directly requires the local build and server; it is the document served at `/homepage/`.

The server binds to loopback. Keep dependencies and generated files machine-local when working in cloud-synchronised folders: copy this exploration to a local directory and set `GYRINX_SOURCE` to the absolute path of this Gyrinx checkout before building. Do not share a virtual environment or `node_modules` across Macs.

## Review

- Check the banner fade and headline in both themes. The fade retains the dark background colour in light mode.
- On desktop, Username and Latest updates share a baseline. Three updates have dividing rules and no internal scrollbar.
- On mobile, swipe the three callouts or use their keyboard and arrow controls. Updates follow the callouts.
- Callout titles balance across lines; striped headers and the hover zoom retain the approved design.
- The regular N26 footer uses the supplied centre-cropped photograph with the original Patreon and Gyrinx logo overlays.
- Try the theme switcher, menu, skip link and keyboard focus.

Submitting the login form **does not authenticate**: it clears the fields and displays a preview message. No credentials are sent or stored. Account and information links open the real site. Latest updates renders three entries from the dated public snapshot in `homepage-changelog.json`; it does not fetch live updates.

## Verify

With the server running, use a second terminal in this directory:

```bash
npm run check
npm run format:check
```

Browser checks use Google Chrome on macOS. Elsewhere, set `CHROME_EXECUTABLE` to an installed Chromium browser, or install Playwright's Chromium with `npx playwright install chromium`. For another preview port, set `HOMEPAGE_URL=http://127.0.0.1:8767/homepage/`. Checks cover responsive placement, both themes, carousel navigation, form behaviour, footer assets, focus and menu behaviour. Captures go to ignored `qa/`.

## Source and design provenance

Edit `src/homepage.jsx`, `src/homepage.css`, `src/callout-card.css` and the two Cotton composition templates. `prepare.py` renders button, anchor-button, input and label recipes through the current checkout's Cotton exporter, and renders the real N26 footer and changelog components. It derives the container width from the N26 page shell and builds a separate stylesheet from the current theme, scanning only this homepage. Rebuild with `bash start.sh`; generated recipes, styles and bundles are ignored.

The custom callout geometry and banner layout are approved exploration choices. The controls, focus tokens, colours, typography, container cap, footer and changelog derive from N26. The shadow boundary isolates the preview stylesheet. React owns preview interactions; this standalone mount is not an application React island.

The banner is generated as WebP from the repository's existing homepage photograph. `assets/homepage/support.webp` is the supplied `DSCF9442 (1).jpg`, cropped from the centre to 1440 × 756 with both original logo overlays restored. It is 80,078 bytes, approximately the previous footer image's file size. Only this exploration uses it. Images reserve dimensions and the footer image loads lazily. Page assets are approximately 0.49 MB before transfer compression, excluding externally hosted fonts.

## Production integration

This is the current approved design demonstration, not a replacement application route. Integration must use Django/allauth for authentication, CSRF and server-side errors; supply the live public changelog queryset; use the application page shell and React island lifecycle for interactions; and decide how the default homepage should use the N26 layout. Do not ship the preview submit handler or static changelog snapshot as production behaviour. No production models, data, routes or dependencies are changed by this exploration.
