# DF-02: Player-data writes

| Metadata | Value |
| --- | --- |
| ID | DF-02 |
| Status | Reviewed against representative N23 and N26 write paths |
| Entry point | N23 list/fighter/campaign forms and N26 /n26/gangs/ actions |
| Actors | Signed-in player ([ADV-02](../adversaries/adv-02-player.md)), campaign insider ([ADV-03](../adversaries/adv-03-campaign-insider.md)) |
| Assets | [A-02 player data](../assets/a-02-player-data.md) |
| Trust boundaries | TB-01, TB-02 |
| Evidence | [N23 list edit](../../../n23/core/views/list/views.py), [N23 permission pattern](../../../n23/core/views/fighter/permissions.py), [N26 create/edit views](../../../n26/core/views/gangs.py), [N26 owner lookup](../../../n26/core/views/permissions.py), [N26 operations](../../../n26/core/operations.py) |

## Sequence

~~~mermaid
sequenceDiagram
    actor Player
    participant Browser
    participant App as Django view and form
    participant Domain as N23 handler or N26 operation
    participant DB as PostgreSQL
    Player->>Browser: Submit a change
    Browser->>App: POST with session and CSRF, crossing TB-01
    Note over Browser,App: TB-01: player controls IDs and form fields, so view must scope authority
    App->>DB: Fetch owned list or gang, crossing TB-02
    alt N23
        App->>Domain: Validated form and request user
        Domain->>DB: Save state and event, crossing TB-02
    else N26
        App->>Domain: Enter operation(gang, actor=user)
        Domain->>DB: Lock gang, write assignments and ledger, settle totals, crossing TB-02
    end
    App-->>Browser: Redirect or validation error, crossing TB-01
~~~

## Boundaries and controls

| Boundary | From → to | Data and authority crossing | Current control / assumption |
| --- | --- | --- | --- |
| TB-01 | Browser → view | Attacker-controlled row IDs and form values | Representative views require login and validate Django forms; CSRF middleware is installed. Each mutation still needs its own object-level check. |
| TB-02 | View/domain operation → database | Player-owned state and financial/game ledger | N23's representative edit scopes List by owner. N26's _own_gang_or_404 scopes by owner and archived=False; operation() uses a transaction, gang row lock, history event and settlement. Campaign arbitrator routes have separate permissions. |

## Failure points

- A missed owner or arbitrator check on one route can cross from one player's authority into another's data.
- A write outside N26 operation() can bypass ledger/history and cached-total reconciliation; the repository treats operation() as the only player-data writer.
