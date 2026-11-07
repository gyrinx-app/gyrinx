# R-06: Public read traffic can exhaust serving capacity

| Metadata | Value |
| --- | --- |
| ID | R-06 |
| Status | Residual after incident response |
| Related threats | [T-06](../threats/t-06-public-read-overload.md) |
| Assets | [A-02](../assets/a-02-player-data.md), [A-01](../assets/a-01-accounts.md) |
| Likelihood | Medium |
| Impact | High |
| Priority | High |
| Confidence | High for the mechanism; medium for current edge policy |
| Owner | Public page performance and edge operations |

## Why this rating

The [August 2026 incident](../../operations/incidents/2026-08-06-crawler-overload.md) demonstrated that a crawl of public gang pages could exhaust the application's connection pool and cause errors. Route-aware robots rules, cache changes and edge throughput controls reduced exposure, but robots directives are voluntary and current Cloud Armor policy is outside this repository. A repeatable public request path makes likelihood material; broad site unavailability makes impact high.

## Treatment

Keep route-aware robots tests, cache capacity and anonymous throughput protections aligned with the public URL structure. Check current edge enforcement and pool saturation during representative repeated public reads. Revisit this rating after a load test using realistic gang detail and print pages; do not publish operational thresholds in this document.
