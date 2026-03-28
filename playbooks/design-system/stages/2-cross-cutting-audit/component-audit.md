# Component Audit

This is the most critical dimension.

## Output

`output/audit/components.md`

## Process

### 1. Aggregate All Component Instances

For each component type (button, card, table, nav, form element, badge, icon, dropdown, tooltip, custom):

- Total instances
- Distinct variants (unique class combinations)
- Frequency of each variant
- Which views each variant appears on

### 2. Classify Each Variant

Use the component taxonomy from `reference/component-taxonomy.md`:

| Classification | Definition | Action |
|---------------|------------|--------|
| **Canonical** | Dominant, most consistent variant | Encode as-is |
| **Acceptable Variant** | Intentionally different for good reason | Encode as named variant |
| **Drift** | Unintentional deviation | Migrate to canonical |
| **Bespoke** | One-off, doesn't fit any standard | Design decision needed |
| **Anti-pattern** | Causes UX or accessibility problems | Fix during migration |
| **Dead** | Defined in CSS but not used | Remove during migration |

### 3. Produce Component Profiles

For each component type:

```markdown
### {Component Type}

**Total instances:** {N}
**Distinct variants:** {N}

#### Variant Table
| Classes | Frequency | Views | Classification | Notes |
|---------|-----------|-------|---------------|-------|

#### Canonical Definition
- Classes: `{classes}`
- Appears: {N} times across {N} views

#### Recommended Variants
| Variant name | Use case | Classes | Difference from canonical |
|-------------|----------|---------|--------------------------|

#### Migration Targets
| Current classes | Target classes | Affected views | Effort |
|----------------|---------------|----------------|--------|
```

### 4. Identify Missing Components

- UI patterns implemented with raw HTML/CSS that should be components (e.g., `border rounded p-2` callout)
- Django `{% include %}` patterns that are de facto components but not formalised

### 5. Identify Shared Template Includes

- List every `{% include %}` template
- Map which views use each include
- Note which are component-like (reusable UI) vs structural (page sections)
