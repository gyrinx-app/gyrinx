# Stage 6: Finalisation

## Purpose

Wrap up, verify completeness, and produce the summary.

## Execution Model

Sequential, single agent.

## Steps

### 1. Run Template Linter Across Entire Codebase

- Report remaining violations
- Categorise: intentional exceptions vs missed migrations

### 2. Run SCSS Linter

- Report remaining violations

### 3. Full Screenshot Sweep

- Re-screenshot every view
- Compare against Stage 0 baseline screenshots
- Produce a visual diff summary

### 4. Verify Style Guide

- Load `/design-system/`
- Confirm all components render correctly
- Confirm navigable and usable as documentation

### 5. Verify Spec Document

- `DESIGN-SYSTEM.md` matches implemented reality
- Every component in spec exists as a template
- Every token in spec exists in `_tokens.scss`
- Every Django template component reference is correct

### 6. Produce `output/SUMMARY.md`

- What was done (overview of all stages)
- Key statistics: colours before/after, text styles before/after, component variants before/after
- Remaining work (any views not migrated, known exceptions)
- How to maintain the system going forward
- How to use the template linter in CI
- Links to key files: spec, style guide URL, token file, linter config

### 7. Produce `output/migration-tracker.md`

- Table of every view, migration status, and branch/PR
- Overall completion percentage

## Exit Criteria

- [ ] `output/SUMMARY.md` exists
- [ ] `output/migration-tracker.md` exists with completion status
- [ ] Final screenshot sweep complete
- [ ] Spec verified against implementation
- [ ] Human has clear picture of what's done and what remains

## Human Checkpoint

Present the final summary. Ask:
> "Is there anything missing or anything you'd like me to revisit?"
