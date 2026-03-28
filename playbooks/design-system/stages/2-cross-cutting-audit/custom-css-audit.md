# Custom CSS Audit

## Output

`output/audit/custom-css.md`

## Process

### 1. Inventory All Custom SCSS

- Every rule that isn't a Bootstrap override
- Every custom class (like `caps-label`, `fs-7`)
- Every element selector or ID selector

### 2. Classify Each Custom Rule

| Classification | Definition |
|---------------|------------|
| **Token candidate** | Should become a design token (custom colour, size) |
| **Component candidate** | Should become a named component style |
| **Bootstrap extension** | Extends Bootstrap in a standard way (e.g., `fs-7`) |
| **Override/fix** | Works around a Bootstrap limitation |
| **Dead code** | Not referenced in any template |

### 3. Produce Recommendation

Which custom rules to keep, formalise, replace, or remove.
