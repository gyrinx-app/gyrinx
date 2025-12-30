# Stage 2: Pattern Aggregation

**Mode:** Sequential (single agent)
**Duration:** 15-30 minutes

## Purpose

Aggregate findings from Stage 1 to identify cross-cutting patterns, cluster similar issues, and calculate total impact.

## Prerequisites

- Stage 1 completed
- All `output/{trace-id}/groups/*/profile.md` files exist
- All `output/{trace-id}/groups/*/bottlenecks.md` files exist

## Aggregation Tasks

### 1. Issue Clustering

Group all identified issues by type and calculate aggregate impact.

**Output:** `output/{trace-id}/aggregation/issue-clusters.md`

**Template:** `playbooks/trace/templates/issue-cluster.md`

Clustering dimensions:

- **By Issue Type:** N+1, missing prefetch, expensive computation
- **By Impact:** High (>100ms), Medium (10-100ms), Low (<10ms)
- **By Fix Difficulty:** Easy, Medium, Hard
- **By Code Location:** Model, View, Template, Query

### 2. Time Attribution

Account for all time in the trace:

**Output:** `output/{trace-id}/aggregation/time-attribution.md`

Format:

```
| Category | Time (ms) | % of Total | Operations |
|----------|-----------|------------|------------|
| View logic | X | Y% | Operation list |
| DB queries | X | Y% | Operation list |
| Untraced | X | Y% | Gaps identified |
```

### 3. N+1 Pattern Summary

Consolidate all N+1 patterns found:

**Output:** `output/{trace-id}/aggregation/n-plus-one-summary.md`

For each pattern:

- Operation name
- Call count
- Total time consumed
- Potential savings if batched
- Fix complexity

### 4. Prefetch Gap Analysis

Identify missing prefetches across all operations:

**Output:** `output/{trace-id}/aggregation/prefetch-gaps.md`

For each gap:

- Where accessed (operation)
- What's missing (relationship)
- Current query count
- Estimated savings

### 5. Critical Path Analysis

Identify the longest sequential chain of operations:

**Output:** `output/{trace-id}/aggregation/critical-path.md`

Contents:

- Critical path operations (in order)
- Time per operation
- Dependencies
- Parallelization opportunities

## Cross-Reference Enrichment

After aggregation, enrich Stage 1 outputs:

- Add cluster membership to each issue
- Add priority ranking based on aggregate impact
- Cross-reference related issues in other groups

## Exit Criteria

- [ ] `output/{trace-id}/aggregation/issue-clusters.md` exists
- [ ] `output/{trace-id}/aggregation/time-attribution.md` exists
- [ ] `output/{trace-id}/aggregation/n-plus-one-summary.md` exists
- [ ] `output/{trace-id}/aggregation/prefetch-gaps.md` exists
- [ ] `output/{trace-id}/aggregation/critical-path.md` exists
- [ ] 100% of trace time attributed
- [ ] All issues from Stage 1 clustered

## Next Stage

Proceed to Stage 3 (Impact Synthesis) once all aggregation complete.
