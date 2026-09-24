# N26 development instructions

N26 is a parallel edition mounted at `/n26/`. Every view must state who may
read it. Player-data actions require a signed-in owner. Authoring and the
component gallery require staff. Gang sheets are shareable, and their available
actions depend on whether the reader owns the gang.

## Instructions by package

- [`library/AGENTS.md`](library/AGENTS.md) — content, authoring, ingest and author documentation.
- [`library/models/AGENTS.md`](library/models/AGENTS.md) — content models and modifiers.
- [`core/AGENTS.md`](core/AGENTS.md) — player-data operations, reads, views and tests.
- [`core/models/AGENTS.md`](core/models/AGENTS.md) — assignments, ledger records and model wiring.
- [`core/templates/AGENTS.md`](core/templates/AGENTS.md) — N26 templates and Cotton components.
- [`frontend/AGENTS.md`](frontend/AGENTS.md) — React island source and dependency rules.
- [`designsystem/AGENTS.md`](designsystem/AGENTS.md) — the component gallery and demos.
- [`tests/AGENTS.md`](tests/AGENTS.md) — shared fixtures and end-to-end sandbox tests.

The untracked `n26/design/` directory contains the maintainer's design notes.
When it is present, read the relevant note before a non-trivial change.
`glossary.md` defines shared vocabulary. Module docstrings are the fallback.

## Import boundaries

`library` owns content and `core` reads it. Do not import `n23.*`. Do not import
`gyrinx.*` from N26 except through these narrow platform seams:

| Seam | Platform dependency | Constraint |
| --- | --- | --- |
| `n26/analytics.py` | `gyrinx.analytics` | Views call the edition seam; they do not import the platform module. |
| `n26/flags.py` | `gyrinx.site.flags` | Declare edition feature slugs here and claim them from `n26/core/apps.py`. |
| `n26/notifications.py` | `gyrinx.site.models` notifications | This is the only N26 file that writes notifications. |
| `n26/impersonation.py` | `gyrinx.impersonation` | Keep the shared session and audit behaviour behind this file. |
| `n26/write_pause.py` | `gyrinx.site.write_pause` | Keep the platform write-pause state behind this file. |
| `n26/maintenance.py` | `gyrinx.maintenance`, `gyrinx.tasks` | Register edition repairs here. Never import `gyrinx.maintenance.admin`. |
| `n26/library/artwork.py` | `gyrinx.artwork` | Bind N26's upload folder here; keep storage-address checks in the platform. |
| `n26/core/templatetags/artwork.py` | `gyrinx.svg` | Use the shared SVG sanitiser rather than another allowlist. |
| `n26/core/templatetags/banner.py` | `gyrinx.site.icons` | Reuse the platform's banner icon set. |
| Gang and campaign search views | `gyrinx.querysets` | Pass N26 querysets through the model-agnostic search helper only. |
| Stateful N26 models and propagation | `gyrinx.state_machine` | Use the shared row-locked transition implementation and exception. |
| `n26/core/views/changelog.py` | `gyrinx.site.models.ChangelogEntry` | Keep the import deferred in the shared queryset helper. |
| `n26/tests/` | Platform test seams | Tests may import platform code to verify integration. |

N26 templates may load a platform tag library or reverse a platform URL only
for account or site concerns. Current examples are supporter badges, account
home, notifications, dice, banners and impersonation. This permission does not
extend to Python imports or N23 routes.

Within N26:

- `n26/core/models/` refers to library models by string labels and never imports
  `n26.library`.
- Library code imports `n26.core.select` and `n26.core.browse` inside functions.
  It may import only core model bases, constraints and fields at module level.
- `n26.core` never imports `n26.designsystem`; the gallery depends on core.
- Platform code refers to N26 through app labels, settings and URL includes.
  Never change the pinned `n26`, `library`, or `designsystem` app labels.

The seam modules and their docstrings explain why each exception exists. Add a
new platform dependency only by creating or extending an explicit seam.

## Vocabulary

- Do not use "cost". Use **price** for what a surface asks now and **rating**
  for the value pinned to the gang when it bought the item. The ban applies to
  code, templates and sample data.
- Call an assignment an assignment, never a row.
- The Python class is `Miniature`; user-facing text says "model".
- "Profile" means a hireable fighter entry. Use `WeaponProfile` for a weapon's
  profile.
- Use `n26/design/glossary.md` and `n26/library/concepts.md`. Discuss any new
  domain term before introducing it.
- Use British spelling in prose and project names. Preserve spelling from CSS
  and external APIs, such as a component's `color=` prop.

## N26-wide design rules

- Every user-facing subhead is human-authored copy: a content field written by
  an author, or an explicit sentence written for interface context. Names may
  supply context; generated modifier prose and assembled labels cannot serve
  as the subhead. Omit it when no useful authored copy exists.
- The gang roster is the model card's frontfat; the fighter Edit page is its
  backfat. On frontfat, show an assignable row only when the model carries an
  assignable in that row or has an offer for it. Always show the statline,
  Skills and Gear. Assignment happens on backfat or a dedicated offer page;
  frontfat presents the model's current facts and may point to an offer.
- Inform rather than police. Restrictions usually become `Note` objects and
  shorter lists. Owners may act freely except that they cannot spend past the
  founding budget.
- Store names, numbers and behaviour, never copyrighted rules text.
- Recompute pinned ratings and credits from the ledger instead of applying
  deltas. `n26.core.reconcile` checks the cached totals.
- Build each display surface as a plain dataclass before rendering it. Tests
  assert on that structure.
- Use React for interactive UI and Cotton for static UI. Load the `n26-react`
  skill before changing an interaction. Do not add Alpine directives.
- Put shareable state in the URL. React may own temporary search, selection,
  focus, open controls and unsaved drafts. Django owns validation, permissions
  and domain operations.
- A `success` button submits a form. A `primary` button opens or starts one.
- Use Python 3.14. Some N26 syntax does not parse on older versions.

## Comments

Comments state a constraint, invariant, or consequence that the code cannot
show. Write for a reader who does not know the game or the change history.

- Do not mention people, tickets, pull requests, dates or earlier behaviour.
- Do not hide future work in "for now" comments; track it outside the code.
- Keep comments to one or two sentences. Put longer reasoning in a module
  docstring or `n26/design/` note and cite the filename.

Design notes may record decisions and history. Code comments may not.

## Tests

Run all edition tests with `pytest n26`. Read [`tests/AGENTS.md`](tests/AGENTS.md)
for the full conventions.

- N26 tests may use classes as narrative headings and sentence-length names.
- Keep shared N26 fixtures in `n26/tests/fixtures.py`. Do not add them to the
  repository root conftest or create a nearer conftest that shadows platform
  fixtures.
