# Stage 1: Per-Span-Group Analysis

**Mode:** Parallel (multiple operations analyzed concurrently)
**Duration:** Variable based on operation count

## Purpose

Deep analysis of each major operation group to understand its performance characteristics, identify bottlenecks, and classify issues.

## Prerequisites

- Stage 0 completed
- `output/{trace-id}/operation-index.md` exists
- `output/{trace-id}/scope.md` confirms analysis parameters

## Operation Groups to Analyze

Typical groups in Django/web application traces:

| Prefix | Description | Typical Concerns |
|--------|-------------|------------------|
| `GET /...` | HTTP requests | Total request time |
| `*View_*` | Django view operations | View logic time |
| `list_*` | List-level operations | Query efficiency |
| `listfighter_*` | Fighter-level operations | N+1 queries |
| `listfighterequipment*` | Equipment operations | Cost calculations |
| `*_cached` | Cached property access | Cache effectiveness |

## Analysis Per Group

For each operation group, create:

### 1. Operation Profile (`output/{trace-id}/groups/{prefix}/profile.md`)

**Template:** `playbooks/trace/templates/operation-profile.md`

Contents:

- Operation description and purpose
- Call frequency (count)
- Duration statistics (total, avg, min, max)
- Parent-child relationships
- Identified issues

### 2. Bottleneck Analysis (`output/{trace-id}/groups/{prefix}/bottlenecks.md`)

**Template:** `playbooks/trace/templates/bottleneck-analysis.md`

Contents:

- Slowest individual operations
- Time breakdown by sub-operation
- N+1 pattern detection
- Missing prefetch opportunities

### 3. Issue Classification

Tag each issue using the taxonomy in `playbooks/trace/reference/issue-taxonomy.md`:

| Tag | Description |
|-----|-------------|
| `N+1_QUERY` | Same query repeated per item |
| `MISSING_PREFETCH` | Related data not prefetched |
| `EXPENSIVE_COMPUTATION` | CPU-bound calculation |
| `CACHE_MISS` | Cache not utilized |
| `UNTRACED_TIME` | Time not accounted for |

## Execution

### Parallelization

Launch one agent per operation group:

- Recommended: 3-5 concurrent agents
- Each agent writes to isolated directory
- No cross-agent dependencies

### Sub-Agent Prompt Template

```
Analyze the '{prefix}' operation group from the trace.

Input:
- Trace file: {trace_path}
- Operation prefix: {prefix}
- Scope: {scope_path}

Output directory: output/{trace-id}/groups/{prefix}/

Tasks:
1. Read playbooks/trace/stages/1-per-span-group/README.md
2. Create profile.md using template
3. Create bottlenecks.md using template
4. Tag issues using taxonomy

Exit when both files created with >500 bytes each.
```

## Exit Criteria

For each operation group:

- [ ] `output/{trace-id}/groups/{prefix}/profile.md` exists (>500 bytes)
- [ ] `output/{trace-id}/groups/{prefix}/bottlenecks.md` exists (>500 bytes)
- [ ] Issues classified with taxonomy tags
- [ ] Duration statistics accurate

Overall:

- [ ] All operation groups from index analyzed
- [ ] No failed or incomplete analyses

## Next Stage

Proceed to Stage 2 (Pattern Aggregation) once all groups analyzed.
