# T-04: Draft authoring CSV disclosed by public storage

| Metadata | Value |
| --- | --- |
| ID | T-04 |
| Last reviewed | 2026-11-07 |
| Next review | On material change or by 2027-02-07 |
| STRIDE | Information Disclosure |
| Adversary | [ADV-01: anonymous caller](../adversaries/adv-01-anonymous.md) |
| Assets | [A-05: held ingest sheets](../assets/a-05-ingest-sheets.md) |
| Data flow / boundary | [DF-04](../data-flows/staff-authoring.md) and [DF-05](../data-flows/media.md); TB-03 |
| Risk | [R-04: held CSV](../risk-assessment/r-04-held-csv.md) |
| Status | Public-read exposure remains; object names are fixed by sheet type |
| Evidence | [UploadedSheet model](../../../n26/library/models/staging.py), [sheet storage](../../../n26/library/ingest.py), [GCS storage settings](../../../gyrinx/storage_settings.py), [bucket setup](../../gcs-cdn-setup.md) |

## Scenario

A staff author uploads an ingest CSV for preview before publication. UploadedSheet writes it through the same default object store as public media, under ingest-sheets/. The documented bucket setup grants public object read access, and storage URLs are unsigned. A caller who learns or predicts the fixed sheet-type object name can download draft source data without passing the staff-only authoring view.

## Existing controls and uncertainty

Authoring pages and application queries are staff-gated; uploads are capped at 8 MB and scoped to the author in the database. store_sheet uses a fixed name for each sheet kind, so object-name secrecy is weak and these controls do not govern direct object-store reads. The repository documents a public bucket, but this assessment has not queried live IAM policy or existing objects.
