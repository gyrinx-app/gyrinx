# A-03: Game content catalogue

| Metadata | Value |
| --- | --- |
| ID | A-03 |
| Status | Initial baseline |
| Location and owner | N23 CustomContentPack and content rows; N26 library packs and authoring rows in the application database |
| Sensitivity | Mostly public after publication; unlisted packs and staged content are internal to their intended audience |
| Integrity need | High: one shared rule change can affect many gangs and campaigns |
| Availability need | High: list building and gang rendering rely on catalogue content |
| Flows | [DF-04](../data-flows/staff-authoring.md), [DF-03](../data-flows/shared-reads.md), [DF-02](../data-flows/player-writes.md) |
| Evidence | [N23 pack permissions](../../../n23/core/models/pack.py), [N26 pack](../../../n26/library/models/pack.py), [N26 authoring views](../../../n26/library/views.py), [N26 campaign type link](../../../n26/core/models/campaign.py) |

## What must be protected

Community packs and their editor permissions, the shared N26 rules catalogue, and staff authoring changes. N23 owners can share edit access to a custom pack. N26's system pack is shared, and a campaign's founding type continues to refer to shared library content. These are different authority levels within one content asset.

## Security properties

- Confidentiality: Preserve the intended boundary around unlisted community packs and staged content until they are released.
- Integrity: Apply pack owner/editor checks and staff authoring checks at each write; prevent untrusted rich text or attachments from becoming executable content in readers' browsers.
- Availability: Prevent catalogue corruption or removal that blocks existing gangs and campaigns.
