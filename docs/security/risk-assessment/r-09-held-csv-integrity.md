# R-09: Held ingest CSVs share an object key across authors

| Metadata | Value |
| --- | --- |
| ID | R-09 |
| Last reviewed | 2026-11-07 |
| Next review | On material change or by 2027-02-07 |
| Status | Open |
| Related threats | [T-10](../threats/t-10-held-sheet-collision.md) |
| Assets | [A-05](../assets/a-05-ingest-sheets.md), [A-03](../assets/a-03-content.md) |
| Likelihood | Medium |
| Impact | High |
| Priority | High |
| Confidence | High for fixed-key code path; medium for deployed storage behavior |
| Owner | N26 library ingest and held-file lifecycle |
| Tracking issue | [#3136](https://github.com/gyrinx-app/gyrinx/issues/3136) |

## Why this rating

[store_sheet](../../../n26/library/ingest.py) saves each sheet type under the same object name regardless of author. [UploadedSheet](../../../n26/library/models/staging.py) keeps separate database rows, but the default production GCS backend can overwrite an existing object at that key. Two authors working on one sheet type are plausible, and a preview/import can read the wrong bytes. The replacement, discard and direct-delete cleanup paths can also remove a shared object. An unintended import can change content used by many players, making integrity impact high. The live backend configuration and existing references remain unverified.

## Treatment

Give every upload a unique object key. For replacement and deletion, remove an old object only after the transaction commits and only when no UploadedSheet row still references that key. Add regression tests that create two legacy rows pointing to one stored object and exercise replacement, discard and direct deletion. Verify existing production references before cleanup or migration. Private storage for confidentiality is a separate treatment in [R-04](r-04-held-csv.md).
