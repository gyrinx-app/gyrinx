# Issue Taxonomy

Classification tags for performance issues identified during trace analysis.

## Primary Tags

Use these mutually exclusive tags to classify the root cause of each issue:

| Tag | Description | Example |
|-----|-------------|---------|
| `N+1_QUERY` | Same query repeated per item in a loop | Fetching equipment for each fighter separately |
| `MISSING_PREFETCH` | Related data not prefetched in initial query | Fighter loaded without equipment prefetched |
| `EXPENSIVE_COMPUTATION` | CPU-bound calculation taking significant time | Complex cost calculations per item |
| `CACHE_MISS` | Data should be cached but isn't | Re-computing same value multiple times |
| `UNTRACED_TIME` | Significant time not covered by spans | Gap between traced operations |
| `SERIAL_EXECUTION` | Operations run sequentially that could parallelize | Independent queries run one after another |
| `REDUNDANT_QUERY` | Same exact query executed multiple times | Duplicate fetches of same data |
| `OVER_FETCHING` | Retrieving more data than needed | SELECT * when only id needed |
| `UNDER_FETCHING` | Not retrieving enough data, causing follow-up queries | Missing related data in initial query |

## Impact Tags

Classify the severity of each issue:

| Tag | Time Impact | Priority |
|-----|-------------|----------|
| `IMPACT_HIGH` | >100ms | Address immediately |
| `IMPACT_MEDIUM` | 10-100ms | Address soon |
| `IMPACT_LOW` | <10ms | Address if convenient |

## Fix Complexity Tags

Estimate the effort to resolve:

| Tag | Description | Typical Effort |
|-----|-------------|----------------|
| `FIX_EASY` | Add prefetch, simple cache | < 1 hour |
| `FIX_MEDIUM` | Refactor query pattern, add caching layer | 1-4 hours |
| `FIX_HARD` | Architectural change, data model update | > 4 hours |

## Location Tags

Where in the codebase the fix applies:

| Tag | Description |
|-----|-------------|
| `LOC_MODEL` | Fix in model layer (prefetch, property) |
| `LOC_VIEW` | Fix in view layer (queryset optimization) |
| `LOC_TEMPLATE` | Fix in template (reduce calls) |
| `LOC_QUERY` | Fix in raw/custom query |
| `LOC_CACHE` | Fix involves caching strategy |

## Usage Examples

### Example 1: N+1 Query Pattern

```markdown
### Issue: Fighter equipment queries

**Tags:** `N+1_QUERY`, `IMPACT_HIGH`, `FIX_EASY`, `LOC_VIEW`

**Description:** Each fighter triggers a separate query for equipment.

**Evidence:**
- 20 identical query patterns for 20 fighters
- Total time: 150ms

**Solution:** Add `prefetch_related('equipment')` to queryset
```

### Example 2: Missing Prefetch

```markdown
### Issue: Category not prefetched

**Tags:** `MISSING_PREFETCH`, `IMPACT_MEDIUM`, `FIX_EASY`, `LOC_MODEL`

**Description:** Fighter category accessed but not in prefetch.

**Evidence:**
- 10 additional queries for category lookup
- Total time: 45ms

**Solution:** Add `select_related('category')` to fighter queryset
```

### Example 3: Expensive Computation

```markdown
### Issue: Cost calculation overhead

**Tags:** `EXPENSIVE_COMPUTATION`, `IMPACT_MEDIUM`, `FIX_MEDIUM`, `LOC_MODEL`

**Description:** Cost calculations performed per-fighter without caching.

**Evidence:**
- 800ms spent in cost_with_override methods
- Same calculations repeated

**Solution:** Cache cost at list level, reuse across fighters
```

## Tagging Guidelines

1. **Always apply one primary tag** - The root cause classification
2. **Always apply one impact tag** - Based on measured time
3. **Apply fix complexity when known** - May require investigation
4. **Apply location tags as identified** - Multiple locations possible

## Cross-Reference

Issues with the same primary tag often have related solutions. During Stage 2 (Pattern Aggregation), group issues by primary tag to identify systemic patterns.
