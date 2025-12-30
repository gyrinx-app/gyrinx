# Trace Analysis Glossary

Definitions for metrics, terms, and concepts used in trace performance analysis.

## Trace Concepts

### Span

A single timed operation within a trace. Has a start time, end time, name, and optional parent span.

### Trace

A collection of spans representing a single request/transaction through a system.

### Parent Span

The span that initiated/contains another span. Forms the trace hierarchy.

### Root Span

The top-level span with no parent, typically the HTTP request handler.

### Span Duration

Time between span start and end: `end_time - start_time`

### Critical Path

The longest sequential chain of dependent operations. Optimizing the critical path directly reduces total time.

## Metrics

### Total Request Time

Time from first span start to last span end. What the user experiences.

### Traced Time

Sum of all individual span durations. May exceed total request time if operations run in parallel.

### Untraced Time

Time not accounted for by any span. Calculated as gaps between traced operations.

```
Untraced = Total Request Time - (Sum of traced operations accounting for overlap)
```

### N+1 Query Count

Number of times an operation is repeated when it could be batched.

```
N+1 Score = (Repeat Count - 1) × Average Duration
```

### Prefetch Efficiency

Ratio of prefetched to total data accesses.

```
Efficiency = Prefetched Accesses / Total Accesses
```

## Common Operation Patterns

### View Operations

Django view methods: `get_object()`, `get_context_data()`, `get_queryset()`

### Model Operations

Database access patterns: `filter()`, `get()`, `select_related()`, `prefetch_related()`

### Cached Properties

Python `@cached_property` decorated methods. First access computes, subsequent access uses cache.

### Prefetch Related

Django ORM method to batch load related objects in a single query.

### Select Related

Django ORM method to join related tables in a single query.

## Performance Thresholds

| Metric | Good | Acceptable | Poor |
|--------|------|------------|------|
| Total Request Time | <500ms | 500-2000ms | >2000ms |
| Single Query | <10ms | 10-50ms | >50ms |
| N+1 Pattern | None | 2-5 repeats | >5 repeats |
| Untraced Ratio | <10% | 10-25% | >25% |

## Django-Specific Terms

### QuerySet

Lazy database query that only executes when iterated or evaluated.

### Prefetch Object

Custom prefetch specification with filtered queryset and target attribute.

### Manager

Class that provides database query methods for a model.

### with_related_data()

Common pattern: QuerySet method that adds all standard prefetches/selects for a model.

## Google Cloud Trace Terms

### Trace ID

Unique identifier for a trace, typically a UUID or hex string.

### Span ID

Unique identifier for a span within a trace.

### Labels

Key-value metadata attached to spans (also called attributes in OpenTelemetry).

### Parent Span ID

Reference to the parent span, used to build the trace tree.
