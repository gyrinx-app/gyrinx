# Stage 5: Template Migration

## Purpose

Migrate every template in the app to use the design system consistently.

## Execution Model

Parallel per migration unit. PR granularity determined by the agent based on audit findings.

## Input

- Design system spec (`output/spec/DESIGN-SYSTEM.md`)
- Component templates
- All per-view audits
- Linting output

## Migration Planning

### Determining Migration Units

See `migration-plan.md` for full guidelines. Key rules:

- **Shared includes first:** A template include used on 10 views is one PR that fixes 10 views
- **Foundation changes as single PR:** `_tokens.scss` and Bootstrap variable overrides
- **Component-level PRs** when spanning many views with mechanical changes
- **View-level PRs** for view-specific structural changes
- **Never mix** structural refactors with cosmetic changes

Produce: `output/migration/plan.md` with every migration unit in order.

### Migration Order

1. SCSS foundation (tokens, variable overrides)
2. Shared component templates (create `components/` includes)
3. Shared layout templates (base templates, page shells)
4. Shared include templates (fighter cards, weapon tables, etc.)
5. Individual page templates (by importance, otherwise alphabetical)
6. Print styles

## Per-Migration-Unit Process

See `visual-regression.md` for screenshot comparison details.

For each unit:

1. **Create git branch:** `design-system/{unit-name}`
2. **Take "before" screenshots** of every affected view (1280px desktop)
3. **Make changes:**
   - Replace raw HTML with `{% include "components/..." %}` where applicable
   - Swap hardcoded classes for standardised ones per spec
   - Replace hardcoded colour/spacing values with token-based alternatives
   - Fix inconsistencies flagged in per-view audit
4. **Compile SCSS** (if SCSS changes included)
5. **Take "after" screenshots**
6. **Compare before/after:** flag unexpected visual differences
7. **Run template linter** on changed files — confirm violations reduced
8. **Commit with descriptive message**
9. **Write PR description** using `templates/migration-pr.md`
10. **Save** to `output/migration/{unit-name}/pr-description.md`

## Exit Criteria

- [ ] `output/migration/plan.md` exists with all migration units
- [ ] Every unit has a branch, commits, before/after screenshots, and PR description
- [ ] Template linter shows reduced violations
- [ ] All views render without errors (no 500s, no missing templates)

## Human Checkpoint

Present the migration plan. For completed migrations, present before/after screenshots for the 5 highest-risk changes. Ask:
> "Are you happy with how these look? Should I proceed with the remaining migrations?"
