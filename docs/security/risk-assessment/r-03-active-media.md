# R-03: Active document uploaded through TinyMCE

| Metadata | Value |
| --- | --- |
| ID | R-03 |
| Last reviewed | 2026-11-07 |
| Next review | On deployment verification or by 2027-02-07 |
| Status | Verification pending after code change in this PR |
| Related threats | [T-03](../threats/t-03-active-upload.md) |
| Assets | [A-04](../assets/a-04-media.md), [A-01](../assets/a-01-accounts.md) |
| Likelihood | Low after fix |
| Impact | Medium |
| Priority | Low after fix |
| Confidence | High |
| Owner | N23 TinyMCE upload and media storage |

## Why this rating

The previous [UploadedFile validation](../../../n23/core/models/upload.py) allowed SVG and relied on the browser-supplied content type. The public media origin could serve an SVG as an active document. The direct impact is unsafe content on the media origin; impact on the application origin depends on deployed origin and cookie policy, so this model does not assume application-session theft.

## Treatment

This PR removes SVG from the accepted MIME types and rejects non-raster filename extensions, including a spoofed SVG or HTML name with a raster MIME claim. [Upload tests](../../../n23/core/tests/test_upload.py) cover those paths and ordinary PNG upload. Existing TinyMCE SVG objects, if any, are outside this code change; inventory them before declaring historical media clean. Staff artwork still accepts raw SVG for storage and sanitizes it when drawn inline, so direct media URLs and origin isolation require separate review. That staff-only path is part of the privileged-authoring boundary in R-01, not a claim that player uploads remain open. Raw raster bytes are not decoded by this validation, so media response headers also remain useful defense in depth.
