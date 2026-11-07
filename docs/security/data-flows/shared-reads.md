# DF-03: Public and shared reads

| Metadata | Value |
| --- | --- |
| ID | DF-03 |
| Status | Reviewed against representative read paths |
| Entry point | N23 list URL and N26 /n26/gangs/<id>/ |
| Actors | Anonymous visitor or crawler ([ADV-01](../adversaries/adv-01-anonymous.md)), player or link recipient ([ADV-02](../adversaries/adv-02-player.md)) |
| Assets | [A-02 player data](../assets/a-02-player-data.md) |
| Trust boundaries | TB-01, TB-02 |
| Evidence | [N23 list discovery and detail](../../../n23/core/views/list/views.py), [N23 list form wording](../../../n23/core/forms/list.py), [N23 private-note template](../../../n23/core/templates/core/includes/list_notes.html), [N26 gang sheet](../../../n26/core/views/gangs.py), [N26 read permissions](../../../n26/core/views/permissions.py) |

## Sequence

~~~mermaid
sequenceDiagram
    actor Reader
    participant Browser
    participant App as Django read view
    participant DB as PostgreSQL
    Reader->>Browser: Follow roster link or browse listings
    Browser->>App: GET with optional session, crossing TB-01
    Note over Browser,App: TB-01: URL knowledge is not ownership, and owner-only material needs a separate check
    App->>DB: Read non-archived roster and related records, crossing TB-02
    Note over App,DB: TB-02: public discovery filters differ from direct shared-link lookup
    App-->>Browser: Public sheet with owner controls or private notes only when authorised
~~~

## Boundaries and controls

| Boundary | From → to | Data and authority crossing | Current control / assumption |
| --- | --- | --- | --- |
| TB-01 | Reader → app | Public URL and optional identity | N23 public=False means unlisted, not private: discovery filters public=True while detail fetches by ID. N26 explicitly allows anyone to read an active gang sheet; ownership adds editing controls. |
| TB-02 | App → database | Roster and owner-specific material | N26 excludes archived gangs. N23's private fighter notes are rendered only for the owner; share links include only selected card-view query parameters. |

## Failure points

- Any field placed on an intentionally shareable sheet may become public even when its edit page was owner-only.
- Unlisted N23 lists are reachable by their URL; do not treat the public flag as an access-control setting.
