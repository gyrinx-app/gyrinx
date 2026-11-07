# T-06: Automated public reads exhaust serving capacity

| Metadata | Value |
| --- | --- |
| ID | T-06 |
| STRIDE | Denial of Service |
| Adversary | [ADV-01: anonymous caller](../adversaries/adv-01-anonymous.md) |
| Assets | [A-02: gangs and campaigns](../assets/a-02-player-data.md) (availability), [A-01: accounts](../assets/a-01-accounts.md) (site access) |
| Data flow / boundary | [DF-03](../data-flows/shared-reads.md); TB-01 and TB-02 |
| Risk | [R-06: public overload](../risk-assessment/r-06-public-overload.md) |
| Status | Observed in August; October outage correlation under investigation |
| Evidence | [crawler incident](../../operations/incidents/2026-08-06-crawler-overload.md), 20 October 2026 Cloud Run request and application logs (internal review), [production pool settings](../../../gyrinx/settings_prod.py), [robots route](../../../gyrinx/pages/views.py) |

## Scenario

A crawler or deliberate requester repeatedly opens public gang detail, print, or index pages. Their database work competes with ordinary users for a bounded per-process connection pool. At sufficient concurrency, requests wait past pool timeout and the site returns errors. A broad crawl is enough; the attacker need not authenticate or mutate data.

On 20 October 2026, Cloud Run recorded 13,585 5xx responses on `/n23/lists/`; 12,799 came from 398 IPs in one source range. The application logged five-second database pool timeouts starting at 06:04 UTC. This traffic plausibly contributed to the outage, but the logs do not establish that it initiated it.

## Existing controls and uncertainty

The August 2026 incident led to route-aware robots rules, larger caches, crawler edge blocks and an anonymous throughput cap on affected paths. Robots rules are advisory, and the edge policy lives outside this repository. This is a residual availability scenario, not a claim that the earlier outage remains unfixed.
