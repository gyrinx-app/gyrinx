# Database design inputs

These inputs preserve the design discussed in the independent editor workspace, so the prototype remains reproducible after application components change.

- `templates/` contains only the 14 N26/Cotton templates and a minimal page-width fragment used to render the database page, navigation, grouped model body, statline headers/cells, sections and controls. They were captured from the pinned 8 October 2026 source archive, with the page-width fragment and missing gear wrapper from that workspace's existing checkout. The source archive SHA-256 is `3ad0d4f386c75dd29e62e20971fab90d44edd9ec5816926d3aca19aba709f2a7`.
- `n26.css` and `cotton-ui.sources.css` retain that design's actual theme inputs. Paths and source scans are local, root theme selectors target the shadow host, and the unrelated print import is omitted.
- `style-provenance.json` records the original sandbox card/callout stylesheet hashes and the retained subset sizes. `src/cards.css` is the focused, editable derivative of the New style model cards; it drops roster actions, photos/uploads, tabs and unrelated callout layouts.
- `public/classic-blank.jpg` is Gyrinx's existing classic blank artwork. `public/logo.svg` is the same Gyrinx mark used by the local campaign prototype.

These are Apache-2.0 Gyrinx design inputs. Third-party Cotton implementations remain dependencies pinned in `requirements.txt`; their source is not copied here. `prepare.py` renders the reference templates and records their paths and hashes in the generated presentation tree. Browser checks reject stale template hashes.

Refresh captured templates deliberately with `GYRINX_SOURCE` and optional `GYRINX_FALLBACK_SOURCE` pointing at the desired Gyrinx source, then run `prepare.py --capture-reference`. Existing reference files take precedence; replace a selected input explicitly before regenerating it. Review resulting visual changes rather than silently synchronising from another branch. Ordinary rebuilds need no access to the original workspace.
