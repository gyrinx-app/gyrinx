# Crawler overload — 6 August 2026

Search and AI crawlers began walking pages that had been excluded from crawling,
and the load took the site down intermittently for several hours.

Operational specifics — thresholds, current rule configuration, capacity figures
— are deliberately absent; see the private runbook. What follows is the
mechanism and the reasoning.

## Symptoms

- Request volume climbing from around midnight.
- Intermittent 500s, concentrated on the most query-heavy pages: gang detail and
  its print variants, and the paginated gang index.
- `OperationalError: couldn't get a connection` raised from the database
  connection pool.
- `CacheKeyWarning` for the page-reference cache filling the logs — which turned
  out to be a symptom rather than a fault, since that warning fires on every
  cache operation and its volume tracked the miss rate.

## Cause

`robots.txt` disallowed a set of paths. When the edition moved under a `/n23/`
URL prefix, **those paths stopped matching any real URL**, and the pages they had
been protecting became crawlable. Nothing errored; the file was still valid and
still served.

The test covering it asserted that the expected `Disallow` line was *present in
the response*. It verified the text existed, not that it corresponded to a route
the site actually serves, so it passed unchanged through the URL restructure.

A second instance of the same class sat next to it: a rule naming one crawler by
a token that crawler does not use. It had never matched anything, and nothing
had ever indicated that.

**The lesson.** A `robots.txt` rule is a claim about your URL structure, and it
rots silently when that structure changes. Assert that each rule *resolves to a
real route*, not that the file contains the right words. The fixed test
substitutes an id for each wildcard and requires resolution.

## Why crawling was enough to cause an outage

Three multipliers, none introduced by the crawl. It only found them.

**Connection pool versus container concurrency.** Each container accepts
considerably more concurrent requests than it holds database connections. Pages
issuing many queries occupy a connection for a long time, so under load the
excess threads queue, exceed the pool timeout and return 500.

Worth knowing for diagnosis: this is *client-side pool exhaustion*, and it looks
much like the database refusing connections while requiring a different response.
The database was nowhere near its limit. Searching the logs for
`FATAL: too many clients` distinguishes the two in seconds.

**A cache smaller than its working set.** The page-reference caches used the
framework default for maximum entries, which was well below the number of
distinct lookups the content generates. Past that ceiling the cache evicts a
fraction of itself on every insert, so under a broad crawl — which touches many
distinct keys in quick succession — the hit rate collapses toward zero and each
miss runs a query no index can serve.

**Empty results were never cached.** The lookup tested the cached value for
truthiness:

```python
cached = cache.get(key)
if cached:      # an empty result is falsy, so it reads as a cache miss
```

Anything with no match re-queried on every single call and could never be cached.
Fixed with a sentinel, so "cached, and the answer is nothing" is distinct from
"not cached".

**Compounding all three:** the caches are per-process, so every new container and
worker starts cold. Autoscaling under load therefore makes the miss rate worse at
exactly the moment it can least afford to.

## Response

**Corrected the cause.** `robots.txt` repointed at the current URL structure,
with the print views excluded too — they are the most expensive pages and have no
reason to be indexed. The test rewritten to assert resolution.

**Sized the caches to the working set** and fixed the empty-result hole.

**Blocked declared crawlers at the edge** with a Cloud Armor deny rule. Search
engines and link-preview fetchers are exempt: blocking the former costs search
visibility, and the latter is a different agent from the AI crawler that shares
its vendor, so blocking it would break link previews.

**Capped anonymous throughput** on the affected paths once it became clear the
remaining load came from a client presenting as an ordinary browser and spread
thinly across many addresses — a shape that defeats both agent-based blocking and
per-address rate limiting. Signed-in users are unaffected.

## Judgements worth recording

**Roll out edge rules in preview first.** Cloud Armor's preview mode evaluates a
rule and logs what it would have done without acting. It took a few minutes and
confirmed the rule matched only what was intended before it was enforced. This is
cheap insurance on a policy that has produced false positives before.

**A rule left in preview is worse than no rule.** The policy already contained a
per-address rate limit that had been in preview indefinitely — logging, never
acting. It appeared on the dashboard as protection that did not exist.

**Its own preview logs decided its fate.** Rather than reasoning about whether to
enforce it, we read what it *would* have done. It would have blocked a major
search engine's crawler, and because that rule bans an address outright rather
than rejecting a single request, the damage would have been ongoing and
attributed to nothing. It was deleted rather than enforced or left misleading.

**Identity-based controls only work on clients that are honest about their
identity.** Well-behaved crawlers identify themselves and were stopped. A client
that presents as a browser is a different problem needing a different control.

## Cloud Armor notes

Two syntax details that cost time:

- Capture groups are rejected in rule expressions. Use non-capturing `(?:...)`.
- For case-insensitive matching, use the inline `(?i)` flag rather than a
  `.lower()` call on the header.

Rule changes take a minute or two to propagate. Test with an actual request
rather than assuming an update has taken effect — and note that Cloud Armor has
no enable/disable switch, so preview mode is how a rule is turned off without
losing it.

## Diagnostic checklist

1. **Is it real traffic?** Group requests by user agent and source address over
   the last half hour. Many addresses making one or two requests each means
   per-address limiting will not help.
2. **Which paths are failing?** Concentration on expensive pages suggests
   crawling rather than a user-facing regression.
3. **Pool or database?** Look for `FATAL: too many clients`. Its absence means
   the application's connection pool is the constraint.
4. **Did something deploy just before it started?** Compare the running revision
   and build history against the time errors began.
5. **Is `robots.txt` still accurate?** Any URL restructure can invalidate it
   silently, and nothing will tell you.
