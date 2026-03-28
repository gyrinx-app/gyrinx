# Stage 4: Design System Implementation

## Purpose

Create the actual code artefacts that make the design system real.

## Execution Model

Sequential — each artefact depends on the previous.

## Input

`output/spec/DESIGN-SYSTEM.md`, `output/spec/tokens.json`, the codebase.

## Sub-stages

Detailed instructions in each file:

| Sub-stage | File | Output |
|-----------|------|--------|
| SCSS Tokens | `scss-tokens.md` | `static/scss/_tokens.scss` |
| Template Components | `template-components.md` | `templates/components/*.html` |
| Style Guide App | `style-guide-app.md` | `gyrinx/designsystem/` Django app |
| Linting | `linting.md` | `.stylelintrc.json`, template linter script |

## Exit Criteria

- [ ] `_tokens.scss` exists, compiles, and the app renders correctly
- [ ] All component templates exist in `templates/components/`
- [ ] The `designsystem` Django app exists and is registered
- [ ] Style guide renders at `/design-system/` showing all components
- [ ] Linting configuration exists and runs without errors on current codebase

## Human Checkpoint

Present the living style guide URL. Ask:
> "Does the style guide look right? Are you happy with the component implementations before I start migrating templates?"

Also present linting output showing current violation counts.
