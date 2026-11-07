# A-04: Uploaded public media

| Metadata | Value |
| --- | --- |
| ID | A-04 |
| Status | Initial baseline |
| Location and owner | N23 uploaded files and attachments, N26 gang/model images, and production GCS default storage |
| Sensitivity | Public by design once stored in the uploads bucket |
| Integrity need | High: browser-served media must remain the intended inert file |
| Availability need | Medium: missing images reduce usability but do not normally erase game records |
| Flows | [DF-05](../data-flows/media.md), [DF-03](../data-flows/shared-reads.md) |
| Evidence | [N23 upload model](../../../n23/core/models/upload.py), [N23 attachment policy](../../../n23/core/models/pack.py), [N26 gang image](../../../n26/core/models/gang.py), [storage settings](../../../gyrinx/storage_settings.py), [bucket setup](../../gcs-cdn-setup.md) |

## What must be protected

User-supplied image and pack attachment bytes and the URLs embedded in pages. Production storage uses the uploads bucket with unsigned URLs; the bucket setup document grants public object read. This makes validation and safe browser rendering important. Public media should not contain private source material; [A-05](a-05-ingest-sheets.md) covers held CSVs separately.

## Security properties

- Confidentiality: None is promised after public storage; warn or separate any upload that requires privacy.
- Integrity: Validate content and extension, constrain active formats, and keep untrusted content out of the site's script origin.
- Availability: Keep media serving and deletion behavior predictable; avoid disproportionate storage or bandwidth use.
