---
description: |
  Load the Gyrinx design system reference (patterns, colours, typography, components, spacing,
  buttons, tables, forms, page shells, inline action menus, etc.). Trigger when working on
  UI, templates, frontend, styling, design patterns, component patterns, or when the user
  mentions "design system", "design library", "UI pattern", "component pattern", or asks
  how something should look.
---

# Design System

First identify the edition. N26 uses Tailwind and django-cotton-ui, not Bootstrap.

## N26

Read `n26/designsystem/CLAUDE.md`, `n26/designsystem/assets/app.css`, and the
relevant primitives under `n26/core/templates/cotton/`. The living gallery is
`/n26/design/`; the catalog is `n26/designsystem/catalog.py`. For interactive
work also load `.agents/skills/n26-react/SKILL.md`. React adapters in
`n26/frontend/ui.tsx` take their classes from rendered Cotton at build time;
extend those adapters instead of copying class recipes into features.

## N23

Load both the design system spec and the living HTML reference into context.

## Reference files

Read these files to get the full design system:

!`cat docs/DESIGN-SYSTEM.md`

!`cat n23/core/templates/core/debug/design_system.html`

## How to use

- When creating or modifying templates, follow the patterns documented in these files
- Use the HTML file as a source of copy-pasteable patterns
- The markdown file has the rules and rationale; the HTML file has live examples
- If you add a new pattern, add it to both files
