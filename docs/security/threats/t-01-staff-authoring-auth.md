# T-01: Password-only staff access to N26 authoring

| Metadata | Value |
| --- | --- |
| ID | T-01 |
| Last reviewed | 2026-11-07 |
| Next review | On material change or by 2027-02-07 |
| STRIDE | Spoofing |
| Adversary | [ADV-04: compromised staff identity](../adversaries/adv-04-staff-session.md) |
| Assets | [A-01: accounts](../assets/a-01-accounts.md), [A-03: content catalogue](../assets/a-03-content.md) |
| Data flow / boundary | [DF-01](../data-flows/account-session.md) and [DF-04](../data-flows/staff-authoring.md); TB-01 and TB-06 |
| Risk | [R-01: staff MFA](../risk-assessment/r-01-staff-mfa.md) |
| Status | Observed gate difference; production impact depends on staff account policy |
| Evidence | [admin_site.py](../../../gyrinx/admin_site.py), [settings.py](../../../gyrinx/settings.py), [N26 authoring views](../../../n26/library/views.py), [N26 routes](../../../n26/urls.py) |

## Scenario

An attacker obtains a staff password for an account without an enrolled second factor. Allauth can create an ordinary staff session. The Django admin requires MFA enrollment and a challenged session, but the N26 authoring routes use Django's staff-only decorator and sit outside the admin gate. The attacker can reach content authoring and publication functions with that password-only session. A malicious catalogue update can affect all players using the published content.

## Existing controls and uncertainty

The admin login redirects to allauth, and GyrinxAdminSite checks the current session's MFA record. N26 authoring checks that the user is active and staff; Django CSRF protection still applies to writes. The repository does not establish whether every production staff account independently has MFA enrolled, so this is a demonstrated difference in gates rather than proof of a compromised account.
