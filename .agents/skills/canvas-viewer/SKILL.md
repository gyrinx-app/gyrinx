---
name: canvas-viewer
description: >-
  Open and visually check .canvas.tsx artifacts from the CLI in a local browser.
  Use when the IDE Canvas surface is unavailable, when a user cannot open a Canvas
  link, or when a Canvas needs browser QA through the repository's local viewer.
---

# Canvas viewer

Use the repository viewer at `tools/canvas-viewer`. It discovers the Cursor
Canvas directory for the repository's shared git checkout, so it also works from
a task worktree.

## Start the viewer

Start the development server and keep its terminal session running. The script
installs the viewer's isolated Node dependencies when they are absent or stale:

```bash
./scripts/canvas-viewer.sh
```

Use the loopback URL printed by Vite. The server is configured for
`127.0.0.1`; do not expose it on `0.0.0.0` or another network interface.

The viewer selects among every `.canvas.tsx` file in the discovered directory.
Link to one directly with `?canvas=<encoded filename>`. Set `CANVAS_DIR` to an
absolute directory only when the Canvas belongs to another workspace:

```bash
CANVAS_DIR=/absolute/path/to/canvases ./scripts/canvas-viewer.sh
```

## Check a Canvas

1. Confirm `/api/canvases` lists the expected file.
2. Open the printed URL in a browser and select the Canvas.
3. Check the page at desktop and narrow-phone widths, including interactive
   filters or controls.
4. Read any load or render error shown in the viewer before changing the
   Canvas. The server reloads when a `.canvas.tsx` file changes.

The viewer supplies a local compatibility implementation of `cursor/canvas`.
It renders the public layout, table, card, form, chart, diff, and state
primitives, but it is not the Cursor host. Host actions such as `openFile` are
shown in a notice and never run. Treat the Cursor IDE as authoritative when a
difference depends on host integration.

Run the viewer's checks after changing the viewer or its compatibility layer:

```bash
npm --prefix tools/canvas-viewer test
npm --prefix tools/canvas-viewer run build
```
