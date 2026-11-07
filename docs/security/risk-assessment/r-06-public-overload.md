# R-06: Public read traffic can exhaust serving capacity

| Metadata | Value |
| --- | --- |
| ID | R-06 |
| Last reviewed | 2026-11-07 |
| Next review | On material change or by 2027-02-07 |
| Status | Residual after incident response; October outage correlation under investigation |
| Related threats | [T-06](../threats/t-06-public-read-overload.md) |
| Assets | [A-02](../assets/a-02-player-data.md), [A-01](../assets/a-01-accounts.md) |
| Likelihood | Medium |
| Impact | High |
| Priority | High |
| Confidence | High for the mechanism; medium for October attribution and current edge policy |
| Owner | Public page performance and edge operations |

## Why this rating

The [August 2026 incident](../../operations/incidents/2026-08-06-crawler-overload.md) demonstrated that a crawl of public gang pages could exhaust the application's connection pool and cause errors. A review of 20 October 2026 production logs found 17,040 site-wide 5xx responses and 2,355 429 responses; 12,799 of the 13,585 `/n23/lists/` 5xx responses came from 398 IPs in one source range. Database pool timeouts appeared at the start of the error spike. This supports automated load as a plausible contributor, not a proven initiating cause. Route-aware robots rules, cache changes and edge throughput controls reduced exposure after August, but robots directives are voluntary and current Cloud Armor policy is outside this repository. A repeatable public request path makes likelihood material; broad site unavailability makes impact high.

## Treatment

Keep route-aware robots tests, cache capacity and anonymous throughput protections aligned with the public URL structure. Investigate the 20 October causal sequence and check current edge enforcement and pool saturation during representative repeated public reads. Revisit this rating after a load test using realistic gang detail, list and print pages; do not publish operational thresholds in this document.
