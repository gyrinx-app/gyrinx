# Adversaries

| Metadata | Value |
| --- | --- |
| Scope | Plausible actors at the application, provider, staff, and deployment boundaries |
| Baseline date | 2026-11-07 |
| Record status | Initial code-based assessment |
| Model | Starting authority matters; a legitimate account may act outside its authorized scope |
| Exclusions | Physical compromise and direct Cloud SQL/GCS administrator abuse are outside this first application-focused pass |

| ID | Starting position | Relevant boundaries | Main assets at risk |
| --- | --- | --- | --- |
| [ADV-01](adv-01-anonymous.md) | No Gyrinx account | TB-01, TB-03, TB-04, conditional TB-05 | [A-01](../assets/a-01-accounts.md), [A-02](../assets/a-02-player-data.md), [A-04](../assets/a-04-media.md), [A-06](../assets/a-06-service-secrets.md) |
| [ADV-02](adv-02-player.md) | Authenticated ordinary account | TB-01, TB-02, TB-03 | [A-01](../assets/a-01-accounts.md), [A-02](../assets/a-02-player-data.md), [A-03](../assets/a-03-content.md), [A-04](../assets/a-04-media.md) |
| [ADV-03](adv-03-campaign-insider.md) | Campaign participant, arbitrator, or shared admin | TB-01, TB-02 | [A-02](../assets/a-02-player-data.md), [A-03](../assets/a-03-content.md) |
| [ADV-04](adv-04-staff-session.md) | Compromised or malicious staff account/session | TB-01, TB-02, TB-03, TB-06 | [A-01](../assets/a-01-accounts.md), [A-03](../assets/a-03-content.md), [A-05](../assets/a-05-ingest-sheets.md) |
| [ADV-05](adv-05-deployment-principal.md) | Compromised source or cloud deployment principal | TB-02, TB-03, TB-05, TB-07 | [A-01](../assets/a-01-accounts.md), [A-02](../assets/a-02-player-data.md), [A-06](../assets/a-06-service-secrets.md), [A-07](../assets/a-07-task-state.md), [A-08](../assets/a-08-release.md) |

These are capability profiles for analysis, not claims that any person or provider is acting maliciously. A forged Patreon, Discord, or Pub/Sub request starts as ADV-01 unless the attacker already holds a trusted secret or principal.
