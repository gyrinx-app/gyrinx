# ADV-02: Authenticated player

| Metadata | Value |
| --- | --- |
| ID | ADV-02 |
| Status | Initial baseline |
| Starting access | Valid ordinary Gyrinx account and its own session |
| Reachable boundaries | TB-01 request to app; TB-02 authorized database reads/writes; TB-03 upload and media read |
| Assets sought | [A-01](../assets/a-01-accounts.md), [A-02](../assets/a-02-player-data.md), [A-03](../assets/a-03-content.md), [A-04](../assets/a-04-media.md) |
| Evidence / assumption | [N23 list ownership](../../../n23/core/models/list/list.py), [N23 pack permissions](../../../n23/core/models/pack.py), [N26 gang ownership](../../../n26/core/models/gang.py), [N26 player-data rules](../../../n26/core/AGENTS.md) |

## Goals and capabilities

Can create and change their own gangs, lists, and community packs; submit forms, identifiers, rich text, and image uploads; and read public or shared game data. They can repeat or race requests. The concern is reaching another player's private data or write authority, or causing content they control to execute in another reader's browser.

## Limits

A valid player session does not grant staff authoring, Django admin, ownership of another player's gang, or arbitrary task execution. Campaign-specific authority is modeled in [ADV-03](adv-03-campaign-insider.md).
