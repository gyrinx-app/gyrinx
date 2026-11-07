# R-01: Staff authoring does not share the admin MFA gate

| Metadata | Value |
| --- | --- |
| ID | R-01 |
| Status | Open |
| Related threats | [T-01](../threats/t-01-staff-authoring-auth.md) |
| Assets | [A-01](../assets/a-01-accounts.md), [A-03](../assets/a-03-content.md) |
| Likelihood | Medium |
| Impact | High |
| Priority | High |
| Confidence | High for the code-path difference; medium for production account exposure |
| Owner | Account access and N26 library authoring |

## Why this rating

[N26 authoring views](../../../n26/library/views.py) use staff checks, while [GyrinxAdminSite](../../../gyrinx/admin_site.py) checks current-session MFA for admin and admin documentation. A staff password-only session can therefore pass the N26 route's code-level check without passing the admin gate. A password compromise is plausible; whether every production staff user already enrolls MFA is not established by this repository. Published content affects many players, so unauthorized authoring has high integrity impact.

## Treatment

Require current-session MFA on N26 authoring and ingest routes, using the admin gate's policy and challenge flow. Add tests for a staff user with and without a challenged session, and confirm the production staff enrollment policy. Staff checks and CSRF remain useful but do not supply a second factor.
