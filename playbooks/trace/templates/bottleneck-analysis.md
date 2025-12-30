# Bottleneck Analysis: [Operation Group]

## Summary

**Total Time in Group:** [X]ms
**% of Request:** [X]%
**Primary Bottleneck:** [operation name]

## Time Breakdown

### By Operation

| Rank | Operation | Time (ms) | % of Group | Issue Type |
|------|-----------|-----------|------------|------------|
| 1 | [name] | [X] | [X]% | [tag] |
| 2 | [name] | [X] | [X]% | [tag] |
| 3 | [name] | [X] | [X]% | [tag] |

### By Issue Type

| Issue Type | Time (ms) | Operations Affected |
|------------|-----------|---------------------|
| N+1_QUERY | [X] | [list] |
| MISSING_PREFETCH | [X] | [list] |
| EXPENSIVE_COMPUTATION | [X] | [list] |

## N+1 Pattern Detection

### Pattern 1: [Description]

**Operation:** `[span_name]`
**Call Count:** [N]
**Time Per Call:** [X]ms
**Total Time:** [X]ms
**Potential Savings:** [X]ms (if batched to 1 query)

**Evidence:**

```
[Span name appears N times in trace]
Call 1: Xms
Call 2: Xms
...
Call N: Xms
```

**Root Cause:**
[Why this happens - e.g., "Called once per fighter in template loop"]

**Fix:**
[Specific fix - e.g., "Add prefetch for X at view level"]

## Missing Prefetch Opportunities

### Gap 1: [Relationship Name]

**Accessed In:** `[operation_name]`
**Relationship:** `[model.related_field]`
**Current Queries:** [N]
**Expected With Prefetch:** 1
**Estimated Savings:** [X]ms

**Where to Add:**

```python
# In [file:method]
.prefetch_related('[relationship_path]')
```

## Slowest Individual Operations

### 1. [Operation Name] - [X]ms

**Span ID:** [id]
**Parent:** [parent operation]
**Child Operations:** [count]

**Analysis:**

- Time in operation itself: [X]ms
- Time in children: [X]ms
- Unaccounted: [X]ms

**Why Slow:**
[Analysis of why this specific instance was slow]

## Optimization Opportunities

| Priority | Operation | Current | Target | Savings | Effort |
|----------|-----------|---------|--------|---------|--------|
| 1 | [name] | [X]ms | [X]ms | [X]ms | [effort] |
| 2 | [name] | [X]ms | [X]ms | [X]ms | [effort] |

## Untraced Time

**Total Untraced:** [X]ms ([X]% of group)

**Likely Causes:**

- [Cause 1 - e.g., "Template rendering"]
- [Cause 2 - e.g., "Uninstrumented DB queries"]

**Recommendation:**
[Whether to add more tracing or investigate further]
