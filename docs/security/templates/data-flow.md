# DF-XX: [Flow name]

| Metadata | Value |
| --- | --- |
| ID | DF-XX |
| Status | Draft / reviewed |
| Last reviewed | YYYY-MM-DD |
| Next review | [Date or concrete trigger] |
| Entry point | [Route, job, webhook, CLI, or other trigger] |
| Actors | [Linked adversary or legitimate actor records] |
| Assets | [Linked asset records] |
| Trust boundaries | [Boundary IDs used in the diagram] |
| Evidence | [Code and deployment paths] |

## Sequence

~~~mermaid
sequenceDiagram
    actor User
    participant Browser
    participant App
    participant Store
    User->>Browser: [Action]
    Browser->>App: Example request crossing TB-XX
    Note over Browser,App: TB-XX: [Who controls each side]
    App->>Store: Example read or write crossing TB-YY
    App-->>Browser: Example response crossing TB-XX
~~~

## Boundaries and controls

| Boundary | From → to | Data and authority crossing | Current control / assumption |
| --- | --- | --- | --- |
| TB-XX | [Source] → [destination] | [Data, identity, command] | [Observed check] |

## Failure points

- [Directly relevant threat links or observed gaps.]
