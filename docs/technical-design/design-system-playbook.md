# Gyrinx Design System Playbook — Specification

## Document Purpose

This document is a complete specification for a playbook that will be implemented using the `playbook-dev` Claude Code plugin. It defines every stage, analysis type, template, taxonomy, and quality gate needed to:

1. Audit the current Gyrinx UI (code and rendered output)
2. Design a consolidated design system on top of Bootstrap 5
3. Build the design system as code (SCSS tokens, Django template components, living style guide)
4. Migrate every template in the application to use the new system
5. Add linting rules to enforce the system going forward

The playbook targets **Claude Code** as the executing agent, with human review checkpoints between major stages.

---

## 1. Context

### 1.1 Application

- **App:** Gyrinx — a Necromunda tabletop gaming platform
- **URL:** https://gyrinx.app
- **Repo:** https://github.com/gyrinx-app/gyrinx
- **Purpose:** Expert-user tool for managing fighters, campaigns, equipment, battles, and rules for Necromunda tabletop gaming

### 1.2 Technical Stack

| Layer | Technology |
|-------|-----------|
| Backend | Django (Python) |
| Templates | Django template language (server-rendered HTML) |
| CSS framework | Bootstrap 5, compiled from SCSS source via npm scripts |
| Custom styles | SCSS files: `styles.scss`, `screen.scss`, `print.scss` |
| JavaScript | Vanilla JS only (no framework). Bootstrap's built-in JS for tabs, dropdowns, tooltips, collapse. Custom JS limited to things like `data-gy-toggle-submit` |
| Icons | Bootstrap Icons (`bi-*` classes) |
| Forms | Standard Django form submissions |

### 1.3 Bootstrap Usage Patterns

The app uses Bootstrap heavily but in a specific way that the playbook must understand:

- **Utility-class-heavy:** `text-muted`, `fs-7`, `small`, `hstack`, `vstack`, `gap-*`, `d-flex`, `btn-group`, `border`, `rounded`, `p-2`, etc.
- **Grid system:** Mobile-first responsive (`col-12 col-md-6 col-xl-4`)
- **Components used:** Cards, tables (`table table-sm table-borderless`), nav tabs, dropdowns, buttons (`btn btn-primary btn-sm`, `btn-outline-secondary btn-sm`), tooltips, collapse
- **Components NOT used or used unusually:** Alerts (uses `border rounded p-2` callouts instead), modals (check usage)
- **Custom extensions:** `fs-7` (smaller font size), `caps-label` (section headers), `icon-link`
- **Base font size:** `0.875rem` (14px)
- **SCSS variable overrides:** Exist but extent must be audited

### 1.4 Frontend Surface Area

- ~30–40 distinct URL patterns
- ~20–50 distinct template files
- Significant template reuse via Django `{% include %}` tags (fighter cards, weapon tables, gear sections)
- Key areas: lists (gang lists), fighters, campaigns, packs, equipment editing, skills, rules, attributes, battles, invitations

### 1.5 Dev Environment

- Django dev server runs locally and Claude Code can access it via browser
- Representative test data is seeded (users, campaigns, fighters, equipment)
- SCSS compiles via npm scripts (check `package.json` for exact commands)
- Git repo is clean and Claude Code can create branches and commits

---

## 2. Playbook Architecture

### 2.1 Stage Overview

```
Stage 0: Setup (Interactive)
    ↓ [human checkpoint]
Stage 1: Per-View Audit (Parallel)
    ↓ [human checkpoint]
Stage 2: Cross-Cutting Audit (Single agent)
    ↓ [human checkpoint]
Stage 3: Design System Specification (Single agent)
    ↓ [human checkpoint]
Stage 4: Design System Implementation (Sequential)
    ↓ [human checkpoint]
Stage 5: Template Migration (Parallel per-template)
    ↓ [human checkpoint]
Stage 6: Finalisation (Sequential)
```

Each `[human checkpoint]` is a mandatory pause. The agent produces a summary of what it found/did, the human reviews and approves before the next stage begins. The agent must explicitly request human input and wait for confirmation.

### 2.2 Directory Structure

```
playbook/
├── instructions.md                    # Master orchestration document
├── stages/
│   ├── 0-setup/
│   │   └── README.md                 # Environment validation, scope, screenshots
│   ├── 1-per-view-audit/
│   │   └── README.md                 # Per-view analysis instructions
│   ├── 2-cross-cutting-audit/
│   │   ├── README.md                 # Aggregation instructions
│   │   ├── colour-audit.md           # Colour extraction and clustering
│   │   ├── typography-audit.md       # Type scale analysis
│   │   ├── spacing-audit.md          # Spacing value analysis
│   │   ├── component-audit.md        # Component inventory and variants
│   │   ├── icon-audit.md             # Icon usage inventory
│   │   ├── layout-audit.md           # Grid and page structure patterns
│   │   └── custom-css-audit.md       # Non-Bootstrap CSS analysis
│   ├── 3-design-system-spec/
│   │   ├── README.md                 # Spec authoring instructions
│   │   ├── foundations.md             # Tokens, scales, principles
│   │   ├── components.md             # Component specifications
│   │   └── patterns.md               # Page-level patterns
│   ├── 4-implementation/
│   │   ├── README.md                 # Implementation instructions
│   │   ├── scss-tokens.md            # SCSS variable/token file creation
│   │   ├── template-components.md    # Django template tag/include creation
│   │   ├── style-guide-app.md        # Living style guide Django app
│   │   └── linting.md                # Linting rule creation
│   ├── 5-migration/
│   │   ├── README.md                 # Migration execution instructions
│   │   ├── migration-plan.md         # How to determine PR granularity
│   │   └── visual-regression.md      # Screenshot comparison process
│   └── 6-finalisation/
│       └── README.md                 # Summary, cleanup, verification
├── templates/
│   ├── per-view-analysis.md          # Template for Stage 1 output
│   ├── audit-dimension.md            # Template for Stage 2 dimension reports
│   ├── design-system-spec.md         # Template for the final spec document
│   ├── component-spec.md             # Template for individual component specs
│   ├── migration-pr.md               # Template for migration PR descriptions
│   └── human-checkpoint.md           # Template for checkpoint summaries
├── reference/
│   ├── bootstrap-5-defaults.md       # Key Bootstrap 5 default values for comparison
│   ├── component-taxonomy.md         # Classification system for UI components
│   ├── colour-clustering.md          # How to cluster and consolidate colours
│   ├── django-template-components.md # How Django template tags work as components
│   └── visual-regression.md          # How to do screenshot comparison
└── output/                           # All playbook outputs land here
    ├── screenshots/                  # Organised by stage and view
    ├── audit/                        # Stage 1 and 2 outputs
    ├── spec/                         # Stage 3 outputs
    └── migration/                    # Stage 5 PR descriptions and screenshots
```

### 2.3 Data Flow

```
[Gyrinx codebase + running app]
         ↓
Stage 0: Environment validation ──────→ output/scope.md
         ↓                              output/screenshots/baseline/*.png
Stage 1: Per-view audit ──────────────→ output/audit/views/{view-name}.md (one per view)
         ↓
Stage 2: Cross-cutting audit ─────────→ output/audit/colours.md
                                        output/audit/typography.md
                                        output/audit/spacing.md
                                        output/audit/components.md
                                        output/audit/icons.md
                                        output/audit/layouts.md
                                        output/audit/custom-css.md
                                        output/audit/SUMMARY.md
         ↓
Stage 3: Design system spec ──────────→ output/spec/DESIGN-SYSTEM.md (the primary deliverable)
                                        output/spec/tokens.json (machine-readable tokens)
         ↓
Stage 4: Implementation ──────────────→ Actual code changes:
                                          - gyrinx/designsystem/ (new Django app)
                                          - static/scss/_tokens.scss
                                          - templates/designsystem/ (style guide templates)
                                          - templates/components/ (reusable template components)
                                          - .stylelintrc (linting config)
         ↓
Stage 5: Migration ───────────────────→ Git branches + commits per migration unit
                                        output/migration/{unit}/before/*.png
                                        output/migration/{unit}/after/*.png
                                        output/migration/{unit}/pr-description.md
         ↓
Stage 6: Finalisation ───────────────→ output/SUMMARY.md
                                       output/migration-tracker.md
```

---

## 3. Stage Specifications

### 3.0 Stage 0: Setup

**Purpose:** Validate the environment, establish scope, take baseline screenshots of every view.

**Execution model:** Interactive (requires human input)

**Steps:**

1. **Validate repository access**
   - Confirm the Gyrinx repo is cloned and accessible
   - Identify the project root directory
   - Check git status is clean (or note uncommitted changes)
   - Identify the current branch

2. **Map the codebase structure**
   - Find all Django template files (`.html` files in template directories)
   - Find all SCSS files and their import structure
   - Find all static JS files
   - Find the `package.json` and identify the SCSS build command
   - Find the Django URL configuration and map URL patterns to views to templates
   - Produce a file: `output/scope/template-map.md` listing every template, its URL (if any), and its includes

3. **Validate the dev server**
   - Start the Django dev server (or confirm it's running)
   - Confirm it's accessible via browser
   - Confirm test data is present by hitting a known populated URL
   - Record the base URL (e.g., `http://localhost:8000`)

4. **Compile SCSS**
   - Run the npm SCSS build to ensure compiled CSS is current
   - Note the build command for future use

5. **Enumerate all visitable views**
   - From the URL map, produce a list of every distinct URL that can be visited
   - For views that require authentication, note the login flow
   - For views that require specific data (e.g., a specific fighter ID), identify suitable test data IDs from the seeded database
   - For views with multiple states (e.g., tabs, filters), note each state as a separate screenshot target
   - Produce: `output/scope/view-inventory.md`

6. **Take baseline screenshots**
   - Visit every URL in the view inventory
   - Take a full-page screenshot at 1280px width
   - Take a mobile screenshot at 375px width for views that appear responsive
   - Save to `output/screenshots/baseline/{view-name}-desktop.png` and `{view-name}-mobile.png`
   - If a view has multiple states (tabs, etc.), screenshot each state: `{view-name}-{state}-desktop.png`

7. **Produce scope document**
   - Write `output/scope.md` summarising:
     - Number of templates found
     - Number of views screenshotted
     - Any views that couldn't be reached and why
     - SCSS file structure
     - Bootstrap version confirmed
     - Any initial observations (e.g., "print.scss exists, suggesting print styles need consideration")

**Exit criteria:**

- `output/scope/template-map.md` exists and lists all templates
- `output/scope/view-inventory.md` exists and lists all visitable URLs
- `output/screenshots/baseline/` contains a screenshot for every view
- `output/scope.md` exists with the summary
- Dev server is confirmed accessible

**Human checkpoint:** Present the scope document and screenshot count. Ask the human to review the baseline screenshots and confirm the inventory is complete before proceeding. Specifically ask: "Are there any views, states, or areas I've missed?"

---

### 3.1 Stage 1: Per-View Audit

**Purpose:** Analyse each view individually, cataloguing every UI element, its styling, and any inconsistencies.

**Execution model:** Parallel — one sub-agent per view (or per small group of related views if they share templates heavily). Target 5–8 concurrent agents.

**Input:** `output/scope/view-inventory.md`, baseline screenshots, access to the codebase and running app.

**Per-view analysis process:**

For each view, the agent must:

1. **Identify the template chain**
   - Find the primary template file for this view
   - Trace all `{% include %}`, `{% extends %}`, and `{% block %}` relationships
   - List every template file involved in rendering this view

2. **Extract rendered styles** (from the running app)
   - Load the page in the browser
   - For every visible element, extract computed styles via JavaScript:
     - `color`, `background-color`, `border-color` (all colour properties)
     - `font-family`, `font-size`, `font-weight`, `line-height`, `letter-spacing`
     - `padding`, `margin` (all four sides)
     - `gap` (for flex/grid containers)
     - `border-radius`, `box-shadow`
     - `width`, `max-width` (for layout containers)
   - Group elements by their semantic role (heading, body text, label, button, table cell, etc.)

3. **Extract source styles** (from the templates and SCSS)
   - For every element, identify which CSS classes are applied in the template
   - Categorise each class as: Bootstrap utility, Bootstrap component, custom class, or inline style
   - For custom classes, find their definition in the SCSS files
   - Note any inline `style=""` attributes

4. **Catalogue components on this view**
   - List every distinct UI component instance:
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
   - For each instance, record the exact classes used

5. **Identify inconsistencies within this view**
   - Are similar elements styled differently? (e.g., two buttons that should match but don't)
   - Are there hardcoded values that should be variables?
   - Are there accessibility issues? (contrast, missing labels)

6. **Produce the view analysis document**
   - Write to `output/audit/views/{view-name}.md` using the per-view analysis template

**Per-view output template:**

```markdown
# View Audit: {View Name}

## Metadata
- **URL:** {url}
- **Template:** {primary template path}
- **Template chain:** {list of all templates involved}
- **Screenshot:** {link to baseline screenshot}

## Components Found

### Buttons
| Text | Classes | Variant | Size | Icon | Notes |
|------|---------|---------|------|------|-------|

### Cards
| Purpose | Classes | Has Header | Has Footer | Notes |
|---------|---------|------------|------------|-------|

### Tables
| Purpose | Classes | Columns | Row count | Notes |
|---------|---------|---------|-----------|-------|

### Navigation
| Type | Classes | Items | Notes |
|------|---------|-------|-------|

### Forms
| Element | Type | Classes | Label | Help Text | Notes |
|---------|------|---------|-------|-----------|-------|

### Icons
| Icon class | Context | Size | Colour | Notes |
|------------|---------|------|--------|-------|

### Other Components
| Type | Classes | Description | Notes |
|------|---------|-------------|-------|

## Typography Usage
| Element | Computed size | Computed weight | Computed line-height | Classes applied | Semantic role |
|---------|--------------|-----------------|---------------------|-----------------|---------------|

## Colour Usage
| Element | Property | Computed value | Source (class/inline/inherited) | Semantic purpose |
|---------|----------|---------------|-------------------------------|-----------------|

## Spacing Values
| Element | Property | Computed value | Source class | Notes |
|---------|----------|---------------|-------------|-------|

## Custom CSS
| Class name | Defined in | Properties | Used on elements | Notes |
|------------|-----------|------------|-----------------|-------|

## Inconsistencies
| Issue | Elements involved | Description | Severity (high/medium/low) |
|-------|-------------------|-------------|---------------------------|

## Accessibility Notes
| Issue | Element | Description |
|-------|---------|-------------|
```

**Exit criteria per view:**

- Analysis document exists at the correct path
- All sections are populated (empty sections marked "None found")
- At least the Components, Typography, and Colour sections have data
- File is >500 bytes

**Stage-level exit criteria:**

- Every view in the inventory has an analysis document
- A stage summary exists listing views processed and any failures

**Human checkpoint:** Present a summary showing: number of views audited, total component instances found, number of inconsistencies flagged, top 5 most common components, and any views that failed. Ask the human to spot-check 2–3 view audits for accuracy.

---

### 3.2 Stage 2: Cross-Cutting Audit

**Purpose:** Aggregate all per-view data into dimension-specific reports that reveal the true state of the design system across the whole app.

**Execution model:** Single agent, processing one dimension at a time sequentially (each dimension needs the full dataset).

**Input:** All `output/audit/views/*.md` files, the SCSS source files, the running app.

#### 3.2.1 Colour Audit (`output/audit/colours.md`)

1. **Extract every colour value**
   - From all per-view audits: every computed colour value (hex normalised to lowercase 6-digit)
   - From SCSS source: every colour literal, every Bootstrap variable override, every custom variable
   - From templates: any inline colour values

2. **Deduplicate and count**
   - Produce a table of every unique colour, its frequency (how many elements use it), and where it appears

3. **Cluster by perceptual similarity**
   - Group colours that are within a small perceptual distance (e.g., ΔE < 5 in CIELAB)
   - For each cluster, identify whether it's:
     - **Intentional variants** (e.g., hover state is darker version of primary)
     - **Drift** (e.g., `#6c757d` and `#6b7280` are clearly meant to be the same grey)
   - Flag clusters with >2 members as candidates for consolidation

4. **Map to Bootstrap's palette**
   - For each colour in use, identify whether it matches a Bootstrap default, a Bootstrap variable override, or is entirely custom
   - Produce a table: `| Colour | Bootstrap equivalent | Is override | Is custom |`

5. **Identify semantic usage**
   - Map colours to their semantic purpose: primary action, secondary action, text, muted text, background, border, error, success, warning, info
   - Flag any colour used for multiple conflicting semantic purposes

6. **Produce consolidation recommendation**
   - Proposed consolidated palette with:
     - Semantic name
     - Recommended hex value (chosen from the most common in each cluster)
     - Bootstrap variable it maps to (if any)
     - Number of existing values it replaces

#### 3.2.2 Typography Audit (`output/audit/typography.md`)

1. **Extract every text style combination**
   - From all per-view audits: every unique combination of `font-size`, `font-weight`, `line-height`, `letter-spacing`, `text-transform`
   - Count frequency of each combination

2. **Map to Bootstrap's type scale**
   - Which combinations are stock Bootstrap? (e.g., `h1`–`h6`, `.fs-1`–`.fs-6`, `.small`, `.lead`)
   - Which are the custom `fs-7`?
   - Which are entirely custom (e.g., `caps-label`)?

3. **Identify the implicit type scale**
   - Sort all font sizes in use from largest to smallest
   - Identify the natural clusters (there should be 6–10 meaningful steps)
   - Note gaps and overlaps

4. **Produce consolidation recommendation**
   - Proposed type scale with:
     - Scale name (e.g., `display`, `heading-1`, `heading-2`, `body`, `body-small`, `caption`, `label`)
     - Size, weight, line-height, letter-spacing, text-transform
     - Bootstrap class it maps to
     - Custom class needed (if any)
     - Where it's used (semantic roles)

#### 3.2.3 Spacing Audit (`output/audit/spacing.md`)

1. **Extract every spacing value**
   - All padding, margin, and gap values from per-view audits
   - Count frequency of each value

2. **Identify the implicit scale**
   - Sort values and identify clusters
   - Compare against Bootstrap's default spacing scale (0, 0.25rem, 0.5rem, 1rem, 1.5rem, 3rem)
   - Check if Bootstrap's spacing utilities (`p-1`, `m-2`, `gap-3`, etc.) are used consistently or if there are manual values

3. **Produce consolidation recommendation**
   - Confirm or modify Bootstrap's spacing scale for Gyrinx
   - Flag any non-standard spacing values that need to be mapped to the nearest scale step

#### 3.2.4 Component Audit (`output/audit/components.md`)

This is the most critical dimension.

1. **Aggregate all component instances across all views**
   - For each component type (button, card, table, nav, form element, badge, icon, dropdown, tooltip, custom):
     - How many total instances
     - How many distinct variants (unique class combinations)
     - Frequency of each variant
     - Which views each variant appears on

2. **Classify each component type using the component taxonomy** (see reference/component-taxonomy.md)
   - **Canonical**: The dominant variant that should be the standard (most frequent, most consistent)
   - **Acceptable variant**: Intentionally different for a good reason (e.g., a compact button for dense tables)
   - **Drift**: Unintentional deviation from the canonical (should be migrated)
   - **Bespoke**: One-off implementation that doesn't fit any standard (needs design decision)

3. **For each component type, produce a component profile:**

```markdown
### {Component Type}: Button

**Total instances:** {N}
**Distinct variants:** {N}

#### Variant Table
| Classes | Frequency | Views | Classification | Notes |
|---------|-----------|-------|---------------|-------|

#### Canonical Definition
- Classes: `{classes}`
- Appears: {N} times across {N} views
- Properties: {key CSS properties}

#### Recommended Variants
| Variant name | Use case | Classes | Difference from canonical |
|-------------|----------|---------|--------------------------|

#### Migration Targets
| Current classes | → Target classes | Affected views | Effort |
|----------------|------------------|----------------|--------|
```

1. **Identify missing components**
   - Are there UI patterns that are implemented with raw HTML/CSS that should be components? (e.g., the `border rounded p-2` callout pattern)
   - Are there Django `{% include %}` patterns that are already de facto components but not formalised?

2. **Identify shared template includes**
   - List every `{% include %}` template
   - Map which views use each include
   - Note which includes are component-like (reusable UI elements) vs structural (page sections)

#### 3.2.5 Icon Audit (`output/audit/icons.md`)

1. **List every Bootstrap Icon class used**
   - Frequency of each
   - Context (what it's next to, what it represents)

2. **Identify inconsistencies**
   - Same concept represented by different icons in different places
   - Icons used at different sizes inconsistently
   - Icons used without accessible labels

3. **Produce recommendation**
   - Canonical icon for each concept
   - Standard sizing convention
   - Accessibility requirements

#### 3.2.6 Layout Audit (`output/audit/layouts.md`)

1. **Identify distinct page layouts**
   - Full-width vs constrained-width
   - Sidebar layouts vs single-column
   - Grid structures (how many columns, breakpoint patterns)

2. **Map each view to a layout type**

3. **Identify the implicit layout system**
   - Are there 2–4 standard page shells?
   - Are containers used consistently?
   - Are breakpoints used consistently?

4. **Produce recommendation**
   - Named layout types with their structure
   - Which views use which layout

#### 3.2.7 Custom CSS Audit (`output/audit/custom-css.md`)

1. **Inventory all custom SCSS**
   - Every rule that isn't a Bootstrap override
   - Every custom class (like `caps-label`, `fs-7`)
   - Every element selector or ID selector

2. **Classify each custom rule:**
   - **Token candidate**: Should become a design token (e.g., custom colour, custom size)
   - **Component candidate**: Should become a named component style
   - **Bootstrap extension**: Extends Bootstrap in a standard way (e.g., `fs-7`)
   - **Override/fix**: Works around a Bootstrap limitation
   - **Dead code**: Not referenced anywhere in templates

3. **Produce recommendation**
   - Which custom rules to keep, formalise, replace, or remove

#### 3.2.8 Audit Summary (`output/audit/SUMMARY.md`)

Synthesise all dimension reports into a single overview:

- **Palette health:** How many colours in use vs recommended consolidated count
- **Typography health:** How many text styles vs recommended scale size
- **Spacing health:** How consistently the spacing scale is followed
- **Component health:** Ratio of canonical vs drift vs bespoke instances
- **Biggest wins:** Top 5 changes that would most improve consistency (by frequency × severity)
- **Biggest risks:** Areas where migration is most complex or risky
- **Estimated scope:** Rough count of template changes needed

**Exit criteria:**

- All seven dimension reports exist and contain data
- SUMMARY.md exists and synthesises findings
- Each dimension report includes a consolidation recommendation

**Human checkpoint:** Present the SUMMARY.md. Ask the human to review the consolidation recommendations, especially: proposed colour palette, proposed type scale, and component classifications. These are design decisions that need human approval before being encoded into the spec. Specifically ask: "Do you agree with these consolidation choices, or do you want to adjust any of them?"

---

### 3.3 Stage 3: Design System Specification

**Purpose:** Author the definitive design system specification document that will govern all future UI work.

**Execution model:** Single agent.

**Input:** All Stage 2 outputs (with human-approved consolidation recommendations), the codebase, the running app.

**The primary output is `output/spec/DESIGN-SYSTEM.md`.** This is the single most important deliverable of the entire playbook. It must be self-contained, unambiguous, and usable by humans and AI agents alike.

#### 3.3.1 Document Structure

```markdown
# Gyrinx Design System

## 1. Principles
## 2. Foundations
### 2.1 Colour
### 2.2 Typography
### 2.3 Spacing
### 2.4 Icons
### 2.5 Elevation & Borders
### 2.6 Motion (if applicable)
## 3. Layout
### 3.1 Grid
### 3.2 Page Templates
### 3.3 Responsive Behaviour
## 4. Components
### 4.N {Component Name}
## 5. Patterns
### 5.1 Data Display
### 5.2 Forms
### 5.3 Navigation
### 5.4 Empty States
### 5.5 Loading States
### 5.6 Error States
## 6. Django Template Components Reference
## 7. SCSS Token Reference
```

#### 3.3.2 Section Requirements

**Principles (Section 1)**

Write 5–8 concrete, actionable design principles derived from the audit findings and the nature of the app. These must be specific to Gyrinx, not generic. Examples of the *type* of principle needed (the actual content must come from the audit):

- "Prefer information density. Gyrinx users manage complex gang rosters and need to see many data points simultaneously. Use compact spacing (`gap-2`, `p-2`) and small text (`fs-7`, `.small`) for data displays."
- "Use colour sparingly for emphasis. Most of the UI should be neutral (greys and white). Reserve colour for interactive elements, status indicators, and callouts."
- "Every interactive element must have a visible focus state. Keyboard navigation is required."

Each principle must include: a clear statement, a rationale tied to the app's domain, and a concrete example of how to apply it.

**Foundations (Section 2)**

For each foundation, provide:

- The complete token list with exact values
- The SCSS variable name for each token
- The Bootstrap class mapping where one exists
- Usage guidance (when to use each value)
- Do's and don'ts

**Colour** must include:

- Semantic colour tokens: `$gy-color-text-primary`, `$gy-color-text-secondary`, `$gy-color-text-muted`, `$gy-color-bg-primary`, `$gy-color-bg-secondary`, `$gy-color-bg-surface`, `$gy-color-border`, `$gy-color-interactive`, `$gy-color-interactive-hover`, `$gy-color-success`, `$gy-color-warning`, `$gy-color-danger`, `$gy-color-info`
- The hex value for each
- The Bootstrap variable it maps to (e.g., `$gy-color-interactive` maps to Bootstrap's `$primary`)
- A note on contrast ratios for text colours against their expected backgrounds

Use the `$gy-` prefix for all custom tokens to namespace them away from Bootstrap.

**Typography** must include:

- The complete type scale as a table
- Each entry: scale name, SCSS variable, font-size, font-weight, line-height, letter-spacing, text-transform, Bootstrap class equivalent (if any)
- Semantic mapping: when to use each scale step (e.g., "page titles", "section headers", "body text", "table cell text", "captions", "labels")

**Spacing** must include:

- The spacing scale (likely Bootstrap's default, possibly extended)
- SCSS variables for semantic spacing if needed (e.g., `$gy-spacing-card-padding`)
- Guidance on when to use which scale step

**Icons** must include:

- The canonical icon for each concept (derived from icon audit)
- Size conventions
- Colour conventions
- Accessibility requirements (aria-label, sr-only text)

**Components (Section 4)**

For EACH component in the consolidated component inventory, provide a specification following this structure:

```markdown
### 4.N {Component Name}

**Purpose:** {One sentence: what this component is for}

**When to use:** {Specific guidance on when to reach for this component}

**Django template usage:**
\`\`\`django
{% include "components/{name}.html" with variant="primary" size="sm" %}
\`\`\`
OR
\`\`\`django
{% {name} variant="primary" size="sm" %}...{% end{name} %}
\`\`\`

**Variants:**
| Variant | Classes | Use case |
|---------|---------|----------|

**Sizes:**
| Size | Classes | Use case |
|------|---------|----------|

**States:**
| State | Visual treatment | Classes/attributes |
|-------|-----------------|-------------------|

**Anatomy:**
- {Describe the DOM structure, padding, spacing between sub-elements}

**Colour tokens used:**
- {List which tokens apply to which parts}

**Typography tokens used:**
- {List which type scale entries apply}

**Accessibility:**
- {ARIA requirements, focus behaviour, keyboard interaction}

**Do:**
- {Concrete positive examples}

**Don't:**
- {Concrete anti-patterns, referencing actual instances found in the audit}

**Migration notes:**
- {What currently exists that should become this component}
- {Specific class combinations to find-and-replace}
```

The components section must cover at minimum:

- Button (all variants: primary, secondary, outline, danger, sizes, with/without icon)
- Card (standard, compact, with/without header/footer)
- Data table (standard, compact, borderless)
- Nav tabs
- Dropdown / action menu (three-dots pattern)
- Badge / tag
- Callout (the `border rounded p-2` pattern that replaces alerts)
- Section header (`caps-label`)
- Icon link
- Form field (input, select, textarea, checkbox, with labels and help text)
- Tooltip
- Empty state
- Loading state

**Patterns (Section 5)**

Higher-level compositions. Each pattern must include:

- When to use it
- The DOM structure (pseudo-code or Django template snippet)
- Which components it's composed of
- A real example from Gyrinx (referencing a specific view)

**Django Template Components Reference (Section 6)**

A lookup table for every template component that will be created:

| Component | Template path | Required params | Optional params | Example |
|-----------|--------------|-----------------|-----------------|---------|

**SCSS Token Reference (Section 7)**

A complete listing of every SCSS variable in the token file, grouped by category, with the value and a one-line description.

#### 3.3.3 Secondary Output: `output/spec/tokens.json`

A machine-readable JSON file containing all design tokens:

```json
{
  "color": {
    "text-primary": { "value": "#212529", "scss": "$gy-color-text-primary", "bootstrap": "$body-color" },
    ...
  },
  "typography": {
    "body": { "size": "0.875rem", "weight": "400", "line-height": "1.5", "scss": "$gy-type-body-size" },
    ...
  },
  "spacing": {
    "1": { "value": "0.25rem", "scss": "$spacer * .25", "bootstrap": "$spacer-1" },
    ...
  }
}
```

**Exit criteria:**

- `output/spec/DESIGN-SYSTEM.md` exists and contains all required sections
- Every section has substantive content (not placeholders)
- Every component has a full specification
- `output/spec/tokens.json` exists and is valid JSON
- The spec is internally consistent (no token referenced in a component spec that doesn't exist in the foundations)
- The spec is self-contained (an agent with no other context could implement from it alone)

**Human checkpoint:** Present the full design system spec. Ask the human to review: the principles, the colour palette, the type scale, and the component specifications for the 3 most common components. Ask: "Does this system accurately represent what you want Gyrinx to look like? Are there any components where you'd make different choices?"

---

### 3.4 Stage 4: Design System Implementation

**Purpose:** Create the actual code artefacts that make the design system real.

**Execution model:** Sequential (each artefact depends on the previous).

**Input:** `output/spec/DESIGN-SYSTEM.md`, `output/spec/tokens.json`, the codebase.

#### 3.4.1 SCSS Tokens (`stages/4-implementation/scss-tokens.md`)

1. **Create `static/scss/_tokens.scss`**
   - Every token from `tokens.json` as an SCSS variable
   - Organised by category with comment headers
   - Bootstrap variable overrides at the top (so they take effect before Bootstrap compiles)
   - Custom tokens below

2. **Update the SCSS import chain**
   - `_tokens.scss` must be imported before Bootstrap's source
   - Verify the compiled CSS correctly reflects the token values

3. **Verify nothing breaks**
   - Compile SCSS
   - Load 3 key pages in the browser
   - Visually confirm no regressions

#### 3.4.2 Django Template Components (`stages/4-implementation/template-components.md`)

1. **Create template include files** in `templates/components/`
   - One `.html` file per component from the spec
   - Each component template accepts parameters via `{% with %}` or template context
   - Each component template has a comment block at the top documenting its parameters
   - Use Bootstrap classes internally — the component is the abstraction, not a replacement for Bootstrap

2. **If any components need custom template tags**, create them in the `designsystem` app's `templatetags/` directory

3. **Naming convention:** `components/{component-name}.html` (kebab-case)

Example component template:

```django
{# components/button.html #}
{# Params: variant (primary|secondary|outline|danger), size (sm|md|lg), icon (bi-* class), text, href (optional) #}
{% with variant=variant|default:"primary" size=size|default:"md" %}
{% if href %}
<a href="{{ href }}" class="btn btn-{{ variant }}{% if size != 'md' %} btn-{{ size }}{% endif %}">
  {% if icon %}<i class="bi {{ icon }}"></i> {% endif %}{{ text }}
</a>
{% else %}
<button type="{{ type|default:'button' }}" class="btn btn-{{ variant }}{% if size != 'md' %} btn-{{ size }}{% endif %}">
  {% if icon %}<i class="bi {{ icon }}"></i> {% endif %}{{ text }}
</button>
{% endif %}
{% endwith %}
```

#### 3.4.3 Living Style Guide App (`stages/4-implementation/style-guide-app.md`)

1. **Create a new Django app: `gyrinx/designsystem/`**
   - `views.py` with a single view rendering the style guide
   - URL: `/design-system/` (only accessible in DEBUG mode or to staff users)
   - `templates/designsystem/styleguide.html`

2. **The style guide page must render:**
   - The colour palette (swatches with hex values and token names)
   - The type scale (each step rendered at its actual size)
   - The spacing scale (visual boxes showing each spacing value)
   - Every component in every variant and size
   - Each component section includes the Django template code to use it

3. **The style guide must be a live rendering**, not screenshots — it uses the actual SCSS and component templates, so it's always in sync with the real implementation.

#### 3.4.4 Linting Rules (`stages/4-implementation/linting.md`)

1. **Create a Stylelint configuration** (`.stylelintrc.json` or `.stylelintrc.yml`)
   - Disallow hardcoded colour values (must use tokens)
   - Disallow font-size declarations outside of the defined scale
   - Warn on `!important` usage
   - Enforce SCSS variable naming convention (`$gy-*` prefix for custom tokens)

2. **Create a simple template linter** (can be a Python script)
   - Scan Django templates for known anti-patterns:
     - Inline `style=""` attributes
     - Hardcoded colour classes that should use the semantic system
     - Component patterns that should use an `{% include %}` instead of raw HTML
   - Output: list of violations with file, line, and suggested fix

3. **Document how to run both linters** in the design system spec

**Exit criteria:**

- `_tokens.scss` exists, compiles, and the app renders correctly with it
- All component templates exist in `templates/components/`
- The `designsystem` Django app exists and is registered
- The style guide page renders at `/design-system/` showing all components
- Linting configuration exists and runs without errors on the current codebase (it WILL report violations — that's expected pre-migration)

**Human checkpoint:** Present the living style guide URL. Ask the human to visit it and verify that the components look correct. Also present the linting output showing current violation counts. Ask: "Does the style guide look right? Are you happy with the component implementations before I start migrating templates?"

---

### 3.5 Stage 5: Template Migration

**Purpose:** Migrate every template in the app to use the design system consistently.

**Execution model:** Parallel per migration unit. PR granularity is determined by the agent based on the audit findings (see below).

**Input:** The design system spec, the component templates, all per-view audits (for knowing what needs to change), the linting output (for finding violations).

#### 3.5.1 Determining Migration Units

The agent must decide how to batch changes into PRs. Guidelines:

- **Shared includes first:** If a template include (like a fighter card partial) is used on 10 views, migrating it is one PR that fixes 10 views at once. Always migrate shared includes before the views that use them.
- **Foundation changes as a single PR:** The `_tokens.scss` file and any Bootstrap variable overrides should be their own PR (this may already be done in Stage 4).
- **Component-level PRs when a component spans many views:** If standardising buttons across the whole app, that could be one PR if the changes are mechanical and low-risk.
- **View-level PRs when changes are view-specific:** If a particular view has bespoke layout or structural changes, that's its own PR.
- **Never mix structural refactors with cosmetic changes:** A PR that restructures a template's DOM should not also tweak colours.

Produce: `output/migration/plan.md` listing every migration unit in order, with:

- What changes
- Which files are affected
- Which views are affected
- Estimated risk (high/medium/low)
- Dependencies (which units must be done first)

#### 3.5.2 Per-Migration-Unit Process

For each migration unit:

1. **Create a git branch**: `design-system/{unit-name}`
2. **Take "before" screenshots** of every affected view (at 1280px desktop)
3. **Make the changes:**
   - Replace raw HTML with `{% include "components/..." %}` where applicable
   - Swap hardcoded classes for standardised ones per the spec
   - Replace hardcoded colour/spacing values with token-based alternatives
   - Fix any inconsistencies flagged in the per-view audit
4. **Compile SCSS** (if SCSS changes are included)
5. **Take "after" screenshots** of every affected view
6. **Compare before/after screenshots:**
   - Flag any views where visual differences are unexpected
   - Document intended visual changes vs unintended regressions
7. **Run the template linter** on changed files — confirm violations are reduced
8. **Commit with a descriptive message**
9. **Write a PR description** using the migration PR template:

```markdown
# {Migration Unit Title}

## What changed
{Brief description}

## Files changed
{List of files}

## Views affected
{List of views with URLs}

## Visual comparison
### {View Name}
**Before:** ![before]({path to before screenshot})
**After:** ![after]({path to after screenshot})

## Linting
- Violations before: {N}
- Violations after: {N}

## Risk
{High/Medium/Low with rationale}

## Testing
- [ ] All affected views load without errors
- [ ] Visual comparison reviewed
- [ ] No unintended changes to other views
```

1. **Save the PR description** to `output/migration/{unit-name}/pr-description.md`

#### 3.5.3 Migration Order

The recommended order is:

1. SCSS foundation (tokens, variable overrides)
2. Shared component templates (create the `components/` includes)
3. Shared layout templates (base templates, page shells)
4. Shared include templates (fighter cards, weapon tables, etc.)
5. Individual page templates (ordered by traffic/importance if known, otherwise alphabetical)
6. Print styles

**Exit criteria:**

- `output/migration/plan.md` exists with all migration units
- Every migration unit has a branch, commits, before/after screenshots, and a PR description
- The template linter shows reduced violations after migration
- All views still render without errors (no 500s, no missing templates)

**Human checkpoint:** Present the migration plan. For completed migrations, present the before/after screenshots for the 5 highest-risk changes. Ask: "Are you happy with how these look? Should I proceed with the remaining migrations?"

---

### 3.6 Stage 6: Finalisation

**Purpose:** Wrap up, verify completeness, and produce the summary.

**Execution model:** Sequential, single agent.

**Steps:**

1. **Run the template linter across the entire codebase**
   - Report remaining violations
   - Categorise: intentional exceptions vs missed migrations

2. **Run the SCSS linter across all SCSS**
   - Report remaining violations

3. **Full screenshot sweep**
   - Re-screenshot every view
   - Compare against Stage 0 baseline screenshots
   - Produce a visual diff summary

4. **Verify the style guide**
   - Load `/design-system/`
   - Confirm all components render correctly
   - Confirm the page is navigable and usable as documentation

5. **Verify the spec document**
   - Check that `DESIGN-SYSTEM.md` matches the implemented reality
   - Every component in the spec exists as a template
   - Every token in the spec exists in `_tokens.scss`
   - Every Django template component reference is correct

6. **Produce `output/SUMMARY.md`:**
   - What was done (overview of all stages)
   - Key statistics: colours before/after, text styles before/after, component variants before/after
   - Remaining work (any views not migrated, known exceptions)
   - How to maintain the system going forward
   - How to use the template linter in CI
   - Links to all key files: spec, style guide URL, token file, linter config

7. **Produce `output/migration-tracker.md`:**
   - Table of every view, its migration status, and the branch/PR that migrated it
   - Overall completion percentage

**Exit criteria:**

- `output/SUMMARY.md` exists
- `output/migration-tracker.md` exists and shows completion status
- Final screenshot sweep is complete
- The spec document is verified against the implementation
- The human has a clear picture of what's done and what remains

**Human checkpoint:** Present the final summary. Ask: "Is there anything missing or anything you'd like me to revisit?"

---

## 4. Reference Documents

### 4.1 Component Taxonomy (`reference/component-taxonomy.md`)

Classification system for UI components found during the audit:

| Classification | Definition | Action |
|---------------|------------|--------|
| **Canonical** | The dominant, most consistent variant. Appears most frequently and represents the intended design. | Encode in the design system spec as-is. |
| **Acceptable Variant** | Intentionally different from canonical for a good reason (e.g., compact size for tables, danger variant for destructive actions). | Encode as a named variant in the spec. |
| **Drift** | Unintentional deviation. Same intended component but with slightly different classes, spacing, or colours. | Migrate to canonical. |
| **Bespoke** | One-off implementation for a specific view that doesn't fit any standard. | Design decision needed: standardise into a new variant, or accept as an exception. |
| **Anti-pattern** | Incorrect usage that causes UX or accessibility problems. | Fix during migration. |
| **Dead** | Styles or components defined in CSS but not used in any template. | Remove during migration. |

### 4.2 Bootstrap 5 Defaults Reference (`reference/bootstrap-5-defaults.md`)

Key Bootstrap 5 default values that the audit should compare against. The playbook agent should extract these from the actual Bootstrap source in `node_modules` rather than relying on this reference, but these are useful as a quick cross-reference:

- Default colour palette (primary, secondary, success, danger, warning, info, light, dark)
- Default type scale (fs-1 through fs-6, body, small)
- Default spacing scale (0 through 5, plus auto)
- Default breakpoints (sm: 576, md: 768, lg: 992, xl: 1200, xxl: 1400)
- Default border-radius, box-shadow values
- Default font stack, base size, line-height

### 4.3 Django Template Components Guide (`reference/django-template-components.md`)

How to build reusable UI components using Django's template system:

- `{% include %}` with `{% with %}` for parameterised components
- Custom template tags (simple tags, inclusion tags) for more complex components
- Template fragments and `{% block %}` for composable layouts
- Naming conventions and directory structure
- Limitations: no prop validation, no TypeScript-style type checking, reliance on convention
- How to document components (comment blocks at top of template, usage examples)

### 4.4 Visual Regression Guide (`reference/visual-regression.md`)

How to perform screenshot comparison:

- Tools: Playwright (Python), Puppeteer, or Selenium for browser automation
- Taking consistent screenshots: fixed viewport, wait for fonts/images to load, disable animations
- Comparison: pixel-diff tools (e.g., `pixelmatch` via Node, or Pillow-based Python comparison)
- Threshold: what counts as a meaningful visual difference vs sub-pixel rendering noise
- Storing screenshots: directory structure, naming convention

### 4.5 Colour Clustering Guide (`reference/colour-clustering.md`)

How to identify and consolidate near-duplicate colours:

- Convert hex to CIELAB colour space for perceptual distance calculation
- Use ΔE (Delta E) as the distance metric; ΔE < 2.3 is imperceptible, ΔE < 5 is minimal
- Clustering algorithm: simple greedy grouping by distance threshold
- Selecting the representative colour for each cluster: use the most frequent member, or the one closest to a Bootstrap default

---

## 5. Templates

### 5.1 Human Checkpoint Template (`templates/human-checkpoint.md`)

```markdown
# Checkpoint: {Stage Name}

## Summary
{2-3 sentence overview of what was done}

## Key Findings
{Bulleted list of the most important things discovered or produced}

## Statistics
{Relevant numbers: items processed, issues found, etc.}

## Decisions Needed
{Specific questions for the human to answer before proceeding}

## Files to Review
{List of key output files with paths}

## Next Stage Preview
{Brief description of what the next stage will do}
```

### 5.2 Migration PR Template

(Defined in Section 3.5.2 above)

---

## 6. Operational Constraints

### 6.1 Tool Usage

- Use `Write` / `Read` / `Edit` tools for file operations (no shell `mv`, `cp`, `rm` that prompt for confirmation)
- Use `bash` for: running the dev server, compiling SCSS, running linters, running screenshot scripts
- Use the browser for: navigating views, taking screenshots, extracting computed styles via JS
- Use `git` CLI for: creating branches, committing, diffing

### 6.2 File Organisation

- All playbook outputs go in `output/` within the playbook directory (not in the Gyrinx repo)
- All code changes go in the Gyrinx repo on feature branches
- The `output/` directory is a working directory for the playbook and can be deleted after the playbook completes
- The design system spec (`DESIGN-SYSTEM.md`) should also be copied into the Gyrinx repo (e.g., `docs/DESIGN-SYSTEM.md`) as a permanent artefact

### 6.3 Git Hygiene

- Create branches from `main`
- Use descriptive branch names: `design-system/{description}`
- Commit messages should be clear and reference the migration unit
- Don't squash — individual commits within a migration unit are fine for traceability
- Don't merge branches — leave them for human review

### 6.4 Error Handling

- If a view fails to load: note it in the audit, skip it, continue with other views
- If SCSS fails to compile after a change: revert the change, note the failure, continue
- If a screenshot comparison shows unexpected regression: flag it in the PR description, don't suppress it
- If a template linter rule produces false positives: note them, don't disable the rule

### 6.5 Context Management

- After Stage 0 setup, request context compaction before beginning Stage 1
- At the start of each stage, reload: `instructions.md`, the current stage README, the scope document, and any outputs from the previous stage that are needed as input
- Sub-agents for Stage 1 and Stage 5 should receive: the stage instructions, the specific view(s) they're processing, the relevant templates and SCSS files, and the design system spec (for Stage 5)

---

## 7. Success Criteria

The playbook is complete when:

1. Every view in the app has been audited and screenshotted
2. A comprehensive design system specification exists as a markdown document
3. Design tokens exist as SCSS variables in `_tokens.scss`
4. Django template components exist for all core components
5. A living style guide renders at `/design-system/`
6. Every template has been migrated to use the design system (or explicitly marked as an exception)
7. Before/after screenshots exist for every migrated view
8. SCSS and template linting rules are in place
9. A summary document captures the full state of the migration
10. The human has reviewed and approved the output at every checkpoint
