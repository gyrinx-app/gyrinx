# R-02: Object-level authorization regresses across player routes

| Metadata | Value |
| --- | --- |
| ID | R-02 |
| Status | Controlled invariant; no current bypass established |
| Related threats | [T-02](../threats/t-02-cross-owner-write.md), [T-08](../threats/t-08-shared-read-privacy.md) |
| Assets | [A-02](../assets/a-02-player-data.md) |
| Likelihood | Low |
| Impact | High |
| Priority | Medium |
| Confidence | Medium |
| Owner | N23 and N26 player-data views and operations |

## Why this rating

Shared links and campaign participation let a player learn IDs for objects they do not own. If a write endpoint accepts those IDs without an owner or arbitrator check, another player's game state can change. If a shared-read variant includes owner-only fields, private notes can be disclosed. Current [N26 permission helpers](../../../n26/core/views/permissions.py) distinguish read and write access; N26 writes use operations, and surveyed N23 routes apply owner or arbitrator scopes. This makes a current exploit unlikely but the boundary worth preserving because the impact is high.

## Treatment

Keep owner and campaign authority checks at each object lookup, including nested IDs, and test allowed and denied cases whenever a write or shared display route changes. Treat any demonstrated bypass as a new finding with its own likelihood and remediation. No current exploit is asserted.
