# Stage 1: Per-View Audit

## Purpose

Analyse each view individually, cataloguing every UI element, its styling, and inconsistencies.

## Execution Model

Parallel — one sub-agent per view (or small group of related views sharing templates). Target 5-8 concurrent agents.

## Input

- `output/scope/view-inventory.md`
- Baseline screenshots in `output/screenshots/baseline/`
- Access to the codebase and running app

## Per-View Analysis Process

For each view, the agent must:

### 1. Identify the Template Chain

- Find the primary template file
- Trace all `{% include %}`, `{% extends %}`, `{% block %}` relationships
- List every template file involved in rendering this view

### 2. Extract Rendered Styles (from the running app)

Load the page in the browser and for every visible element, extract computed styles via JavaScript:

- `color`, `background-color`, `border-color`
- `font-family`, `font-size`, `font-weight`, `line-height`, `letter-spacing`
- `padding`, `margin` (all four sides)
- `gap` (for flex/grid containers)
- `border-radius`, `box-shadow`
- `width`, `max-width` (for layout containers)

Group elements by semantic role (heading, body text, label, button, table cell, etc.)

### 3. Extract Source Styles (from templates and SCSS)

- For every element, identify which CSS classes are applied in the template
- Categorise each class as: Bootstrap utility, Bootstrap component, custom class, or inline style
- For custom classes, find their definition in the SCSS files
- Note any inline `style=""` attributes

### 4. Catalogue Components

List every distinct UI component instance:

- Buttons (variant, size, text, icon)
- Cards (structure, header/body/footer usage)
- Tables (classes, column types, row structure)
- Navigation elements (tabs, breadcrumbs, nav links)
- Form elements (input types, labels, help text, error states)
- Badges/tags
- Icons (which `bi-*` icon, size, colour, context)
- Tooltips
- Dropdowns/menus
- Custom elements (callouts, section headers, etc.)

For each instance, record the exact classes used.

### 5. Identify Inconsistencies

- Similar elements styled differently?
- Hardcoded values that should be variables?
- Accessibility issues (contrast, missing labels)?

### 6. Produce the View Analysis Document

Write to `output/audit/views/{view-name}.md` using `templates/per-view-analysis.md`.

## Exit Criteria (Per View)

- [ ] Analysis document exists at `output/audit/views/{view-name}.md`
- [ ] All sections populated (empty sections marked "None found")
- [ ] At least Components, Typography, and Colour sections have data
- [ ] File is >500 bytes

## Exit Criteria (Stage)

- [ ] Every view in the inventory has an analysis document
- [ ] A stage summary exists listing views processed and any failures

## Human Checkpoint

Present a summary showing:

- Number of views audited
- Total component instances found
- Number of inconsistencies flagged
- Top 5 most common components
- Any views that failed

Ask: "Can you spot-check 2-3 view audits for accuracy?"
