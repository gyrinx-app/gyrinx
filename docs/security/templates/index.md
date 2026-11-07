# Threat-model templates

| Metadata | Value |
| --- | --- |
| Purpose | Repeatable records for a maintained Gyrinx threat model |
| Record types | Data flow, asset, adversary, threat, risk |
| Scope | Files under docs/security |
| Status | Template; replace bracketed prompts before publishing a record |

Use stable IDs: DF for data flows, A for assets, ADV for adversaries, T for threats, and R for assessed risks. Link records by ID and relative path. Record what the current code and deployment documentation establish; label assumptions and unknowns. Keep a threat to one plausible action or event and its direct harm. A risk may group threats that share the same cause and mitigation. Omit marginal risks and effects already captured by a larger risk.

Follow the [review and archive process](../process.md). Record a review date, next trigger, owner, tracking link and brief decision history when creating or changing a threat or risk. A PR containing a fix does not close a record until deployed behavior and residual exposure are verified. Every index lists the full records in its folder and explains its fields; archived full records have separate indexes, while old paths may contain forwarding stubs. Update indexes whenever records change.
