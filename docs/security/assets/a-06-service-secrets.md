# A-06: Service secrets and identities

| Metadata | Value |
| --- | --- |
| ID | A-06 |
| Status | Initial baseline |
| Location and owner | Production environment and cloud IAM; read by Django settings and integration handlers |
| Sensitivity | Secret |
| Integrity need | High: wrong keys or service identities change who can submit trusted requests |
| Availability need | High: loss or misconfiguration breaks auth, mail, tasks, or integrations |
| Flows | [DF-01](../data-flows/account-session.md), [DF-06](../data-flows/tasks.md), [DF-07](../data-flows/integrations.md), [DF-08](../data-flows/deployment.md) |
| Evidence | [base settings](../../../gyrinx/settings.py), [production settings](../../../gyrinx/settings_prod.py), [Patreon and Discord handlers](../../../gyrinx/api/views.py), [task OIDC check](../../../gyrinx/tasks/views.py) |

## What must be protected

Django SECRET_KEY; SMTP credentials; Patreon webhook secret; Discord bot token and verification key; GitHub dispatch token; Cloud Run, Pub/Sub, database, and GCS service identities. These values bridge the application to systems that trust its signatures, tokens, and permissions. This record covers the authority they grant, not each individual environment variable as a separate asset.

## Security properties

- Confidentiality: Keep signing and API credentials out of public responses, repository files, and task/status output.
- Integrity: Bind provider requests and task pushes to the expected sender; make missing required identity configuration fail closed.
- Availability: Rotate compromised values without prolonged loss of login, mail, storage, or tasks.
