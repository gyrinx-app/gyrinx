# T-08: Shared read exposes owner-only gang data

| Metadata | Value |
| --- | --- |
| ID | T-08 |
| STRIDE | Information Disclosure |
| Adversary | [ADV-01: anonymous caller](../adversaries/adv-01-anonymous.md), [ADV-03: campaign insider](../adversaries/adv-03-campaign-insider.md) |
| Assets | [A-02: gangs and campaigns](../assets/a-02-player-data.md) |
| Data flow / boundary | [DF-03](../data-flows/shared-reads.md); TB-01 and TB-02 |
| Risk | [R-02: authorization](../risk-assessment/r-02-authorization.md) |
| Status | Credible regression scenario; no specific leak is established here |
| Evidence | [N23 list reads and print variants](../../../n23/core/views/list/views.py), [N26 read/write permission split](../../../n26/core/views/permissions.py), [N23 public profiles](../../../n23/core/public_profiles.py) |

## Scenario

A reader obtains a shared gang or campaign URL, or enumerates public records, then opens a nested page or print variant that includes owner-only notes or other private details. The system intentionally allows some reads without ownership, so each display path must keep private fields out of its response. A single new template or serializer that uses a full model object without that distinction can disclose personal or strategic notes.

## Existing controls and uncertainty

N23 print variants explicitly blank fighter private notes unless the viewer is the owner. Public-profile queries filter by visibility, and N26 names distinct shared-read and owner-write helpers. This record identifies a high-consequence boundary to keep covered as new variants appear; it does not assert an existing leak.
