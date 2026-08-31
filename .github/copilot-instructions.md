# Gyrinx — repository instructions

Gyrinx is a Django app for managing Necromunda gangs and campaigns. Server-rendered
HTML with Bootstrap 5 and a little vanilla JS. There is no SPA, no client-side
framework and no JS build step. Python 3.12, Postgres, deployed to Cloud Run.

## What matters most in review

**UI state belongs in the URL.** Anything that picks a form variant, switches a
visible section or selects a tab is a navigation: a link or a GET form pointing at
the same view, with the state in the query string, rendered by the server. JS may
enhance, but the page must work and be linkable without it. Flag any
`addEventListener('change', …)` that rewrites a form, hides fields or alters
validation — that is the pattern this codebase deliberately does not use.

**Use the components, don't hand-write Bootstrap.** UI primitives live as
django-cotton components in `gyrinx/templates/cotton/` and are invoked like
`<c-btn variant="primary">Save</c-btn>`. New or edited templates should use them
rather than repeating class strings. See `.github/instructions/templates.instructions.md`
for the specifics.

**Security.** Never apply `|safe` to user-supplied content — the project ships a
`safe_rich_text` filter for sanitising. Always validate redirect targets from user
input with `safe_redirect` / `get_return_url` (`gyrinx/http.py`).

**Microcopy is plain, explicit, and invisible.** The canonical rules are in
`.agents/skills/microcopy/SKILL.md`. The human-written marketing sections
(the signed-out landing pitch on the homepage) are exempt — that is the
maintainer's voice, not microcopy. For any new or changed user-facing string
(template text, button labels, form labels/help text, `messages.*`, emails,
admin screens), flag:

- "successfully", trailing exclamation marks, "Get started", "Ready to…",
  marketing adjectives ("powerful", "seamless", "robust") — success messages
  state the fact ("Battle recorded."), refusals state the rule ("Only the
  campaign owner can edit this battle.").
- Cleverness of any kind: personification (the app, the rules, or a number
  never asks, knows, refuses, or sells), negation riddles ("the rules know no
  other Type" — say "Type is Fighter or Vehicle."), quaint vocabulary
  ("nought", "had already gone"), and compression the reader must decode.
  Plain and slightly wordy beats short and clever.
- Title Case in labels — sentence case throughout, domain nouns lowercase
  ("Add gang", not "Add Gang"); only true proper nouns capitalised.
- Banned words in product copy: "cost" in n26 (price vs rating), "row" for an
  assignment, "shelf"/"shop"/"till", a collection that "sells" its contents
  (it contains them), "pressed" (say clicked), "obligation"/"debt", "answer"
  (pick = option groups and choose = offers-a-choice are reserved verbs;
  select is the skills verb and also fine generally — skills are never
  "learned"), "please", emoji.

**The fighter list is the hot query path.** Adding a FK or M2M to `ListFighter`
means updating `ListFighterQuerySet.with_related_data()` and the query-count
snapshot at `n23/core/tests/fixtures/performance_view_queries.json`. Missing a
prefetch degrades silently in dev and only shows up under load.

**Content packs: archive is a soft-delete for the *owner*, not a retraction.** Once
a list or campaign subscribes to a pack, archived items in it must stay visible to
that subscriber. Subscriber read paths must not filter `archived=False`; pass
`include_archived_items=True` to `ContentQuerySet.with_packs()`. Owner-side
library, gallery and picker views should filter it out.

**Models and tests.** Core models inherit `AppBase` (UUID pk, owner, archive,
history); content models inherit `Content`. Never call `self.full_clean()` from
`save()`. Tests are module-level pytest functions with `@pytest.mark.django_db` —
no `TestCase` — and should use the fixtures in `gyrinx/conftest.py` rather than
building users, houses, fighters or lists inline.

**Don't commit generated CSS.** `n23/core/static/core/css/` is built from SCSS.

## Long-term projects

These are directions the codebase is actively moving in. Reviews should push work
towards them, and flag changes that move against them — even when the change is
otherwise fine.

### Adopting the cotton component library

The four core UI families (buttons, badges, callouts, form fields) exist as
components, and roughly 290 call sites use them — but about 800 hand-written
Bootstrap sites remain, including the fighter-card stack, the equipment pickers and
`core/layouts/base.html`. The direction is to keep converting them.

What to look for:

- **New hand-written markup is a regression.** `scripts/check_raw_markup.py` holds a
  per-pattern ceiling in `scripts/raw_markup_baseline.json` and fails if it rises.
  If a diff adds raw `btn btn-*`, `badge text-bg-*`, `alert alert-*` or a
  `border rounded` box, ask for the component instead.
- **Opportunistic conversion is welcome.** A template being edited for another
  reason is a good moment to move its markup onto components. Not required, but
  worth suggesting.
- **The remaining hot paths need care, not avoidance.** Fighter cards render many
  times per page and are shared between screen and print, so conversions there
  should come with a look at render cost — but "it's the hot path" is not a reason
  to leave it hand-written forever.
- **`linked-*` over `link-*`.** Bootstrap's `.link-*` is underlined at rest; the
  project's `.linked-*` family underlines on hover/focus only. New links should use
  `linked-*`.

### Design-system documentation

`docs/DESIGN-SYSTEM.md` is the written spec and `/_debug/design-system/` is the
living reference that renders the real components. They should agree. The markdown
still lacks canonical sections for badges, back links and form-field anatomy
(issue #2002) — worth filling in when touching those areas.

## Conventions worth knowing

- Django management commands run via `manage`, not `python manage.py`.
- Conventional-commit prefixes on commits and PR titles (`feat:`, `fix:`,
  `refactor:`, `docs:`, `test:`, `chore:`, `perf:`, `style:`). Titles must also
  name the thing that changed — see [COMMIT_STYLE.md](COMMIT_STYLE.md). Flag any
  title that opens with an article or "what" plus a generic noun ("the sweep", "a
  question"), or that names nothing you could grep for.
- Mobile-first; design at 375px and enhance upwards. Dense over spacious.
- Colour signals state, never decoration.
- Avoid `alert` classes for neutral grouped content — use a bordered box. Bootstrap
  `card` is reserved for fighter grids and equipment categories.
- Never put machine-local paths (`/Users/…`, `~/`) in commits, PRs or committed
  docs.
