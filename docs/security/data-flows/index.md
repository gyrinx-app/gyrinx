# Data flows and trust boundaries

| Metadata | Value |
| --- | --- |
| Record type | Mermaid sequence diagrams of security-relevant flows |
| Scope | Production N23 and N26 web application, staff tools, integrations, tasks, and deployment |
| Evidence date | 2026-11-07, repository main at bdce46108 |
| Status | Initial model; deployment configuration outside this repository remains an assumption |
| Boundary notation | TB labels on the crossing arrows and notes in every diagram |

A boundary marks a change in who can control data or issue commands. An internal service call may still cross a boundary when it changes authority, such as a browser becoming an authenticated staff request. These diagrams show representative paths, not every URL.

| ID | Boundary | Security decision |
| --- | --- | --- |
| TB-01 | Visitor or browser → Django application | Host, session, CSRF, form, route, and access checks |
| TB-02 | Django application → PostgreSQL | Query scoping, transactions, persistence, audit rows |
| TB-03 | Application or browser → media storage/CDN | Upload validation, object permissions, public delivery |
| TB-04 | External webhook provider → Django | Provider signature and payload validation |
| TB-05 | Application → Pub/Sub → task push handler | Publisher authority, OIDC audience/service identity, task registry |
| TB-06 | Authenticated staff identity → privileged authoring/admin action | Staff check and, for admin, current-session MFA gate |
| TB-07 | Application or worker → external API/SMTP | Outbound credentials, request contents, provider response |
| TB-08 | GitHub source → Cloud Build | Source and trigger integrity, build identity |
| TB-09 | Cloud Build/Artifact Registry → Cloud Run | Image provenance and deployment authority |
| TB-10 | Cloud Run runtime environment → Django process | Runtime secrets, DB credentials, service identity |

| Flow | Entry point | Main boundary | Record |
| --- | --- | --- | --- |
| DF-01 | Accounts and admin login | TB-01, TB-06 | [Account, session and admin access](account-session.md) |
| DF-02 | N23 and N26 player changes | TB-01, TB-02 | [Player-data writes](player-writes.md) |
| DF-03 | Shared N23 list and N26 gang URLs | TB-01, TB-02 | [Public and shared reads](shared-reads.md) |
| DF-04 | N26 authoring and ingest | TB-06, TB-02 | [Staff content authoring](staff-authoring.md) |
| DF-05 | TinyMCE, pictures, artwork and CSV | TB-01, TB-03 | [Uploads and media delivery](media.md) |
| DF-06 | Task enqueue and Pub/Sub push | TB-05, TB-02 | [Background task delivery](tasks.md) |
| DF-07 | Patreon and Discord hooks | TB-04, TB-07 | [External integrations](integrations.md) |
| DF-08 | Cloud Build and Cloud Run | TB-08, TB-09, TB-10 | [Deployment and runtime configuration](deployment.md) |
