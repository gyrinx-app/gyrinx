# T-04: Draft authoring CSV disclosed by public storage

| Metadata | Value |
| --- | --- |
| ID | T-04 |
| STRIDE | Information Disclosure |
| Adversary | [ADV-01: anonymous caller](../adversaries/adv-01-anonymous.md) |
| Assets | [A-05: held ingest sheets](../assets/a-05-ingest-sheets.md) |
| Data flow / boundary | [DF-04](../data-flows/staff-authoring.md) and [DF-05](../data-flows/media.md); TB-03 |
| Risk | [R-04: held CSV](../risk-assessment/r-04-held-csv.md) |
| Status | Public-read exposure remains; predictable names and cross-author collisions mitigated in this branch |
| Evidence | [UploadedSheet model](../../../n26/library/models/staging.py), [sheet storage](../../../n26/library/ingest.py), [GCS storage settings](../../../gyrinx/storage_settings.py), [bucket setup](../../gcs-cdn-setup.md) |

## Scenario

A staff author uploads an ingest CSV for preview before publication. UploadedSheet writes it through the same default object store as public media, under ingest-sheets/. The documented bucket setup grants public object read access, and storage URLs are unsigned. A caller who learns an object's URL can download draft source data without passing the staff-only authoring view.

## Existing controls and uncertainty

Authoring pages and application queries are staff-gated; uploads are capped at 8 MB and scoped to the author in the database. This branch gives each upload a UUID-suffixed object name, avoiding predictable first names and cross-author overwrite of a shared key. Object-name secrecy is not an access-control mechanism, and those controls do not govern direct object-store reads. The repository documents a public bucket, but this assessment has not queried live IAM policy or existing objects.
