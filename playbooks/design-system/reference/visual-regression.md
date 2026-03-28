# Visual Regression Guide

How to perform screenshot comparison for migration verification.

## Taking Screenshots

### Tools

Use browser automation (Chrome via MCP tools or Playwright/Puppeteer):

- Fixed viewport sizes: 1280px (desktop), 375px (mobile)
- Wait for fonts and images to load
- Disable animations/transitions if possible
- Use consistent browser settings

### Consistency

- Same browser, same viewport, same user, same data
- Wait for page fully loaded (no spinners, no lazy-loading in progress)
- Capture full page height, not just viewport

## Comparison

### What Counts as Meaningful

- Layout shifts (elements moved)
- Colour changes
- Font size/weight changes
- Spacing changes
- Missing or added elements

### What to Ignore

- Sub-pixel rendering differences
- Anti-aliasing variations
- Minor shadow/gradient rendering differences

## Directory Structure

```
output/screenshots/baseline/{view-name}-desktop.png    # Stage 0
output/migration/{unit}/before/{view-name}-desktop.png  # Stage 5 before
output/migration/{unit}/after/{view-name}-desktop.png   # Stage 5 after
```

## Reporting

In PR descriptions, include before/after for every affected view. Flag any unexpected differences prominently.
