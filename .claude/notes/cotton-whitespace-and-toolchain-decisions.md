# Cotton: whitespace + toolchain decisions (empirically established)

Cross-cutting rules for ALL component streams. Every claim below was measured in
this worktree, not inferred from docs. Supersedes earlier guidance.

## 1. Component files MUST NOT end with a trailing newline

A cotton component emits its file content verbatim, so a trailing newline lands
after the closing tag and collapses to a **rendered space**.

Measured, component file `<span class="badge …">{{ slot }}</span>`:

| Case | With trailing `\n` | Without trailing `\n` |
|---|---|---|
| Mid-sentence `mid<c-x>X</c-x>.` | `…</span>\n.` → visible space before the full stop | `…</span>.` clean |
| Adjacent `<c-x>X</c-x><c-x>Y</c-x>` | `</span>\n<span>` → visible gap | `</span><span>` clean |

Real breakage this caused: dice-result badges butted together in the `{% for %}`
at `core/campaign/campaign_action_outcome.html:22`.

**This is only enforceable because `gyrinx/templates/cotton/` is excluded from
`end-of-file-fixer` and from djlint reformat** (`pyproject.toml`
`extend_exclude`, plus three `exclude:` entries in `.pre-commit-config.yaml`).
`djlint --reformat` re-adds the newline even when the file carries `djlint:off`,
and reports "0 files were updated" while doing it — exclusion is the only fix.

**CONSEQUENCE: inline components ARE viable.** An earlier conclusion that
components could never be used mid-sentence (so no inline badges, no `None`
placeholder, no comma lists) was wrong and is retracted.

**REQUIRED GUARD:** the no-trailing-newline rule is invisible and any editor with
"insert final newline" silently breaks it — and nothing in the formatter chain
will catch it, by construction. Add a test that globs
`gyrinx/templates/cotton/**/*.html` and asserts each file does not end in `\n`.

## 2. `{% spaceless %}` is an independent second safety net

Measured: with a component that *does* carry a trailing newline, wrapping
adjacent call sites in `{% spaceless %}` collapses `</span>\n<span>` to
`</span><span>` — fully clean, even with the source split across lines.

- Works for **tag-to-tag** adjacency (adjacent components, components inside
  `{% for %}` loops). Already a documented Gyrinx pattern — see the
  comma-separated-lists section of the design system.
- Does **not** help **tag-to-text** adjacency (mid-sentence), where the
  whitespace sits between a tag and bare text. Rule 1 is the only fix there.

## 3. djlint call-site reflow is cosmetic, not a correctness problem

`djlint --reformat` splits adjacent one-line components onto separate lines and
moves slot content to its own line:

```
<div><c-badge variant="primary">A</c-badge><c-badge variant="secondary">B</c-badge></div>
```
becomes six lines. Measured facts:

- **Dropping `custom_html` does NOT prevent this** — output is byte-identical
  with and without it. The badges stream's proposed remedy would not have worked.
  Keep `custom_html = "c-[\\w.-]+"` (it stops djlint flattening the indentation
  of component children).
- Reflow is harmless given rule 1 (component has no trailing newline) or rule 2
  (`{% spaceless %}` at the call site). Slot padding is stripped inside
  `.badge` because inline-block establishes a block container; note it is **not**
  stripped inside `<a>`, so `<c-btn href=…>` slot padding renders as real spaces
  inside the link text.
- A one-liner inside `{% for %}…{% endfor %}` on a single line is left untouched.

**DECISION:** the "drop `custom_html`, or split each pattern into a mechanical
commit plus a formatting-only commit" question is a **diff-reviewability**
choice, not a correctness one. Recommend the two-commit split anyway on the
big-bang branch — ~37% of the diff is pure reflow and separating it is what makes
a 400-file change reviewable.

## 4. djlint `H026` blocker

`H026 Empty id and class tags can be removed.` fires purely on the presence of
`class=""`. Declaring a `class` default in `<c-vars>` is mandatory for cotton's
manual class merge (cotton has no auto-merge; an undeclared `class` emits two
`class` attributes and the caller's is dropped), so every component would trip it
and `./scripts/fmt.sh` would fail. Fixed: `ignore = "H006,H026"`.

Related silent failure: `custom_html = "c-[\w.-]+"` (single backslash) is invalid
TOML — djlint prints "Failed to load pyproject.toml file" and falls back to
defaults. Must be `"c-[\\w.-]+"`. Spot-check after any edit to that block.

## 5. Context isolation stays OFF

`COTTON_ENABLE_CONTEXT_ISOLATION = False` (note: this is the real setting name,
not the documented `COTTON_ISOLATE_BY_DEFAULT`; cotton reads it via
`getattr(settings, …, False)` so a typo fails silently).

Measured in the Phase 0 spike: turning it on builds a fresh `RequestContext` per
component instance, re-running all 8 context processors — **one extra
`notifications` COUNT query per component rendered** (20 components → 21 queries)
and 40µs/component vs 8.8µs. A literal N+1 on every page.

Use the per-call-site `only` flag for isolation instead (1 query, ~8.8µs).
Caveat: `only` drops `csrf_token`, so never use it on a component rendering a form.

This retracts the earlier plan to adopt isolation-by-default.

## 6. Housekeeping owed before anything ships

- Competing design streams wrote parallel component sets to disk under `c3/`,
  `mc/`, `zb/`, `_zlint/` and `mc/_probe.html`. Consolidate to one canonical set
  and delete the rest.
- One stream ran `djlint --reformat gyrinx/templates` before the exclusions
  landed and reformatted 32 untracked component files belonging to other streams.
  Re-check whitespace and trailing newlines on every surviving component file
  against rule 1.
- `gyrinx/templates/django/forms/field.html` (the project-wide Django
  form-renderer override) was modified by a stream. This has blast radius across
  every form in the app — review on its own merits before it goes near a commit.
