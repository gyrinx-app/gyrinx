# R-04: Held ingest CSV is stored with public media

| Metadata | Value |
| --- | --- |
| ID | R-04 |
| Last reviewed | 2026-11-07 |
| Next review | On material change or by 2027-02-07 |
| Status | Open |
| Related threats | [T-04](../threats/t-04-held-sheet-disclosure.md) |
| Assets | [A-05](../assets/a-05-ingest-sheets.md) |
| Likelihood | Medium |
| Impact | Medium |
| Priority | Medium |
| Confidence | High for storage design; medium for current live bucket policy |
| Owner | N26 library ingest and media infrastructure |

## Why this rating

[UploadedSheet](../../../n26/library/models/staging.py) uses the default file storage. [Production storage settings](../../../gyrinx/storage_settings.py) put that storage in the media bucket with unsigned URLs, and the [bucket setup](../../gcs-cdn-setup.md) describes public object reads. Staff-only authoring routes do not gate a direct object request. [store_sheet](../../../n26/library/ingest.py) uses a fixed name for each sheet kind, so an object key can be predicted. Draft source files are internal, but this record does not assume they contain credentials or personal data. The live bucket policy has not been queried.

## Treatment

Use a separate private bucket or equivalent storage backend for held CSVs, with access mediated by staff authorization. Verify deployed bucket IAM and direct unauthenticated access with a synthetic object. Give new objects unpredictable names as a secondary defense, while addressing the separate integrity risk in [R-09](r-09-held-csv-integrity.md). Assess existing objects before migration.
