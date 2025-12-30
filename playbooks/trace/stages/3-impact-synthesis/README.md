# Stage 3: Impact Synthesis

**Mode:** Sequential (single agent)
**Duration:** 20-30 minutes

## Purpose

Synthesize aggregated patterns into actionable optimization opportunities with estimated impact and implementation guidance.

## Prerequisites

- Stage 2 completed
- All aggregation files exist
- Issue clusters defined

## Synthesis Tasks

### 1. Opportunity Analysis

For each major issue cluster, create an opportunity document:

**Output Directory:** `output/{trace-id}/opportunities/`

**Template:** `playbooks/trace/templates/opportunity.md`

Contents per opportunity:

- Problem statement
- Root cause analysis
- Proposed solution
- Implementation approach
- Estimated impact (time savings)
- Confidence level
- Dependencies
- Risk assessment

### 2. Impact Estimation Framework

Apply consistent impact estimation:

| Confidence | Variance | Criteria |
|------------|----------|----------|
| High | ±10% | Direct measurement, clear fix |
| Medium | ±25% | Logical connection, some uncertainty |
| Low | ±50% | Speculative, needs validation |

**Output:** `output/{trace-id}/synthesis/impact-estimates.md`

### 3. Priority Matrix

Rank opportunities by:

```
Priority Score = (Time Savings × Confidence) / (Effort × Risk)
```

**Output:** `output/{trace-id}/synthesis/priority-matrix.md`

Format:

| Rank | Opportunity | Savings | Effort | Priority Score |
|------|-------------|---------|--------|----------------|
| 1 | ... | Xms | Y days | Z |

### 4. Implementation Roadmap

Group opportunities into implementation phases:

**Output:** `output/{trace-id}/synthesis/roadmap.md`

Phases:

1. **Quick Wins** (< 1 day effort, high impact)
2. **Medium Term** (1-3 days, significant impact)
3. **Long Term** (> 3 days, architectural changes)

### 5. Code Location Mapping

Map each opportunity to specific code locations:

**Output:** `output/{trace-id}/synthesis/code-locations.md`

Format:

| Opportunity | File | Line/Method | Change Type |
|-------------|------|-------------|-------------|
| Batch X | path/to/file.py | method_name | Add prefetch |

## Comparison Analysis (If Applicable)

If analyzing before/after traces:

### 6. Delta Analysis

**Output:** `output/{trace-id}/synthesis/delta-analysis.md`

Contents:

- Operations that improved
- Operations that regressed
- New operations
- Removed operations
- Net impact

### 7. Attribution Analysis

Map improvements to specific changes:

**Output:** `output/{trace-id}/synthesis/attribution.md`

Contents:

- Change description
- Affected operations
- Measured improvement
- Attribution confidence

## Exit Criteria

- [ ] Opportunity documents created for top issues
- [ ] `output/{trace-id}/synthesis/impact-estimates.md` exists
- [ ] `output/{trace-id}/synthesis/priority-matrix.md` exists
- [ ] `output/{trace-id}/synthesis/roadmap.md` exists
- [ ] `output/{trace-id}/synthesis/code-locations.md` exists
- [ ] All opportunities have confidence levels
- [ ] Dependencies mapped between opportunities

## Next Stage

Proceed to Stage 4 (Recommendations) once synthesis complete.
