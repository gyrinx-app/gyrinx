# Recommendation: [Title]

## Quick Reference

| Attribute | Value |
|-----------|-------|
| **Priority** | [1-5] |
| **Impact** | [X]ms savings |
| **Confidence** | [High/Medium/Low] |
| **Effort** | [X person-days] |
| **Risk** | [Low/Medium/High] |

## Problem

[2-3 sentence description of what's wrong]

**Evidence:**

- [Specific measurement from trace]
- [Specific measurement from trace]

## Solution

[2-3 sentence description of the fix]

## Implementation

### Step 1: [Action]

```python
# File: [path/to/file.py]
# Location: [class/method]

[Code change or description]
```

### Step 2: [Action]

```python
# File: [path/to/file.py]
# Location: [class/method]

[Code change or description]
```

## Verification

### Before Change

- Capture trace of same request
- Note: [metric to measure]

### After Change

1. [ ] Run tests: `pytest [relevant tests]`
2. [ ] Capture new trace
3. [ ] Compare: [metric] should be [expected change]
4. [ ] Check for regressions in [related area]

### Expected Outcome

- [Metric]: [Current] → [Expected]
- Total request time: -[X]ms

## Dependencies

**Requires:**

- [Other changes that must happen first]

**Enables:**

- [Other optimizations this unlocks]

## Risks

| Risk | Likelihood | Impact | Mitigation |
|------|------------|--------|------------|
| [Risk 1] | [L/M/H] | [L/M/H] | [How to mitigate] |

## Related

- **Analysis:** `output/{trace-id}/groups/[prefix]/bottlenecks.md`
- **Cluster:** `output/{trace-id}/aggregation/issue-clusters.md#[section]`
- **Other Recommendations:** [Related recommendation cards]
