# DF-01: Account, session and admin access

| Metadata | Value |
| --- | --- |
| ID | DF-01 |
| Status | Reviewed against repository code |
| Entry point | /accounts/ and /admin/ |
| Actors | Visitor ([ADV-01](../adversaries/adv-01-anonymous.md)), account holder ([ADV-02](../adversaries/adv-02-player.md)), staff-session holder ([ADV-04](../adversaries/adv-04-staff-session.md)) |
| Assets | [A-01 accounts](../assets/a-01-accounts.md), [A-06 service secrets](../assets/a-06-service-secrets.md) |
| Trust boundaries | TB-01, TB-02, TB-06, TB-07 |
| Evidence | [URL routing](../../../gyrinx/urls.py), [authentication settings](../../../gyrinx/settings.py), [admin gate](../../../gyrinx/admin_site.py), [production cookie settings](../../../gyrinx/settings_prod.py) |

## Sequence

~~~mermaid
sequenceDiagram
    actor Person
    participant Browser
    participant App as Django and allauth
    participant DB as PostgreSQL
    participant Mail as SMTP provider
    Person->>Browser: Sign up, verify email, or sign in
    Browser->>App: Form and session cookie, crossing TB-01
    Note over Browser,App: TB-01: untrusted client becomes an authenticated request only after validation
    App->>DB: Read identity and session, crossing TB-02
    App->>Mail: Send verification or reset email, crossing TB-07
    App-->>Browser: Set session cookie and next step, crossing TB-01
    Person->>Browser: Open admin URL
    Browser->>App: Admin request, crossing TB-01 and TB-06
    Note over Browser,App: TB-06: staff role plus current-session MFA required for Django admin
    App->>DB: Check staff and MFA state, crossing TB-02
    App-->>Browser: Admin page or allauth MFA redirect
~~~

## Boundaries and controls

| Boundary | From → to | Data and authority crossing | Current control / assumption |
| --- | --- | --- | --- |
| TB-01 | Browser → app | Credentials, cookies, CSRF tokens, return URL | Session/auth/CSRF middleware; production secure session and CSRF cookies. Allauth handles login and mandatory email verification. |
| TB-02 | App → database | Account, email verification, session and MFA state | Django authentication backends and allauth models. |
| TB-06 | Staff session → admin | Privileged admin reads and writes | Admin login redirects to allauth; admin and admindocs require staff plus current-session MFA when ADMIN_REQUIRE_MFA is enabled (default in production). |
| TB-07 | App → SMTP | Verification and reset messages | Production SMTP settings are environment supplied; provider controls delivery. |

## Failure points

- A stolen session can act with its holder's authority until invalidated. Admin's current-session MFA gate narrows privileged use.
- The custom admin MFA gate does not wrap the separate N26 authoring URLs; see [DF-04](staff-authoring.md).
