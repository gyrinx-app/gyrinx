# A-01: Account identities and sessions

| Metadata | Value |
| --- | --- |
| ID | A-01 |
| Status | Initial baseline |
| Location and owner | Django auth, allauth, sessions, and UserProfile in the application database |
| Sensitivity | Personal; session credentials are secret |
| Integrity need | High: identity, verified email, staff status, and MFA state determine access |
| Availability need | High: account access is needed to manage gangs and campaigns |
| Flows | [DF-01](../data-flows/account-session.md), [DF-07](../data-flows/integrations.md) |
| Evidence | [account model](../../../gyrinx/accounts/models.py), [auth settings](../../../gyrinx/settings.py), [admin gate](../../../gyrinx/admin_site.py) |

## What must be protected

User accounts, verified email addresses, password and MFA state, active sessions, profile preferences, and Patreon-linked email, member ID, status, and tier. The profile model persists Patreon attributes against a user; allauth owns email verification and login. A session can exercise the account's authority.

## Security properties

- Confidentiality: Keep personal profile data and session material from other users and public responses.
- Integrity: Only authenticated account flows and verified provider events should change identity-linked state; staff privilege and MFA must not be inferred from unverified claims.
- Availability: Users need a working login and recovery path to reach their own data.
