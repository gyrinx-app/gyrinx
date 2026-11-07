# DF-04: Staff content authoring and ingest

| Metadata | Value |
| --- | --- |
| ID | DF-04 |
| Status | Reviewed against N26 authoring paths |
| Entry point | /n26/authoring/ and its ingest and staged-content pages |
| Actors | Staff author or session holder ([ADV-04](../adversaries/adv-04-staff-session.md)) |
| Assets | [A-03 content](../assets/a-03-content.md), [A-05 ingest sheets](../assets/a-05-ingest-sheets.md) |
| Trust boundaries | TB-01, TB-02, TB-03, TB-06 |
| Evidence | [Authoring views](../../../n26/library/views.py), [Authoring verbs](../../../n26/library/authoring.py), [Ingest implementation](../../../n26/library/ingest.py), [Staged-content rules](../../../n26/library/staged.py), [Admin MFA gate](../../../gyrinx/admin_site.py) |

## Sequence

~~~mermaid
sequenceDiagram
    actor Author
    participant Browser
    participant App as Staff authoring view
    participant Store as Media storage
    participant DB as PostgreSQL
    Author->>Browser: Edit content or upload CSV
    Browser->>App: Staff request and form; crosses TB-01 and TB-06
    Note over Browser,App: TB-06: staff role grants content-writing authority
    App->>Store: Hold CSV bytes for preview; crosses TB-03
    App->>DB: Read held sheet, plan against library; crosses TB-02
    App-->>Browser: Preview changes; crosses TB-01
    Author->>Browser: Confirm import or put staged row live
    Browser->>App: POST; crosses TB-01 and TB-06
    App->>DB: Atomic import or publication; crosses TB-02
~~~

## Boundaries and controls

| Boundary | From → to | Data and authority crossing | Current control / assumption |
| --- | --- | --- | --- |
| TB-01 | Browser → app | Uploaded files, form fields, row IDs | Django forms and CSRF middleware; ingest validates sheet kind, UTF-8, size and non-empty rows. |
| TB-06 | Staff session → authoring action | Create, change, stage and publish shared content | Authoring views use staff_member_required. The admin-specific current-session MFA gate does not wrap these routes. |
| TB-03 | App → media storage | Held source CSV bytes | UploadedSheet is owner-scoped in DB; storage and URL policy are separate. |
| TB-02 | App → database | Library rows and publication state | Ingest plans current data on each request, performs inside transaction, and records an import event. |

## Failure points

- A staff session without a configured second factor can reach authoring even while the Django admin gate would require one.
- A mistaken or malicious import can change content visible to all players; the preview is a control, but staff authority is broad.
- Held CSVs reside in the default media storage; the repository does not establish whether the deployed bucket/CDN blocks unauthenticated object reads.
- Different staff authors' held rows can share a fixed sheet-type storage key, so one author's upload or cleanup can affect another author's preview and import.
