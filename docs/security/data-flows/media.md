# DF-05: Uploads and media delivery

| Metadata | Value |
| --- | --- |
| ID | DF-05 |
| Status | Reviewed against upload code; deployed bucket policy unverified |
| Entry point | /tinymce/upload/, N26 picture/artwork forms, N26 authoring ingest |
| Actors | Player ([ADV-02](../adversaries/adv-02-player.md)), staff author ([ADV-04](../adversaries/adv-04-staff-session.md)), public reader ([ADV-01](../adversaries/adv-01-anonymous.md)) |
| Assets | [A-04 media](../assets/a-04-media.md), [A-05 ingest sheets](../assets/a-05-ingest-sheets.md) |
| Trust boundaries | TB-01, TB-02, TB-03 |
| Evidence | [TinyMCE upload view](../../../n23/core/views/upload.py), [UploadedFile validation](../../../n23/core/models/upload.py), [N26 picture conversion](../../../n26/core/images.py), [Artwork storage/lookup](../../../gyrinx/artwork.py), [Held sheets](../../../n26/library/models/staging.py), [sheet storage](../../../n26/library/ingest.py), [Production storage settings](../../../gyrinx/storage_settings.py) |

## Sequence

~~~mermaid
sequenceDiagram
    actor Uploader
    actor Reader
    participant Browser
    participant App as Django upload view
    participant DB as PostgreSQL
    participant Media as GCS or CDN
    Uploader->>Browser: Choose raster image, artwork SVG, or authoring CSV
    Browser->>App: Multipart POST, crossing TB-01
    Note over Browser,App: TB-01: filename, MIME claim and bytes are client-controlled
    App->>App: Validate quota/type/size or transform picture
    App->>Media: Save object, crossing TB-03
    App->>DB: Store owner and object name, crossing TB-02
    App-->>Browser: Object address, crossing TB-01
    Reader->>Media: GET object address, crossing TB-03
    Note over Reader,Media: TB-03: media serving is outside Django's owner checks
    Media-->>Reader: Object bytes
~~~

## Boundaries and controls

| Boundary | From → to | Data and authority crossing | Current control / assumption |
| --- | --- | --- | --- |
| TB-01 | Browser → app | File bytes, filename, content-type header | TinyMCE requires login/POST/CSRF, applies per-file and daily quotas, and allows only raster MIME types and filename extensions. Its MIME claim still comes from the client header or filename guess. N26 pictures are decoded, cropped and re-encoded as JPEG. Artwork uploads require small UTF-8 SVG; inline rendering sanitises the SVG. |
| TB-03 | App → storage; reader → storage/CDN | Uploaded object becomes a URL-served asset | Production uses GCS; MEDIA_URL points to CDN or direct bucket, querystring_auth=False, and public cache headers. External bucket/CDN access policy is not in this repo. |
| TB-02 | App → database | Owner, filename, content type, held-sheet path | UploadedFile tracks owner and quota. UploadedSheet is limited to one sheet per staff author and sheet kind, but store_sheet uses the same object key for every author of a sheet kind. |

## Failure points

- TinyMCE rejects SVG MIME types and non-raster filename extensions. Its remaining MIME claim is client-controlled, and this path does not decode raster bytes before storage; serving headers and media-origin policy still matter.
- A direct media URL bypasses application permission checks. Held ingest CSVs use fixed sheet-type object names in the same storage backend as public media; whether a direct URL can be read anonymously needs deployment verification.
- Two staff authors can save the same sheet-type object key; an overwrite or cleanup can change or remove bytes another author's row still references.
- The quota check and save are separate operations, so concurrent uploads may exceed a daily allowance.
