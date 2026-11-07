# R-09: Held ingest CSVs share an object key across authors

| Metadata | Value |
| --- | --- |
| ID | R-09 |
| Last reviewed | 2026-11-07 |
| Next review | On material change or by 2027-02-07 |
| Status | Control implemented; deployment verification pending |
| Related threats | [T-10](../threats/t-10-held-sheet-collision.md) |
| Assets | [A-05](../assets/a-05-ingest-sheets.md), [A-03](../assets/a-03-content.md) |
| Likelihood | Low after fix |
| Impact | High |
| Priority | Medium |
| Confidence | High |
| Owner | N26 library ingest and held-file lifecycle |
| Tracking issue | [#3136](https://github.com/gyrinx-app/gyrinx/issues/3136) |

## Why this rating

Before unique per-upload keys, [store_sheet](../../../n26/library/ingest.py) saved each sheet type under the same object name regardless of author. [UploadedSheet](../../../n26/library/models/staging.py) kept separate database rows, but the production service does not override the pinned GCS backend's overwrite-by-default setting. A read-only review found five UploadedSheet rows, four object keys and one shared-key group; it read no filenames or contents and changed no data. The shared reference does not prove an overwrite, but it confirms that cleanup must preserve legacy objects. An unintended import could change content used by many players, so impact remains high.

## Treatment

Every new upload receives a random 128-bit object key. One shared cleanup path covers replacement, discard, direct deletion and cascades: it runs after commit and deletes only when no UploadedSheet row still references the key. Regression tests keep two legacy rows on one object and prove that the remaining author can still preview or import after the other replaces or discards their row. After deployment, verify distinct new keys and safe legacy cleanup before archiving this record. Private storage for confidentiality remains separate in [R-04](r-04-held-csv.md).
