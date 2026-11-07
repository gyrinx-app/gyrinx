# T-10: Held CSV key shared across staff authors

| Metadata | Value |
| --- | --- |
| ID | T-10 |
| Last reviewed | 2026-11-07 |
| Next review | On material change or by 2027-02-07 |
| STRIDE | Tampering |
| Adversary | [ADV-04: malicious staff session](../adversaries/adv-04-staff-session.md); the event can also be accidental |
| Assets | [A-05: held ingest sheets](../assets/a-05-ingest-sheets.md), [A-03: content catalogue](../assets/a-03-content.md) |
| Data flow / boundary | [DF-04](../data-flows/staff-authoring.md) and [DF-05](../data-flows/media.md); TB-02 and TB-03 |
| Risk | [R-09: held CSV integrity](../risk-assessment/r-09-held-csv-integrity.md) |
| Status | Mitigation in PR; deployment and legacy-reference verification pending |
| Evidence | [sheet storage and discard](../../../n26/library/ingest.py), [UploadedSheet model](../../../n26/library/models/staging.py), [GCS settings](../../../gyrinx/storage_settings.py), [storage dependency](../../../uv.lock) |

## Scenario

Before this branch, two staff authors uploading the same sheet type received owner-scoped database rows but the same storage key. The deployed service does not override the installed GCS backend's overwrite-by-default setting, so one upload could change the bytes another author's preview or import would read. Replacement or deletion could also remove the shared object while another row still referred to it. A mistaken import could alter the published catalogue.

## Existing controls and uncertainty

Authoring routes are staff-only; ingest validates sheet type, size, UTF-8 and rows, and preview precedes import. This branch gives each new upload a cryptographically random key. Replacement, discard, direct deletion and cascade deletion schedule cleanup after commit and delete only when no UploadedSheet row still names the object.

A read-only production review on 2026-11-07 found five UploadedSheet rows, four distinct object keys and one shared-key group. It inspected no filenames or contents and changed no data. The shared reference confirms that compatibility is required, but it does not establish that the stored bytes were overwritten. Keep this threat active until deployment verifies distinct new keys and safe legacy cleanup.
