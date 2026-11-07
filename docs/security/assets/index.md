# Assets

| Metadata | Value |
| --- | --- |
| Scope | Identities, player records, content, uploads, secrets, and asynchronous state handled by the Gyrinx application |
| Baseline date | 2026-11-07 |
| Record status | Initial code-based assessment |
| Granularity | Security-relevant groups of data or authority, not one record per database model |
| Sensitivity | Public, internal, personal, or secret; a public record can still need strong integrity protection |

| ID | Asset | Main security need | Data flows |
| --- | --- | --- | --- |
| [A-01](a-01-accounts.md) | Account identities and sessions | Keep authentication authority and personal data safe | [DF-01](../data-flows/account-session.md), [DF-07](../data-flows/integrations.md) |
| [A-02](a-02-player-data.md) | Player gangs and campaigns | Preserve ownership, visibility, and game history | [DF-02](../data-flows/player-writes.md), [DF-03](../data-flows/shared-reads.md) |
| [A-03](a-03-content.md) | Game content catalogue | Preserve authoring authority and shared rules | [DF-04](../data-flows/staff-authoring.md), [DF-03](../data-flows/shared-reads.md) |
| [A-04](a-04-media.md) | Uploaded public media | Prevent unsafe or altered files from reaching readers | [DF-05](../data-flows/media.md) |
| [A-05](a-05-ingest-sheets.md) | Held ingest spreadsheets | Keep pre-publication source files confined to staff | [DF-04](../data-flows/staff-authoring.md), [DF-05](../data-flows/media.md) |
| [A-06](a-06-service-secrets.md) | Service secrets and identities | Prevent forged sessions, webhooks, and task calls | [DF-01](../data-flows/account-session.md), [DF-06](../data-flows/tasks.md), [DF-07](../data-flows/integrations.md), [DF-08](../data-flows/deployment.md) |
| [A-07](a-07-task-state.md) | Task and webhook records | Keep internal commands and diagnostic payloads controlled | [DF-06](../data-flows/tasks.md), [DF-07](../data-flows/integrations.md) |
| [A-08](a-08-release.md) | Deployed release artifact and control | Preserve the running code and configuration | [DF-08](../data-flows/deployment.md) |

Source paths in each record refer to the repository revision used for this baseline. Cloud IAM and live object permissions still require operational verification; repository configuration alone does not prove current cloud state.
