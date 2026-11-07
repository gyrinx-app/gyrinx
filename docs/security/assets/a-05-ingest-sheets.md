# A-05: Held ingest spreadsheets

| Metadata | Value |
| --- | --- |
| ID | A-05 |
| Status | Initial baseline; live bucket permissions unverified |
| Location and owner | UploadedSheet rows in the database and files under ingest-sheets/ in the default storage |
| Sensitivity | Internal pre-publication source data; current documented bucket setup makes objects publicly readable |
| Integrity need | High: preview and import must read the same author's intended bytes |
| Availability need | Medium: authors can re-upload, but a lost file interrupts import |
| Flows | [DF-04](../data-flows/staff-authoring.md), [DF-05](../data-flows/media.md) |
| Evidence | [held sheet model](../../../n26/library/models/staging.py), [store and import path](../../../n26/library/ingest.py), [production storage](../../../gyrinx/settings_prod.py), [bucket setup](../../gcs-cdn-setup.md) |

## What must be protected

Staff-uploaded CSV source files held between preview and import. UploadedSheet is owner-scoped in the database, but its FileField uses the production default GCS storage. store_sheet uses one fixed object name per sheet type, so two authors can have separate rows that point to the same stored file. A later upload can overwrite the bytes another author expects, and cleanup can delete a file another row still references. The documented bucket setup grants public object read to every object, and the application has no separate private storage backend for these files.

## Security properties

- Confidentiality: The CSV bytes should remain limited to the uploading author and authorized staff until deliberate publication. Fixed sheet-type names make direct object lookup easier; storage authorization is still required. Verify live IAM and separate private uploads from public media.
- Integrity: Keep each author's preview and import bound to the same object; the owner-scoped row alone does not protect the shared object key.
- Availability: Retain a held file while any row references it; delete it only after the last reference is gone.
