# DF-07: External webhooks and outbound integrations

| Metadata | Value |
| --- | --- |
| ID | DF-07 |
| Status | Reviewed against current webhook and task code |
| Entry point | /api/v1/hooks/patreon.json and /api/v1/discord/interactions |
| Actors | Patreon, Discord, external sender ([ADV-01](../adversaries/adv-01-anonymous.md)) |
| Assets | [A-01 accounts](../assets/a-01-accounts.md), [A-07 task state](../assets/a-07-task-state.md), [A-06 service secrets](../assets/a-06-service-secrets.md) |
| Trust boundaries | TB-02, TB-04, TB-05, TB-07 |
| Evidence | [Webhook routes](../../../gyrinx/api/urls.py), [Webhook verification](../../../gyrinx/api/views.py), [Patreon account matching](../../../gyrinx/api/patreon.py), [Discord task](../../../gyrinx/api/tasks.py), [GitHub workflow](../../../.github/workflows/discord-issue.yml) |

## Sequence

~~~mermaid
sequenceDiagram
    actor Provider as Patreon or Discord
    participant App as Django webhook view
    participant DB as PostgreSQL
    participant Queue as Task queue
    participant API as GitHub and Discord APIs
    Provider->>App: Signed POST payload; crosses TB-04
    Note over Provider,App: TB-04: provider identity is asserted by HMAC or Ed25519 signature
    App->>DB: Persist webhook or update verified-email match; crosses TB-02
    alt Discord Create Issue
        App->>Queue: Enqueue command; crosses TB-05
        Queue->>API: Dispatch GitHub workflow and respond to Discord; crosses TB-07
        Note over Queue,API: TB-07: outbound API credentials and message content leave Gyrinx
    end
    App-->>Provider: Acknowledge or reject
~~~

## Boundaries and controls

| Boundary | From → to | Data and authority crossing | Current control / assumption |
| --- | --- | --- | --- |
| TB-04 | Provider → app | Events that change supporter status or create an issue request | Patreon verifies raw-body HMAC with its webhook secret; Discord verifies Ed25519 signature over timestamp and body. Both exempt CSRF as external callbacks. |
| TB-02 | App → database | Webhook audit payload and supporter profile | Patreon matches only a verified allauth email address before updating supporter state. |
| TB-05 | App → task queue | Discord interaction token and message details | Registered background task handles outbound work. |
| TB-07 | Worker → GitHub/Discord | Dispatch token, bot token, message content | Worker calls fixed provider API hosts; GitHub workflow has issues:write and uses its own secrets. |

## Failure points

- Webhook secrets and Discord public key are runtime inputs. An absent Patreon secret returns 503; absent Discord key returns 503.
- A valid provider signature does not make the provider payload harmless. Patreon and Discord retain control of its fields, including text sent to the GitHub automation.
