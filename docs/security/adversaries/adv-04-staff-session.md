# ADV-04: Compromised staff session

| Metadata | Value |
| --- | --- |
| ID | ADV-04 |
| Status | Initial baseline |
| Starting access | A stolen active staff session or a staff account used maliciously |
| Reachable boundaries | TB-01 staff routes; TB-02 library and admin writes; TB-03 uploads; TB-06 staff authority |
| Assets sought | [A-01](../assets/a-01-accounts.md), [A-03](../assets/a-03-content.md), [A-05](../assets/a-05-ingest-sheets.md), [A-07](../assets/a-07-task-state.md) |
| Evidence / assumption | [authoring decorators](../../../n26/library/views.py), [admin MFA gate](../../../gyrinx/admin_site.py), [impersonation route](../../../gyrinx/views_impersonation.py) |

## Goals and capabilities

Can reach staff-only N26 authoring and ingest pages and change shared content. If the account also has Django admin permissions, admin views and data become reachable subject to the admin MFA gate. A superuser can start an impersonation overlay under separate checks.

## Limits

A stolen staff cookie does not automatically grant cloud IAM or repository deployment access. The admin MFA gate checks this session; the staff authoring decorators use staff status, so the same MFA requirement is not established for those routes by the cited code.
