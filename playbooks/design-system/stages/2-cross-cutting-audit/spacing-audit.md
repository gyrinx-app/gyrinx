# Spacing Audit

## Output

`output/audit/spacing.md`

## Process

### 1. Extract Every Spacing Value

All padding, margin, and gap values from per-view audits. Count frequency.

### 2. Identify the Implicit Scale

- Sort values and identify clusters
- Compare against Bootstrap's default spacing scale (0, 0.25rem, 0.5rem, 1rem, 1.5rem, 3rem)
- Check if Bootstrap utilities (`p-1`, `m-2`, `gap-3`) are used consistently or if there are manual values

### 3. Produce Consolidation Recommendation

- Confirm or modify Bootstrap's spacing scale for Gyrinx
- Flag non-standard spacing values to map to nearest scale step
