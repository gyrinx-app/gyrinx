# Comparison Analysis: [Before] vs [After]

## Overview

| Attribute | Before | After | Delta |
|-----------|--------|-------|-------|
| **Trace ID** | [id] | [id] | - |
| **Date** | [date] | [date] | - |
| **Total Time** | [X]ms | [X]ms | [±X]ms ([±X]%) |
| **Span Count** | [N] | [N] | [±N] |
| **Query Count** | [N] | [N] | [±N] |

## Summary

[One paragraph summary: What changed between traces, what was the net impact, were optimizations successful?]

---

## Changes Between Traces

### Code/Config Changes

| Change | Files | Expected Impact |
|--------|-------|-----------------|
| [Description] | [files] | [expected effect] |

### Environment Changes

- [Any infrastructure/config differences]

---

## Performance Delta by Operation

### Operations That Improved

| Operation | Before (ms) | After (ms) | Delta | Change (%) |
|-----------|-------------|------------|-------|------------|
| [name] | [X] | [X] | -[X] | -[X]% |

### Operations That Regressed

| Operation | Before (ms) | After (ms) | Delta | Change (%) |
|-----------|-------------|------------|-------|------------|
| [name] | [X] | [X] | +[X] | +[X]% |

### Operations Unchanged

| Operation | Before (ms) | After (ms) | Notes |
|-----------|-------------|------------|-------|
| [name] | [X] | [X] | [note] |

### New Operations

| Operation | Time (ms) | Notes |
|-----------|-----------|-------|
| [name] | [X] | [why added] |

### Removed Operations

| Operation | Was (ms) | Notes |
|-----------|----------|-------|
| [name] | [X] | [why removed] |

---

## Attribution Analysis

### Change: [Description]

**Expected Effect:** [What we thought would happen]
**Actual Effect:** [What actually happened]
**Attribution Confidence:** [Strong/Moderate/Weak/None]

**Evidence:**

- [Specific data point linking change to outcome]
- [Specific data point]

**Operations Affected:**

- [operation_1]: [before] → [after]
- [operation_2]: [before] → [after]

---

## N+1 Pattern Comparison

| Pattern | Before | After | Status |
|---------|--------|-------|--------|
| [pattern_1] | [N] calls, [X]ms | [N] calls, [X]ms | [Fixed/Improved/Same/Regressed] |

---

## Query Efficiency

| Metric | Before | After | Assessment |
|--------|--------|-------|------------|
| Total Queries | [N] | [N] | [Better/Same/Worse] |
| Prefetch Usage | [N] | [N] | - |
| Avg Query Time | [X]ms | [X]ms | - |

---

## Time Attribution Comparison

### Before

| Category | Time (ms) | % |
|----------|-----------|---|
| [category] | [X] | [X]% |

### After

| Category | Time (ms) | % |
|----------|-----------|---|
| [category] | [X] | [X]% |

---

## Assessment

### What Worked

- [Optimization that achieved expected results]

### What Didn't Work

- [Optimization that didn't have expected impact]

### Unexpected Effects

- [Side effects, regressions, or surprises]

### Remaining Opportunities

- [Issues not addressed by changes]

---

## Recommendations

Based on this comparison:

1. **[Recommendation]** - [Rationale]
2. **[Recommendation]** - [Rationale]

---

## Next Steps

- [ ] [Action item based on comparison]
- [ ] [Action item]
