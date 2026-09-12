---
name: pr-screenshots
description: Capture useful UI evidence and attach it to GitHub pull requests. Load when a change affects rendered UI, when working in a cloud environment where the user cannot see the browser, or when creating or rewriting a PR that contains screenshots.
---

# PR screenshots

Give reviewers visual evidence when it helps them understand or verify a change.
This is a strong default for meaningful changes to rendered UI, particularly in a
cloud session where the user cannot see the browser. Use judgment: backend-only
changes and tiny visual changes may not benefit from a screenshot. If a visible
change has no capture, say briefly why in the PR.

## Choose useful evidence

- Prefer a focused **after** screenshot that shows the changed state in context.
- Add **before and after** only when the comparison explains the change better.
- Capture multiple viewports only when responsive behaviour changed.
- Use a short video instead of many screenshots when the interaction is the change.
- Do not capture every manual test step. Choose the smallest set that helps review.
- Use synthetic or local data. Check images for personal data, credentials, tokens,
  private campaign details, and debug output before uploading them.

## Capture locally

Load the `dev-server` skill, start the worktree server, and exercise the real UI.
Browser tooling may save a capture directly. For a named Django URL, the helper is:

```bash
.codex/run.sh python scripts/screenshot.py core:campaign \
  --args <campaign-id> \
  --after \
  --output-dir screenshots/<task>
```

The helper uses the worktree's `DJANGO_PORT` and mints a local staff session for
`agent` by default. `screenshots/` is gitignored: it is staging, not the durable
home of the review evidence.

## Attach to the PR

GitHub CLI 2.99 or newer uploads local images and rewrites matching Markdown image
paths when `--attach` is supplied. Put the images in a `## Screenshots` section of
the PR body, then pass each local file with a repeated flag:

```markdown
## Screenshots

![Campaign equipment after the change](screenshots/equipment/after.png)
```

```bash
gh pr create --title "..." --body-file /tmp/pr-body.md \
  --attach screenshots/equipment/after.png
```

For an existing PR:

```bash
gh pr edit <number> --body-file /tmp/pr-body.md \
  --attach screenshots/equipment/after.png
```

When rewriting a PR body, preserve valid existing screenshot URLs or replace them
with fresh captures when the UI changed again. Do not silently drop the section.

Verify the result:

```bash
gh pr view <number> --json body --jq .body
```

The body should contain a GitHub-hosted attachment URL, not a local path. If the
installed CLI lacks `--attach`, use GitHub's browser uploader when available. If
neither route is available, report the local artifact path and the limitation;
do not commit generated images merely to satisfy this guidance.
