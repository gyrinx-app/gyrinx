# Browser inspection and blockframing

Use a browser with DOM evaluation, screenshots and computed-style inspection.
Prefer the available browser tool's native element inspector and grid/flex
highlighter. The included helper adds portable alignment and massing views.
The helper needs no package installation or external image service.

## Load the helper

Open the worktree page and wait for fonts and React to settle. Read
`.agents/skills/design-refinement/scripts/browser-review.js` and evaluate its
source in the page using the browser tool. For Chrome DevTools tools,
`evaluate_script` accepts `sourcePath` pointing to that local file with `format: "script"`. If the tool
requires a function, pass a function whose body is the file's source and
returns the IIFE result. Confirm `{ ready: true }` before calling the API.
If the shared browser profile is unavailable, use a task-owned Playwright
browser through `.codex/run.sh python`; do not stop another session's browser.
The repository already includes Playwright. Launch an isolated headless browser,
open the local agent login URL, then load the helper and inspect the same page:

```python
from pathlib import Path
from playwright.sync_api import sync_playwright

with sync_playwright() as p:
    browser = p.chromium.launch(channel="chrome", headless=True)
    page = browser.new_page(viewport={"width": 1280, "height": 900})
    page.goto(local_agent_login_url)
    page.evaluate("document.fonts.ready")
    page.evaluate(Path(".agents/skills/design-refinement/scripts/browser-review.js").read_text())
    print(page.evaluate("window.gyrinxDesignReview.inspect('main h1')"))
    page.evaluate("window.gyrinxDesignReview.overlay({root: 'main', mode: 'blocks'})")
    page.screenshot(path="screenshots/design-review/blocks.png")
    page.evaluate("window.gyrinxDesignReview.clear()")
    browser.close()
```

Create the screenshot directory first. View the captured image with the image
viewer; do not stop at collecting measurements. Wait for relevant React controls
to mount before measuring them. Use the installed Chromium default launch when
Chrome is unavailable; follow the repository's browser setup guidance if neither
is installed.

It installs `window.gyrinxDesignReview` for this document only. Reloading removes
it. The helper makes no requests or persistent changes.

Use screenshots at each stage. JSON geometry alone is not a visual inspection.
Save review captures under the task worktree's ignored `screenshots/` directory.
Keep baseline and revised captures at the same viewport, zoom, scroll, content,
theme and role. Capture the normal page before adding overlays.

## Measure actual elements

Use real selectors from the inspected DOM, scoped to the affected region.
The selectors below illustrate the API; replace them with the page's selectors.

```javascript
window.gyrinxDesignReview.inspect('main h1, main h2, main article');
window.gyrinxDesignReview.compare(['#section-title', '#first-entry']);
```

`inspect` returns CSS-pixel rectangles and resolved font, spacing, grid and
alignment styles for visible matches. `compare` requires one visible match
per selector and reports edge deltas relative to the first element. Compare
only elements intended to share an anchor. Inspect a parent and its children
to locate the padding or nested margin responsible for an offset. Use the
native computed-style inspector to find the winning rule before editing it.

Read `document.fonts.status`, browser zoom and computed font family when
unexpected wrapping or weight might be a missing font rather than a layout
problem. Check the actual rendered font in browser tools when available.
Bounding boxes measure line boxes, not glyph baselines.

## Check grids and rhythm

```javascript
window.gyrinxDesignReview.overlay({
  root: 'main', mode: 'grid', step: 4, columns: 12, gutter: 16,
});
window.gyrinxDesignReview.overlay({
  root: 'main', mode: 'anchors', selectors: ['#section-title', '#first-entry'],
});
window.gyrinxDesignReview.clear();
```

The grid is anchored to the selected root, not the viewport. Choose the root's
actual content wrapper, then set step, columns and gutter from the edition's
tokens and computed grid. Four CSS pixels is a starting diagnostic, not a new
spacing rule; a phone layout may need one or two columns. The overlay's
horizontal lines expose block rhythm; vertical tracks expose alignment and
gutters. Anchors project the selected elements' real edges in both directions.

Check repeated text starts, title-to-list edges, aligned numerical values,
label/control pairs, nested padding and action bars. Measure suspect deltas.
Do not adjust unrelated zones to a shared edge merely because a guide crosses
them. Optical alignment of icons and typographic baselines can legitimately
differ from bounding-box alignment.

## Abstract at two scales

1. **Observed detail massing.** Use `mode: 'blocks'` on the affected content
   wrapper. Text becomes monochrome line bars using its measured line width,
   font size and weight. Surfaces retain their geometry and greyscale colour;
   images and controls become neutral placeholders. Inspect gaps, repetitive
   padding, density and which masses dominate. This is an approximation of
   observed emphasis, not a pixel-perfect grayscale screenshot or squint test.
2. **Functional zones.** Choose meaningful, preferably non-overlapping regions
   such as context, task content and actions. Assign priorities from the task
   brief and use `mode: 'zones'`. Dark/medium/light show declared priority,
   not automatic judgments about what is important. Compare area and position
   with the original and the detailed massing view.

```javascript
window.gyrinxDesignReview.overlay({ root: 'main', mode: 'blocks' });
window.gyrinxDesignReview.overlay({
  root: 'main', mode: 'zones', regions: [
    { selector: '#task-content', priority: 1 },
    { selector: '#page-context', priority: 2 },
    { selector: '#occasional-tools', priority: 3 },
  ],
});
window.gyrinxDesignReview.clear();
```

Use a page-level zone view first, then isolate a representative repeated unit.
If the composition is wrong, explore arrangements with materially different
allocation of space. Restoring real copy and controls is part of verification.
The helper deliberately does not move or resize the application DOM. Try a
layout change in browser style tools if useful, then implement it in source
and reload; temporary style edits are not a completed fix.

## Limits and cleanup

Overlays follow scrolling and resizing; rerun them after changing state or
content. They cover only the current viewport. Use a viewport screenshot,
then scroll for other regions; a stitched full-page screenshot will not repeat
a fixed overlay. The helper does not analyse cross-origin frames, shadow DOM,
pseudo-elements, clipping inside every ancestor, image salience or complex
stacking contexts. Bars can overrepresent whitespace in text nodes. Native
inputs and media are placeholders, so inspect their original typography and
colour separately. A modal top layer may cover the diagnostic overlay.

Use native inspection for those cases. No occupancy percentage, automated
hierarchy score or alignment tolerance is a universal pass condition.
After review, call `clear()`, remove any temporary DevTools style changes and
capture the normal page. Exercise the actual task and changed disclosures
with keyboard and pointer. Report measurement limitations that affect a finding.

## Verify changes to the helper

Run `.codex/run.sh python .agents/skills/design-refinement/scripts/test_browser_review.py`.
It launches an isolated browser and checks known edge deltas, computed type,
hidden content, overlay replacement/cleanup, dark backgrounds, invalid options
and redraw after scrolling/resizing. These checks verify the helper's behaviour;
inspect representative real pages to verify a design.
