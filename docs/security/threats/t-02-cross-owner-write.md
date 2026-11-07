# T-02: Player write crosses an ownership boundary

| Metadata | Value |
| --- | --- |
| ID | T-02 |
| Last reviewed | 2026-11-07 |
| Next review | On material change or by 2027-02-07 |
| STRIDE | Elevation of Privilege |
| Adversary | [ADV-02: authenticated player](../adversaries/adv-02-player.md), [ADV-03: campaign insider](../adversaries/adv-03-campaign-insider.md) |
| Assets | [A-02: gangs and campaigns](../assets/a-02-player-data.md) |
| Data flow / boundary | [DF-02](../data-flows/player-writes.md); TB-01 and TB-02 |
| Risk | [R-02: authorization](../risk-assessment/r-02-authorization.md) |
| Status | Credible regression scenario; no specific cross-owner write is established here |
| Evidence | [N26 permission helpers](../../../n26/core/views/permissions.py), [N26 operation guidance](../../../n26/core/AGENTS.md), [N23 list views](../../../n23/core/views/list/views.py) |

## Scenario

A signed-in player substitutes another gang, fighter, assignment, or campaign ID in a write request. If a new endpoint uses a shareable read lookup for a write, trusts a nested form ID without checking its parent, or extends a campaign arbitrator's authority too far, the operation can change another player's records. A guessed identifier is less likely than one learned from a shared page or campaign membership.

## Existing controls and uncertainty

N26 distinguishes shareable read helpers from owner-scoped write helpers and funnels player-data writes through operations. N23 uses owner-filtered lookups and explicit arbitrator checks on many write routes. This record is a material invariant to preserve across both editions; it is not an allegation that the surveyed routes currently allow cross-owner edits.
