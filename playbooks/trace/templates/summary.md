# Trace Performance Analysis Summary

**Trace ID:** [trace-id]
**Endpoint:** [endpoint path]
**Analysis Date:** [YYYY-MM-DD]
**Total Request Time:** [X]ms

---

## Overview

[One paragraph summary of the analysis findings. What was analyzed, what were the main issues discovered, and what is the overall assessment of performance.]

---

## Key Metrics

| Metric | Value | Assessment |
|--------|-------|------------|
| Total Request Time | [X]ms | [Good/Needs Work/Critical] |
| Total Spans | [N] | - |
| Traced Time | [X]ms ([X]%) | - |
| Untraced Time | [X]ms ([X]%) | [OK/Investigate] |
| N+1 Patterns | [N] | [None/Some/Many] |
| Query Count | [N] | - |

---

## Top Bottlenecks

| Rank | Operation | Time | % | Issue Type |
|------|-----------|------|---|------------|
| 1 | [name] | [X]ms | [X]% | [tag] |
| 2 | [name] | [X]ms | [X]% | [tag] |
| 3 | [name] | [X]ms | [X]% | [tag] |
| 4 | [name] | [X]ms | [X]% | [tag] |
| 5 | [name] | [X]ms | [X]% | [tag] |

---

## Top Recommendations

### 1. [Title] - [X]ms savings

**Priority:** [1-5] | **Effort:** [X days] | **Confidence:** [H/M/L]

[One sentence description]

→ Details: `output/{trace-id}/recommendations/[name].md`

### 2. [Title] - [X]ms savings

**Priority:** [1-5] | **Effort:** [X days] | **Confidence:** [H/M/L]

[One sentence description]

→ Details: `output/{trace-id}/recommendations/[name].md`

### 3. [Title] - [X]ms savings

**Priority:** [1-5] | **Effort:** [X days] | **Confidence:** [H/M/L]

[One sentence description]

→ Details: `output/{trace-id}/recommendations/[name].md`

---

## Quick Wins

Immediate actions that can be implemented today:

1. **[Action]** - [X]ms savings
   - [Specific change]

2. **[Action]** - [X]ms savings
   - [Specific change]

---

## Performance Baseline

Current performance characteristics for future comparison:

| Characteristic | Value |
|----------------|-------|
| Request Time | [X]ms |
| DB Query Count | [N] |
| Slowest Operation | [name] ([X]ms) |
| N+1 Operations | [list] |
| Cache Hit Rate | [X]% (if applicable) |

---

## Navigation Guide

### For Developers

- Start with: `output/{trace-id}/synthesis/code-locations.md`
- Then: `output/{trace-id}/recommendations/*.md`
- Reference: `output/{trace-id}/groups/*/bottlenecks.md`

### For Tech Leads

- Start with: `output/{trace-id}/synthesis/priority-matrix.md`
- Then: `output/{trace-id}/synthesis/roadmap.md`
- Reference: `output/{trace-id}/aggregation/issue-clusters.md`

### For Deep Dive

- Operation details: `output/{trace-id}/groups/{prefix}/profile.md`
- Pattern analysis: `output/{trace-id}/aggregation/n-plus-one-summary.md`
- Impact estimates: `output/{trace-id}/synthesis/impact-estimates.md`

---

## Files in This Analysis

```
output/{trace-id}/
├── SUMMARY.md                 ← You are here
├── scope.md                   # Analysis parameters
├── baseline.md                # Performance baseline
├── groups/                    # Per-operation analysis
├── aggregation/               # Pattern aggregation
├── synthesis/                 # Impact synthesis
├── opportunities/             # Opportunity details
└── recommendations/           # Action cards
```

---

## Next Steps

1. [ ] Review recommendations with team
2. [ ] Implement quick wins
3. [ ] Schedule medium-term fixes
4. [ ] Plan architectural changes
5. [ ] Capture new trace after changes
6. [ ] Compare with baseline
