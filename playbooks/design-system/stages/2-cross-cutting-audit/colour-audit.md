# Colour Audit

## Output

`output/audit/colours.md`

## Process

### 1. Extract Every Colour Value

- From all per-view audits: every computed colour value (hex normalised to lowercase 6-digit)
- From SCSS source: every colour literal, every Bootstrap variable override, every custom variable
- From templates: any inline colour values

### 2. Deduplicate and Count

Produce a table of every unique colour, its frequency, and where it appears.

### 3. Cluster by Perceptual Similarity

Group colours within small perceptual distance (Delta-E < 5 in CIELAB):

- **Intentional variants:** hover state is darker version of primary
- **Drift:** `#6c757d` and `#6b7280` are clearly meant to be the same grey

Flag clusters with >2 members as consolidation candidates.

### 4. Map to Bootstrap's Palette

For each colour, identify whether it matches a Bootstrap default, a Bootstrap variable override, or is entirely custom.

Table: `| Colour | Bootstrap equivalent | Is override | Is custom |`

### 5. Identify Semantic Usage

Map colours to semantic purpose: primary action, secondary action, text, muted text, background, border, error, success, warning, info.

Flag colours used for multiple conflicting semantic purposes.

### 6. Produce Consolidation Recommendation

Proposed consolidated palette:

| Semantic name | Recommended hex | Bootstrap variable mapping | Replaces N values |
|---------------|----------------|---------------------------|-------------------|
