# Stage 2: Cross-Cutting Audit

## Purpose

Aggregate all per-view data into dimension-specific reports that reveal the true state of the design system across the whole app.

## Execution Model

Single agent, processing one dimension at a time sequentially (each dimension needs the full dataset).

## Input

- All `output/audit/views/*.md` files
- The SCSS source files
- The running app

## Dimensions

Process each dimension in order. Each has its own instruction file in this directory:

| Dimension | Instruction File | Output File |
|-----------|-----------------|-------------|
| Colour | `colour-audit.md` | `output/audit/colours.md` |
| Typography | `typography-audit.md` | `output/audit/typography.md` |
| Spacing | `spacing-audit.md` | `output/audit/spacing.md` |
| Components | `component-audit.md` | `output/audit/components.md` |
| Icons | `icon-audit.md` | `output/audit/icons.md` |
| Layout | `layout-audit.md` | `output/audit/layouts.md` |
| Custom CSS | `custom-css-audit.md` | `output/audit/custom-css.md` |

### Final Step: Audit Summary

After all dimensions, produce `output/audit/SUMMARY.md` synthesising:

- **Palette health:** Colours in use vs recommended consolidated count
- **Typography health:** Text styles vs recommended scale size
- **Spacing health:** How consistently the spacing scale is followed
- **Component health:** Ratio of canonical vs drift vs bespoke instances
- **Biggest wins:** Top 5 changes that would most improve consistency (by frequency x severity)
- **Biggest risks:** Areas where migration is most complex or risky
- **Estimated scope:** Rough count of template changes needed

## Exit Criteria

- [ ] All seven dimension reports exist and contain data
- [ ] `output/audit/SUMMARY.md` exists and synthesises findings
- [ ] Each dimension report includes a consolidation recommendation

## Human Checkpoint

Present SUMMARY.md. Ask:
> "Do you agree with these consolidation choices, or do you want to adjust any of them?"

Focus review on: proposed colour palette, proposed type scale, and component classifications.
