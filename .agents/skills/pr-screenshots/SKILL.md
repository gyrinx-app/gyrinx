---
name: pr-screenshots
description: Capture useful UI evidence and attach it to GitHub pull requests. Load when a change affects rendered UI, when working in a cloud environment where the user cannot see the browser, or when creating or rewriting a PR that contains screenshots.
---

# PR screenshots

Attach visual evidence to PRs that change rendered UI: N23 and N26 pages, React
islands, authoring screens, and design-system components. This applies in local
and cloud sessions, including small and copy-only UI changes. Automated tests do
not replace the capture. Backend-only changes with no visible effect do not need
one. If the change cannot be rendered with the available data, login or services,
say why in the PR.

## Choose useful evidence

- Prefer a focused **after** screenshot that shows the changed state in context.
- Add **before and after** only when the comparison explains the change better.
- Capture multiple viewports only when responsive behaviour changed.
- Use a short video (about 5–15 seconds) when the interaction is the change.
- Do not capture every manual test step. Choose the smallest set that helps review.
- Use synthetic or local data. Check images for personal data, credentials, tokens,
  private campaign details, and debug output before uploading them.

## Lay out evidence for review

For a comparison, capture a matched pair: the same viewport, zoom, theme and crop,
with the same pixel size. Keep fixture data and UI state consistent except for
the change being demonstrated. Crop to the changed area with enough surrounding
context to understand it; keep the detail readable.

Use a side-by-side Markdown table for narrow, same-size captures (about 450px wide
or less), such as menus, cards or mobile views:

```markdown
## Screenshots

| Before | After |
| --- | --- |
| ![Equipment menu before](./screenshots/equipment/before.png) | ![Equipment menu after](./screenshots/equipment/after.png) |
```

Stack wide captures under separate headings. A PR body is about 900px wide;
putting desktop screenshots in table cells makes their details hard to read.
Explain what to look at in each capture:

```markdown
## Screenshots

### Before: equipment actions wrap onto a second line

![Gang equipment before](./screenshots/equipment/before.png)

### After: equipment actions fit beside the heading

![Gang equipment after](./screenshots/equipment/after.png)
```

Keep screenshots and videos visible in the PR body. Keep videos outside tables
and alone in their paragraph so they play correctly. Only capture metadata or
lengthy supporting notes belong in a collapsed `<details>` block below the
evidence.

## Capture locally

Load the `dev-server` skill, start the worktree server, and exercise the real UI.
Browser tooling may save a capture directly. For a named Django URL, the helper is:

```bash
.codex/run.sh python scripts/screenshot.py core:campaign \
  --args <campaign-id> \
  --after \
  --output-dir screenshots/<task>
```

N26 is included without a Django URL namespace. Use the bare name
(`authoring-create`), not `n26:authoring-create`. The helper strips a leading
`n26:` if you pass one. Keep real namespaces such as `core:` and
`designsystem:`.

```bash
.codex/run.sh python scripts/screenshot.py authoring-create \
  --args pickable \
  --after \
  --output-dir screenshots/<task>
```

The helper uses the worktree's `DJANGO_PORT` and mints a local staff session for
`agent` by default. `screenshots/` is gitignored: it is staging, not the durable
home of the review evidence.

### Local CLI handoff

Screenshots do not render in a local CLI terminal. After capturing them, give the
user a clickable Markdown link to their **parent directory using its full absolute
path**, for example:

```markdown
[Open the screenshot folder](/absolute/path/to/worktree/screenshots/task/)
```

`scripts/screenshot.py` prints `Screenshot folder: <absolute path>` after a run;
use that exact directory in the link. Link the folder rather than listing several
individual files so the user can browse the whole capture set.

## Attach to the PR

Check `gh pr create --help` or `gh pr edit --help` for `--attach`. It uploads local
images and videos and rewrites matching Markdown image paths. Use
`![alt](./path)` references in the PR body, including inside tables, and pass each
file with a repeated flag. Match the path in the body to the attachment argument:

```markdown
## Screenshots

![Campaign equipment after the change](./screenshots/equipment/after.png)
```

```bash
gh pr create --title "..." --body-file /tmp/pr-body.md \
  --attach ./screenshots/equipment/after.png
```

For an existing PR:

```bash
gh pr edit <number> --body-file /tmp/pr-body.md \
  --attach ./screenshots/equipment/after.png
```

For the comparison examples above, attach both `./screenshots/equipment/before.png`
and `./screenshots/equipment/after.png`. Videos can be attached with the same flag;
leave the uploaded video URL alone in its paragraph, outside any table.

When rewriting a PR body, preserve valid existing screenshot URLs or replace them
with fresh captures when the UI changed again. Do not silently drop the section.

Verify the result:

```bash
gh pr view <number> --json body --jq .body
```

The body should contain GitHub-hosted attachment URLs in place of local paths.
Check the rendered PR to confirm images remain readable and videos play. If the
installed CLI lacks `--attach` or uploads fail, use GitHub's browser uploader when
available. If neither route is available, report the local artifact path and the
limitation. Never commit generated screenshots or videos.
