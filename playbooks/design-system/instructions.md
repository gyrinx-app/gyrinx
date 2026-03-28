# Gyrinx Design System Playbook

## Purpose

Audit the Gyrinx UI, design a consolidated design system on top of Bootstrap 5, build it as code, and migrate every template to use it.

## Stage Pipeline

```
Stage 0: Setup (Interactive)         → output/scope.md, screenshots
    ↓ [human checkpoint]
Stage 1: Per-View Audit (Parallel)   → output/audit/views/{view}.md
    ↓ [human checkpoint]
Stage 2: Cross-Cutting Audit         → output/audit/{dimension}.md
    ↓ [human checkpoint]
Stage 3: Design System Spec          → output/spec/DESIGN-SYSTEM.md
    ↓ [human checkpoint]
Stage 4: Implementation              → Code: _tokens.scss, components/, designsystem app
    ↓ [human checkpoint]
Stage 5: Template Migration          → Git branches per migration unit
    ↓ [human checkpoint]
Stage 6: Finalisation                → output/SUMMARY.md
```

## Execution Rules

### Human Checkpoints

Every `[human checkpoint]` is mandatory. The agent must:

1. Produce a checkpoint summary using `templates/human-checkpoint.md`
2. Present it to the user
3. Wait for explicit approval before proceeding

### Parallelisation

- **Stage 1:** 5-8 concurrent sub-agents, one per view (or small group of related views sharing templates)
- **Stage 5:** Parallel per migration unit after the migration plan is approved
- All other stages: single agent, sequential

### Context Management

- After Stage 0, request context compaction before beginning Stage 1
- At each stage start, reload: this file, the stage README, `output/scope.md`, and previous stage outputs needed as input
- Sub-agents receive: stage instructions, their specific view(s)/unit, relevant templates/SCSS, and the design system spec (Stage 5)

### Tool Usage

- File operations: `Write` / `Read` / `Edit` (not shell `mv`/`cp`/`rm`)
- Shell: running dev server, compiling SCSS, running linters, running screenshot scripts
- Browser: navigating views, taking screenshots, extracting computed styles via JS
- Git: creating branches, committing, diffing (CLI)

### File Organisation

- All playbook working outputs: `output/` within this playbook directory
- All code changes: Gyrinx repo on `design-system/{description}` branches
- Final spec: also copied to `docs/DESIGN-SYSTEM.md` in the repo

### Git Hygiene

- Branch from `main`
- Descriptive branch names: `design-system/{description}`
- Don't squash commits
- Don't merge branches — leave for human review

### Error Handling

- View fails to load: note it, skip, continue
- SCSS fails to compile: revert change, note failure, continue
- Unexpected visual regression: flag in PR description, don't suppress
- Linter false positives: note them, don't disable the rule

## Stage Details

Each stage has a README in `stages/{N}-{name}/README.md` with full instructions.

| Stage | Directory | Execution | Agent Count |
|-------|-----------|-----------|-------------|
| 0 | `stages/0-setup/` | Interactive | 1 |
| 1 | `stages/1-per-view-audit/` | Parallel | 5-8 |
| 2 | `stages/2-cross-cutting-audit/` | Sequential | 1 |
| 3 | `stages/3-design-system-spec/` | Sequential | 1 |
| 4 | `stages/4-implementation/` | Sequential | 1 |
| 5 | `stages/5-migration/` | Parallel | Per unit |
| 6 | `stages/6-finalisation/` | Sequential | 1 |

## Success Criteria

The playbook is complete when:

1. Every view has been audited and screenshotted
2. A comprehensive design system spec exists (`DESIGN-SYSTEM.md`)
3. Design tokens exist as SCSS variables in `_tokens.scss`
4. Django template components exist for all core components
5. A living style guide renders at `/design-system/`
6. Every template has been migrated (or explicitly marked as exception)
7. Before/after screenshots exist for every migrated view
8. SCSS and template linting rules are in place
9. A summary document captures the full migration state
10. The human has reviewed and approved at every checkpoint
