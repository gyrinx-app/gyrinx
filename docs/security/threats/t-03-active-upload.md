# T-03: Active SVG through ordinary player media upload

| Metadata | Value |
| --- | --- |
| ID | T-03 |
| STRIDE | Tampering |
| Adversary | [ADV-02: authenticated player](../adversaries/adv-02-player.md) |
| Assets | [A-04: public uploaded media](../assets/a-04-media.md), [A-01: accounts](../assets/a-01-accounts.md) |
| Data flow / boundary | [DF-05](../data-flows/media.md); TB-01 and TB-03 |
| Risk | [R-03: active media](../risk-assessment/r-03-active-media.md) |
| Status | Mitigated ordinary-player path in this branch |
| Evidence | [TinyMCE upload view](../../../n23/core/views/upload.py), [UploadedFile validation](../../../n23/core/models/upload.py), [GCS storage settings](../../../gyrinx/storage_settings.py), [pack attachment validation](../../../n23/core/models/pack.py) |

## Scenario

Before this branch, a signed-in player could upload an SVG containing active script through the rich-text image endpoint, then share its public media URL. A direct navigation could execute script in the media origin. The direct harm could include convincing branded content, and might extend to site data if origin, cookies, or cross-origin policy were configured permissively. This threat is scoped to the ordinary-player TinyMCE path.

## Existing controls and uncertainty

The endpoint requires login, POST and CSRF, with a 10 MB file limit and 100 MB daily quota. This branch rejects SVG MIME types and executable filename extensions even when a browser claims a raster MIME type, matching the adjacent content-pack attachment guard. Staff-uploaded artwork in [artwork.py](../../../gyrinx/artwork.py) can still store raw SVG and sanitizes it when drawn inline; a direct public media URL may remain an active document. Its staff-only upload authority makes that residual part of staff/media-origin controls rather than this ordinary-player threat. This record does not assume the media origin equals the app origin.
