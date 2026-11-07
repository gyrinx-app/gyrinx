# R-04: Held ingest CSV is stored with public media

| Metadata | Value |
| --- | --- |
| ID | R-04 |
| Status | Open; predictable-key and overwrite paths mitigated in this PR |
| Related threats | [T-04](../threats/t-04-held-sheet-disclosure.md) |
| Assets | [A-05](../assets/a-05-ingest-sheets.md) |
| Likelihood | Medium |
| Impact | Medium |
| Priority | Medium |
| Confidence | High for storage design; medium for current live bucket policy |
| Owner | N26 library ingest and media infrastructure |

## Why this rating

[UploadedSheet](../../../n26/library/models/staging.py) uses the default file storage. [Production storage settings](../../../gyrinx/storage_settings.py) put that storage in the media bucket with unsigned URLs, and the [bucket setup](../../gcs-cdn-setup.md) describes public object reads. Staff-only authoring routes do not gate a direct object request. An attacker still needs the URL or object name after this PR's UUID-suffixed filenames; a URL may appear in logs, copied links, or operational tooling. Draft source files are internal, but the record does not assume they contain credentials or personal data.

## Treatment

Use a separate private bucket or equivalent storage backend for held CSVs, with access mediated by staff authorization. Verify deployed bucket IAM and direct unauthenticated access with a synthetic object. This PR changes [store_sheet](../../../n26/library/ingest.py) to generate a unique, unpredictable key for each upload, preventing the previous same-name overwrite and making guessing harder. Random names reduce exposure but are not access control. Assess and migrate existing held objects when private storage is introduced.
