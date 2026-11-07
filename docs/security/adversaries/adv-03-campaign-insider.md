# ADV-03: Campaign insider

| Metadata | Value |
| --- | --- |
| ID | ADV-03 |
| Status | Initial baseline |
| Starting access | A player accepted into an N26 campaign, its arbitrator, or an N23 campaign owner/shared admin |
| Reachable boundaries | TB-01 campaign requests; TB-02 campaign and member-gang rows |
| Assets sought | [A-02](../assets/a-02-player-data.md), [A-03](../assets/a-03-content.md) |
| Evidence / assumption | [N26 campaign roles](../../../n26/core/models/campaign.py), [N23 shared admins](../../../n23/core/models/campaign.py), [N26 gang owner](../../../n26/core/models/gang.py) |

## Goals and capabilities

Can act with a legitimate campaign relationship. An accepted N26 participant can reach member surfaces, while the arbitrator owns the campaign and its additions pack. N23 shared admins can administer a campaign. These roles may try to change another participant's gang, invitees, campaign assets, or campaign content beyond the permissions of their own role.

## Limits

The roles are not interchangeable. N26's campaign model explicitly says an arbitrator does not own member gangs. An N26 invitee who has not accepted is not a member. The threat analysis must identify which role a scenario needs.
