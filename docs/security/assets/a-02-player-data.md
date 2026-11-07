# A-02: Player gangs and campaigns

| Metadata | Value |
| --- | --- |
| ID | A-02 |
| Status | Initial baseline |
| Location and owner | N23 List, Campaign, and related rows; N26 Gang, Campaign, assignments, and ledger in the application database |
| Sensitivity | Mixed: public sheets and campaigns, private or unlisted records, and participant information |
| Integrity need | High: unauthorized changes alter ownership, game state, and financial history |
| Availability need | High: gangs and campaigns are the application's primary user data |
| Flows | [DF-02](../data-flows/player-writes.md), [DF-03](../data-flows/shared-reads.md), [DF-06](../data-flows/tasks.md) |
| Evidence | [N23 list](../../../n23/core/models/list/list.py), [N23 campaign](../../../n23/core/models/campaign.py), [N26 gang](../../../n26/core/models/gang.py), [N26 campaign](../../../n26/core/models/campaign.py), [N26 ledger](../../../n26/core/models/ledger.py) |

## What must be protected

Player-created lists and gangs, fighters and equipment, campaign membership and invitations, campaign assets, credits, and change history. N23 lists and campaigns have public flags; N26 gangs and campaigns carry owners, and accepted campaign participants have a narrower role than the arbitrator. N26 ledger events record who changed gang state.

## Security properties

- Confidentiality: Honor private and unlisted visibility, and avoid exposing invitations or membership details outside their intended audience.
- Integrity: A player may change their own gang; campaign authority must not silently confer ownership of another player's gang. Preserve N26's operation and ledger invariants.
- Availability: Avoid loss or inaccessible state during writes, cloning, and background work.
