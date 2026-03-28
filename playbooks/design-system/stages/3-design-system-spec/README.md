# Stage 3: Design System Specification

## Purpose

Author the definitive design system specification that will govern all future UI work.

## Execution Model

Single agent.

## Input

All Stage 2 outputs (with human-approved consolidation recommendations), the codebase, the running app.

## Primary Output

`output/spec/DESIGN-SYSTEM.md` — the single most important deliverable. Must be self-contained, unambiguous, and usable by humans and AI agents alike.

## Document Structure

```
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

## Section Requirements

### Principles (Section 1)

5-8 concrete, actionable design principles derived from audit findings. Each must include:

- Clear statement
- Rationale tied to the app's domain
- Concrete example of how to apply it

Must be specific to Gyrinx, not generic.

### Foundations (Section 2)

For each foundation, provide:

- Complete token list with exact values
- SCSS variable name (`$gy-` prefix for custom tokens)
- Bootstrap class mapping where one exists
- Usage guidance
- Do's and don'ts

**Colour tokens** must include: `$gy-color-text-primary`, `$gy-color-text-secondary`, `$gy-color-text-muted`, `$gy-color-bg-primary`, `$gy-color-bg-secondary`, `$gy-color-bg-surface`, `$gy-color-border`, `$gy-color-interactive`, `$gy-color-interactive-hover`, `$gy-color-success`, `$gy-color-warning`, `$gy-color-danger`, `$gy-color-info`. Plus hex values, Bootstrap mapping, and contrast ratios.

**Typography** must include the complete type scale as a table with: scale name, SCSS variable, font-size, font-weight, line-height, letter-spacing, text-transform, Bootstrap class equivalent, semantic roles.

**Spacing** must include the spacing scale (likely Bootstrap's default, possibly extended) with semantic spacing variables if needed.

**Icons** must include canonical icon for each concept, size conventions, colour conventions, and accessibility requirements.

### Components (Section 4)

For EACH component, follow the template in `templates/component-spec.md`. Must cover at minimum:

- Button (all variants), Card, Data table, Nav tabs, Dropdown/action menu, Badge/tag
- Callout (`border rounded p-2` pattern), Section header (`caps-label`), Icon link
- Form field, Tooltip, Empty state, Loading state

### Patterns (Section 5)

Higher-level compositions. Each includes: when to use, DOM structure, which components it's composed of, a real example from Gyrinx.

### Django Template Components Reference (Section 6)

| Component | Template path | Required params | Optional params | Example |
|-----------|--------------|-----------------|-----------------|---------|

### SCSS Token Reference (Section 7)

Complete listing of every SCSS variable, grouped by category, with value and description.

## Secondary Output

`output/spec/tokens.json` — machine-readable JSON of all design tokens:

```json
{
  "color": { "text-primary": { "value": "#212529", "scss": "$gy-color-text-primary", "bootstrap": "$body-color" } },
  "typography": { "body": { "size": "0.875rem", "weight": "400", "line-height": "1.5", "scss": "$gy-type-body-size" } },
  "spacing": { "1": { "value": "0.25rem", "scss": "$spacer * .25", "bootstrap": "$spacer-1" } }
}
```

## Exit Criteria

- [ ] `output/spec/DESIGN-SYSTEM.md` exists with all required sections
- [ ] Every section has substantive content (not placeholders)
- [ ] Every component has a full specification
- [ ] `output/spec/tokens.json` exists and is valid JSON
- [ ] Internally consistent (no token referenced that doesn't exist)
- [ ] Self-contained (an agent with no other context could implement from it alone)

## Human Checkpoint

Present the full spec. Ask:
> "Does this system accurately represent what you want Gyrinx to look like? Are there any components where you'd make different choices?"

Focus review on: principles, colour palette, type scale, and the 3 most common component specs.
