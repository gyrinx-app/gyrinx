# ADV-01: Anonymous network caller

| Metadata | Value |
| --- | --- |
| ID | ADV-01 |
| Status | Initial baseline |
| Starting access | Public HTTP endpoints and public media URLs; no Gyrinx account |
| Reachable boundaries | TB-01 browser/client to app; TB-03 public media; TB-04 claimed provider input; conditional TB-05 task push |
| Assets sought | [A-01](../assets/a-01-accounts.md), [A-02](../assets/a-02-player-data.md), [A-04](../assets/a-04-media.md), [A-06](../assets/a-06-service-secrets.md), [A-07](../assets/a-07-task-state.md) |
| Evidence / assumption | [URL map](../../../gyrinx/urls.py), [task handler](../../../gyrinx/tasks/views.py), [provider handlers](../../../gyrinx/api/views.py), [public bucket setup](../../gcs-cdn-setup.md) |

## Goals and capabilities

Can automate requests, choose paths and identifiers, submit account-registration input, fetch public pages and media, and send provider-shaped bodies to public webhook paths. Provider signatures and task OIDC are separate checks. A caller who controls an unrelated Google service account may be able to mint an ID token for the public task endpoint audience; that only becomes useful if the expected sender identity is not enforced and the endpoint is reachable.

## Limits

Does not initially own a Gyrinx session, Patreon or Discord signing secret, the configured Pub/Sub sender identity, or cloud deployment credentials. This model does not assume guessing a cryptographically random group key.
