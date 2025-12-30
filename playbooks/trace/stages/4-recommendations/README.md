# Stage 4: Recommendations

**Mode:** Sequential (single agent)
**Duration:** 15-20 minutes

## Purpose

Finalize analysis with executive summary, actionable recommendations, and institutional memory capture.

## Prerequisites

- Stage 3 completed
- All synthesis files exist
- Priority matrix defined

## Finalization Tasks

### 1. Executive Summary

Create the primary output document:

**Output:** `output/{trace-id}/SUMMARY.md`

**Template:** `playbooks/trace/templates/summary.md`

Sections:

1. **Overview** - One paragraph summary of findings
2. **Key Metrics** - Total time, span count, top bottlenecks
3. **Top Recommendations** - Prioritized list (max 5)
4. **Quick Wins** - Immediate actions
5. **Performance Baseline** - Current performance characteristics
6. **Navigation Guide** - Where to find detailed analysis

### 2. Recommendation Cards

Create standalone recommendation cards for each opportunity:

**Output Directory:** `output/{trace-id}/recommendations/`

**Template:** `playbooks/trace/templates/recommendation-card.md`

One file per recommendation with:

- Title
- Impact (time savings)
- Effort (person-days)
- Priority (1-5)
- Problem summary
- Solution summary
- Implementation steps
- Code changes required
- Verification steps

### 3. Performance Baseline Document

Document current performance for future comparison:

**Output:** `output/{trace-id}/baseline.md`

Contents:

- Trace metadata (date, ID, endpoint)
- Total request time
- Top 10 slowest operations
- Query count
- Key ratios (traced vs untraced time)

### 4. Institutional Memory

Capture validated learnings:

**Output:** `output/{trace-id}/learnings.md`

Format for each learning:

```markdown
## Learning: [Title]

**Date:** YYYY-MM-DD
**Trace:** [Trace ID]
**Confidence:** High/Medium/Low

### What We Found
[Description of issue]

### Root Cause
[Why this happens]

### Solution
[How to fix]

### Impact
[Measured or estimated improvement]

### Evidence
[Links to analysis files]
```

### 5. Verification Checklist

Create checklist for validating optimizations:

**Output:** `output/{trace-id}/verification-checklist.md`

For each recommendation:

- [ ] Change implemented
- [ ] Tests pass
- [ ] New trace captured
- [ ] Improvement measured
- [ ] Regression checked

## Link Validation

Verify all internal links work:

- Summary links to detailed files
- Recommendation cards link to evidence
- Code locations are accurate

## Exit Criteria

- [ ] `output/{trace-id}/SUMMARY.md` exists and is scannable in 5-10 minutes
- [ ] Recommendation cards created for top 5 opportunities
- [ ] `output/{trace-id}/baseline.md` exists
- [ ] `output/{trace-id}/learnings.md` exists
- [ ] `output/{trace-id}/verification-checklist.md` exists
- [ ] All links validated
- [ ] Analysis directory complete and organized

## Completion

Analysis playbook complete. Outputs ready for review and implementation.

### Output Structure

```
output/{trace-id}/
├── SUMMARY.md                    # Start here
├── scope.md                      # Analysis parameters
├── trace-summary.md              # Trace metadata
├── operation-index.md            # Operation inventory
├── baseline.md                   # Performance baseline
├── learnings.md                  # Institutional memory
├── verification-checklist.md     # Implementation tracking
├── groups/                       # Per-operation analysis
│   └── {prefix}/
│       ├── profile.md
│       └── bottlenecks.md
├── aggregation/                  # Pattern aggregation
│   ├── issue-clusters.md
│   ├── time-attribution.md
│   ├── n-plus-one-summary.md
│   ├── prefetch-gaps.md
│   └── critical-path.md
├── synthesis/                    # Impact synthesis
│   ├── impact-estimates.md
│   ├── priority-matrix.md
│   ├── roadmap.md
│   └── code-locations.md
├── opportunities/                # Opportunity details
│   └── {opportunity-name}.md
└── recommendations/              # Action cards
    └── {recommendation-name}.md
```
