# CLAUDE.md — the n26 edition

n26 is a new edition of Gyrinx, built alongside the existing app rather than
on top of it. It is mounted at `/n26/` and fenced behind the "N26 Testers"
group: staff and members pass, anonymous visitors are sent to log in, and
other signed-in users get a 404 — the beta is invisible, not locked.

## The map

| package | what it holds |
|---|---|
| `n26/library/` | Game content and the tools for writing it: models, authoring verbs, specs, generated forms, spreadsheet ingest, the staff authoring pages. |
| `n26/core/` | Player data (gangs, models, assignments, the money ledger) and the pure-Python layers that turn rows into cards, sheets, and shop listings. |
| `n26/designsystem/` | The living component gallery at `/n26/design/`. Documents the components; owns none of them. |
| `n26/tests/` | Shared fixtures and the sandbox suites — whole slices of real rulebook content built and exercised end to end. |
| `n26/design/` | The specification. These markdown files are where design decisions are recorded and argued. **Not committed — they exist only in the maintainer's checkout.** When present, read the relevant one before a non-trivial change (`glossary.md` defines the shared vocabulary); when absent, module docstrings are the next-best source. Code cites them as `design/foo.md`. |

Each package has its own CLAUDE.md with the detailed rules. This file holds
what is true everywhere.

## Boundaries — what may import what

The dependency direction is: `library` holds content, `core` reads it.
Concretely:

- **No app code in `n26/` imports `n23.*` or `gyrinx.*`.** n26 is a
  parallel edition, not a layer on the old one. Two deliberate
  exceptions: the dashboard reads `gyrinx.site.models.ChangelogEntry`,
  deferred inside the view, and `n26/tests/` may import platform pieces
  to test the seam. Do not add others.
- **Templates may `{% load %}` a platform tag library** where the thing
  it answers is genuinely the platform's and not an edition's — today
  that is `badge_tags`, because which badge a person shows follows from
  their supporter standing and staff flag, which belong to the account
  rather than to either edition. The edition still draws it in its own
  components (`<c-n26.user-link>`); what crosses is the answer, never
  the markup. This is not a licence for Python imports: a tag library
  loaded by name in a template is the whole of the dependency.
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
- The Python class is `Miniature` (to avoid Django's `Model`); every
  user-facing word is "model".
- "Profile" on its own means a hireable fighter entry. A weapon's firing
  line is a `WeaponProfile`.
- Use the words in `n26/design/glossary.md`. If you need a term that is
  not there, that is a design conversation, not a naming choice.
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
  dataclass first (a card, a sheet, a shop view, a spec); rendering it is
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
