# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Documentation Guidelines

- **`.claude/notes/`** - Internal documentation and plans created by Claude to help with its work
- **`docs/`** - Documentation for humans (user guides, API docs, etc.)
- When creating analysis documents, optimization plans, or working notes, place them in `.claude/notes/`
- Only create user-facing documentation in `docs/` when explicitly requested

## Quick Reference (Most Important)

**Critical Commands:**

- Start dev server: `./scripts/dev.sh` (starts Django + CSS watch, per-worktree isolation)
- Format code: `./scripts/fmt.sh`
- Run tests: `pytest -n auto`
- Django commands: Use `manage` (not `python manage.py`)
- Production shell: `manage prodshell` (read-only access to production database)
- Don't commit CSS files - they're auto-generated from SCSS
- The virtualenv is auto-activated for every Bash command by a `SessionStart` hook
  (`scripts/activate_venv_hook.sh`) that persists `.venv` into `CLAUDE_ENV_FILE`.
  There is no need to prefix commands with `. .venv/bin/activate &&`.
- The session hook also sets `DB_NAME` and `DJANGO_PORT` per-worktree — `manage` and `pytest`
  automatically target the correct database.
- **Codex local worktrees:** configure `.codex/setup.sh` as the local-environment setup script.
  Codex shell commands do not inherit Claude's `CLAUDE_ENV_FILE`, so run direct Python/Django
  commands through `.codex/run.sh` (for example, `.codex/run.sh pytest` or
  `.codex/run.sh manage check`). The existing `scripts/dev.sh` and `scripts/fmt.sh` activate the
  worktree environment themselves.

**Key Principles:**

- Server-rendered HTML, not SPA
- **URL-driven UI state.** Any state that picks a form variant, switches a
  visible section, opens a modal, or selects a tab belongs in the URL
  (path or query string). The server renders the right variant. JS may
  enhance (live preview, async validation, autocomplete) but the page MUST
  work — and be linkable — without it. **Do not** mutate forms client-side
  to swap fields, swap mode choices, hide/show sections, or alter
  validation. If you reach for `addEventListener('change', …)` to rewrite
  a form, you've probably skipped a navigation. See the rationale and the
  full rule in `.claude/skills/gyrinx-conventions/SKILL.md`.
- **Use the cotton components, don't hand-write Bootstrap.** UI primitives live in
  `gyrinx/templates/cotton/` and are invoked as HTML tags:
  `<c-btn variant="primary" size="sm">Edit</c-btn>`, `<c-badge state="injured">`,
  `<c-callout variant="danger">`, `<c-form.field :field="form.name" />`. New and
  edited templates should use them. `scripts/check_raw_markup.py` holds a ceiling on
  hand-written markup and fails if it rises. See
  [n23/core/templates/CLAUDE.md](n23/core/templates/CLAUDE.md) for the call-site
  traps — several of them fail *silently*.
- Mobile-first design
- **Microcopy: load the `microcopy` skill before writing any user- or
  author-facing string** (template text, labels, help_text, `messages.*`,
  emails, admin screens). Plain, explicit, one-pass comprehension; no
  cleverness, no personification, no marketing-speak. The skill
  (`.agents/skills/microcopy/SKILL.md`) is the canonical home of the word
  bans. A warn-only hook (`scripts/check_microcopy.py`) flags the greppable
  subset after each edit; the **copywriter** agent does the full pass.
- Look up model definitions before use - don't assume field names
- Always validate redirect URLs with `safe_redirect`

## Long-term Projects

Directions the codebase is actively moving in. Push work towards them, and say
something when a change moves against them — even if the change is otherwise fine.

**Adopting the cotton component library.** The four core families (buttons, badges,
callouts, form fields) are built and ~290 call sites use them, but ~800 hand-written
Bootstrap sites remain — the fighter-card stack, the equipment pickers and
`core/layouts/base.html` among them. Keep converting:

- Adding raw markup for a pattern a component already covers is a regression. The
  `check-raw-markup` hook enforces the ceiling.
- Converting nearby markup while editing a template for another reason is welcome.
- The remaining hot paths (fighter cards render many times per page and are shared
  between screen and print) need conversions done with an eye on render cost — but
  being a hot path is not a reason to leave them hand-written forever.
- Prefer the project's `.linked-*` link classes over Bootstrap's `.link-*`, which is
  underlined at rest.

**Design-system documentation.** `docs/DESIGN-SYSTEM.md` (the spec) and
`/_debug/design-system/` (the living reference, which renders the real components)
should agree. The markdown still lacks canonical sections for badges, back links and
form-field anatomy — issue #2002.

## Infrastructure

- All our infra is in GCP europe-west2 (London)
- In prod, the bucket for user uploads is gyrinx-app-bootstrap-uploads

## Local Development (Per-Worktree Isolation)

Each git worktree gets its own Postgres database and Django port, started with a single command.

- **Setup (once per machine):** `./scripts/setup-local-postgres.sh` — installs Postgres 16 + pgAdmin via Homebrew,
  migrates data from Docker
- **Start dev server:** `./scripts/dev.sh` — ensures DB exists (forks from template if needed), provisions a
  per-worktree `.venv` on first run in a child worktree, runs migrations, runs `npm install` if
  `node_modules` is missing/stale, does an initial `npm run css` build if `styles.css` is missing/stale,
  then starts Django runserver + npm watch. **Always confirm the `CSS ready:` / `CSS file:` lines appear
  in the startup output — `npm run watch` alone never produces an initial build, so without `dev.sh`
  doing the seed build you'd get unstyled pages.**
- **Reset a worktree DB:** `./scripts/dev.sh --reset-db` — drops and re-forks from template
- **Rebuild a worktree's venv:** `./scripts/dev.sh --reset-venv` — wipes and re-provisions `${WT_ROOT}/.venv`
- **Clean up orphans:** `./scripts/cleanup-worktree-dbs.sh` — drops orphan DBs + reports worktree `.venv` sizes

**How it works:**

- Main worktree uses `gyrinx_main` database (port 8000) — this is the template with curated test data
- Child worktrees get `gyrinx_wt_{hash}` databases forked via `CREATE DATABASE ... TEMPLATE`
- Ports are deterministic per worktree path (range 8100-9599)
- **Template edits apply on the next request — no restart.** Django's `cached.Loader` is
  taken back out of the chain that django-cotton's autoconfig builds (`CACHE_TEMPLATES` in
  `settings_dev.py`, `gyrinx/cotton_dev.py`). Production and the test suite keep it. If
  template edits ever stop showing again, that is the first thing to check — a template-only
  edit touches no `.py` file, so the autoreloader will not save you.
- **Each child worktree gets its own `.venv` with `gyrinx` editable-installed from that worktree**, so
  `import gyrinx` always resolves to worktree-local code (new migrations, new models, etc.). Without this,
  `manage migrate` from a child worktree silently misses new migrations and `pytest` fails with
  `ImportError`. `./scripts/dev.sh` provisions the venv via `uv sync --locked` on
  first run (~1 minute). Main worktree continues to use whatever venv it already had.
- The session hook (`activate_venv_hook.sh`) auto-sets `DB_NAME` and `DJANGO_PORT` for every
  Claude Code Bash invocation
- `setup-local-postgres.sh` appends a block to `.venv/bin/activate` so that
  `source .venv/bin/activate` from any interactive terminal also exports the
  per-worktree DB env vars. **Re-activate the venv after switching worktrees**
  — the hook reads `git rev-parse --show-toplevel` at activation time, not on
  every command. Without this, `pytest` and `manage` from a plain shell fall
  back to `settings.py` defaults (user=postgres) and fail with
  "role postgres does not exist".
- `setup-local-postgres.sh` also tunes `max_locks_per_transaction = 256` in
  the local cluster (the default 64 is too low for pytest-xdist with 12
  workers each running syncdb in parallel — symptom is "out of shared memory").
- pgAdmin 4 (local app) connects to localhost:5432 and is pre-registered with
  a "Gyrinx (local)" server on first setup (CLI-imported into pgAdmin's
  SQLite config at `~/.pgadmin/pgadmin4.db`)

## Agents, Skills, and Commands

This repo has custom agents, skills, and slash commands in `.claude/`. Use them proactively at the right points
in the workflow.

### Agents (`.claude/agents/`)

- **feature-planner** — Use before starting any non-trivial feature or bug fix. Produces a work breakdown, testing
  strategy, and risk assessment. Loads `gyrinx-conventions` automatically.
- **code-simplifier** — Use for architecture review, code review, or refactoring analysis. Applies four analytical
  lenses (simplify, unify, abstract, boundaries). Loads `gyrinx-conventions` and `code-analysis-lenses`.
- **diataxis-docs-expert** — Use when creating or auditing documentation. Follows the Diataxis framework.
- **code-explorer** — Deeply analyzes existing codebase features by tracing execution paths, mapping architecture
  layers, and documenting dependencies.
- **code-architect** — Designs feature architectures by analyzing existing patterns and providing implementation
  blueprints with component designs, data flows, and build sequences.
- **copywriter** — Reviews and rewrites user-facing strings in a diff against the microcopy rules. Run it
  proactively after any task that added or changed such strings, and as a pre-push step on UI PRs.
- **code-reviewer** — Reviews code for bugs, security vulnerabilities, and convention adherence using confidence-based
  filtering (only reports high-confidence issues).

### Slash Commands (`.claude/commands/`)

- `/manual-test-plan [notes]` — Generate a manual test plan for recent changes, formatted for Claude for Chrome.
  Run after implementing a feature to create a browser-testable checklist.
- `/gissue <path>` — Create a GitHub issue from an analysis file (e.g., from `.claude/notes/`), uploading the full
  analysis to a gist and creating a summary issue.
- `/trace-playbook <trace-file>` — Run the full trace performance analysis playbook on a Google Cloud Trace JSON file.
- `/feature-dev [description]` — Guided 7-phase feature development workflow: discovery, codebase exploration,
  clarifying questions, architecture design, implementation, quality review, and summary. Uses `code-explorer`,
  `code-architect`, and `code-reviewer` agents.

### Skills (`.claude/skills/`)

Skills are loaded automatically by agents that need them. They can also be referenced directly:

- **gyrinx-conventions** — Canonical architectural patterns for the project (views, handlers, models, templates, tests)
- **microcopy** — Rules for user- and author-facing strings: the credo, base rules, anti-patterns, and the
  canonical word-ban list. Load before writing or editing any such string.
- **code-analysis-lenses** — Four structured lenses for evaluating code quality
- **edit-github-discussion** — Workflow for editing GitHub Discussions via GraphQL API
- **trace-analysis** — Guide for analyzing OpenTelemetry trace files
- **pr-comments** — Fetch all PR comments, reviews, and review threads in a single GraphQL call. Shows
  resolved/unresolved status, groups by file, and summarises action items. Auto-detects PR from current branch.
  Claude loads this automatically when it needs PR feedback data.
- **pr-feedback** — Review PR feedback from reviewers and Copilot, triage each comment
  (implement / acknowledge / decline), plan changes, and implement approved fixes. Invoke with
  `/pr-feedback [PR number or URL]`. Uses the `pr-comments` fetch script for data.
- **dev-server** — Knowledge about starting/stopping the dev server, reading ports, telling Claude in Chrome
  where to point, log file locations, **and how to mint a session cookie for the browser**. Do not POST
  `/accounts/login/` from an agent session; reCAPTCHA and mandatory email verification block it.
- **worktree-db** — Knowledge about per-worktree database isolation: forking, resetting, migrating, cleanup,
  template workflow, pgAdmin access

## Browser automation

Only use ONE of Chrome DevTools MCP or Claude in Chrome MCP in a session — they cannot work together. Prefer Claude in Chrome for browser testing.

### Logging in locally

The allauth form at `/accounts/login/` is not a reliable way in for an agent.
`LoginForm` always carries reCAPTCHA v3 (`gyrinx/account_forms.py`); computer-use
and curl cannot complete it, and tests only pass because they mock
`django_recaptcha.fields.ReCaptchaField.validate`. Email verification is
`mandatory`, and `manage ensuresuperuser` does not create a verified
`EmailAddress`. `/admin/login/` redirects into the same form.

Cloud Agent install (`.cursor/install.sh`) runs `setupenv` but not
`ensuresuperuser`, so the database may have no users at all. Do not guess
usernames (`tom`, `admin`) or passwords from `.env`.

Mint a session instead. From the repo root, with the venv active:

```bash
python <<'PY'
import os, django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "gyrinx.settings_dev")
django.setup()
from django.conf import settings
from django.contrib.auth import get_user_model
from django.test import Client
from allauth.account.models import EmailAddress

User = get_user_model()
username = os.environ.get("AGENT_LOGIN_AS", "agent")
email = f"{username}@localhost"
u, created = User.objects.get_or_create(
    username=username,
    defaults={"email": email, "is_staff": True, "is_superuser": True},
)
if created:
    u.set_password("password")
u.is_staff = True
u.is_superuser = True
if not u.email:
    u.email = email
u.save()
EmailAddress.objects.get_or_create(
    user=u, email=u.email, defaults={"verified": True, "primary": True},
)
client = Client()
client.force_login(u)
cookie = client.cookies[settings.SESSION_COOKIE_NAME]
print(f"{settings.SESSION_COOKIE_NAME}={cookie.value}")
print(f"user={u.username}")
PY
```

The cookie name is `gyrinx_sessionid_<DJANGO_PORT>` (see `settings_dev.py`), not
`sessionid`. Setting the default name is a silent no-op.

**curl:** `curl -b "$COOKIE" http://localhost:8000/n26/`

**Browser / computer-use:** open any `http://localhost:<port>/` page so the
origin is right, then in the console:

```js
document.cookie = "gyrinx_sessionid_8000=<value>; path=/";
```

Use the name the snippet printed. Navigate to the page under test. n26's gallery
(`/n26/design/`) and authoring screens are `staff_member_required`; the snippet
sets `is_staff`. To use an existing account that already owns gangs, run the
same snippet with `AGENT_LOGIN_AS=<username>` — `force_login` does not need
their password.

This is the same cookie `scripts/screenshot.py` mints. The full SOP lives in
`.claude/skills/dev-server/SKILL.md`.

## Long sessions

If you have the Pushpush MCP installed, you can use it to notify the user that you need their input. The tool is `send_push`. Use the `claude` topic.

IMPORTANT: Use this when you are about to pause to get input, or about to use `AskUserQuestion`.

## Summarising Work

When reporting completed work to the maintainer (chat summaries, PR descriptions),
write for a tech lead reading cold, not a changelog:

- Lead with what changed and why it matters, in plain language.
- Describe bugs by their user-visible effect ("buying an add-on for an item with a
  fixed price made the add-on's value vanish from the books"), then the mechanism
  only if it earns its place.
- Avoid internal shorthand (test-group codes, harness jargon, fixture names) — or
  explain it inline the first time it appears. This means *explain the term*, not
  *avoid naming the thing*: always name the page, model, command or setting you
  are talking about.
- End with concrete "how to try it" steps (URLs, commands) when there is something
  to see.

Keep the fully technical version for commit messages and code comments.

**Commit and PR titles have their own rules — see
[.github/COMMIT_STYLE.md](.github/COMMIT_STYLE.md).** Read that file rather than
copying the phrasing of recent commits; the log has drifted before. Note that the
noun bans in [.agents/skills/microcopy/SKILL.md](.agents/skills/microcopy/SKILL.md)
(no "shelf", no "shop", no "row" for an assignment, and others)
govern product copy, UI strings and identifiers — they do not apply to commit
titles, which should freely name model classes, functions and flags.

## Critical Workflow

### Before Starting

1. Create a new branch for the task: `git checkout -b issue-NAME`
2. **Start the dev server** (`./scripts/dev.sh`) near the start of any coding session —
   don't wait to be asked. Share the URL (per-worktree port, printed in the startup
   banner) so changes can be tested in the browser as they land.
   If the page needs a signed-in user, **mint a session cookie** — do not submit
   `/accounts/login/`. See **Logging in locally** below, or load the `dev-server` skill.
3. **Label the issue (Claude Code on the Web only):** If working on a GitHub issue in a Claude Code for Web session
   (`CLAUDE_CODE_REMOTE=true`), label it so the team knows it's being handled:
   `gh issue edit <NUMBER> --add-label claude-code-web`
   The label definition is created automatically by `scripts/setup_web.sh` during session start; you still need to add this label to the issue manually.
4. For non-trivial features or bug fixes, use the **feature-planner** agent to create an implementation plan before
   writing code

### Before Push

1. Format code: `./scripts/fmt.sh`
2. Run tests: `pytest -n auto`
3. Fix any failing tests
4. Consider running the **code-simplifier** agent on changed files for a quality check
5. If the diff added or changed user-facing strings, run the **copywriter** agent
   over it (also run it proactively right after finishing UI work — don't wait
   for push time)
6. Commit and push changes

- Manually test changes through the running app (dev server + browser) before
  shipping — skip only when the change is trivial
- **Always smoke-test a migration, backfill, or any data-touching feature on a
  real database before shipping it.** Fork the content mirror
  (`createdb -T gyrinx_main gyrinx_smoke`), build a population at production's
  measured volume — read the counts off `manage prodshell` first rather than
  guessing them — run the real code path, and time it. Then verify from
  *outside* the change: compare every affected record yourself, before and
  after, instead of trusting whatever the feature checks internally. Tests
  prove the logic on a handful of rows; this is what catches the volume, the
  runtime, and the data shapes nobody thought to write a fixture for.

**In CI/GitHub Actions:** MUST commit and push before finishing or work is lost.

## Development Commands

**Django:** Use `manage` command (not `python manage.py`)

### Environment Setup

```bash
# Setup virtual environment and install dependencies
uv sync --locked

# Setup environment file
manage setupenv

# Install frontend dependencies and setup node in venv
nodeenv -p
npm install

# Install pre-commit hooks
pre-commit install
```

**Note:** In Claude Code on the Web environments, `setup_web.sh` runs automatically on session
start and configures PostgreSQL directly. Use `pytest` and `manage` directly — there's no
Docker layer to go through.

### Running the Application

```bash
# Start everything — handles DB, migrations, runserver, CSS watch
./scripts/dev.sh
```

### Testing

```bash
# Run full test suite (thin wrapper over pytest; tests use local Postgres)
./scripts/test.sh

# Run tests with pytest-watcher for continuous testing
ptw .

# Run specific test
pytest n23/core/tests/test_models_core.py::test_basic_list

# Run tests with pytest directly
pytest

# Run tests in parallel using pytest-xdist (significant performance improvement)
pytest -n auto  # Uses all CPU cores
pytest -n 4     # Uses 4 workers

# Collect static files before running tests (required for templates with static assets)
manage collectstatic --noinput
```

**IMPORTANT for Claude:** `pyproject.toml` addopts already includes `-n auto --nomigrations`.
The test DB is rebuilt from models on every run (via `--nomigrations` syncdb), so schema
changes are picked up automatically — no `--create-db` or `--migrations` flag needed.
If you want to reuse the test DB across runs for speed, pass `--reuse-db` explicitly —
but be aware that `--reuse-db` combined with `--nomigrations` does NOT detect schema
staleness, so you'll need a one-off `--create-db` run after changing a model.

- When debugging with print output, run `pytest -n 0 -s <test>` — the default `-n auto`
  (pytest-xdist) swallows `-s`/print output in workers.
- CI gates pull requests on `pytest -m core` plus the tests the PR touched; the full suite
  runs but does not block. Mark a file `core` only for fundamental behaviour, a critical
  flow, or a safety/performance check. See `docs/developing-gyrinx/testing.md`.
- **The Postgres cluster is shared by every agent on this machine.** Per-worktree `DB_NAME`
  isolates data, not the cluster's lock table: two `-n auto` runs at once exhaust it and
  *both* fail on every test with `out of shared memory`. Before a full run, check
  `board who` — an agent with ⚙ has a run live — and use `pytest -n 4` while anyone else
  is testing (the board's PreToolUse guard refuses a full run once while another is live).
- A killed xdist run leaves `test_<DB_NAME>_gw<N>` databases behind; the next run then
  fails on every test with `already exists` / `being accessed by other users`. List them
  with `psql -l | grep test_` and drop them, or run `./scripts/cleanup-worktree-dbs.sh`.

### Frontend Development

```bash
# Build CSS from SCSS
npm run css

# Lint CSS
npm run css-lint

# Format JavaScript
npm run js-fmt

# Watch for changes and rebuild CSS
npm run watch
```

DO NOT commit CSS files. They are generated from SCSS automatically.

### Database Operations

```bash
# Create migration for model changes
manage makemigrations core -n "descriptive_migration_name"
manage makemigrations content -n "descriptive_migration_name"

# Create empty migration for data migration
manage makemigrations --empty content

# Apply migrations
manage migrate

# Check for migration issues
./scripts/check_migrations.sh

# Enable SQL debugging (set in .env)
SQL_DEBUG=True
```

### Production Database Access

```bash
# Open interactive read-only shell connected to production database
manage prodshell

# Query production data by piping Python code
echo 'print(User.objects.count())' | manage prodshell
echo 'print(List.objects.filter(archived=False).count())' | manage prodshell
```

- Piped code runs through IPython, which echoes the output of multi-line `for` loops unreliably — use a
  single expression per query (e.g. `print([...comprehension...])`) and read results off
  the `In [N]:` lines.

**Important:** Read-only mode is enforced — all write operations raise `RuntimeError`.

There are two ways in, and `prodshell` picks between them automatically:

- **On a workstation** (`--auth=gcloud`): signs in as you and reads the application's own database
  credentials. Requires the `gcloud` CLI, `cloud-sql-proxy`, and both `gcloud auth login` and
  `gcloud auth application-default login`.
- **On a cloud agent** (`--auth=iam`): uses the agent's federated credentials to connect as
  a dedicated role the database grants `SELECT` and nothing else. No `gcloud`, no
  password, and no key on disk — the agent mints a five-minute token and exchanges it. Chosen
  automatically when `GOOGLE_APPLICATION_CREDENTIALS` names an `external_account` config.

Under `iam` the read-only guarantee is the database's, not just this command's, so it holds for
anything else that connects as that role too.

- **One-off production data repairs run as a Backfill, not a management command.** The app runs on
  Cloud Run, so `manage` can't be pointed at production and `prodshell` is read-only — a repair
  written as a command has no way to be run. Put the logic in a module, add a `Backfill.Operation`
  choice (`n23/core/models/backfill.py`), and trigger it from the maintenance admin
  (`gyrinx/maintenance/admin.py`): GET previews a dry run, POST applies and records a `Backfill`
  row holding the outcome.
- **The work itself MUST run on the tasks framework — never in the request.** POST enqueues a task
  and redirects to the record; the task does the work and writes the outcome onto it. This holds
  however small the repair looks: a request that does the work holds a worker and a database
  transaction for its whole duration, dies at the request timeout with no record of how far it got,
  and gives whoever triggered it a spinning tab instead of a page they can leave and come back to.
  "It only takes a few seconds on my machine" is measured against a copy, not against production
  under load. Follow `convert_specialisation` in `n26/maintenance.py`: a `@task` that takes the
  record's id, an advisory lock so a redelivered message exits without running rather than running twice, an
  attempt count so a run too large to finish is noticed instead of repeating forever, and every
  ending — done, refused, broken — written onto the record rather than raised. Long repairs that
  cannot finish in one go re-enqueue themselves in chunks (`n23/core/tasks.py`), reporting progress
  into the same record.

## Key Models Reference

**Content App (Game Data):**

- `ContentFighter` - Fighter templates
- `ContentEquipment` - Equipment/weapons
- `ContentWeaponProfile` - Weapon stats
- `ContentFighterDefaultAssignment` - Default equipment on fighters
- `ContentEquipmentUpgrade` - Equipment upgrades

**Core App (User Data):**

- `List` - User's gang/list
- `ListFighter` - User's fighters
- `ListFighterEquipmentAssignment` - Equipment assigned to fighters
- `VirtualListFighterEquipmentAssignment` - Wrapper for assignments

## Architecture Overview

### Django Apps Structure

**Main Apps:**

- `content` - Game data models (ContentFighter, ContentEquipment, etc.)
- `core` - User lists/gangs (List, ListFighter, ListFighterEquipmentAssignment)
- `pages` - Static content
- `api` - Webhook handling

### Base Model Architecture

- **`AppBase`** - Abstract base model for all app models, provides:
  - UUID primary key (from `Base`)
  - Owner tracking (from `Owned`)
  - Archive functionality (from `Archived`)
  - History tracking with user information (from `HistoryMixin`)
  - History-aware manager for better user tracking
- All models inherit from `AppBase` to get consistent behavior
- Models already define `history = HistoricalRecords()` for SimpleHistory integration
- **Never call `self.full_clean()` from `save()`.** This is a Django anti-pattern: it duplicates work the form layer
  already does, runs validation queries on every write (including bulk operations and migrations), can fail in
  surprising ways for partially-loaded instances, and conflates form-level validation with persistence. Use form
  validation, `clean()` invoked explicitly where needed, or database constraints instead. A few legacy models still
  do this — do not copy the pattern, and prefer to remove it when touching those files.

### Key Model Relationships

- Content models (ContentFighter, ContentEquipment) → Templates for user data
- Core models (ListFighter, ListFighterEquipmentAssignment) → User-created content
- VirtualListFighterEquipmentAssignment → Wrapper for both default and direct assignments
- All models use django-simple-history for tracking changes

### Technical Principles

- **Not an SPA**: Server-rendered HTML with form submissions, not React/API
- **Mobile-first**: Design for mobile, scale up to desktop
- **Make it work; make it right; make it fast**: Ship functionality first, optimize later
- **Security**: Always validate return URLs using `safe_redirect` when accepting redirect URLs from user input to
  prevent open redirect vulnerabilities

### Domain Rules

#### Content packs: archive semantics

`archived` on `CustomContentPack` and `CustomContentPackItem` is a **pack-owner soft-delete**. It hides the pack/item
from the owner's pack admin/editor and prevents new subscribers from picking it up — but it does **not** retract
content from lists/gangs already subscribed.

Once a list or campaign holds a pack in its `packs` M2M, every item in that pack stays visible to that list — even
items where `archived=True`, and even if the whole pack has been archived. This applies to fighters, equipment,
default assignments, weapon profiles, accessories, skills, rules, psyker disciplines, psyker powers, and any other
pack-aware content.

**Rules of thumb when querying packs / pack items:**

- **Subscriber read paths** (anything driven by `list.packs` or `campaign.packs`) MUST NOT filter `archived=False` on
  `CustomContentPack` or `CustomContentPackItem`. This applies to both directions: the M2M lookup that finds *which*
  packs a list/campaign is subscribed to (e.g. `CustomContentPack.objects.filter(subscribed_lists__id=...)`), and the
  pack-item lookup that resolves content within those packs. The canonical join is `ContentQuerySet.with_packs(packs,
  include_archived_items=True)` in `n23/content/models/base.py` — subscriber paths **must** pass
  `include_archived_items=True`; the default excludes archived items so owner-side callers don't surface them.
- **Pack-owner library views, gallery / featured listings, list-creation pack pickers, and campaign pack-add UIs** —
  these are pack-discovery / write paths. Filtering `archived=False` is correct here so archived packs don't appear
  as new options. For `with_packs([pack])` calls on owner-side, leave the default — archived items stay hidden.
- **Form validation and unique-constraint lookups** — also fine to filter `archived=False`; the unique constraint on
  `CustomContentPackItem` is conditional on `archived=False` and code that looks up the "live" item must match.

If you find a place where archived pack content is being hidden from subscribers, treat it as a bug (see #1742).

### Settings Configuration

- `settings.py` - Production defaults
- `settings_dev.py` - Development overrides
- `settings_prod.py` - Production-specific config
- Environment variables loaded from `.env` file

### Frontend Stack

- Bootstrap 5 for UI components
- SCSS compiled to CSS via npm scripts
- No JavaScript framework - vanilla JS where needed
- Django templates with custom template tags

### Deployment

- Google Cloud Platform (Cloud Run + Cloud SQL PostgreSQL)
- Automatic deployment via Cloud Build on main branch pushes
- WhiteNoise for static file serving
- Docker containerized application

### Content Management

- Content is managed through Django admin interface

### Template Patterns

- Use `{% extends "core/layouts/base.html" %}` for full-page layouts
- Use `{% extends "core/layouts/page.html" %}` for simple content pages
- Back buttons use `{% include "core/includes/back.html" with url=target_url text="Back Text" %}`
- Work "mobile-first" with responsive design
- Left-align templates: typically `col-12 col-xl-6` works well
- User content should use `|safe` filter for HTML rendering
- Templates follow Bootstrap 5 patterns with cards, alerts, and responsive utilities

### UI Patterns

**Button Classes:**

- Primary: `btn btn-primary btn-sm`
- Secondary: `btn btn-secondary btn-sm`
- Danger: `btn btn-danger btn-sm`
- Link style: `link-secondary link-underline-opacity-25 link-underline-opacity-100-hover`

**Layout:**

- Headers: `<h2 class="mb-0">`
- Metadata: `text-secondary` with icons
- Avoid `alert` classes - use `border rounded p-2` instead
- Cards only for fighters in grids

### URL Patterns

- List views: plural noun (e.g., `/campaigns/`, `/lists/`)
- Detail views: singular noun with ID (e.g., `/campaign/<id>`, `/list/<id>`)
- Action views: noun-verb pattern (e.g., `/list/<id>/edit`, `/fighter/<id>/archive`)

### Testing Patterns

- Tests use pytest with `@pytest.mark.django_db` decorator
- Test functions at module level, not in classes
- Do not use Django's TestCase or SimpleTestCase - use plain pytest functions
- Use Django test client for view testing
- Static files must be collected before running tests that render templates
- The conftest.py configures tests to use StaticFilesStorage to avoid manifest issues

**IMPORTANT: Use existing fixtures from `gyrinx/conftest.py`.** Read the conftest before writing tests. Do not
manually create users, houses, fighters, campaigns, or lists inline when a fixture or factory already exists.

Key fixtures:

- `user` - creates user "testuser" with password "password"
- `make_user(username, password)` - factory for additional users
- `client` - Django test client (from pytest-django, use with `client.login()` or `client.force_login(user)`)
- `content_house` - a ContentHouse
- `content_fighter` - a ContentFighter with full statline
- `make_content_fighter(type, category, house, base_cost, **kwargs)` - factory for custom fighters
- `campaign` - an IN_PROGRESS campaign owned by `user`
- `make_campaign(name, **kwargs)` - factory for campaigns
- `make_list(name, **kwargs)` - factory for lists (owned by `user`, uses `content_house`)
- `make_list_fighter(list_, name, **kwargs)` - factory for fighters
- `list_with_campaign` - a list in CAMPAIGN_MODE with associated campaign
- `house` - backward-compat alias, creates a separate ContentHouse (prefer `content_house`)
- `task_queue` - puts the local task backend in `manual` mode to chaos-test background tasks
  (script redelivery / transient failure / message drop and assert idempotency). Background tasks
  otherwise run inline (eager mode) in tests. See `gyrinx/tasks/CLAUDE.md`.

When tests need multiple distinct users (e.g. campaign owner vs list owner), use `make_user` for the extra users
and override the `owner` kwarg on the factory fixtures.

- When seeding demo/test users locally (via `manage shell`, not pytest fixtures), also give each one a verified,
  primary allauth `EmailAddress` so they can log in without hitting email-verification gates. Set `user.email`,
  then `EmailAddress.objects.get_or_create(user=u, email=u.email, defaults={"verified": True, "primary": True})`.

### Security

- Run `bandit -c pyproject.toml -r .` to check for security issues in Python code
- The pre-commmit hooks also check for secrets in the codebase

### Git Workflow

- Before `git pull`, check the index; if the tree is dirty, set the changes
  aside first and restore them after. Prefer a temporary WIP commit — the
  stash stack is shared across worktrees (see the worktree stash rules) —
  and reach for `git stash` only in a plain single checkout.
- This keeps `CLAUDE.local.md` up to date across pulls.
- When writing PR descriptions, keep it simple and avoid "selling the feature" in the PR
- At the end of work, ship with the `commit-push-pr` skill — open the PR ready for
  review (not a draft) so bot reviews and the review-agent watcher kick off
  immediately. Only use `commit-push-draft` when a draft is explicitly requested.
- **Stacked PRs are a GitHub built-in — use `gh stack`, never hand-roll one.**
  Do not chain PRs by pointing one's base at another's branch and managing the
  merges yourself: merging the parent with `--delete-branch` removes the child's
  base branch, and GitHub then *closes* the child rather than retargeting it —
  and a closed PR whose base is gone cannot be reopened.
- Use conventional commit prefixes for commit messages and PR titles:
  - `feat:` — new feature or capability
  - `fix:` — bug fix
  - `refactor:` — code restructuring with no behaviour change
  - `docs:` — documentation only
  - `test:` — adding or updating tests
  - `chore:` — maintenance, dependencies, CI, tooling
  - `perf:` — performance improvement
  - `style:` — formatting, whitespace (no logic change)

## Common File Locations

**Models:**

- `n23/content/models/` - Game content models
- `n23/core/models/list/` - User list/fighter models
- `n23/core/models/campaign.py` - Campaign models

**Views:**

- `n23/core/views/list/` - List/fighter views
- `n23/core/views/campaign/` - Campaign views
- `n23/core/views/vehicle.py` - Vehicle flow

**Templates:**

- `n23/core/templates/core/` - Main templates
- `n23/core/templates/core/includes/` - Reusable components

**Tests:**

- `n23/core/tests/` - Core app tests
- `n23/content/tests/` - Content app tests

## important-instruction-reminders

- Do what has been asked; nothing more, nothing less.
- NEVER create files unless they're absolutely necessary for achieving your goal.
- ALWAYS prefer editing an existing file to creating a new one.
- NEVER proactively create documentation files (\*.md) or README files. Only create documentation files if explicitly
  requested by the User.
- ALWAYS look up model definitions before using their fields or properties - do not assume field names or choices. Use
  the Read tool to check the actual model definition in the models.py file.
