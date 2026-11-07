# T-10: Held CSV key shared across staff authors

| Metadata | Value |
| --- | --- |
| ID | T-10 |
| STRIDE | Tampering |
| Adversary | [ADV-04: malicious staff session](../adversaries/adv-04-staff-session.md); the event can also be accidental |
| Assets | [A-05: held ingest sheets](../assets/a-05-ingest-sheets.md), [A-03: content catalogue](../assets/a-03-content.md) |
| Data flow / boundary | [DF-04](../data-flows/staff-authoring.md) and [DF-05](../data-flows/media.md); TB-02 and TB-03 |
| Risk | [R-09: held CSV integrity](../risk-assessment/r-09-held-csv-integrity.md) |
| Status | Open; observed fixed object-key design, production storage behavior to confirm |
| Evidence | [sheet storage and discard](../../../n26/library/ingest.py), [UploadedSheet model](../../../n26/library/models/staging.py), [GCS settings](../../../gyrinx/storage_settings.py), [storage dependency](../../../uv.lock) |

## Scenario

Two staff authors upload the same sheet type. Their database rows remain owner-scoped, but store_sheet asks default storage to save both files as ingest-sheets/{sheet}.csv. The installed GCS backend overwrites an existing object at that key by default. One author's preview or import can then read the other's CSV. Replacing or discarding a row can also delete the shared object while another row still refers to it. A mistaken import can alter the published catalogue.

## Existing controls and uncertainty

Authoring routes are staff-only; ingest validates sheet type, size, UTF-8 and rows, and preview precedes import. Those checks do not make a shared object key owner-specific. This model has not inspected live storage settings or historical object references, so it does not assert that a production collision has already happened.
