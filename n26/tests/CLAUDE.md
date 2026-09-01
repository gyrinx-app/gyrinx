# CLAUDE.md — n26 tests

Three tiers, split by the kind of claim a test makes — not by which
module changed:

- **Colocated** (`n26/core/test_*.py`, `n26/library/test_*.py`, and
  each app's `tests.py`) — unit tests of one module's contract: field
  defaults, constraints, pure functions. If it would still be true with
  no gang, no fighter, and no rulebook, it belongs here.
- **`n26/tests/`** — the seam with the host platform. The only tests
  allowed to import from outside `n26.*` (the dashboard, the shell, the
  badges an account carries into either edition).
- **`n26/tests/sandbox/`** — the bulk of the suite. Each file builds a
  slice of real rulebook content from scratch with the authoring verbs,
  founds a gang, plays with it, and asserts on the player-facing
  structures. Sandbox files are executable design documents; many cite
  the `n26/design/` note they prove.

## The verbs

`n26/tests/sandbox/actions.py` is the test-facing vocabulary:

- Library-side verbs are re-exports of `n26.library.authoring` — the
  real, shipped authoring API. Use the authoring names in new tests
  (`ef_adds`, `targets_model(has_subtypes(x))`, `attach_to=`); the old
  sandbox aliases exist only so existing suites read as written.
- Player-side wrappers (`found_gang`, `hire`, `give_weapon`, `buy`,
  `choose`, `tally`, `move`, `refund`, …) wrap their writes in an
  `operation(...)` block. They default the actor to the gang's owner;
  the real API deliberately does not.

**Prefer the verbs over the ORM.** Reach for `objects.create` in a
sandbox test only where no verb covers the wiring — and check first,
because verbs have grown to cover ground older tests built by hand.
`test_content_authoring.py` alone uses the raw ORM throughout,
deliberately: its docstring says it is the reference for what an ingest
or the admin really does.

## Fixtures

- Shared fixtures live in **`n26/tests/fixtures.py`** — an importable
  module, not a conftest. Each test-bearing tree has a one-line
  conftest doing `from n26.tests.fixtures import *`. **Never add n26
  fixtures to the repo-root conftest, and never flatten these into a
  higher conftest**: the host repo's root conftest defines fixtures
  with the same names (`make_statline`), and the nearer file wins
  silently.
- `fixtures.py` stays small. File-local fixtures composing the verbs
  are the norm — a sandbox file typically defines ten or so of its own.
- Content shapes go in module-level data tables (a `GRID`, an
  `ARCHETYPES` dict) that fixtures loop over. Importing another file's
  table is fine.
- The platform's fixtures (`content_fighter`, `make_list`, …) are the
  other edition's models — never use them in n26 tests. Make users
  inline with `User.objects.create_user(...)`.
- Request `default_pack` in content-creating tests so the pack exists
  before counting anything.

## Conventions

- `pytestmark = pytest.mark.django_db` at module level, right after the
  imports — or per-test decorators in files whose collection-time
  discovery must stay database-free. Fixtures that need the database
  request `db`.
- Tests are grouped in bare classes used as narrative headings
  (`TestFoundingTheGang`), each with a docstring stating the contract.
  Test names are full sentences:
  `test_the_house_list_arrives_without_anyone_assigning_it`. This
  deliberately differs from the platform's module-level-functions rule;
  do not "fix" it.
- Drive domain behaviour through the verbs; drive view behaviour
  through the test client with real URLs and full POST payloads
  (including formset management data).
- **No golden files.** Two patterns instead: pinned literal tables
  ("pinned so it changes deliberately"), and print-the-text then assert
  on a few load-bearing substrings. Pick substrings the page can only
  contain if the behaviour worked — a test here once passed because a
  stylesheet happened to contain the word "complete".
- End any test that spends money with `assert_reconciled(gang)`.
- For query counts, prefer asserting the count stays the same after
  adding more fighters; a pinned literal count is acceptable for one
  structure's fixed budget.
- **Discovering guards, not lists.** A guard test for a rule that must
  hold for every X discovers the Xs by reflection, pairs with a
  `test_there_is_something_to_check`, and fails with a message saying
  what to do. `test_money_words.py` is the template. Never narrow a guard's
  discovery to make a failure go away.
- Discovery used in `parametrize` runs at collection time — keep it
  import-safe, no database access.
- Tests run with `--nomigrations`, so data migrations never ran: any row
  a data migration would have created exists only if a test creates it.
- Tests name rules by their titles only — never the book's wording.

## Exemplars

- `test_escher_gang.py` — the canonical full-shape sandbox suite.
- `test_budget.py` — the best small suite: one rule, four tests, 74
  lines.
- `test_gang_sheet.py` — one structure, one contract; asserts the plan
  shows a scope was *skipped*, not merely that nothing happened.
- `test_money_words.py` — the discovering-guard template.
- `n26/core/test_printing.py` — the colocated exemplar: no database at
  all.

## Comments

A comment states why the rule is the rule, in the domain's own words,
for a reader who has never seen any earlier version of this code — so
no people, no tickets or PRs, no dates, no changelog narration. Citing
a `n26/design/` doc by filename is the right way to point at deeper
reasoning. Regression tests describe the bug by what a player saw, in a
sentence or two, not by its history.
