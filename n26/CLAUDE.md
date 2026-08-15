# CLAUDE.md — the n26 edition

n26 is a new edition of Gyrinx, built alongside the existing app rather than
on top of it. It is mounted at `/n26/`, and every surface carries its own
guard: a page holding player data wants a signed-in reader
(`login_required`, and the row scoped to its owner), while the authoring
pages and the component gallery want staff (`staff_member_required`). There
is no fence over the prefix, so a new view ships open unless it says who may
see it.

## The map

| package | what it holds |
|---|---|
| `n26/library/` | Game content and the tools for writing it: models, authoring verbs, specs, generated forms, spreadsheet ingest, the staff authoring pages. |
| `n26/core/` | Player data (gangs, models, assignments, the money ledger) and the pure-Python layers that turn rows into cards, sheets, and equip listings. |
| `n26/designsystem/` | The living component gallery at `/n26/design/`. Documents the components; owns none of them. |
| `n26/tests/` | Shared fixtures and the sandbox suites — whole slices of real rulebook content built and exercised end to end. |
| `n26/design/` | The specification. These markdown files are where design decisions are recorded and argued. **Not committed — they exist only in the maintainer's checkout.** When present, read the relevant one before a non-trivial change (`glossary.md` defines the shared vocabulary); when absent, module docstrings are the next-best source. Code cites them as `design/foo.md`. |

Each package has its own CLAUDE.md with the detailed rules. This file holds
what is true everywhere.

## Boundaries — what may import what

The dependency direction is: `library` holds content, `core` reads it.
Concretely:

- **No app code in `n26/` imports `n23.*` or `gyrinx.*`.** n26 is a
  parallel edition, not a layer on the old one. Five deliberate
  exceptions: the dashboard reads `gyrinx.site.models.ChangelogEntry`,
  deferred inside the view; the gangs view searches with
  `gyrinx.querysets.search_queryset`; the artwork tag cleans SVG with
  `gyrinx.svg.sanitize_inline_svg`; `n26/analytics.py` records events
  through `gyrinx.analytics`; and `n26/tests/` may import platform
  pieces to test the seam. Do not add others.
- **`n26/analytics.py` is the third platform module n26 may call, and
  the only file allowed to.** Activity tracking is the site's: one
  events table, one log stream, one dashboard, and every question asked
  of them ("how many people did X this week") is asked of the site.
  A second store in this edition would answer none of them and would
  give the two editions incompatible histories. The whole dependency is
  one file — nouns declared, growth-chart lines registered, and
  `record()` — so the seam can be read and moved in one place, and no
  view imports `gyrinx.analytics` itself. The words stay ours: a noun
  belongs to exactly one edition, so a gang here is never filed under
  n23's "list", and the edition of a row follows from its noun with no
  argument for a call site to forget.
- **`gyrinx.querysets` is the first of the two platform modules n26 code
  may call.** It is model-agnostic — full text plus a substring fallback over
  whatever fields it is handed, knowing nothing about either edition,
  in the way the ORM does not. What crosses is a queryset of n26's own
  rows, filtered; nothing platform-shaped comes back. The alternative
  is a second search here, and two editions that quietly come to
  disagree about what "scav" matches. This does not extend to the rest
  of `gyrinx.*`: a helper qualifies only if it would read the same
  written against any model in any edition.
- **`gyrinx.svg` is the second, and the security one.** Sanitising
  stored SVG before drawing it inline is a property of SVG and of the
  browser, not of a content model — it would read the same written
  against any edition's rows, which is the test. It is also the one kind
  of code that must not exist twice: two allowlists drift, and the one
  that drifts loosest is the one an attacker uses. n26 stores artwork
  against a gang type and cleans it through this on the way out
  (`n26/core/templatetags/artwork.py`). The counter-example sits in the
  same directory: `richtext.py` is a *copy* of the platform's rich-text
  sanitiser, so there are already two allowlists to keep in step. Do not
  make a third.
- **Templates may `{% load %}` a platform tag library** where the thing
  it answers is genuinely the platform's and not an edition's — today
  that is `badge_tags`, because which badge a person shows follows from
  their supporter standing and staff flag, which belong to the account
  rather than to either edition. The edition still draws it in its own
  components (`<c-n26.user-link>`); what crosses is the answer, never
  the markup. This is not a licence for Python imports: a tag library
  loaded by name in a template is the whole of the dependency.
- **Templates may `{% url %}` a platform route** on the same test as a
  tag library: the page it leads to must be the account's or the
  site's, not an edition's — today that is `core:account_home`, the one
  account page both editions send a reader to. Writing the path out
  instead is the worse option, not the safer one: a name that stops
  resolving raises on render, while a path that stops existing serves a
  404 in silence for as long as nobody clicks it. What crosses is a
  URL, and only for a page neither edition owns; a route into n23's own
  surfaces does not qualify.
- **`n26/core/models/` never imports `n26.library`.** It names library
  models by label string (`"library.Profile"`). This keeps the model graph
  one-way: core rows point at library rows, never the reverse.
- **Library code imports core logic (`select`, `browse`) only inside
  functions**, never at module level. Only the primitives —
  `n26.core.models` base classes, `n26.core.constraints`,
  `n26.core.fields` — are imported at the top of a file. Break either
  discipline and the app stops booting; nothing enforces it mechanically,
  so it is enforced here.
- **`n26.core` never imports `n26.designsystem`.** The gallery documents
  core; core must not know it exists.
- The platform reaches n26 by string only (settings, one URL include,
  pinned app labels: `n26`, `library`, `designsystem`). App labels are
  what migrations key on — never change them.

## Vocabulary rules

- **The word "cost" is banned.** It blurs two numbers that part company
  at the first discount: a **price** (what a surface asks right now) and
  a **rating** (what a purchase added to the gang's worth, pinned
  forever). A test discovers and rejects offenders in stored fields and
  player-facing structures (`n26/tests/sandbox/test_money_words.py`);
  the ban also applies where the test cannot see — class names, template
  props, sample data.
- **An assignment is never called a "row".** Much of the code and docs
  use "row" for an assignment, which is confusing and should not be
  copied. If referring to an assignment, say assignment.
- The Python class is `Miniature` (to avoid Django's `Model`); every
  user-facing word is "model".
- "Profile" on its own means a hireable fighter entry. A weapon's firing
  line is a `WeaponProfile`.
- Use the words in `n26/design/glossary.md` and `n26/library/concepts.md` —
  the latter is the rendered Core Concepts reference for what each kind
  is. If you need a term that is in neither, that is a design
  conversation, not a naming choice.
- British spelling in prose and our own names (`colour`,
  `Specialisation`); names that mirror CSS or an installed package's API
  keep that spelling (`css_color`, a kit component's `color=` prop).

## Design stances that hold everywhere

- **Inform, never police.** The app says things (as `Note`s on lines and
  cards) and shortens lists; it almost never refuses. Owners may do
  anything. The one hard no is spending past the founding budget.
- **No rules text, ever.** The book's wording is copyrighted. We store
  names, numbers, and behaviour; the player reads the rule in the book.
- **Recompute, never nudge.** Pinned totals (ratings, credits) are
  rewritten by recomputing from the ledger, never adjusted by deltas.
  `n26.core.reconcile` proves the caches honest.
- **Structures before renderers.** Every surface is built as a plain
  dataclass first (a card, a sheet, an equip view, a spec); rendering it is
  a separate, dumber step. Tests assert on the structure.
- **UI state lives in the URL, with one sanctioned exception.** The
  platform rule applies here too: anything that picks a form variant,
  changes what the server renders, or should survive a reload belongs in
  the URL. The exception: Alpine may narrow or reorder content already
  on the page (filtering a table, a sidebar search) — presentation only,
  nothing the server would render differently.
- **A `success` button ends a form; a `primary` button starts one.**
  Green is the commit — Save, Create, Add this thing. A control that
  opens a form or goes to one is `primary`, however creative the thing
  it leads to: "New weapon" at the top of a listing begins the journey
  that "Create weapon" finishes.
- Python 3.14 is required, not just supported — some files use syntax
  that will not parse on older versions.

## Comments

The house style: a comment states a constraint, an invariant, or a
consequence the code cannot show — in plain words, for a reader who does
not know the game. Two good examples of the register:

> The stash is excluded: rating is what the models are worth; stashed
> gear counts in wealth instead.

> Stored effects write rows at assign time — running one here would
> breed pets on every render.

**The rule: a comment must make sense to a reader who has never seen any
earlier version of this code.** That one test rejects everything we do
not want:

- No people ("agreed with Tom", "per review").
- No tickets or PRs ("see #1234", "fixed in PR …").
- No changelog narration ("used to be", "no longer", "exactly as
  before", "ported from v1", dates).
- No disguised TODOs ("for now", "note for later"). If work remains,
  track it outside the code.

Keep comments short. A constraint usually fits in one or two sentences;
if the *reasoning* genuinely needs a paragraph, it belongs in the module
docstring or a `n26/design/` doc, referenced by filename. Citing a
design doc is fine; citing a person, a date, or an issue number is not.

Design docs under `n26/design/` may record who decided what and when —
that is what they are for. Code comments may not. The rule applies to
everything written from here on; a handful of older comments predate it
and may be cleaned when touched.

## Tests

`pytest n26` runs everything. The detailed conventions are in
`n26/tests/CLAUDE.md`; the two rules worth knowing before you get there:

- n26 tests use classes as narrative headings and sentence-length test
  names. This deliberately differs from the platform's "module-level
  functions only" rule; do not "fix" it.
- Never add n26 fixtures to the repo-root conftest, and never create a
  conftest above `n26/tests/` for them: the host repo's root conftest
  defines fixtures with the same names (`make_statline`), and whichever
  file is nearer wins silently. Shared fixtures live in
  `n26/tests/fixtures.py`.
