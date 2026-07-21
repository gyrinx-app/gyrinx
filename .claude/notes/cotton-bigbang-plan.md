# Cotton big bang — implementation plan

Worktree: `/Users/tom/code/gyrinx/gyrinx/.claude/worktrees/cotton-bigbang`
Branch: `worktree-cotton-bigbang` · merge-base `be3d9080` · `origin/main` head `746ad616`
Written 2026-07-21. Every number below was measured in this worktree unless marked otherwise.

---

## 1. Summary

### What we are doing

Gyrinx's templates hand-write Bootstrap class strings. `btn btn-primary btn-sm` appears
in 502 places. `text-bg-*` in 94. `alert alert-* alert-icon` in 80. A form field's
label/widget/help/errors anatomy is hand-rolled in roughly 200. Because each site is a
fresh decision, they have drifted: "Dead" is `text-bg-dark` on one page and
`text-bg-danger` on two others; there are 13 label-class variants and 6 different ways of
rendering field errors; the same flash-message level cascade exists twice and the bug
fixed in one copy is still live in the other.

We are replacing that vocabulary with four **django-cotton** components — plain `.html`
files in `gyrinx/templates/cotton/`, invoked as `<c-btn variant="primary">Save</c-btn>` —
inside the existing Django template engine. No SPA, no second renderer, no dual-engine
period. This is the direction the maintainer set when closing PR #1997.

The four families, in priority order:

| Component | Replaces | Sites |
|---|---|---|
| `c-btn` (+ `c-cancel`, `c-back`) | `btn btn-*` strings, `includes/cancel.html`, `includes/back.html` | 502 + 23 + 119 |
| `c-badge` (+ `.fighter-state`, `.chip`) | `badge text-bg-*` strings | 94 |
| `c-callout` / `c-box` / `c-messages` / `c-errors` | `alert alert-*`, `border rounded p-*`, two message loops | 80 + ~28 |
| `c-form.field` | `includes/form_field.html`, `django/forms/field.html`, hand-rolled fields | 37 + 30 + ~200 |

**Headline: 965 hand-written markup sites are under the ratchet today.** The migration
converts ~1,450 curated call sites across ~243 templates, eliminating the four class
vocabularies from everywhere except one file each. `badge.html` becomes the only template
in the repo containing `text-bg-`.

> **Corrected 2026-07-21 (completeness audit).** The earlier figures "~1,190 call sites /
> 234 templates" did not match the batch table: the table's Sites column sums to **1,479**
> (1,446 excluding `DEL0` and `FR1`), and re-deriving file membership from the table gives
> **235** migrated templates, not 234. Batch `BK1` (added by this audit, §4.3) adds 8 more.
> Treat every aggregate in this document as ±2 until someone regenerates them from the
> table mechanically — they were hand-totalled and they do not all agree.
>
> **The "`btn.html` is the only file containing `btn-`" invariant is already false** and
> should not be stated as an outcome. `cancel.html`, `callout.html` (`btn-close`),
> `confirm.html`, `filter/query.html`, `form/actions.html` and `form/stepper.html` all
> contain the string, mostly in API-doc comments but `callout.html:107` emits a real
> `class="btn-close"`. See R6, which is also wrong about `form/actions.html`.

Along the way it structurally fixes four bugs that have been patched one template at a
time and keep coming back:

1. **Hidden form errors (#2001).** `c-form.field` has no prop that suppresses errors.
   The class of bug — a hand-rolled field block that forgets `field.errors` — cannot
   recur.
2. **`message.tags` vs `message.level_tag`.** Still live at
   `gyrinx/core/templates/allauth/layouts/base.html:8`. A message with `extra_tags`
   fails every equality test and renders blue, including errors. One `c-messages`,
   used by both base layouts.
3. **Colourless state badges.** `fighter_card_content.html:38,43` has no `{% else %}`
   branch. `c-badge`'s `state` table is total over every model's `choices` and a test
   fails if a model drifts.
4. **The two field renderings.** `includes/form_field.html` and
   `templates/django/forms/field.html` disagreed on help-text and error markup. The app
   shipped two different-looking fields depending on whether a template said
   `{{ form }}` or included the partial. Now there is one.

### The honest risk position

**The technology is fine. The schedule is the risk.**

Cotton itself checked out: 232 component tests pass, `djlint gyrinx --check` reports 0
files, `manage check` is clean, and the measured per-component cost (~8.6 µs) is 1.9× an
`{% include %}` on a page that already executes 160–390 includes. Nothing here is a
performance problem outside two equipment-picker pages.

What is genuinely dangerous:

- **`main` moves 9 times a day** (measured over the last 24 h), PRs merge in 20–90
  minutes, and **155 distinct `.html` files were touched in the last 60 days** — against
  a migration scope of 234. The estate other people are editing and the estate this
  branch rewrites are the same estate. `746ad616` landed today and invented a badge
  shape (`{{ badge.badge }}` from a view-supplied dict) that no component was designed
  for. **The failure mode is not a painful rebase; it is that resolving a
  rewrite-vs-edit conflict by "keeping my side" silently reverts somebody's fix, and
  every test stays green.**
- **There is no visual regression net in this repo** beyond six markup-asserting tests,
  and the four components emit the same Bootstrap classes, so those six pass either way.
  We built a golden-HTML harness for this branch; before it, nothing would have caught a
  dropped `ms-2`.
- **Three subsets should not be big-banged**: the fighter-card stack (8× median render
  multiplier and the only markup shared with print), the equipment pickers (300–900
  components in one request), and `design_system.html` (its raw class strings *are* the
  documentation). Section 7 says so explicitly.

The mitigation for all of it is the same: **ship as a stack of small, independently
green, independently revertible PRs, ordered coldest-file-first, and land them the same
day they are opened.** A branch that is 95% right and lands today beats one that is 100%
right in a week, because the week costs ~60 commits of drift.

---

## 2. Phase 0 status — what is already done in this worktree

Everything in this section is **verified fact**, re-checked while writing this document,
unless explicitly marked ASSUMPTION.

> **Independent re-verification, 2026-07-21 (completeness audit).** The following were
> re-checked from scratch and **hold**: django-cotton **2.7.2** / Django **6.0.7** /
> djlint **1.40.4** installed; `COTTON_ISOLATE_BY_DEFAULT` absent from the package and
> `COTTON_ENABLE_CONTEXT_ISOLATION` the only real flag (§2.3); engine builtins after
> `ready()` are `[defaulttags, defaultfilters, loader_tags, django_cotton.templatetags.cotton]`
> with `APP_DIRS` popped (§2.2); `{{ attrs }}` injection via `:id` with a `"…"`-bookended
> payload **does** produce a live `onmouseover` handler while `title="{{ x }}"` is safely
> entity-escaped (§2.5); `[tool.djlint]` and all three pre-commit exclusions are in the
> tree as quoted (§2.4); `alert.html`/`_alert_inner.html`/`empty_state.html` have zero
> external call sites (`DEL0`); `allauth/layouts/base.html:8` still keys on
> `message.tags` while `core/layouts/base.html:149` keys on `level_tag` (§1 bug 2);
> `zb/` and `c3/` are referenced by nothing; **155** `.html` files touched in 60 days and
> **9** commits on `origin/main` in 24 h (R1); 232 tests pass with `-n 0`.
>
> **The component sources quoted in §3 were re-verified by rendering, not by reading.**
> `btn.html`, `badge.html`, `badge/chip.html`, `box.html`, `callout.html`, `errors.html`,
> `messages.html`, `cancel.html`, `back.html` and `form/field.html` all match the bodies
> quoted below byte-for-byte and all render correctly: element selection off `href`
> *presence*, `disabled` as a native attribute (never `disabled="False"`), `type` omitted
> when unset, `{{ attrs }}` passthrough of `name`/`value`/`id`, the `raw_attrs` slot, the
> `label` visually-hidden span, `c-cancel` picking up an **ambient** `return_url`,
> `c-messages` rendering empty string when there are no messages, all three
> `c-form.field` branches (fieldset / checkbox / plain) derived from the widget, and
> `require_bound_field` raising on `field="{{ form.name }}"`. `btn.html` and `badge.html`
> confirmed to have **no trailing newline**.
>
> **What did NOT hold** is corrected inline below and in §4.2, §4.3, §5.4, §7, R6 and D7:
> the xdist diagnosis, the missing `test_cotton_btn.py`, the X8 `{% load %}` rule, the
> `list_performance.html` and Django-admin "zero patterns" claims, the file/site/batch
> totals, the `btn-` invariant, `form/actions.html` in R6, the empty `menu/act/btn` dirs,
> and 9 pattern-bearing templates that appeared in no batch (now `BK1`).
>
> **Not re-verified — treat as ASSUMPTION:** every timing figure in §2.8 (the ~8.6 µs
> per-component cost, the 39.2 ms isolation-on number, the 3–8 ms picker estimate), the
> isolation-on query-count table in §2.3, the render-equivalence harness's
> three-consecutive-identical-runs claim, and §4.1's "124 of 234 files carry 2+ patterns /
> 34 carry 3+ / 21 carry all four" (a rough re-count over the batch files gave 152 / 57 /
> 11 using a broader `border rounded` match, so the numbers are not comparable — but they
> are also not confirmed).

### 2.1 Version and install

- **django-cotton 2.7.2** (latest; `Requires-Dist: django (>=4.2,<7.0)`). Installed
  clean, zero transitive deps.
- The project runs **Django 6.0.7** — top of cotton's declared range, and a real compat
  risk that checked out.
- **djlint 1.40.4** in the venv; `1.40.2` is the pre-commit pin. Both numbers are right
  in different places and behave identically here.
- The pin went in `requirements.txt`, not `pyproject.toml` — the project uses
  `dynamic = ["version", "dependencies"]` with `dependencies = {file = ["requirements.txt"]}`.

**Pin `django-cotton==2.7.2` exactly.** Isolation semantics, the context-processor
snapshot and the attribute-escaping logic have all changed between recent releases, and
cotton's `main` currently carries unreleased behaviour under the same version number.

### 2.2 Settings — autoconfig rewrites `TEMPLATES`, and that is fine

`django_cotton` is in `INSTALLED_APPS` (`gyrinx/settings.py`). Its `AppConfig.ready()`
**pops `APP_DIRS`** and substitutes an explicit chain. Verified post-`ready()`:

```
APP_DIRS present: False
loaders: [('django.template.loaders.cached.Loader',
           ['django_cotton.cotton_loader.Loader',
            'django.template.loaders.filesystem.Loader',
            'django.template.loaders.app_directories.Loader'])]
builtins: ['django_cotton.templatetags.cotton']
```

`app_directories.Loader` stays, so app templates still resolve; all three `DIRS` are
preserved, so the allauth override tree at `gyrinx/core/templates/allauth/` still
shadows the installed app. The forced `cached.Loader` matches Django 6.0's own default
(`Engine.__init__` wraps unconditionally; the old `if not debug` guard is gone).
`manage check` → **"System check identified no issues (0 silenced)."**

Cotton also monkeypatches `template.base.Lexer.tokenize` globally, with a fast-path
bail-out when no `{% cotton %}` tag is present — compile-time only.

### 2.3 ⚠️ Isolation: the briefed setting name is wrong, and the plan must be inverted

**`COTTON_ISOLATE_BY_DEFAULT` does not exist in 2.7.2.** `grep -rn ISOLATE_BY_DEFAULT`
over the sdist returns nothing; `_component.py:268` reads only
`COTTON_ENABLE_CONTEXT_ISOLATION`. Setting the briefed name **fails silently** and you
get full ambient-context leakage while believing you are isolated.

And the real flag must stay **off**. On 2.7.2, `_create_partial_context` builds a fresh
`RequestContext` per component, re-running all 8 context processors — including
`notifications`, which issues an uncached `COUNT`. Measured:

| components | isolation ON | isolation OFF | `{% include %}` |
|---|---|---|---|
| 1 | 2 queries | 1 | 1 |
| 5 | 6 | 1 | 1 |
| 20 | **21** | 1 | 1 |

That is a literal N+1 per component. At ~440 buttons + 94 badges a gang page would add
hundreds of `COUNT`s. **Neither setting is set.** The reasoning is recorded in a comment
in `gyrinx/settings.py` so nobody re-adds it.

Per-call-site isolation is still available via the bare `only` flag (1 query, 4.5×
faster) — but `only` silently drops `csrf_token`, so it suits presentational components
and never form-bearing ones. We do not use it.

### 2.4 djlint — clean, with one required config line

Verified: `djlint gyrinx --check` → **`0 files would be updated`**. No H025/H021/T002
errors on `<c-…>` tags. Self-closing `<c-vars />`, dotted names, `:prefixed` attrs and
bare booleans all survive reformat byte-identically, and reformat is idempotent.

The exact `pyproject.toml` change, **already in the tree**:

```toml
[tool.djlint]
profile = "django"
custom_blocks = "element,slot,setvar,is_active"
ignore = "H006,H026"
custom_html = "c-[\\w.-]+"
extend_exclude = "gyrinx/templates/cotton,gyrinx/core/tests/goldens"
```

Four things to understand about it:

1. **`custom_html` is required, not optional.** Without it djlint treats `<c-…>` as
   unknown *inline* tags and flattens children's indentation. `custom_blocks` is
   irrelevant — that is for `{% %}` blocks like allauth's `{% element %}`.
2. **`H026` was added to `ignore`** because it fires on the `class=""` default every
   component must declare in `<c-vars>`.
3. **`extend_exclude` on the component directory is load-bearing.** A component's file
   content is emitted verbatim, so a trailing newline lands after the closing tag and
   collapses to a rendered space between adjacent inline elements — the dice-result
   badges butted together at `core/campaign/campaign_action_outcome.html:22`.
   `djlint --reformat` re-appends that newline **even when the file carries
   `djlint:off`**, while reporting "0 files were updated".
4. **`extend_exclude` on `goldens` is equally load-bearing.** Goldens are rendered
   output, not templates. Measured: djlint would rewrite 16 of them, silently
   rebaselining the equivalence harness against reformatted output and making it pass no
   matter what the migration did.

`extend_exclude` is ignored for the *explicit file paths* pre-commit passes, so both
exclusions are repeated in `.pre-commit-config.yaml` on `djlint-reformat-django`,
`djlint-django` and `end-of-file-fixer`. All three are already patched.

**The verbosity trade-off is a live decision** — see Open Decision D1. `custom_html`
expands `<c-btn>Save</c-btn>` to three lines, which is ~1,000 extra diff lines across
~530 button sites; dropping it keeps one-liners and preserves adjacent-component
whitespace byte-for-byte, at the cost of flat indentation inside multi-child components.

### 2.5 Escaping — `{{ attrs }}` is an injection vector, and the rule is precise

- **Slot content: safe.** Normal autoescaping.
- **Declared props rendered as `{{ prop }}`: safe.** Autoescaped — including with the
  `:` prefix, because the value renders through `{{ prop }}` in the component body.
- **`{{ attrs }}`: NOT safe.** `Attrs.__str__` returns `mark_safe(...)` and
  `ensure_quoted()` early-returns any value that already starts and ends with `"`.
  Verified: a payload of `"a" onmouseover=alert(1) "` passed as `:id=` produced a
  genuinely parsed `onmouseover` handler.

So the rule is **not** "don't use `:` on `title`/`aria-label`/`value`". It is:

> **Never use the `:` prefix on an attribute the target component does not declare in
> its `<c-vars>`.** String interpolation (`id="{{ x }}"`) is always safe, on declared and
> undeclared attributes alike.

`test_cotton_call_site_gates.py::test_dynamic_props_only_on_declared_props` enforces
exactly that by parsing `<c-vars>` out of each component. The test suite keeps a
**negative control** asserting `:id="payload"` *does* inject — if a future cotton release
fixes `ensure_quoted()`, that test fails loudly and the rule gets relaxed deliberately.

This matters directly: Gyrinx puts user-controlled gang and fighter names into `title=`
and `data-bs-title=` at 70 tooltip sites.

### 2.6 Two other silent failure modes, both now gated

**A Django tag in attribute position does not raise.** Verified:
`<c-btn variant="primary" {% if not can %}disabled{% endif %}>` renders the braces as
literal text; `html.parser` reads the attributes as `[…, ('{%',None), ('if',None),
('%}disabled{%',None), …]` — **there is no `disabled` attribute and the button ships
enabled.** djlint lints it clean and reformats it into something that looks correct.
(In `c-callout`/`c-box` the same shape was observed failing *non-deterministically*
depending on cotton's mtime-keyed compile cache — sometimes raising, sometimes emitting
literal source with the closing tag mangled. That is worse than a hard failure, and it
is why the defence is static.)

**`:disabled="not can_roll"` silently resolves to nothing** and also ships the button
enabled. Cotton's `:` is a variable resolver, not an evaluator; `not`, filters and
comparisons all vanish without error. Same for
`:url="back_url|default:pack.get_absolute_url"` (cotton #273), which would silently lose
both the back URL and the back text at `pack/pack_archived.html:7`.

Both are hard-gated by `test_cotton_call_site_gates.py`, and both gates were verified to
fail on planted violations.

### 2.7 Cotton fails **open**

Cotton compiles in the *loader*. With `django_cotton` absent from `INSTALLED_APPS` there
is no loader, no builtin, and no exception: every `<c-*>` tag reaches the browser as
literal text with HTTP 200. Only six pre-existing tests assert on Bootstrap markup, so
the suite would pass green against a completely unstyled application. **This actually
happened once in this worktree** — the settings edit was lost and re-added.

Guards now in place:
- `gyrinx/core/checks.py` raises `gyrinx.E001` / `E002` at `manage check`, registered
  from `CoreConfig.ready()`. Verified to fire when the app is removed.
- `test_rendered_pages_contain_no_uncompiled_component_tags` asserts `b"<c-"` never
  appears in a rendered response.

**Related:** `Template(string)` / `engines[...].from_string()` pass `<c-…>` through
**verbatim and silently**. Component tests must use `render_to_string`; anything that
renders a template out of a database column cannot use components.

### 2.8 Performance

1000 components per render, median of 7, warm:

| | median | per component | vs raw |
|---|---|---|---|
| raw HTML | 0.34 ms | 0.34 µs | 1× |
| `{% include %}` | 4.55 ms | 4.55 µs | 13× |
| **cotton (isolation off)** | **8.3–8.8 ms** | **~8.6 µs** | **~25×** |
| cotton (isolation on) | 39.2 ms | 39.2 µs | 115× + N+1 |

**~1.9× an `{% include %}`.** Against production multipliers (median gang = 8 fighters,
p90 = 13, max = 36; ~3–4 badges + 2 buttons per fighter) a p90 gang page adds ~45 badge
and ~26 button components to a render that already executes 160–390 include nodes.
Negligible.

The one real exposure is the equipment pickers: `list_fighter_gear_edit.html` and
`list_fighter_weapons_edit.html` iterate an unpaginated catalogue of **900 equipment
items, 687 weapon profiles and 241 upgrades**, producing 300–900 `form-check` instances
per request. At ~8.6 µs that is 3–8 ms — probably fine, but it is the only place the
bet could lose, and there is **no render-timing guard anywhere in this repo**.

Production gets the `cached.Loader` (`DEBUG = False` in both `settings.py` and
`settings_prod.py`), so cotton's transpile step is a one-off per template per worker
process, not per request.

Add before the picker batches: `DEBUG_TOOLBAR_CONFIG = {"SKIP_TEMPLATE_PREFIXES": ("cotton/",)}`
— debug-toolbar's Templates panel is a known 114 ms → 4 s amplifier at 2,000 components,
and `debug_toolbar` is installed here.

### 2.9 Current tree state

```
 M .gitignore  .pre-commit-config.yaml  pyproject.toml  requirements.txt
 M gyrinx/settings.py  gyrinx/settings_dev.py  gyrinx/core/apps.py
 M gyrinx/core/static/core/scss/styles.scss
 M gyrinx/core/templates/allauth/elements/button.html      <- adapter, done
 M gyrinx/core/templates/core/includes/form_field.html     <- one-line shim, done
 M gyrinx/templates/django/forms/field.html                <- one-line shim, done
?? gyrinx/templates/cotton/                                <- components
?? gyrinx/core/checks.py  gyrinx/core/templatetags/form_tags.py
?? gyrinx/core/tests/{goldens/,render_world.py,render_normalise.py,
                      test_render_equivalence.py,test_cotton_*.py}
?? scripts/{check_cotton.py,check_cotton.sh,check_raw_markup.py,raw_markup_baseline.json}
```

Verified green: **232 cotton + equivalence tests pass** (`-n 0`), `djlint gyrinx --check`
→ 0 files, `manage check` → no issues, `python3 scripts/check_raw_markup.py` →
`raw-markup ratchet OK (965 sites at baseline)`.

**The gate tests are not xdist-safe — but the diagnosis below was wrong, and so was the
recommended fix.** Re-checked 2026-07-21:

- Scratch filenames are **already globally unique** (`test_cotton_badge.py:47` uses
  `uuid.uuid4().hex`), so "parallel workers collide on scratch filenames" is not the
  mechanism, and adding `os.getpid()` would change nothing.
- `test_cotton_call_site_gates.py` **already** filters `_cotton_test*`, `_probe*` and
  `_cotton_test_host/`, and already catches `FileNotFoundError` in `call_sites()`. That
  half is done.
- **The residual hole is a directory the filter does not name.** `TEMPLATE_ROOTS =
  [REPO_ROOT / "gyrinx"]`, and the component harness writes its scratch templates to
  `gyrinx/core/templates/cotton_test/f<uuid>.html` — which matches none of the three
  exclusions. **Verified by planting
  `gyrinx/core/templates/cotton_test/fdeadbeef.html` containing
  `<c-btn variant="primary" {% if x %}disabled{% endif %}>`: the gate module went from 10
  passed to 2 failed** (`test_no_template_tags_in_component_attribute_position` and
  `test_check_cotton_script_passes`). Under `-n auto`, any component test that renders a
  deliberately-forbidden shape can trip the gate worker mid-scan.
- **ASSUMPTION, not reproduced:** 232 tests passed serially, and the gate module passed
  3/3 standalone and 4/4 alongside the badge/callout/form modules under the default
  `-n auto`. The flake is real in principle but was **not observed** in seven runs today,
  so its frequency is unknown.

**Fix: add `cotton_test` to the gate's exclusion list and to `scripts/check_cotton.py`'s**
(both scan the same tree). Do not bother with `os.getpid()`. Still a `GATE0` blocker — a
flaky gate teaches people to re-run until green.

**No `test_cotton_btn.py` exists.** The 232 passing tests cover badge (77), callouts,
forms and the call-site gates. `c-btn` — the component with the most call sites by a
factor of five, and the one with the most conditional logic in its body — has **zero unit
tests**. §3.1's "Unit-test plan" is a plan, not a result. Writing it is part of `GATE0`.
Its behaviour *was* spot-checked by rendering during this audit (element selection across
`href` absent/empty/set, `tag=` override, `type` omitted when unset, `disabled` on both
branches, `label`, passthrough of `name`/`value`/`id`, `raw_attrs`, and the `:id` XSS
negative control all behaved exactly as §3.1 documents) — but a spot-check is not a suite.

**Two orphaned namespaces are in the tree.** `gyrinx/templates/cotton/zb/` (3 files) and
`gyrinx/templates/cotton/c3/` (10 files) are parallel agents' candidate variants,
divergent from the chosen set and referenced by nothing outside themselves. **Delete
before PR 1** — see risk R6.

---

## 3. The component library

All components live in **`gyrinx/templates/cotton/`**. That directory is on the template
path via `DIRS`, so `<c-btn>` resolves from anywhere. Do not split the set across
`gyrinx/core/templates/cotton/` as well — name collisions would then be governed by
`DIRS` order.

### Cross-cutting rules every component obeys

| # | Rule |
|---|---|
| X1 | One directory: `gyrinx/templates/cotton/`. Never split. |
| X2 | Every prop is declared in `<c-vars>` with a default (so it is stripped from `{{ attrs }}`), and the root tag ends with `{{ attrs }}` so `id`/`data-bs-*`/`aria-*`/`name`/`value`/`form` pass through untouched. |
| X3 | **No implicit spacing.** A component never emits `mb-*`, `ms-*`, `mt-*`. Spacing arrives via `class=` at the call site. This is the single biggest diff-safety rule. |
| X4 | **No JS-driven state.** `data-bs-*` only when the call site passes it. No prop that only makes sense with JS enabled. |
| X5 | Class order is `base → variant → size → passthrough`, matching the existing literal strings, so a rendered diff is empty. |
| X6 | HTML boolean attributes (`disabled`, `required`, `checked`) get a declared prop plus `{% if %}`, never `{{ attrs }}` passthrough — forwarding emits `disabled="False"`, which disables the control. |
| X7 | Never `:attr="user_data"`. Use `attr="{{ user_data }}"`, a slot, or a declared prop. |
| X8 | Component files carry their own `{% load %}` — it does not propagate in. **Three components currently break this rule and get away with it by accident — see the note below.** |

> **X8 caveat — `get_item` is not the filter you think it is.** `badge.html`,
> `callout.html` and `messages.html` all use `|get_item:` with **no `{% load %}` at all**,
> and they render correctly. The reason is not that loads propagate: it is that
> **`django_cotton.templatetags.cotton` ships its own `get_item` filter** (`cotton.py`:
> `return dictionary.get(key)`) and cotton's autoconfig installs that library as a
> template **builtin**, so the filter resolves everywhere with no load. Verified: engine
> builtins are `[defaulttags, defaultfilters, loader_tags, django_cotton.templatetags.cotton]`,
> and a plain no-load template resolves `|get_item:` fine.
>
> Two consequences worth writing down before someone debugs this at 2 a.m.:
>
> 1. The three components depend on an **undocumented filter in a third-party builtin**.
>    If cotton renames or drops it in 2.8, all three break at once with
>    `Invalid filter: 'get_item'` at compile time. Cheap insurance: add
>    `{% load custom_tags %}` to each of the three, which is what X8 asked for in the
>    first place.
> 2. Gyrinx has its **own** `get_item` in `custom_tags.py:86` with **different semantics**
>    — `obj[key]` with `KeyError/TypeError/IndexError` swallowed, versus cotton's
>    `dictionary.get(key)` which raises `AttributeError` on a non-mapping. Adding the load
>    shadows cotton's with gyrinx's. For the three lookup tables in these components
>    (plain dict, string key) the two are interchangeable, so the swap is safe — but do it
>    deliberately and re-run the badge suite, don't discover it.
| X9 | No `{% extends %}` in a component with `<c-vars>` (cotton hoists `<c-vars>` above it and Django rejects it). |
| X10 | No trailing newline in whitespace-sensitive components (`badge.html`, `badge/*.html`, `btn.html`, `cancel.html`, `back.html`). |

---

### 3.1 BUTTONS — `c-btn`, `c-cancel`, `c-back`

#### Props

**`c-btn`** — 11 declared props, the default slot, the `raw_attrs` escape slot, plus
`{{ attrs }}`.

| Prop | Default | Meaning |
|---|---|---|
| `tag` | `""` | `""` = auto (`a` when an `href` **attribute is written**, else `button`) \| `button` \| `a` \| `label` \| `span`. Explicit wins. Covers the 7 `<label class="btn …">` btn-check toggles and the one `<span class="btn …">` at `list_archived_fighters.html:29`. |
| `variant` | `""` | Bootstrap suffix **verbatim**, including outline forms: `primary`, `success`, `danger`, `secondary`, `link`, `warning`, `dark`, `outline-primary`, `outline-secondary`, … `""` emits a bare `.btn` (`fighter_switcher.html` needs it). Template expressions work. |
| `size` | `""` | `sm` \| `lg`. **No implicit `btn-sm`** — 63 `btn-success`, 53 `btn-primary` and 88 `btn-link` sites are full-size. |
| `href` | `""` | Emitted on the `a` branch. |
| `type` | `""` | **No default.** Emitted on the `button` branch only when set, so a type-less button keeps HTML's implicit `submit`. |
| `disabled` | `""` | Element-aware. `button` → native attribute; `a` → `.disabled` + `aria-disabled` + `tabindex="-1"`; `label`/`span` → `aria-disabled` only (**not** `.disabled`, whose `pointer-events:none` would kill the explanatory tooltip). |
| `label` | `""` | Accessible name for an icon-only control. Emits **only** a trailing `<span class="visually-hidden">`, never `title`. |
| `title` | `""` | Native tooltip, autoescaped. |
| `tooltip` | `""` | `data-bs-title` + `data-bs-toggle="tooltip"` **unless** the caller already passed a `data-bs-toggle`. |
| `current` | `""` | Truthy → `aria-current="page"`. Feed it `current="{% active_view 'core:dice' %}"`. |
| `class` | `""` | Appended last. |

Emitted order: `class → href/type → title → tooltip → disabled → current → passthrough`.

**Element selection is by attribute *presence*, not value.** `<c-btn href="{{ u }}">`
with `u=""` renders `<a href="">`, exactly as the raw markup does. 60 estate anchors take
`href` from a bare context variable, and `{% url … as x %}` yields `""` silently when
reverse fails; keying off emptiness would turn a link into an identically-styled inert
`<button>` with no visual cue.

**`c-cancel`** — `url`, `text` (falls back to `"Cancel"`), `class`. Delegates to
`c-btn variant="link"`.
**`c-back`** — `url`, `text` (falls back to `"Back"`), `class`. A breadcrumb
`nav`/`ol`/`li`, **not a button**.

Both keep the include's three-step href cascade: `url` → `return_url` →
`{% safe_referer "/" %}`. **`return_url` is deliberately NOT declared** so it inherits
ambiently exactly as `{% include %}` did — declaring it shadows the view-computed value
on 19 bare-include sites whose views call `get_return_url()`, and after a failed POST the
Referer *is* the form page, so Cancel would loop back into the form. Never pass
`return_url=`; pass `url=`. Neither has a `url_arg` prop (that foot-gun was removed in
`a8ca3c5c`).

`c-back` bakes in the #2001 a11y fix: it drops `aria-current="page"` from the `<li>` that
links to the **parent** page, while **keeping** the `.active` class (which drives
`--bs-breadcrumb-item-active-color`). A screen-reader fix with a zero-pixel diff — the
only kind safe to apply to 119 pages in one commit.

#### Source — `gyrinx/templates/cotton/btn.html`

The file on disk is complete and correct. The comment block (lines 1–145) is the API
documentation and must not be trimmed; the **entire renderable body is the single final
line**:

```django
{% comment %}...(145 lines of API docs — see the file)...{% endcomment %}{% comment %} djlint:off {% endcomment %}<c-vars tag="" variant="" size="" href="" type="" disabled="" label="" title="" tooltip="" current="" class="" />{% if "href" in attrs %}{% firstof tag "a" as el %}{% else %}{% firstof tag "button" as el %}{% endif %}<{{ el }} class="btn{% if variant %} btn-{{ variant }}{% endif %}{% if size %} btn-{{ size }}{% endif %}{% if disabled and el == "a" %} disabled{% endif %}{% if class %} {{ class }}{% endif %}"{% if el == "a" %} href="{{ href }}"{% endif %}{% if el == "button" and type %} type="{{ type }}"{% endif %}{% if title %} title="{{ title }}"{% endif %}{% if tooltip %}{% if "data-bs-toggle" not in attrs %} data-bs-toggle="tooltip"{% endif %} data-bs-title="{{ tooltip }}"{% endif %}{% if disabled %}{% if el == "button" %} disabled{% else %} aria-disabled="true"{% endif %}{% endif %}{% if disabled and el == "a" %} tabindex="-1"{% endif %}{% if current %} aria-current="page"{% endif %}{% with attrstr=attrs|stringformat:"s" %}{% if attrstr %} {{ attrstr|safe }}{% endif %}{% endwith %}{% if raw_attrs.strip %} {{ raw_attrs }}{% endif %}>{{ slot }}{% if label %}<span class="visually-hidden">{{ label }}</span>{% endif %}</{{ el }}>{% comment %} djlint:on {% endcomment %}
```

Note the three things that look odd and are deliberate: the whole file is one physical
line after the comment (no injected whitespace); `{% if "href" in attrs %}` tests the
**mapping**, which retains `<c-vars>` keys even though the **string** output strips them;
and `{{ attrs }}` is guarded on `attrstr` so nothing passed means no stray space before
`>`.

`gyrinx/templates/cotton/cancel.html` (54 lines) and `back.html` (62 lines) are likewise
complete on disk. `cancel.html`'s body:

```django
{% load custom_tags %}{% comment %} djlint:off {% endcomment %}<c-vars url="" text="" class="" /><c-btn variant="link" href="{% if url %}{{ url }}{% elif return_url %}{{ return_url }}{% else %}{% safe_referer "/" %}{% endif %}" class="{{ class }}" :attrs="attrs">{% if text %}{{ text }}{% else %}Cancel{% endif %}</c-btn>{% comment %} djlint:on {% endcomment %}
```

`back.html`'s body:

```django
{% load custom_tags %}{% comment %} djlint:off {% endcomment %}<c-vars url="" text="" class="" /><nav aria-label="breadcrumb"{% with attrstr=attrs|stringformat:"s" %}{% if attrstr %} {{ attrstr|safe }}{% endif %}{% endwith %}>
    <ol class="breadcrumb{% if class %} {{ class }}{% endif %}">
        <li class="breadcrumb-item active">
            <i class="bi-chevron-left"></i>
            <a href="{% if url %}{{ url }}{% elif return_url %}{{ return_url }}{% else %}{% safe_referer "/" %}{% endif %}">{% if text %}{{ text }}{% else %}Back{% endif %}</a>
        </li>
    </ol>
</nav>{% comment %} djlint:on {% endcomment %}
```

#### Before / after

**The form footer — the commonest shape, and the one the ambient-`return_url` decision
buys.** `core/list_fighter_kill.html:24-28`:

```django
{# BEFORE #}
<div class="mt-3">
    <button type="submit" class="btn btn-danger">
        <i class="bi-heartbreak"></i> Kill Fighter
    </button>
    {% include "core/includes/cancel.html" %}
</div>

{# AFTER #}
<div class="mt-3">
    <c-btn variant="danger" type="submit">
        <i class="bi-heartbreak"></i> Kill Fighter
    </c-btn>
    <c-cancel />
</div>
```

Renders, with `return_url="/campaign/1/actions"` in context:
`<a class="btn btn-link" href="/campaign/1/actions">Cancel</a>`. The bare `<c-cancel />`
is correct — 19 hand-edits removed from the diff.

**A conditional attribute — the shape that silently ships enabled.**
`core/list_fighter_advancement_dice_choice.html:69`:

```django
{# BEFORE #}
<button class="btn btn-outline-primary" type="submit" name="roll_action" value="roll_manual"
        {% if not can_roll_dice %}disabled{% endif %}>Roll manually</button>

{# AFTER — note the quoted value #}
<c-btn variant="outline-primary" type="submit" name="roll_action" value="roll_manual"
       disabled="{% if not can_roll_dice %}1{% endif %}">Roll manually</c-btn>
```

Both `{% if %}` in attribute position and `:disabled="not can_roll_dice"` are CI-blocked.

**A button-styled label.** `core/campaign/campaign_add_lists.html:79-86`:

```django
{# BEFORE #}
<label class="btn btn-outline-primary btn-sm" for="owner-all">All Gangs</label>
{# AFTER #}
<c-btn tag="label" variant="outline-primary" size="sm" for="owner-all">All Gangs</c-btn>
```

**Four kinds of template logic in one tag.** `core/includes/notification_nav_button.html:7-12`:

```django
{# BEFORE #}
<a class="btn btn-dark position-relative {{ extra_classes }} {% active_view 'core:notifications' %}"
   {% active_aria 'core:notifications' %}
   href="{% url 'core:notifications' %}"
   data-bs-toggle="tooltip"
   data-bs-title="{% if unread_notification_count %}You have unread notifications{% else %}No unread notifications{% endif %}"
   aria-label="Inbox{% if unread_notification_count %} ({{ unread_notification_count }} unread){% endif %}">

{# AFTER #}
<c-btn variant="dark"
       href="{% url 'core:notifications' %}"
       class="position-relative {{ extra_classes }} {% active_view 'core:notifications' %}"
       current="{% active_view 'core:notifications' %}"
       tooltip="{% if unread_notification_count %}You have unread notifications{% else %}No unread notifications{% endif %}"
       aria-label="Inbox{% if unread_notification_count %} ({{ unread_notification_count }} unread){% endif %}">
```

`{% active_aria %}` emits a **whole attribute**, which cannot live in a component's
attribute list — `current=` takes the tag's *value* instead. (It also cannot go in
`raw_attrs`: slot content is autoescaped and yields `aria-current=&quot;page&quot;`.)

#### Escape hatch — four rungs, lowest first

1. **A template expression inside a quoted attribute value.** This is the normal API and
   covers everything the inventory called "needs an agent":
   `variant="{% if is_pinned %}success{% else %}secondary{% endif %}"`,
   `class="dropdown-toggle{% if x %} disabled{% endif %}"`,
   `url="{{ back_url|default:pack.get_absolute_url }}"`. **Filters and `{% if %}` work
   here and only here.**
2. **A declared prop absorbing a tag's output** — `current="{% active_view … %}"`.
3. **The `raw_attrs` named slot**, injected verbatim into the opening tag. Reserved for
   the one thing cotton cannot express: a *conditional group* of attributes. Literal
   attribute text only; never user data. Expected estate usage: `fighter_gear_filter.html:77`
   plus the allauth adapter. If it spreads beyond ~5 sites, add a count assertion.
4. **Raw HTML.** `c-btn` is optional. Preferred permanently for `gyrinx/templates/errors/*`,
   `design_system.html`'s showcase sections, and the 14 Django-admin buttons.

**Accepted limitations, to state in the PR:** `&` becomes `&amp;` in interpolated hrefs
(browsers decode identically; equivalence tests entity-normalise); attribute order differs
from source; djlint expands one-liners.

#### Unit-test plan

`gyrinx/core/tests/test_cotton_btn.py` (to write). Render via `render_to_string` only —
`Template(string)` passes `<c-btn>` through silently and every assertion vacuously passes.
Use a unique filename per render (`cached.Loader` is unconditional on Django 6.0; reusing
a probe filename returns the previous template — this bit me during verification). Parse
with `html.parser` and compare `(tag, sorted attrs, sorted class set)`; substring matching
cannot see `disabled` vs `disabled="False"`, a duplicate `data-bs-toggle`, or junk
attributes from a literal `{% if %}`.

Must cover: element selection across `href` absent / `""` / `{{ missing }}` / `/x`;
`tag` overriding auto including `tag="button"` with an href present; `type` emitted only
when set; the `disabled` matrix per element and all four falsy forms; class order
`btn btn-outline-secondary btn-sm js-sub-die`; exactly one `class` attribute; the XSS
matrix with the `"…"`-bookended payload including the `:id` negative control; the
attribute census round-trip (`name`/`value`/`form`/entity-encoded `data-clipboard-text`);
no trailing space before `>`; the tooltip/dropdown collision; `raw_attrs` in both
branches plus the `{% active_aria %}` negative; and equivalence with `cancel.html` /
`back.html` including the **ambient `return_url`** case and the empty-`text` fallback.

---

### 3.2 BADGES — `c-badge`, `c-badge.fighter-state`, `c-badge.chip`

#### Props

**`c-badge`**

| Prop | Default | Meaning |
|---|---|---|
| `variant` | `secondary` | → `text-bg-{variant}`. `bg-*` is never emitted. `"ghost"` → `text-body border fw-normal` with no `text-bg-*` — the outlined print/placeholder treatment. Accepts template expressions. |
| `state` | `""` | Domain status → colour via the embedded table. **Wins over `variant`**; falls through to `variant` when blank or unknown. |
| `pill` | `""` | Bare boolean → `rounded-pill`, emitted **before** the colour token to match the three existing `badge rounded-pill text-bg-danger` strings. |
| `href` | `""` | Renders `<a>` + `text-decoration-none`, **only** for a root-relative path (starts `/`, not `//`). `javascript:`, `data:`, `//host` and absolute URLs render a plain badge with no link. Fails closed. |
| `tag` | `span` | `span` \| `div`; anything else renders a span. Constrained, not interpolated — autoescaping does nothing in tag-name position. Preserves 19 legacy `<div class="badge">` line boxes. |
| `title` | `""` | Autoescaped. Declared because five live sites put user-controlled names here. |
| `tooltip` | `""` | Emits a real `title` **plus** `data-bs-toggle="tooltip"`, so it degrades without JS (X4). Overrides `title`. |
| `class` | `""` | Appended last. No spacing, sizing or positioning of its own. |

Class order: `badge [rounded-pill] <colour> [text-decoration-none] [caller classes]`.

**The state table is total** over every status vocabulary rendered as a badge:

```
ListFighter.injury_state  active→success · recovery, convalescence, in_repair→warning · dead→danger
capture pseudo-states     captured→warning · sold_to_guilders→secondary
Crew.status               draft→secondary · locked→success
Battle.status             pre_battle→secondary · in_progress→success · post_battle→secondary
Campaign.status           pre_campaign→secondary · in_progress→success · post_campaign→secondary
aliases                   injured→warning · sold→secondary · archived→secondary
```

`test_state_table_covers_model_choices` reads the table out of the component and asserts
it is a superset of every model's `choices`. **That test, not the fallthrough, is what
makes `state` safe** — adding a sixth injury state fails a test instead of turning a
green pill grey.

Including the crew/battle/campaign vocabularies is what lets the five
`text-bg-{% if %}` sites use the component at all — including
`home/campaign_row.html:8`, where the conditional is **inside the class token** so no
`text-bg-<word>` grep finds it.

**`c-badge.fighter-state`** — `fighter` (required, pass dynamically), `show_state`
(default on), `show_active` (default off), `show_capture` (default on), `state_href`,
`captured_href`, `class`. Renders nothing for an active uncaptured fighter; renders
**both** badges for a dead-and-captured fighter, matching the original's two independent
`{% if %}` blocks. `show_state` and `show_capture` are separate because the original
gates them differently — `is_captured` is a plain property over a persistent
`capture_info` relation, so a gang that leaves campaign mode keeps its captured fighters
and must keep the badge.

**`c-badge.chip`** — `value` (object with `.colour` and `.name`), `dot` (default `8px`;
`campaign_attributes.html` passes `10px`), `class`.

#### Source — `gyrinx/templates/cotton/badge.html`

Complete on disk (100 lines; 96 of comment). The renderable body:

```django
{% endcomment %}<c-vars variant="secondary" state="" pill="" href="" tag="span" title="" tooltip="" class="" :state_variants="{'active': 'success', 'recovery': 'warning', 'convalescence': 'warning', 'in_repair': 'warning', 'injured': 'warning', 'captured': 'warning', 'sold_to_guilders': 'secondary', 'sold': 'secondary', 'archived': 'secondary', 'dead': 'danger', 'draft': 'secondary', 'locked': 'success', 'pre_battle': 'secondary', 'in_progress': 'success', 'post_battle': 'secondary', 'pre_campaign': 'secondary', 'post_campaign': 'secondary'}" />{% firstof state_variants|get_item:state variant "secondary" as tone %}{% if href|slice:":1" == "/" and href|slice:":2" != "//" %}{% firstof href as link %}{% else %}{% firstof "" as link %}{% endif %}<{% if link %}a href="{{ link }}"{% elif tag == "div" %}div{% else %}span{% endif %} class="badge{% if pill %} rounded-pill{% endif %} {% if tone == "ghost" %}text-body border fw-normal{% else %}text-bg-{{ tone }}{% endif %}{% if link %} text-decoration-none{% endif %}{% if class %} {{ class }}{% endif %}"{% if tooltip %} title="{{ tooltip }}" data-bs-toggle="tooltip"{% elif title %} title="{{ title }}"{% endif %}{% if attrs.attrs_dict %} {{ attrs }}{% endif %}>{{ slot }}</{% if link %}a{% elif tag == "div" %}div{% else %}span{% endif %}>
```

Two subtleties worth flagging to a reviewer: `{% if attrs.attrs_dict %}` — **not** a bare
truthiness test on `attrs`, which is always true because `<c-vars>` keys stay in the
mapping, so an unguarded proxy emits a stray space at every call site. And **the file has
no trailing newline**, which is load-bearing (§2.4).

`badge/fighter_state.html` body:

```django
{% endcomment %}<c-vars fighter="" show_state="1" show_active="" show_capture="1" state_href="" captured_href="" class="" />{% if show_state and show_active or show_state and not fighter.is_active %}<c-badge state="{{ fighter.injury_state }}" href="{{ state_href }}" class="{{ class }}">{{ fighter.get_injury_state_display }}</c-badge>{% endif %}{% if show_capture and not fighter.is_vehicle %}{% if fighter.is_captured %}<c-badge state="captured" href="{{ captured_href }}" class="{{ class }}" tooltip="Captured by {{ fighter.capture_info.capturing_list.name }}">Captured</c-badge>{% elif fighter.is_sold_to_guilders %}<c-badge state="sold_to_guilders" href="{{ captured_href }}" class="{{ class }}">Sold to Guilders</c-badge>{% endif %}{% endif %}
```

`badge/chip.html` body:

```django
{% endcomment %}<c-vars value="" dot="8px" class="" /><c-badge variant="light" class="fw-normal border d-inline-flex align-items-center gap-1{% if class %} {{ class }}{% endif %}" :attrs="attrs">{% if value.colour %}<span class="d-inline-block rounded-circle" style="width: {{ dot }}; height: {{ dot }}; background-color: {{ value.colour }}"></span>{% endif %}{{ value.name }}</c-badge>
```

Note `:attrs="attrs"` in the composites, not `{{ attrs }}` — cotton masks the latter
inside a component tag and would emit it as literal text.

#### Before / after

**The plain case.** `core/list_fighter_xp_edit.html`:

```django
{# BEFORE #}  <span class="badge text-bg-primary">{{ fighter.xp_current }}</span>
{# AFTER  #}  <c-badge variant="primary">{{ fighter.xp_current }}</c-badge>
```

**The conditional inside the class token — invisible to a `text-bg-<word>` grep.**
`core/includes/home/campaign_row.html:8`:

```django
{# BEFORE #}
<div class="badge text-bg-{% if campaign.is_in_progress %}success{% else %}secondary{% endif %}">
{# AFTER #}
<c-badge tag="div" state="{{ campaign.status }}">
```

`tag="div"` matters: `.home-row-meta`'s min-height is tuned in `styles.scss:389-395` to
the badge's `0.75em`/`line-height: 1` box.

**The fighter card's seven-badge block.** `core/includes/fighter_card_content.html:33-57`
expresses a three-way permission/mode matrix by duplicating each badge as `<a>` or
`<span>`, and its injury cascade has no `{% else %}`:

```django
{# BEFORE (abridged) #}
{% if list.is_campaign_mode %}
    {% if can_edit %}
        <a href="{% url 'core:list-fighter-state-edit' list.id fighter.id %}"
           class="badge ms-2 text-decoration-none {% if fighter.is_injured %}text-bg-warning{% elif fighter.is_dead %}text-bg-danger{% endif %}">
            {{ fighter.get_injury_state_display }}</a>
    {% else %}
        <span class="badge ms-2 …">{{ fighter.get_injury_state_display }}</span>
    {% endif %}
{% endif %}
{% if fighter.is_captured %}<a … class="badge ms-2 text-bg-warning …">Captured</a>{% endif %}

{# AFTER — note the two guards stay SEPARATE #}
{% url 'core:list-fighter-state-edit' list.id fighter.id as state_url %}
{% url 'core:campaign-captured-fighters' list.campaign.id as captured_url %}
<c-badge.fighter-state :fighter="fighter"
                       show_state="{% if list.is_campaign_mode %}1{% endif %}"
                       state_href="{% if can_edit and not print %}{{ state_url }}{% endif %}"
                       captured_href="{% if can_edit and not print %}{{ captured_url }}{% endif %}"
                       class="ms-2" />
```

**Loop hazard, and it is not theoretical.** Never write
`{% if can_edit %}{% url … as u %}{% endif %}` inside a `{% for %}`. `ForNode` pushes
context once for the whole loop, so the URL survives into iterations where the guard is
false and rows the viewer cannot act on get action links (reproduced: `[/][/][/]` for
`editable=[True,False,False]`). Assign unconditionally, gate inside the attribute value
(verified: `[/][][]`). This applies to every component, not just badges.

**The print variant.** `core/includes/fighter_card_cost.html`:

```django
{# BEFORE #}
{% if print %}{% firstof cost_classes 'text-body border fw-normal' as badge_classes %}
{% else %}{% firstof cost_classes 'text-bg-secondary bg-secondary' as badge_classes %}{% endif %}
<div class="badge {{ badge_classes }}">{{ fighter.cost_display }}</div>

{# AFTER #}
<c-badge tag="div" variant="{% if print %}ghost{% else %}secondary{% endif %}">{{ fighter.cost_display }}</c-badge>
```

**Find every caller passing `cost_classes` / `cost_alt_classes` first** — the variable is
overridable by any calling template, so this is a rewrite, not a substitution.

#### Escape hatch

Same four rungs as `c-btn`. Badge-specific notes:

- `variant="{{ banner.colour }}"` and `variant="{% if x %}success{% else %}secondary{% endif %}"`
  both work. There is deliberately **no whitelist inside the component**, so a DB-driven
  variant stays expressible; literal typos are caught by CI instead, and the one dynamic
  source (`SiteBanner.colour`) should be constrained with `choices=` at the model layer.
- `:title="names|join:', '"` renders **no title at all** — filters are dropped in `:props`.
  Use `title="{{ names|join:', ' }}"`. `list_packs.html:68` has exactly this shape.
- **`campaign_resource_modify.html` must not be migrated mechanically.** Inline JS assigns
  `newAmountSpan.className = 'badge text-bg-danger fs-5'` **wholesale**, clobbering whatever
  the component emits. Rewrite the JS or leave the markup.
- **`list_post_battle_updates.html` must not use `state=` or the composite.** It styles
  "Dead" `text-bg-dark` (vs `text-bg-danger` elsewhere), labels "Sold" not "Sold to
  Guilders", and renders one badge from an `elif` cascade. Migrate with explicit
  `variant=` per branch, and record the three colour divergences as a deliberate decision.
- **"Badge" is overloaded.** There is a separate supporter-badge system with its own
  `{% user_badge %}` / `{% badge_icon %}` tags, `.user-badge` / `.badge-icon` CSS and
  `.badge-preview`. `c-badge` is the Bootstrap chip only. Any find/replace on the string
  "badge" corrupts that feature.

#### Unit-test plan

`gyrinx/core/tests/test_cotton_badge.py` — **77 tests, all passing.** Covers: all 17
state keys; `state` beating `variant`; unknown state falling through; the model-choices
totality test; `ghost`; `pill` ordering; the href scheme guard (`javascript:`, `data:`,
`//evil`, absolute — all render `<span>`); `tag` constraint; the XSS matrix including
`:title` and the chip's `style`; **zero slot padding**; **the adjacent-badge gap**;
bare valueless attribute survival (`bs-tooltip` stays bare, not `="True"`); the
`{% url … as %}` loop-leak test asserting rendered elements are exactly `[a, span]`;
`show_capture=""` leaving exactly one badge; capture-badge independence.

---

### 3.3 CALLOUTS — `c-callout`, `c-box`, `c-messages`, `c-errors`

Three genuinely different things live under "callout" and must stay separate.

#### Props

**`c-callout`** — the filled Bootstrap alert. Feedback only.

| Prop | Default | Meaning |
|---|---|---|
| `variant` | `info` | `success` \| `danger` \| `warning` \| `info` \| `secondary` \| `primary`. Drives `alert-{variant}` **and the icon**. Unknown variant falls back to `bi-info-circle` rather than blanking. |
| `icon` | `""` | `""` derive from variant; `"bi-dice-6"` a full class string (copy-paste from the old markup); `"none"` no icon, no `alert-icon` class, no body wrapper. It is the **string** `"none"` because a template cannot tell `False` from `""`. |
| `heading` | `""` | Bold lead line, autoescaped. Renders `<strong>`, never `<h5 class="alert-heading">` — body text stays at body font size. |
| `body_class` | `""` | Classes on the body wrapper, for the two alerts whose body is itself a flex row (`index.html:31`, `list_fighter_advancement_other.html:23`). **Not for spacing.** Both sites migrate by hand. |
| `dismissible` | `""` | Bare boolean → `alert-dismissible fade show` + `btn-close`. Flash messages only. |
| `role` | `alert` | Declared, so an override replaces rather than duplicating. |
| `class` | `""` | Appended last. |

**The icon is derived, not chosen.** 83 of the 84 icon-bearing estate alerts already use
exactly the variant default, so choosing at a call site was never a real decision — only
a chance to get it wrong. The one exception (`bi-dice-6` on `alert-info`, at
`list_fighter_advancement_type.html`) passes `icon=`.

**No implicit `mb-0`.** 68 of 80 sites use it; the rest use `mb-3`, `mb-4`, `mb-last-0`,
`mt-3`, `p-2 fs-7` or `g-col-12`. Baking it in makes the diff empty for 68 and silently
wrong for 12. Pass `class="mb-0"` explicitly and it is provably empty for all of them.

The anatomy is **fixed** because `.alert-icon` (`styles.scss:183`) is a flex rule
selecting the direct-child `i` and `div`:

```
div.alert.alert-{variant}.alert-icon[role=alert]
  i[aria-hidden]      flex-shrink: 0
  div                 flex-grow: 1; min-width: 0   <- the slot
  button.btn-close    only when dismissible
```

**`c-box`** — `compact` (bare boolean; `p-2` instead of `p-3`), `class`. Renders a
`<div>`. **It must never acquire a `variant` prop** — the moment `c-box` can be coloured
it becomes a second alert system and the distinction the design system protects
collapses. A coloured, icon-led aside is `c-note`, a *named situation*, not a colour knob.

**`c-messages`** — no props. Reads `messages` from the context processor (the one legal
category of ambient read). Keys on **`message.level_tag`**, mapping
`debug→secondary, info→info, success→success, warning→warning, error→danger`, default
`info`. Renders nothing at all — wrapper div included — when there are no messages.

**`c-errors`** — `form` (pass with a colon), `errors`, `class`. Covers the 33 hand-rolled
`{% if form.non_field_errors %}<div class="alert alert-danger …">` blocks, **and renders
hidden-field errors**, which `visible_fields()` silently drops today.

#### Source

`gyrinx/templates/cotton/callout.html` (111 lines) — renderable body:

```django
<c-vars variant="info"
        icon=""
        heading=""
        body_class=""
        dismissible=""
        role="alert"
        class=""
        :icons="{'success': 'bi-check-lg', 'danger': 'bi-exclamation-triangle', 'warning': 'bi-exclamation-triangle', 'info': 'bi-info-circle', 'secondary': 'bi-info-circle', 'primary': 'bi-info-circle'}" />
<div class="alert alert-{{ variant }}{% if icon != "none" %} alert-icon{% endif %}{% if dismissible %} alert-dismissible fade show{% endif %}{% if class %} {{ class }}{% endif %}"
     role="{{ role }}"
     {{ attrs }}>
    {% if icon != "none" %}
        <c-icon name="{% firstof icon icons|get_item:variant "bi-info-circle" %}" />
        <div {% if body_class %}class="{{ body_class }}"{% endif %}>
            {% if heading %}<strong>{{ heading }}</strong>{% endif %}
            {{ slot }}
        </div>
    {% else %}
        {% if heading %}<strong>{{ heading }}</strong>{% endif %}
        {{ slot }}
    {% endif %}
    {% if dismissible %}
        <button type="button"
                class="btn-close"
                data-bs-dismiss="alert"
                aria-label="Close"></button>
    {% endif %}
</div>
```

`gyrinx/templates/cotton/box.html` (71 lines) — renderable body:

```django
<c-vars compact="" class="" />
<div class="border rounded {% if compact %}p-2{% else %}p-3{% endif %}{% if class %} {{ class }}{% endif %}"
     {{ attrs }}>{{ slot }}</div>
```

`gyrinx/templates/cotton/messages.html` (40 lines) — renderable body:

```django
<c-vars :variants="{'debug': 'secondary', 'info': 'info', 'success': 'success', 'warning': 'warning', 'error': 'danger'}" />
{% if messages %}
    <div>
        {% for message in messages %}
            <c-callout variant="{% firstof variants|get_item:message.level_tag "info" %}"
                       dismissible>{{ message }}</c-callout>
        {% endfor %}
    </div>
{% endif %}
```

`gyrinx/templates/cotton/errors.html` (85 lines) — renderable body:

```django
<c-vars form="" errors="" class="" />
{% if form and not form.fields %}
    <!-- COTTON-MISUSE c-errors: pass :form="form" with a colon; a colon-less form= stringifies the form and silently hides every error -->
{% endif %}
{% if errors %}
    <c-callout variant="danger" class="{{ class }}" :attrs="attrs">
        {{ errors }}
    </c-callout>
{% endif %}
{% if form.non_field_errors %}
    <c-callout variant="danger" class="{{ class }}" :attrs="attrs">
        {{ form.non_field_errors }}
    </c-callout>
{% endif %}
{% for hidden in form.hidden_fields %}
    {% if hidden.errors %}
        <c-callout variant="danger" class="{{ class }}">
            <strong>{% firstof hidden.label hidden.name %}</strong>
            {{ hidden.errors }}
        </c-callout>
    {% endif %}
{% endfor %}
```

`gyrinx/templates/cotton/icon.html` (used by `c-callout`) is complete on disk: it maps
17 semantic names (`add`→`plus-lg`, `edit`→`pencil`, …), tolerates and strips a leading
`bi-`, and always emits `aria-hidden="true"` — all 614 estate icon uses are decorative,
and an icon-only control gets its name from `<c-btn label="…">`.

#### Before / after

**The 83-site mechanical case.** `core/list_fighter_kill.html:14`:

```django
{# BEFORE #}
<div class="alert alert-warning alert-icon mb-0" role="alert">
    <i class="bi-exclamation-triangle"></i>
    <div>
        <strong>Are you sure?</strong>
        <p class="mb-0">This will mark {{ fighter.name }} as dead.</p>
    </div>
</div>

{# AFTER #}
<c-callout variant="warning" heading="Are you sure?" class="mb-0">
    <p class="mb-0">This will mark {{ fighter.name }} as dead.</p>
</c-callout>
```

**The messages loop — one implementation, two consumers.**
`core/layouts/base.html:145-158` and `allauth/layouts/base.html:8` both collapse to:

```django
<c-messages />
```

`allauth/layouts/base.html` is the one still keying on `message.tags`; this kills it.
**Intended visual change:** flash messages gain the pinned variant icon and the
`alert-icon` class they currently lack. To ship without it, add `icon="none"` to the
`c-callout` inside `messages.html` — one line, revertible in one commit.

**The bordered box.** `core/includes/notification_banners.html`:

```django
{# BEFORE #}  <div class="border rounded p-2 d-flex gap-2 align-items-start" role="alert">
{# AFTER  #}  <c-box compact class="d-flex gap-2 align-items-start" role="alert">
```

#### Escape hatch

- **A conditional attribute inside a cotton tag is the one thing that silently corrupts a
  page** — and here it fails *non-deterministically* depending on cotton's compile cache:
  sometimes raising, sometimes emitting literal template source with the closing tag
  mangled. Two estate boxes are written that way and are **excluded by name**:
  `pages/forms/widgets/bs_checkbox_select_compact.html:8` and
  `core/pack/includes/weapon_profile_stats_form.html:27`. Both carry the `id` that
  `static/core/js/index.js` queries for the filter widget, so a silent loss breaks trait
  and equipment filtering with no error anywhere.
- **Three files keep hand-rolled alert markup by decision:** `core/includes/site_banner.html`
  (variant *and* icon from DB columns, `border-0 py-2 px-0` strips the alert chrome,
  `hstack` substitutes for `alert-icon`, dismiss is a `btn-outline` with a JS hook),
  `allauth/elements/alert.html` and `allauth/elements/fields.html`. Two of the three carry
  visual changes that need a PR of their own.
- **Non-div bordered elements stay raw** — `a`, `label`, `form`, `fieldset`, `pre`. Use
  `c-disclosure` for the `details`/`summary` case.
- **Scope discipline: do not migrate the whole box family.** Only the ~28 notice-shaped
  boxes are in scope. The ~72 pure-layout boxes (grid parents, scroll containers,
  responsive rows, form wrappers) carry no callout semantics; converting them buys nothing
  and each is a chance to regress a grid or flex container.
- **Class order changes** at the 14 sites that write utilities *before* `border rounded`,
  so byte-equality does not hold for `c-box` — assert DOM equality with class as a set.
- `c-callout` reads no ambient context, so it is safe on the 500 handler.

#### Unit-test plan

`gyrinx/core/tests/test_cotton_callouts.py` — passing. Covers: the icon-per-variant map;
`icon="none"` dropping the class, the icon **and** the body wrapper; `icon="bi-dice-6"`
overriding; **icon and body as direct children in that order** (the `.alert-icon` flex
contract); `heading` as `<strong>` never `alert-heading`; `dismissible` emitting
`btn-close` with `data-bs-dismiss`; no implicit `mb-0`; `role` override not duplicating;
`c-box` `p-3`/`p-2` and class passthrough; **`c-box` has no `variant` prop** (assert the
attribute is not consumed); `c-messages` keyed on `level_tag` with the
`extra_tags="toast"` + `ERROR` regression case rendering `alert-danger`; `c-messages`
rendering nothing when empty; `c-errors` rendering hidden-field errors.

---

### 3.4 FORM FIELDS — `c-form.field`

#### Props

| Prop | Default | Meaning |
|---|---|---|
| `field` | `""` | A `BoundField`. **Required, and always pass with the colon: `:field="form.name"`.** |
| `label` | `""` | Override the label **text** only. Still goes through `BoundField.label_tag()`, so `for=`, multi-widget id resolution and required/aria handling survive. |
| `class` | `""` | Classes for the wrapper element (grid columns, spacing). The component emits none. |

**What it decides for you** (`docs/DESIGN-SYSTEM.md` § Forms):

- anatomy is **label → widget → help → errors**, always;
- labels carry `form-label` and **no trailing colon** — one decision applied to both the
  include sites and the 30 `{{ form }}` pages, so the two renderings cannot drift apart
  again;
- help text is `.form-text.text-secondary` carrying the `<auto_id>_helptext` id that
  Django's own `aria-describedby` already points at — **today that reference dangles at
  all 36 include sites**;
- errors are `<div class="invalid-feedback d-block">` rendering **all** of them, never
  `.errors.0`;
- the branch (fieldset / checkbox / plain) is read off the widget, never chosen by the
  caller.

**What it deliberately does not accept:** `label_class`, `help_class`, `errors=`,
`layout=`, `widget_class`. Those knobs are precisely how the estate grew 13 label-class
variants and 6 error renderings. If a call site needs a different label weight it is a
different *kind* of field — `<c-form.cell>` (dense numeric grid) or `<c-form.choices>`
(visible option list) — not a restyled one.

**There is no prop that suppresses errors.** That is the structural fix for #2001.

**Branch order matters:** `use_fieldset` is tested **first**, because
`CheckboxSelectMultiple` reports `input_type == "checkbox"` too and would otherwise be
mistaken for a single checkbox.

#### The colon, and the guard

`<c-form.field field="{{ form.name }}" />` **stringifies the widget**; every `field.*`
lookup then resolves to nothing and the component renders a plausible wrapper with no
label, no help text and — the part that matters — **no errors**. That is a verbatim
reintroduction of #2001 inside the component built to prevent it.

`{% require_bound_field %}` is called **unconditionally**, outside every `{% if %}`, on
the first line, so the mistake raises in DEBUG instead of rendering.
`scripts/check_cotton.py` rejects it at commit time and
`test_cotton_call_site_gates.py` at CI time. `COTTON_STRICT_COMPONENTS` defaults to
`DEBUG` and is forced on in `settings_dev.py` so it also fires under pytest (where
pytest-django sets `DEBUG = False`); production logs instead of 500-ing, because the two
static gates already make a mis-wired call site uncommittable.

#### Source — `gyrinx/templates/cotton/form/field.html`

Complete on disk (103 lines). Renderable body:

```django
{% load form_tags %}
{% comment %}...(API docs)...{% endcomment %}
{# djlint:off H026 #}
<c-vars field="" label="" class="" />
{# djlint:on #}
{% require_bound_field field "form.field" %}
{% if field.use_fieldset %}
    <fieldset{% if class %} class="{{ class }}"{% endif %}
        {% if field.help_text and field.auto_id and "aria-describedby" not in field.field.widget.attrs %}aria-describedby="{{ field.auto_id }}_helptext"{% endif %}{{ attrs|space_before }}>
        {% if field.label %}
            {% field_label field text=label css_class="form-label mb-1 float-none w-auto" tag="legend" %}
        {% endif %}
        {{ field }}
        {% if field.help_text %}
            <div class="form-text text-secondary"
                 {% if field.auto_id %}id="{{ field.auto_id }}_helptext"{% endif %}>{{ field.help_text }}</div>
        {% endif %}
        {% if field.errors %}<div class="invalid-feedback d-block">{{ field.errors }}</div>{% endif %}
    </fieldset>
{% elif field.field.widget.input_type == "checkbox" %}
    <div class="form-check{% if class %} {{ class }}{% endif %}"{{ attrs|space_before }}>
        {{ field }}
        {% if field.label %}
            {% field_label field text=label css_class="form-check-label" %}
        {% endif %}
        {% if field.help_text %}
            <div class="form-text text-secondary"
                 {% if field.auto_id %}id="{{ field.auto_id }}_helptext"{% endif %}>{{ field.help_text }}</div>
        {% endif %}
        {% if field.errors %}<div class="invalid-feedback d-block">{{ field.errors }}</div>{% endif %}
    </div>
{% else %}
    <div{% if class %} class="{{ class }}"{% endif %}{{ attrs|space_before }}>
        {% if field.label %}
            {% field_label field text=label css_class="form-label" %}
        {% endif %}
        {{ field }}
        {% if field.help_text %}
            <small class="form-text text-secondary"
                   {% if field.auto_id %}id="{{ field.auto_id }}_helptext"{% endif %}>{{ field.help_text }}</small>
        {% endif %}
        {% if field.errors %}<div class="invalid-feedback d-block">{{ field.errors }}</div>{% endif %}
    </div>
{% endif %}
```

It depends on `gyrinx/core/templatetags/form_tags.py` (already written), which exists
because Django templates cannot do four things: `require_bound_field` (the guard above),
`field_label` (templates cannot call a method with arguments, so `{{ field.label_tag }}`
can never carry a CSS class or replacement text — which is why 101 sites hand-write
`<label>` and throw away Django's `for` resolution and required/aria handling),
`submit_variant` (maps a semantic intent to a colour and **fails** on an unknown intent
rather than defaulting — `|default:'success'` would turn `intent="destroy"` into a green
button on a delete page), and `space_before` (whitespace-exact attribute emission).

#### The two one-line shims — the highest-leverage edits in the whole programme

Both are **already written**.

`gyrinx/core/templates/core/includes/form_field.html` → `<c-form.field :field="field" />`.
This moves **all 36 include call sites** onto the component by editing one file —
including the three that pass no `with field=` and pick `field` up from an enclosing loop
(`campaign_sub_asset_new.html:20`, `campaign_sub_asset_edit.html:19`,
`campaign/includes/asset_properties_fields.html:14`). Rewriting them by hand would put 36
chances to drop the colon into one diff for no behaviour change.

`gyrinx/templates/django/forms/field.html` → `<c-form.field :field="field" />`. Reached
because `FORM_RENDERER = "django.forms.renderers.TemplatesSetting"`. **Exact coverage,
checked against Django 6.0.7's own templates, not assumed:**

| Call | Route | Sites |
|---|---|---|
| `{{ form }}` | `as_div` → `div.html` → here | 27 |
| `{{ form.as_div }}` | `div.html` → here | 1 |
| `{{ field.as_field_group }}` | here | 2 |
| `{{ form.as_p }}` | `p.html`, which **inlines** label/widget/helptext — does **not** reach this file | 3 |

The three `as_p` sites are `admin/core/notification/broadcast.html` (Django-admin CSS) and
two vendored allauth MFA templates — surfaces the migration leaves alone by design. They
keep Django's stock rendering, and `test_cotton_call_site_gates.py` pins that list so it
cannot grow.

**So one line moves 30 sites with zero edits to any of those templates.** It also ends a
real split: this file used to be a three-branch cascade disagreeing with
`includes/form_field.html` on help text (`div.helptext.form-text` vs
`small.form-text.text-secondary`) and errors (bare `errorlist` vs
`invalid-feedback d-block`).

**Three intended visual changes on those 30 pages,** each pinned by a test and each
needing a screenshot in the PR:

1. Labels gain `class="form-label"` (margin-bottom `.5rem`, was the project's bare-label
   `.25rem`) and **lose the trailing colon**. `label_suffix=""` is passed everywhere, so
   the 101 hand-rolled `<label class="form-label">` sites then migrate byte-identically.
2. Legends gain `form-label mb-1 float-none w-auto`, so a fieldset heading renders at body
   size instead of Bootstrap's floated full-width 1.5rem reboot default. Affects
   `theme_color`, `participants`, and the pack rules/traits pickers.
3. Field errors move from **before** the widget to **after** it, inside
   `invalid-feedback d-block` (0.875em) rather than a bare 1rem `errorlist`. This is the
   anatomy the 36 include sites already use.

No recursion: `{{ field }}` inside the component is `BoundField.__str__` → `as_widget()`,
which renders `django/forms/widgets/*.html` and never re-enters. Django's renderer
resolves this file through `get_template()`, so cotton's loader compiles the tag —
`from_string()` would not.

Known cosmetic diff: Django's `div.html` already wraps each field in
`<div {{ field.css_classes }}>`, so whole-form renders emit one extra, inert nesting
level. Both are plain block divs and nothing depends on the depth. Overriding `div.html`
would mean taking ownership of the `field.css_classes` error/required hook — not worth it.

#### Before / after

```django
{# BEFORE #}  {% include "core/includes/form_field.html" with field=form.name %}
{# AFTER  #}  <c-form.field :field="form.name" />     {# or leave it — both render identically #}

{# BEFORE — one of ~200 hand-rolled blocks #}
<div>
    <label class="form-label" for="{{ form.xp_cost.id_for_label }}">XP Spend</label>
    {{ form.xp_cost }}
    {% if form.xp_cost.errors %}
        <div class="invalid-feedback d-block">{{ form.xp_cost.errors.0 }}</div>
    {% endif %}
</div>
{# AFTER #}
<c-form.field :field="form.xp_cost" label="XP Spend" />
```

That second example carries a **behaviour change to flag**: `.errors.0` renders only the
first error. 11 sites across 9 files do this. The component renders all of them — which
is the #2001 fix, and is visible on those pages. Each needs a human nod.

#### Escape hatch

- **Bootstrap control classes live in Python, not templates.** 86 `form-control`,
  48 `form-select`, 44 `form-check-input` across `gyrinx/core/forms/*.py`. A template
  component can wrap a `BoundField` but can never set the control's own class. Any "the
  component owns the control classes" design is impossible without a project-wide Widget
  base class.
- **Three SCSS rules make DOM shape load-bearing with no test coverage.**
  `.form-check > label { @extend .form-check-label; }` is a **direct-child** selector; a
  wrapper between them silently loses the styling. `.color-radio-input:checked +
  .color-radio-label` is an **adjacent-sibling** selector. `.errorlist { @extend
  .list-unstyled; color: var(--bs-danger) }` is why the 18 bare `{{ field.errors }}` sites
  look acceptable today.
- **Django widget templates cannot be components** — they are reached via
  `widget.template_name`, not `{% include %}`. All 9 are excluded (§7).
- **Fields scattered across table cells** (`list_fighter_stats_edit.html`,
  `pack/includes/weapon_profile_stats_form.html`) need widget-only mode plus a separate
  errors block. Leave raw.
- **`form="search"` cross-form association** (22 inputs, 5 submits across the filter
  includes) must survive verbatim or the filter silently posts nothing.
- **Form *properties* rendered as display text** — `{{ form.current_value }}` at
  `list_fighter_counters_edit.html:17` sits one line above `{{ form.value }}`, a real
  bound field. Any script treating `{{ form.<x> }}` as a field wraps an integer in
  `c-form.field`. Build a deny-list from the form classes: `current_value`, `method_intro`,
  `shows_count`, `fighter_rows`, `slot_fields`, `standard_fields`, `has_custom_statline`,
  `random_group_label`, `random_group_help`, `shows_random`, `shows_picks`,
  `instance.term_singular`.
- **`{{ form }}` shadowing** — `list_fighter_equipment_sell.html` iterates a Python-side
  `zip` of `(item, form)` pairs, so the inner `form` shadows the outer one. Same in
  `crew_form.html` and `crew_loadouts.html`.
- `c-form.field` never changes which fields are visible, never reads a query param, and
  has no `mode`/`variant` prop. Form variance is URL-driven and resolved in
  `Form.__init__`.

#### Unit-test plan

`gyrinx/core/tests/test_cotton_form.py` — passing. Covers: all three branches derived from
the widget, with `use_fieldset` tested first (`CheckboxSelectMultiple` must not be
mistaken for a checkbox); **errors always rendered and unsuppressible**, including
multiple errors on one field; help text carrying the `_helptext` id that
`aria-describedby` points at, block-level in the checkbox/fieldset branches and inline
`<small>` in the plain one; `label` overriding text while `for=` and required handling
survive; `require_bound_field` raising on a stringified field; the three intended visual
changes on the `{{ form }}` path (`form-label`, legend classes, error position); and the
`as_p` pin list.

---

## 4. The migration work-plan

### 4.1 Two structural decisions

**(a) One pass per file, all four patterns — not per-pattern.**

**124 of 234 in-scope files (53%) carry 2+ patterns; 34 carry 3+; 21 carry all four.**
Per-pattern passes would re-touch those 124 files 2–4 times — ~190 redundant
file-touches. The patterns are also physically interleaved: `core/index.html:31` is an
`alert alert-warning alert-icon` whose body contains a `btn btn-warning btn-sm`, so
whichever pass runs second reads a diff-modified file, not the file the inventory
described. And file-disjointness is the only cheap way to parallelise: per-pattern
batching makes files the shared resource and forces cross-batch locking.

Cost: each agent must know all four APIs. That is one skill-load, versus 190 extra passes.

**(b) Batch size: 10 files / 60 sites, whichever binds first.**

Both caps are needed because file size is bimodal — the median in-scope file has 4 sites,
`design_system.html` has 110. Ten files is the ceiling at which an agent can still hold
every file's structure in working memory for the self-diff review, which is the step that
catches the silent failures. Sixty sites is a single sustained pass at ~2 min/site
including render verification. Files over 25 sites get solo or paired batches.

Result: **33 call-site batches (including `BK1`), mean ~7.4 files / ~43 sites** — plus
`DEL0` and `GATE0`, which move no call sites. (The Sites column sums to 1,479; 1,446
excluding `DEL0` and `FR1`. §1's older "~1,190" figure was never derived from this table.)

### 4.2 Scope reconciliation

449 `.html` files in `gyrinx/` today. **The reconciliation to the brief's "402" needs two
subtractions, not one:** 449 − 39 cotton components − 8 golden HTML snapshots
(`gyrinx/core/tests/goldens/`, which are rendered output living under a `.html` extension)
= **402 exactly**. The earlier text subtracted only the components and landed on 410.

Of the 402: **251 carry at least one of the four patterns** (measured 2026-07-21 with
`btn btn-`/`class="btn`, `badge text-bg-`/`class="badge`, `alert alert-`/`border rounded`,
`form-control|form-label|form-check|form-select|invalid-feedback|includes/form_field`, and
`includes/{back,cancel}.html`). The earlier "264 pattern-bearing" figure is unreproduced
and its decomposition does not balance — `3 deleted + 17 excluded + ~24 allauth + 234
migrated = 278 ≠ 264`. **Do not quote the 264/17 split; re-derive it if a number is
needed.** What is solid:

- **238 files** are named by the batch table today (see §4.3), of which 3 are `DEL0`
  deletions → **235 migrated**.
- **`BK1` (added by this audit) adds 8 more**, all of which were pattern-bearing and in no
  batch → **243 migrated**.
- The "Never migrated" table in §7 is captioned "17 files" but names **28 distinct file
  tokens**, several of them globs that expand to 6–7 files each; the concrete count is
  roughly **32 non-allauth files plus ~24 allauth templates**. The caption is wrong; the
  list is what matters.

### 4.3 Batch table

Pattern key: **B**=buttons, **D**=badges, **C**=callouts, **F**=form fields. Paths are
relative to the worktree root.

#### Tier 0 — pre-flight (must land before any call site moves)

| ID | Files | Pat | Sites | Risk | Instructions |
|---|---|---|---|---|---|
| **DEL0** | `core/includes/alert.html`<br>`core/includes/_alert_inner.html`<br>`core/includes/empty_state.html` | C | 3 | LOW | **Delete, do not migrate.** All three verified to have **zero** call sites (`alert.html` is referenced only by itself → `_alert_inner.html`). Their prop names are already lifted into `c-callout`. Confirm with `rg -n 'includes/(alert\|_alert_inner\|empty_state)' --glob '*.html' --glob '*.py' --glob '*.js'` returning empty, then `git rm`. **Also delete `gyrinx/templates/cotton/zb/` (3 files) and `cotton/c3/` (10 files)** — 13 orphaned candidate components (risk R6); re-verified 2026-07-21 that nothing outside those directories references them. **And `rmdir gyrinx/templates/cotton/{menu,act,btn}/`** — three empty directories §7 wrongly described as holding components. |
| **GATE0** | `core/tests/test_cotton_call_site_gates.py`<br>`core/tests/test_cotton_btn.py` (**does not exist — write it**)<br>`core/checks.py`, `core/apps.py`<br>`scripts/check_cotton.py`<br>`pyproject.toml`, `.pre-commit-config.yaml` | — | — | **BLOCKER** | On disk (except `test_cotton_btn.py`) but must be green **and xdist-safe** before batch 1. **Three things, not one:** (1) **Write `test_cotton_btn.py`** — `c-btn` has ~530 call sites and zero tests today; §3.1 specifies the coverage; see D9. (2) **Add `cotton_test` to the gate's exclusion list and to `scripts/check_cotton.py`** — both scan `gyrinx/` wholesale and both pick up the badge harness's scratch templates in `gyrinx/core/templates/cotton_test/`, which contain deliberately-forbidden shapes (§2.9, D7). The previously-recommended `os.getpid()` fix is not needed and would not help. (3) Verify each gate fails on a planted violation, not just passes on a clean tree — re-verified today that `check_cotton.py` → `cotton checks: OK`, `check_raw_markup.py` → `965 sites at baseline`, and 232 tests pass with `-n 0`. Verify `extend_exclude` in `[tool.djlint]` **and** the `exclude:` on both djlint hooks and `end-of-file-fixer` (all three confirmed present today). |
| **A1** | `allauth/elements/alert.html`<br>`allauth/elements/field.html`<br>`allauth/elements/fields.html`<br>`allauth/layouts/base.html` | B C F | 20 | HIGH | Adapter batch — rewrite bodies to delegate, keep the `{% element %}` API so 60 vendored + ~83 unvendored upstream call sites stay untouched. `elements/button.html` is already done. **Three live bugs:** (1) `layouts/base.html:8` still keys on `message.tags` — route through `<c-messages />`; (2) `elements/fields.html` renders non-field errors as a `<br>`-joined loop — must agree with `c-errors`; (3) verify allauth `{% slot %}` nested inside a cotton default slot resolves; if not, capture via `{% setvar %}` first. **Smoke-test `/accounts/login/`, `/accounts/signup/`, `/accounts/email/`, `/accounts/password/reset/`.** |
| **FR1** | `gyrinx/templates/django/forms/field.html` | F | 30 sites moved | **BLOCKER** | **Already written; review it alone.** One line changes markup on 30 pages. The three intended visual changes (§3.4) each need a screenshot. Note `.errorlist { @extend .list-unstyled; color: var(--bs-danger) }` at `styles.scss:483` is why bare `{{ field.errors }}` looks acceptable today. |

#### Tier 1 — chrome and low-traffic (canary wave)

| ID | Files | Pat | Sites | Risk | Instructions |
|---|---|---|---|---|---|
| **DS1** | `core/debug/design_system.html` | BDCF | 110 | MEDIUM | **Solo, and the designated canary — first of all call-site batches.** Densest file in the repo (36 btn / 10 badge / 27 callout / 13 form), debug-gated, protected by one assertion (`test_debug_views.py:29` asserts `b"house-icon"`). Exercises every variant of all four families in one render. **Editorial decision (D4):** its raw class strings **are** the documentation, and lines 658/662/694 plus the `<pre>` at :1397 are **prose** containing `border rounded p-3`. **Recommended: keep the raw showcase verbatim, ADD a parallel "Component API" section.** Deny-list it for any script. `design_system.html:862` ("Never use `btn-success` in toolbars") contradicts `docs/DESIGN-SYSTEM.md` — reconcile or note. |
| **CH1** | `core/includes/`: `account_sidebar`, `battle_summary_card`, `featured_pack_card`, `home/campaign_row`, `home/gang_row`, `impersonation_banner`, `notification_banners`, `notification_list_item`, `notification_nav_button`, `site_banner` | BDCF | 18 | HIGH | Small but three of the worst hard cases. **`site_banner.html`: recommend leaving as a bespoke include** (DB-driven variant *and* icon, `border-0 py-2 px-0` strips alert chrome, `hstack` substitutes for `alert-icon`, dismiss is a `btn-outline` with a JS hook read at `static/core/js/index.js:581`). `notification_nav_button.html`: `{% active_aria %}` emits a whole attribute — use `current=`, never `raw_attrs`. `notification_banners.html`: a bordered box deliberately impersonating an alert with a server-side POST dismiss; its own comment explains `btn-close` is invisible in dark mode. `home/campaign_row.html:8`: conditional inside the class token — use `state=`. `battle_summary_card.html:8`: whitespace-sensitive inside an `<h6>`. |
| **CH2** | `core/layouts/base.html` | B C | 9 | HIGH | **Solo — 183 templates extend this.** The messages block (`:145-158`) becomes `<c-messages />`, shared with `A1`. **Intended visual change: flash messages gain the pinned icon — call it out in the PR.** Line 19's dice button has `{% active_aria %}` in attribute position and is icon-only with no accessible name. Verify `/` renders and the navbar is intact. |
| **DP1** | `core/debug/print_lab.html`<br>`core/print_config/{delete,form,index}.html` | BDCF | 56 | HIGH — PRINT | `print_lab.html` opens with a file-wide `{# djlint:off H021 #}`, uses `caps-label` not `form-label`, and has boxes with no padding utility and hardcoded hex backgrounds. `print_config/form.html` has `#fighter-checkboxes` and `#no-fighters-message` as DOM contracts for script that mutates `disabled`/`checked`/inline `opacity` on every child checkbox — **any wrapper between the id and the inputs breaks the descendant selector.** Its collapse-header button uses 5 of 6 utilities to *cancel* `.btn` defaults. **Open the print-lab page manually.** |
| **LA1** | `core/list/invitation_pack_setup.html`<br>`core/list/list_invitations.html` | BDCF | 9 | LOW | `invitation_pack_setup.html`: a `<label class="border rounded p-2 …" data-name="…">` wrapping a checkbox — the whole box is the click target, no `div.form-check`, no `for=`. **Keep the label-wraps-input shape.** |

#### Tier 2 — feature areas (bulk wave)

| ID | Files | Pat | Sites | Risk | Instructions |
|---|---|---|---|---|---|
| **BT1** | `core/battle/`: `battle`, `battle_archive`, `battle_edit`, `battle_end`, `battle_new`, `battle_note_add`, `battle_roles`, `battle_start` | BDCF | 32 | LOW | `battle.html:10` uses the coloured-border idiom (`border border-{colour} rounded`) invisible to `border rounded` greps. `battle.html:63,134` use `Battle.status` → `state=`. `battle_archive.html:44` bare cancel include → `<c-cancel />` with **no** `url=`. |
| **CR1** | `core/crew/`: `crew`, `crew_archive`, `crew_extra_form`, `crew_form`, `crew_loadouts`, `crew_lock`, `crew_setup` | BDCF | 57 | MEDIUM | **Rebase against `746ad616` first** — it changed `crew_setup`'s badges to a view-supplied `{{ badge.badge }}` loop. `crew.html:65` uses `Crew.status` → `state=`. `crew_setup.html:41` is the URL-driven form-variant switcher: a "field" whose control is a group of links, with `{% if entry.is_current %}aria-current="page"{% endif %}` in attribute position → `current=`. It has a sessionStorage script keyed on `{{ form.name.id_for_label }}`. `crew_form.html` iterates `row.checkbox`/`row.set_field` — the inner `form` shadows the outer. |
| **CA1** | `core/campaign/`: `campaign`, `campaign_action_outcome`, `campaign_actions`, `campaign_add_lists`, `campaign_arbitrators`, `campaign_archive` | BDCF | 59 | MEDIUM | `campaign.html:38` pin button — conditional variant + title + **icon suffix** (`bi-pin-angle{% if %}-fill{% endif %}`); **keep icons in the slot**. Sibling star button at `includes/list.html:136` is in HOT2 — do not deduplicate across batches. `campaign_add_lists.html:79-102`: 3 btn-check `<label class="btn …">` → `tag="label"`. `campaign_action_outcome.html:22` butts dice badges together — **the trailing-newline case**. |
| **CA2** | `campaign_asset_{edit,new,remove,transfer,type_edit,type_new,type_remove}`, `campaign_assets`, `campaign_attribute_type_{edit,new}` | B C F | 37 | LOW | `campaign_assets.html:52,147` icon-only dropdown toggles with **no accessible name** — the gate test fails unless `label=` is added. **A human must invent the wording; record it in the batch report.** The `*_remove.html` confirm alerts share a `<strong>` + `<p>` + conditional `<hr>` shape with 5 siblings in CA3/CA5 — use `heading=`. The `<hr>` inside an alert is undocumented (#2002 gap). |
| **CA3** | `campaign_attribute_type_remove`, `campaign_attribute_value_{edit,new,remove}`, `campaign_attributes`, `campaign_battles`, `campaign_captured_fighters`, `campaign_copy_from` | BDCF | 57 | HIGH | `campaign_copy_from.html:182` has `onclick="document.getElementById('id_source_campaign').value='{{ tc.id }}'; this.closest('form').submit();"` — inline JS mutating a form field, arguably violating the URL-driven-UI rule. **Forward `onclick` verbatim through `{{ attrs }}`, or rewrite as a real POST first (flag to human).** 4 "Select all" links select checkboxes **by name** in inline JS, so `name` is a contract. `:84` coloured-border idiom. `campaign_attributes.html:126` badge-as-flex-container with a DB colour in an inline `style` and a 10px dot → `c-badge.chip dot="10px"`. `campaign_captured_fighters` styles "Sold to Guilders" secondary while `campaign_lists` styles it warning — `state=` forces a decision. |
| **CA4** | `campaign_copy_to`, `campaign_edit`, `campaign_end`, `campaign_list_attribute_assign`, `campaign_log_action`, `campaign_new`, `campaign_pack_remove`, `campaign_packs`, `campaign_remove_list` | BDCF | 59 | MEDIUM | `campaign_copy_to.html`: 4 more name-based "Select all" links; `:82` coloured-border; `:120,231` take `href` from a bare context variable. `campaign_log_action.html:23`, `campaign_new.html:8` bare includes → **no `url=`**. `campaign_edit.html:8` passes `text=form.instance.name` — keep the `{% if text %}` fallback. |
| **CA5** | `campaign_reopen`, `campaign_resource_modify`, `campaign_resource_type_{edit,new,remove}`, `campaign_start`, `campaign_sub_asset_{edit,new,remove}`, `fighter_release` | BDCF | 32 | MEDIUM | **`campaign_resource_modify.html`: inline JS assigns `className` wholesale**, clobbering the component's output and hard-coding the expected string. Migrating the markup without rewriting the JS leaves a badge that reverts on first keystroke. Only `id=` on any badge. `campaign_sub_asset_{new,edit}.html:19-20` include `form_field.html` with **no `with field=`** inside a `{% for %}` — the shim handles them; do not hand-convert without `:field="field"`. `fighter_release.html:34` bare cancel. |
| **CA6** | `fighter_return_to_owner`, `fighter_sell_to_guilders`, `includes/_status_indicator`, `includes/asset_properties_fields`, `includes/attribute_type_form_fields`, `includes/attribute_value_form_fields`, `includes/campaign_list_row_actions`, `includes/campaign_lists`, `includes/property_schema_editor`, `includes/resource_type_form_fields` | BDCF | 41 | HIGH | **`property_schema_editor.html`: controls inside a `<template id="property-row-template">` cloned by JS and located by CLASS** (`row.querySelector('.property-label')`); those inputs have no `name` and serialise to a hidden JSON field. **Class strings are a JS contract; rendered markup must stay byte-stable.** `.property-row` writes padding **before** `border rounded`, so `s/border rounded p-2/` misses it. `:35` icon-only trash, no label. `asset_properties_fields.html:14` gets `field` from a dynamic `{% with field=form\|get_item:field_name %}`. `_status_indicator.html` interpolates a **responsive breakpoint** (`d-{{ collapse }}-inline-block`) into the class alongside the variant. |
| **CA7** | `core/campaign/includes/sub_asset_schema_editor.html` | B C F | 20 | HIGH | **Solo.** Same `<template>`-clone hazard with 4 class-keyed inputs and 2 icon-only buttons with no name (`:30`, `:72`). `.sub-asset-type-entry p-3 border rounded` puts padding first. **Verify the editor still adds/removes rows in the browser.** |
| **PK1** | `core/pack/`: `customise_weapon`, `house_rule_delete`, `house_rule_form`, `house_rule_picker`, `includes/_accessory_mods_picker`, `includes/_equipment_mods_picker`, `includes/fighter_default_equipment`, `includes/fighter_equipment_list`, `includes/fighter_preview_card`, `includes/weapon_profile_stats_form` | BDCF | 37 | MEDIUM | Both `_mods_picker` files use `<details class="border rounded p-2" {% if … %}open{% endif %}>` — a **non-div element with a conditional bare boolean**. → `<c-disclosure :open="form.any_fighter_stat_mod_set">` (a semantic transformation), and `:open` must be a bare variable path or the gate fails. 5 instances. `house_rule_picker.html` renders a table row as a submit button with dynamic `name`/`value` — losing either breaks `request.POST['target_id']`. **`weapon_profile_stats_form.html:27` is EXCLUDED BY NAME** (conditional `id=` attribute, §3.3). |
| **PK2** | `pack`, `pack_archived`, `pack_attachment_{add,delete}`, `pack_campaigns`, `pack_edit`, `pack_fighter_default_{assignment_remove,gear_add,psyker_powers,weapons_add}` | BDCF | 58 | MEDIUM | `pack.html`: 5 single-line `.pack-rich-desc border rounded p-2` boxes at 60–80 columns of indentation inside nested loops, carrying user HTML via `\|safe`; reflowing churns the file. **`pack_archived.html:7` is the filter trap** — `:url="a\|default:b"` silently resolves to nothing; use `url="{{ back_url\|default:pack.get_absolute_url }}"`. `pack_edit.html:8` bare back include. `pack_fighter_default_assignment_remove.html:15` coloured-border. |
| **PK3** | `pack_fighter_equipment_list_{accessory_add,accessory_edit,accessory_remove,gear_add,item_edit,item_remove}`, `pack_item_add`, `pack_item_add_stats`, `pack_item_delete` | B C F | 54 | MEDIUM | `pack_item_add.html` has a client-side `statline_type` swap flagged in #2001 as a JS-required flow — **out of scope, and X4 forbids making it easier. Leave the JS alone.** |
| **PK4** | `pack_item_edit`, `pack_item_modifiers`, `pack_lists`, `pack_new`, `pack_permissions`, `pack_weapon_mode_select`, `packs`, `weapon_profile_{add,delete,edit}` | BDCF | 44 | LOW | `pack_item_edit.html:99,179` take `href` from `{{ back_url }}`. **`pack_lists.html:68` has a join-filter title** — `title="{{ names\|join:', ' }}"`, never `:title=`. `pack_new.html:8` bare back include. |
| **IN1** | `core/includes/`: `_list_card_toggle`, `advancement_equipment_form`, `advancement_skill_form`, `campaign_captured_fighters`, `campaigns_filter`, `cancel` | BDCF | 44 | MEDIUM | **`cancel.html`: delete after confirming all 23 call sites have moved** — this is the last batch to touch it, so verify with a repo-wide grep. `_list_card_toggle.html` has a conditional icon **name**, conditional `aria-expanded` value, and a `data-gy-collapse-icon` hook on the **child `<i>`** — the strongest argument for slot-first icons. `advancement_skill_form.html` is the only size-overridden alert (`p-2 fs-7`) — pass as call-site `class`. `campaigns_filter.html` has 6 `form-check` blocks with `form="search"`. |
| **IN2** | `core/includes/`: `lists_filter`, `number_stepper`, `packs_filter`, `refund_checkbox` | B F | 40 | MEDIUM | `lists_filter.html:177` takes `href` from `{{ action }}` supplied by the includer. Filter checkboxes carry `form="search"` pointing at a form they are not nested in — must survive verbatim or the filter silently posts nothing. |
| **LF1** | `core/`: `badge_settings`, `change_username`, `dice`, `index`, `list_archive`, `list_archived_fighters`, `list_attribute_edit`, `list_clone`, `list_credits_edit`, `list_edit` | BDCF | 53 | HIGH | **`dice.html` is the densest concentration of button pathologies**: conditional variant ×2, conditional `.disabled` **class on an anchor**, `aria-disabled` in attribute position, `js-*` selector classes bound to page JS, two of only three `btn-lg` sites, and hrefs built from `{% qt %}`/`{% qt_nth %}` with **nested double quotes and filter chains inside** (verified to round-trip, but any naive regex corrupts it). **Migrate it last within this batch, or leave it raw and say so.** `badge_settings.html:18,28` are label-wraps-radio boxes — keep the shape. `list_archive.html:79` bare cancel, `:12` bare back, coloured-border with a literal ⚠️ emoji and `bg-warning bg-opacity-10` (a third tint convention). **`list_archived_fighters.html:29` is the `<span class="btn">` disabled-with-tooltip site** → `tag="span" disabled` (aria-disabled only). `index.html:31` alert body carries `flex-grow-1` and a nested `btn-warning` → `body_class=`. |
| **LF2** | `list_fighter_add_injury`, `list_fighter_advancement_{confirm,delete,dice_choice,other,select,type}`, `list_fighter_advancements`, `list_fighter_archive`, `list_fighter_assign_convert` | BDCF | 50 | HIGH | **`list_fighter_advancement_dice_choice.html:43,69` are the credit-spending disabled buttons.** Use `disabled="{% if not can_roll_dice %}1{% endif %}"`; both wrong forms are CI-blocked. `list_fighter_advancement_type.html` is the **only alert whose icon is not the variant default** (`bi-dice-6` on `alert-info`) — pass `icon=` or a script silently swaps it. It also has 3 `.errors.0` sites and `{{ form.*.id_for_label }}` JS contracts. `list_fighter_advancement_other.html` alert body carries `d-flex justify-content-between flex-grow-1` → `body_class=`. |
| **LF3** | `list_fighter_assign_{cost_edit,delete_confirm,disable,reassign,upgrade_delete_confirm,upgrade_edit}`, `list_fighter_clone`, `list_fighter_counters_edit`, `list_fighter_delete`, `list_fighter_edit` | BDCF | 50 | MEDIUM | **`list_fighter_counters_edit.html:17` renders `{{ form.current_value }}` — a form PROPERTY as display text — one line above `{{ form.value }}`, a real bound field.** Build the deny-list from §3.4. `list_fighter_assign_upgrade_edit.html:7` bare back include. `list_fighter_assign_reassign.html` has a `.errors.0` site. |
| **LF4** | `list_fighter_equipment_{sell,set_edit,sets}`, `list_fighter_injuries_edit`, `list_fighter_kill`, `list_fighter_mark_captured`, `list_fighter_narrative_edit`, `list_fighter_new`, `list_fighter_notes_edit` | BDCF | 58 | HIGH | **`list_fighter_equipment_sell.html`: a Python-side `zip` of `(item, form)` — the inner `form` SHADOWS the outer**, so a component resolving `form.X` from the wrong scope silently renders the last form's fields. Page JS reads `{{ form.price_method.html_name }}` and `.id_for_label`. Two `.errors.0` sites. **`list_fighter_equipment_sets.html` has a `{% spaceless %}` block** — cotton emits its own whitespace and inside `spaceless` the result is not what the author sees — plus an inline `onsubmit="return confirm(…)"` and a `required` input inside a dropdown-menu form. `list_fighter_notes_edit.html` is where #2001's hidden-errors bug was found; `c-form.field` is the structural fix. |
| **LF5** | `list_fighter_psyker_powers_edit`, `list_fighter_remove_injury`, `list_fighter_restore_confirm`, `list_fighter_resurrect`, `list_fighter_roll_flow`, `list_fighter_roll_flow_confirm`, `list_fighter_roll_result_remove`, `list_fighter_roll_results_edit`, `list_fighter_rules_edit`, `list_fighter_state_edit` | BDCF | 43 | HIGH | **`list_fighter_roll_flow.html:45,71` are the other two credit-spending conditional-disabled buttons.** **`list_fighter_roll_result_remove.html` has closing `</div>`s indented as if they closed OUTER elements** — valid HTML, structurally misleading; any rewrite locating the element end by indentation mis-slices this file. Its body has an inline `{% if %}` spanning a sentence including punctuation, so slot extraction must be character-exact. `list_fighter_state_edit.html` must pass `show_capture=""` to keep exactly one badge. `list_fighter_rules_edit.html:112` puts padding first. |
| **LF6** | `list_fighter_stats_edit`, `list_fighter_weapon_edit`, `list_fighter_weapon_profile_delete`, `list_fighter_weapons_accessories_edit`, `list_fighter_weapons_accessory_delete`, `list_fighter_xp_edit`, `list_new`, `list_new_packs`, `list_packs` | BDCF | 49 | MEDIUM | **`list_fighter_stats_edit.html` scatters field parts across four table cells** with row classes driven by custom attributes on `field.field` (`is_first_of_group`, `stat_def.short_name`, `base_value`) — no wrapper component can express it; leave raw. `list_new.html:7` bare back. `list_new_packs.html:49` label-wraps-checkbox with a `.pack-item` hook. |
| **LF7** | `list_post_battle_updates`, `list_skill_trees_edit`, `list_skill_trees_manage`, `notifications`, `user` | BDCF | 60 | HIGH | **`list_post_battle_updates.html` is the hardest file in this tier. RepeatedSelect**: the bound field renders N `<select>`s via a custom `render()` at `gyrinx/core/forms/post_battle.py:33`, cloned by JS via `data-pb-repeat`, then paired with `select[name^='state_']` by **name prefix** inside `[data-pb-row]` — three DOM contracts a wrapper would disturb. Its mass-XP input has an inline style (H021-suppressed), a bare boolean data attribute, and no `name`. **Its badge cascade is the colour-divergence trap** (§3.2) — explicit `variant=` per branch, **not** `state=`, and **not** the composite. `notifications.html:68` is another conditional-disabled site. `list_skill_trees_edit.html` has `onchange="this.form.submit()"` with a `<noscript>` fallback — the current URL-driven filter mechanism; removing it changes behaviour. |
| **BK1** | `core/includes/back.html` (**delete**)<br>`core/includes/advancement_progress.html`<br>`core/includes/back_to_list.html`<br>`core/campaign/campaign_resources.html`<br>`core/list_attributes_manage.html`<br>`core/list_campaign_clones.html`<br>`core/pack/customise_weapon_picker.html`<br>`core/pack/pack_activity.html`<br>`core/pack/pack_item_equipment.html` | B | 8 | LOW | **ADDED BY THE COMPLETENESS AUDIT — every one of these was pattern-bearing and in no batch.** Each of the 8 call-site files contains **exactly one** site: a `{% include "core/includes/back.html" %}`, so this is the most mechanical batch in the programme. Two of them are themselves includes (`advancement_progress.html` is 17 lines, `back_to_list.html` is 2 lines and is nothing *but* a back link) — render them via a parent page for the baseline. **This batch also owns deleting `core/includes/back.html`, which appeared in no batch at all** while `includes/cancel.html` was correctly assigned to `IN1`; without it the 119-site back-link include could never be removed and the `include-back` ratchet could never reach 0. **Run last in Wave 4**, after every other batch has moved its back links, and gate the delete on a repo-wide `rg -n 'includes/back\.html'` returning only this file. Measured today: **118 files / 122 include sites** for `back.html` and **22 files / 25 sites** for `cancel.html` — slightly under the ratchet's 119/23 because the ratchet also counts the two mentions inside `cotton/back.html`'s and `cotton/cancel.html`'s own doc comments. |
| **LF8** | `core/vehicle_confirm`, `vehicle_crew`, `vehicle_select`<br>`gyrinx/pages/templates/flatpages/default.html` | B F | 9 | LOW | **`flatpages/default.html` is in the pages app with its own base** — a script scoped to `gyrinx/core/templates/` misses it. Its back-to-top button has no `type`, seven layout utilities including `position-fixed z-1`, and `d-none` toggled by scroll JS keyed on `#back-to-top`. Its dropdown toggle also has no `type` — **omit `type` rather than defaulting it.** |

#### Tier 3 — measured hot paths (final wave, human-gated)

| ID | Files | Pat | Sites | Risk | Instructions |
|---|---|---|---|---|---|
| **PICK1** | `core/includes/fighter_gear_filter.html`<br>`core/includes/fighter_psyker_powers_filter.html` | B F | 58 | **BLOCKER** | **Two files — the instance ceiling is the risk, not the file count.** `fighter_gear_filter.html` is 296 lines, 22 button + 28 form-field sites, and contains **the single worst site in the estate** (`:77`): a conditional class **suffix** *and* a conditional **block of three attributes** in attribute position. **This is the one legitimate use of `raw_attrs`** — literal attribute text only, no `{{ }}`, no user data. It also has 12 `form-check` inputs with `form="search"` and `checked` computed by nested `{% if %}/{% elif %}` over three context vars plus `{% qt_contains %}` assignments — **hoist to the view or pass a pre-computed boolean; it is not expressible as `:checked="expr"`.** **Measure render time before and after.** |
| **PICK2** | `core/includes/fighter_skills_filter`, `core/list_fighter_gear_edit`, `core/list_fighter_skills_edit`, `core/list_fighter_weapons_edit`, `core/pack/includes/weapon_picker_filter`, `core/pack/includes/weapon_picker_table`, `core/pack/pack_fighter_equipment_list_weapons_add` | BDCF | 53 | **BLOCKER** | Unpaginated loops over a **900-item catalogue, 687 profiles, 241 upgrades**. `list_fighter_gear_edit.html` with the "all" filter on a `can_buy_any` house renders up to 900 button rows plus several hundred `form-check` triples. **The only place "cotton overhead doesn't matter" could be wrong — measure.** **`pack_fighter_equipment_list_weapons_add.html:61-62,93-94` has a LIVE BUG: a duplicate `class` attribute** (browsers keep the first; `w-auto` is dropped). Decide the intended string and record it. It nests inputs across `<td rowspan="{% if … %}2{% else %}1{% endif %}">` with `data-weapon-parent`/`-child` JS pairing — **no wrapper div is permissible anywhere.** `fighter_skills_filter.html:71` has a type-less `<button>` inside `<form id="search-skills">` — omit `type`. `list_fighter_weapons_edit.html` has a `g-col-12` alert inside a Bootstrap `.grid`. |
| **HOT1** | `core/includes/`: `blank_fighter_card`, `blank_vehicle_card`, `fighter_card_content`, `fighter_card_content_inner`, `fighter_card_cost`, `fighter_card_equipment_set_switcher`, `fighter_card_gear`, `fighter_card_stash`, `fighter_switcher`, `home/list_row` | B D C | 32 | **BLOCKER — PRINT** | **The highest-risk batch. Runs 8× on a median gang page, 13× at p90, 36× worst case — and it is the ONLY markup shared between screen and print**, gated by a hand-threaded `print` flag with three consumers (`list_print.html`, `list_fighter_embed.html`, and `list_about`/`list_notes` via `compact=True`). `fighter_card_cost.html` multiplexes print/alt/caller-override on one `{% firstof %}` variable — **use `variant="ghost"` and find every caller passing `cost_classes` FIRST.** `fighter_card_content.html` duplicates each badge as `<a>` or `<span>` across a 3-way matrix; **`.captured-badge-link` is a hook class with no CSS or JS definition anywhere — preserve it, do not assume decorative.** **The capture badge must stay under its own guard, not hoisted under `is_campaign_mode`.** `blank_*_card.html` badges are outlined placeholders whose content is five literal `&nbsp;` determining printed box width — `variant="ghost"`, and the run must survive byte-for-byte. `blank_vehicle_card.html` supplies the grid context its `.card g-col-*` children fuse borders against — **no wrapper, no class reordering.** **`fighter_switcher.html` is the only bare `.btn` with no variant** plus a bespoke SCSS hook — `variant=""` or `btn-primary` wrecks the fighter page header. `fighter_card_content_inner.html` has a badge with a bare valueless `bs-tooltip` and **no whitespace** between `{{ entry.value }}` and a child span. **Print the sheet and compare against a pre-migration PDF.** |
| **HOT2** | `core/includes/`: `list`, `list_about`, `list_common_header`, `list_fighter_weapon_assign_upgrade_form`, `list_fighter_weapon_rows`, `list_fighter_weapons`, `list_notes`, `list_row` | BDCF | 38 | **BLOCKER — PRINT** | `includes/list.html` is the flagship page body (422 lines) **and** the print-sheet body. `:407` is one of only four `<button>`s with **no `type`**, inside the embed offcanvas — **omit `type`, and flag the latent bug rather than silently changing it.** Its `data-clipboard-text` holds entity-encoded markup with encoded nested double quotes and a `{{ }}` inside — verified to round-trip, but no tool may unquote/requote it. `:136` star button (sibling to CA1's pin). `:324` grid-context box. `list_fighter_weapons.html`/`weapon_rows` use `form="weapon-{{ assign.equipment.id }}"` — **dynamic cross-form association; drop or reorder it and the submit silently posts nothing or posts to the wrong form.** `weapon_rows` renders 3 `form-check` classes per profile in `mode="add"`. |

**Reconciliation (re-derived mechanically from the table above, 2026-07-21):**
**35 batch rows** — `DEL0` (delete-only), `GATE0` (no files), and **33 call-site batches**
counting the new `BK1`. **243 migrated · 3 deleted · ~32 non-allauth excluded (+~24
allauth) · 449 total `.html` · 402 real templates.** The earlier footer said "33 batches
· 234 migrated · 17 excluded"; the batch count happened to survive only because `BK1`
replaced the row the old count was already off by.

**No file appears in two batches — this was verified mechanically, not "by construction".**
Every backticked token in the Files column was brace-expanded and resolved against the
filesystem: 0 duplicates, 1 ambiguity.

> **The one ambiguity is a real trap for an implementing agent.**
> `campaign_captured_fighters.html` **exists twice**:
> `core/campaign/campaign_captured_fighters.html` (a page, in **CA3**) and
> `core/includes/campaign_captured_fighters.html` (a partial, in **IN1**). The table names
> both by bare stem in different rows, so an agent grepping for the filename will find and
> may edit the other batch's file. **CA3 owns `core/campaign/…`; IN1 owns
> `core/includes/…`.** Neither agent may touch the other's copy.

### 4.4 Per-batch procedure

An implementing agent follows this exactly.

**Setup**

1. `cd` to the worktree root. Confirm `git status --short` shows no modifications outside
   your batch. **If another batch's files are dirty, stop and report** — batches are
   file-disjoint and a dirty foreign file means a collision.
2. Load the `gyrinx-conventions` and `design-system` skills. Read the docstrings of
   `cotton/btn.html`, `badge.html`, `callout.html`, `box.html`, `form/field.html` **in
   full**. They carry the trap list.
3. Start the dev server (`./scripts/dev.sh`) and note the port.
4. Record a **pre-migration render baseline**: `curl` each URL your templates serve to
   `/tmp/baseline/<name>.html`. For includes, render via the parent page.

**Rewrite — one file at a time**

5. **Read the entire file first.** Do not rewrite from a grep hit — the hard cases in your
   batch's instructions column are exactly the sites that look mechanical in isolation.
6. Rewrite all four patterns in one pass. Non-negotiable:
   - **Icons stay in the slot.** Never an `icon=` prop.
   - **Never `{% if %}` in attribute position** on a `<c-*>` tag. Use
     `prop="{% if x %}1{% endif %}"` or `raw_attrs`.
   - **`:prop` values must be bare dotted paths.** No `not`, no filters, no comparisons.
   - **`:` only on props the component declares.**
   - **Never pass `return_url=`** to `<c-back>`/`<c-cancel>`.
   - **No implicit spacing.** Spacing arrives as call-site `class=`.
   - **Preserve every JS-hook class, `id`, `name`, `value`, `form` and `data-*` verbatim.**
   - **Inside `{% for %}`, never `{% if x %}{% url … as u %}{% endif %}`** — assign
     unconditionally, gate inside the attribute value.
7. If a site cannot be expressed cleanly, **leave it raw and record why.** A raw site with
   a one-line justification is a better outcome than a wrong component.

**Verify — all of these**

8. **Render check.** Re-render and diff against `/tmp/baseline/`. Compare structurally
   (parse with `html.parser`, compare `(tag, sorted attrs, collapsed text)`), then a
   **third pass on inter-element whitespace** (`re.sub(r'>\s+<','><',…)`) applied only
   where the legacy source had none. Known-acceptable: `&` → `&amp;` in interpolated
   hrefs, attribute order. Everything else is a regression.
9. `python3 scripts/check_cotton.py` — the seven gates. **Do not work around them.**
10. `./scripts/fmt.sh` — 0 errors. Run **twice**; the second must report 0 files updated.
    **Run it BEFORE the equivalence check, never after** — otherwise you validate
    pre-format markup that CI will then reformat.
11. `pytest -n auto gyrinx/core/tests/`. Watch the 11 markup-asserting canaries (§5.4).
12. **Self-diff review.** Read every hunk against: any `{%` inside a `<c-` tag? any
    `:prop` with a filter or `not`? any `disabled` that could render as `disabled="False"`?
    any dropped `form=`/`name=`/`value=`/`id=`? any icon-only button without `label=`? any
    component emitting `mb-*`? any `<c-back`/`<c-cancel` with `return_url=`?
13. **Browser check** for any HIGH/BLOCKER batch and every print-flagged file: load the
    page, exercise dropdowns/collapses/tooltips, submit one form, render the print sheet.
14. `rg -n '<c-' <your files>`, then confirm the rendered HTML contains **no** `<c-`
    residue.

**Return**

15. Report: batch id, files changed, sites converted, **sites deliberately left raw with
    reasons**, any bug found in passing, any visual change, and the render-diff result per
    URL. **Do not write a summary `.md` file.**

### 4.5 Sequencing and human checkpoints

```
WAVE 0  DEL0 → GATE0 → A1 → FR1                          [serial, 4]
        ▲ CHECKPOINT 1
WAVE 1  DS1 (solo canary)                                [serial, 1]
        ▲ CHECKPOINT 2 — visual diff of the design-system page
WAVE 2  CH1 ∥ CH2 ∥ DP1 ∥ LA1                            [parallel, 4]
        ▲ CHECKPOINT 3 — chrome renders on every page
WAVE 3  BT1 ∥ CR1 ∥ CA1..CA7 ∥ PK1..PK4 ∥ IN1 ∥ IN2      [parallel, 15]
WAVE 4  LF1..LF8                                         [parallel, 8]
        BK1 (back-link sweep + delete includes/back.html)  [SERIAL, LAST in wave]
        ▲ CHECKPOINT 4 — mid-programme review
WAVE 5  PICK1 ∥ PICK2                                    [parallel, 2]
        ▲ CHECKPOINT 5 — RENDER BUDGET
WAVE 6  HOT1 → HOT2                                      [SERIAL, 2]
        ▲ CHECKPOINT 6 — PRINT + FIGHTER CARD
```

**Checkpoint 1.** Confirm the gates fail on planted violations (not just pass on a clean
tree), `manage check` errors when `django_cotton` is removed, and `/accounts/*` render.
**`FR1` alone changes 30 pages** — read that diff before anything else lands.

**Checkpoint 2.** `DS1` exercises every variant of all four families in one render.
Screenshot side by side. If the API is wrong, this is where it costs one file, not 234.

**Checkpoint 3.** `base.html` is extended by 183 templates. Confirm messages, navbar, site
banner and notification banners logged-in and logged-out. **The flash-message icon change
is visible here — get explicit sign-off.**

**Checkpoint 4.** ~190 files done. Sample diffs for drift in escape-hatch usage; check
`raw_attrs` is still ~5 sites (if it has spread, the API is being misused).

**Checkpoint 5.** **Add render-timing assertions on (a) a 20-fighter gang detail page and
(b) an unfiltered `list_fighter_weapons_edit` page BEFORE `HOT1` runs.** Without them a
perf regression ships silently.

**Checkpoint 6.** Print the sheet against a pre-migration PDF. `print.scss` is 7 lines
(`@import "./styles"` + `body { zoom: 50% }`), so **print correctness lives entirely in
these templates.** Also verify `list_fighter_embed.html` (the third, easily-missed
consumer of the `print` flag) and the `compact=True` paths.

**A third ordering constraint added by this audit:** `BK1` must run **after every other
batch**, because it deletes `core/includes/back.html` and 30+ batches still include it
when they start. If `HOT1`/`HOT2`/`PICK*` are deferred (D6), check whether any deferred
file still includes `back.html` before deleting it — if so, `BK1` converts its 8 files but
leaves the include in place, and the delete moves to the follow-up PR.

**Two non-negotiable ordering constraints:** `HOT1` before `HOT2` (both touch the
fighter-card chain; `HOT2`'s `includes/list.html` is its parent), and `PICK2` before
`HOT2` (`list_fighter_weapon_rows.html` is rendered by `list_fighter_weapons_edit.html`,
and the `mode="add"` form-check triples are the shared surface). Everything else in waves
3–4 is genuinely parallel-safe because the batches are file-disjoint.

### 4.6 Expected diff size

Roughly **+7,500 / −5,000 lines**, plus ~300 deleted from the dead includes and ~13
orphaned components.

The driver is djlint, not the rewrite. With `custom_html`, a one-line
`<button class="btn btn-primary btn-sm">Edit</button>` becomes a three-line `<c-btn>`
block, so **~530 button sites alone contribute ~1,000 extra diff lines** before any
semantic change. Callouts shrink (6 lines → 2), forms shrink substantially (12 → 1),
badges are roughly neutral. See Open Decision D1.

---

## 5. Verification and safety net

### 5.1 Render-equivalence harness

Built and passing. Files:

| Path | Purpose |
|---|---|
| `gyrinx/core/tests/test_render_equivalence.py` | The harness — 8 pages |
| `gyrinx/core/tests/render_world.py` | Determinism (UUID/timestamp pinning) |
| `gyrinx/core/tests/render_normalise.py` | Three-tier comparison |
| `gyrinx/core/tests/goldens/` | 8 captured goldens, 272 KB |

**Capture the goldens on `main` and commit them as the branch's first commit:**

```bash
git checkout main
cp -r <branch>/gyrinx/core/tests/{render_world.py,render_normalise.py,test_render_equivalence.py} \
      gyrinx/core/tests/
GOLDEN=write pytest gyrinx/core/tests/test_render_equivalence.py -n 0 -q
git checkout -b cotton-bigbang && git add gyrinx/core/tests/ \
  && git commit -m "test: capture pre-migration golden HTML"
```

Then on every commit: `pytest gyrinx/core/tests/test_render_equivalence.py -n 0 -q`.
**Use `-n 0`** — xdist reorders work and the harness writes `*.actual.html` on failure.

**Determinism is pinned at source, not regexed out:**

| Source | Treatment |
|---|---|
| UUID pks | Swap `field.default` on every UUID pk. **Patching `uuid.uuid4` does not work** — `Base.id` is `UUIDField(default=uuid.uuid4)` (`gyrinx/models.py:143`) and the function object binds at import. |
| `created`/`modified` | `queryset.update()` bypasses `auto_now` |
| `{% cachebuster %}` | `random.seed(1)` before each request (`custom_tags.py:381` uses `random.random()`) |
| CSRF | The only unavoidable scrub — regex on the `csrfmiddlewaretoken` value |

Verified stable (three consecutive byte-identical runs) and sensitive (injecting one extra
space into a `class` attribute failed the run; reverting passed it).

**Normalisation policy: byte equality is the default.** Every normalisation is a class of
bug the harness stops seeing, so each is opt-in per page via the `ACCEPTED` dict in
`render_normalise.py`, with a written reason. Measured tier behaviour:

| Change | Tier 1 bytes | Tier 2 structural | Tier 3 gaps |
|---|---|---|---|
| djlint whitespace between badges | fails | **passes (blind)** | **fails** |
| attribute order (`type` vs `class`) | fails | passes | passes |
| class order within attribute | fails | passes | passes |

**Tier 3 runs whenever Tier 2 runs**, so relaxing attribute order can never silently relax
whitespace. This matters because **djlint is itself a source of visual regression**:

```
BEFORE djlint: '<span class="badge text-bg-danger">1</span><span class="badge text-bg-danger">2</span>'
AFTER  djlint: '<span class="badge text-bg-danger">\n    1\n</span>\n<span …>\n    2\n</span>'
```

`.badge` is `inline-block`, so the gap renders as a visible space. `extend_exclude`
protects component *files*; it does **not** protect *call sites*.

**Coverage — extend from 8 to ~25.** Currently: `index`, `lists`, `list-detail`,
`list-about`, `list-edit`, `list-print`, `fighter-edit`, `dice`. There are 248 named
`core:` URLs. Add, in priority order:

- **Density**: `core:list-fighter-gear-edit`, `core:list-fighter-weapons-edit`,
  `core:list-fighter-skills-edit`
- **All four families on one page**: `core:campaign`, `core:campaign-actions`, `core:pack`
- **Error paths**: POST an invalid form to `core:lists-new`
- **Print**: `core:list-print` ✓, `core:list-fighter-embed`
- **Messages**: any redirect with `follow=True`
- **allauth**: `/accounts/login/`, `/accounts/signup/`
- **Permission branches**: a logged-out and a non-owner render of `core:list` — they
  change which badges are `<a>` vs `<span>`

### 5.2 Grep ratchet

```bash
python3 scripts/check_raw_markup.py            # enforce
python3 scripts/check_raw_markup.py --update   # re-baseline after a batch
python3 scripts/check_raw_markup.py --list btn # remaining sites
```

Baseline (`scripts/raw_markup_baseline.json`), excluding cotton internals,
`design_system.html`, error pages, admin trees and goldens — **965 sites**:

```json
{"alert": 80, "badge": 94, "border-rounded": 83, "btn": 502,
 "include-back": 119, "include-cancel": 23, "include-form_field": 37,
 "invalid-feedback": 27}
```

`include-back 119` / `include-cancel 23` independently reproduce the briefing's figures.

**It fails in both directions** — verified. An *increase* is new hand-written markup; a
*decrease* is a stale baseline, which also fails, so slack cannot accumulate and the
ceiling stays tight. The goldens directory must stay excluded — during construction the
ratchet counted rendered output and reported a phantom `btn 662 → 582` drop.

### 5.3 djlint gate and pre-commit

All three exclusions are in place (§2.4). Verified: `djlint gyrinx --check` → `0 files
would be updated`.

**Two gates exist but are not wired into pre-commit.** `scripts/check_cotton.sh` claims
"Wired into pre-commit and CI" — it is in CI only (via `pytest`); `grep cotton
.pre-commit-config.yaml` returns nothing but `exclude:` paths. On a branch doing hundreds
of mechanical edits the loop should be seconds, not a push. Add:

```yaml
  - repo: local
    hooks:
      - id: check-cotton
        name: cotton call-site safety
        entry: ./scripts/check_cotton.sh
        language: script
        pass_filenames: false
        files: \.html$
      - id: check-raw-markup
        name: raw Bootstrap markup ratchet
        entry: python3 scripts/check_raw_markup.py
        language: system
        pass_filenames: false
        files: \.html$
```

CI (`.github/workflows/format-check.yml`) runs `djlint --profile=django --lint --check .`
— add both scripts as steps there too, since pre-commit is opt-in locally.

### 5.4 Brittle existing tests

Measured by rendering, not guessed. The perf briefing named 6 files; there are **11**.

| Test | Assertion | Verdict |
|---|---|---|
| `test_edit_single_weapon_no_standard_profiles.py:111` | `<button type="submit" class="btn btn-link btn-sm icon-link">` | **BREAKS** — `c-btn` emits `class` before `type`. Rewrite to assert on parsed attrs. |
| `test_illegal_equipment_visibility.py:185,201` | `class="btn btn-outline-primary btn-sm dropdown-toggle disabled"` | Survives — verified identical |
| `test_accessory_ui_display.py:90` | `<span class="badge text-bg-secondary">10¢</span>` | Survives — **keep as a whitespace canary** |
| `test_xp_tracking.py:446` | `badge text-bg-primary">8 XP</span>` | Survives — **keep; asserts content abuts `>`** |
| `test_notification_badge.py:51,62` | `badge rounded-pill text-bg-danger` | Survives — pill before colour |
| `test_new_list_form_errors.py:47` | `"errorlist" or "invalid-feedback"` | Robust (permissive `or`) |
| `test_injury_forms.py:175,179` | `widget.attrs["class"] == "form-select"` | **Not template-coupled** — asserts Python widget attrs |
| `test_campaign_assets.py`, `test_badge_views.py` | markup fragments | Check during CA2/CA5 |
| `test_debug_views.py:29` | `b"house-icon"` | The only assertion protecting the 1,680-line showcase |

**Do not "fix" the three canaries into robustness** — their precision is the point.

**The perf snapshot cannot be tripped — but not for the reason stated.**
`test_performance_view_queries.py` renders `core/list_performance.html`, which extends
`foundation.html` (not `base.html`). **It does NOT contain "zero target patterns":** line 7
is `<div class="border rounded m-2 mb-3 p-2 mb-last-0 text-secondary">`, a
`c-box compact` candidate. Verified 2026-07-21. The conclusion (leave it alone) is still
right — one box is no upside against a 74-query snapshot — but the justification must be
"one low-value site behind the repo's only SQL guard", not "nothing to convert". Same
correction applies to the §7 exclusion row.

**There are no screenshot tests, no render budgets and no HTML snapshots** in this repo
outside what this branch adds.

### 5.5 Visual verification

HTML diffing cannot see computed colour, flex/grid geometry, focus rings, print
pagination, dark mode, or a `pointer-events:none` that kills a tooltip. Check at **375 px
(mobile-first), 768 px, 1400 px**, in **both light and dark**:

1. **`/list/<id>`** — the flagship. 95% of badge and 60% of button instances are inside
   the fighter loop.
2. **`/list/<id>/print`** — the ghost badge variant. If it fails the sheet becomes solid
   grey blocks.
3. **`/list/<id>/fighter/<id>/gear/edit`** with the "all" filter — up to 900 rows.
4. **The breadcrumb back link** on any of 119 pages — should be a **zero-pixel** change.
5. **Flash messages** — they *gain* icons. Intended; must be seen and called out.
6. **`/accounts/login/`, `/accounts/signup/`** — the adapter fixes `tags="secondary"` and
   `"link"` mappings, so Cancel buttons legitimately change colour.
7. **`/content/design-system/`** — the densest file, 177 target sites.
8. **Disabled controls** — `list_archived_fighters.html:29` (a disabled `<span>` whose
   tooltip must still fire) and the dice-choice buttons.

Use the `dev-server` skill for the port, then Claude in Chrome. Take before/after
screenshots at the merge-base for the same 8 pages.

### 5.6 Commit / PR structure and rollback

A 400-file squashed commit is unrevertable in practice and unbisectable by construction.
Ship a **stack of small, independently green commits**:

```
1  test: capture pre-migration golden HTML          <- from main, no template changes
2  chore: cotton install + settings + djlint config
3  feat: add cotton components + unit tests         <- ZERO call sites; goldens must still pass
4  chore: add raw-markup ratchet + wire gates
5  refactor: migrate campaign templates             <- one batch
…  one commit per batch
N  refactor: migrate fighter card                   <- LAST
```

**Commits 1–4 change no rendered output.** The harness must pass at commit 4 with goldens
captured at commit 1 — that proves the infrastructure is inert before any template moves.

Six PRs, each independently revertible:

| # | Contents | Files | Conflict risk |
|---|---|---|---|
| 1 | Components + settings + djlint + gates. **Zero call sites.** | ~45 new | none |
| 2 | `allauth/elements/*` adapters | ~8 | none |
| 3 | Cold decile (untouched in 90 d) | ~140 | very low |
| 4 | Warm decile | ~60 | low |
| 5 | Hot decile — **one file per PR** | ~20 | high |
| 6 | Fighter card + pickers — recommend deferring (§7) | ~25 | highest |

PR 1 is the one needing real scrutiny and is small enough to get it. PRs 3–4 are
reviewable **by rendered-diff artefact, not source diff** — a CI job that renders N
fixture pages before and after and posts the normalised delta as a comment. If that delta
is empty, the source diff needs no line-by-line reading. **That is the only way 234 files
becomes reviewable**; djlint alone adds ~1,000 formatting lines, and Copilot/CodeRabbit
sample large diffs rather than read them.

**Never re-baseline goldens mid-branch.** If a batch legitimately changes output, add an
`ACCEPTED` entry with a reason — a reviewable line — rather than overwriting the golden,
which is invisible.

**Bisect** (~4 s/step for the harness, ~64 s for the core suite):

```bash
git bisect start HEAD <merge-base>
git bisect run pytest gyrinx/core/tests/test_render_equivalence.py -n 0 -q
```

**Rollback after merge.** `git revert <batch-sha>` undoes one directory. Components,
config and ratchet stay; only call sites revert — and because components are additive, a
reverted call site still renders. **The one thing that cannot be reverted piecemeal is
commit 2** (settings), because cotton fails open (§2.7); `gyrinx/core/checks.py` guards it.

**Merge with a merge commit, not a squash** — squashing destroys the bisectability the
whole structure exists to provide. Note `main` currently squash-merges (zero merge commits
in 60 days), so this needs an explicit exception — Open Decision D5.

---

## 6. Risk register

Ranked by expected cost. Every figure measured in this worktree.

### R1 — Conflict resolution silently discards other people's fixes
**Likelihood: near-certain. Blast radius: unbounded and undetectable. Rank: 1.**

`main` took **9 commits in the last 24 hours**; PRs merge in 20–90 minutes; **155 distinct
`.html` files were touched in 60 days** against a scope of 234.

The proof is already in the tree. `746ad616` landed today:

```diff
-{% if row.status %}
-    <span class="badge text-bg-secondary fw-normal ms-1">{{ row.status }}</span>
-{% endif %}
+{% for badge in row.status_badges %}
+    <span class="badge {{ badge.badge }} ms-1">{{ badge.label }}</span>
+{% endfor %}
```

It fixes badge colour-coding on crew setup **and invents a markup shape that did not exist
when `c-badge` was designed** — a runtime class from a view-supplied dict, which `state=`
cannot absorb. A branch cut before today rewrote the old line into `<c-badge>`; on rebase
git shows a conflict and the obvious resolution keeps the component and drops the loop.
The badges go back to uncoloured, the suite stays green, and the fix is reverted 24 hours
after it shipped.

Hot files are also dense files — the worst correlation:

| File | commits/60d | target lines |
|---|---|---|
| `core/campaign/campaign.html` | **12** | 12 |
| `core/includes/list.html` | 8 | 17 |
| `core/layouts/base.html` | 7 | 11 |
| `core/crew/crew.html` | 6 | 17 |
| `core/pack/pack.html` | 5 | 24 |
| `core/debug/design_system.html` | 4 | **140** |
| `core/includes/fighter_card_content.html` | 3 | 13 |

**Mitigations, by value:**
1. **Order batches by coldness, not tidiness.** Compute per-file churn
   (`git log --since=90d --name-only`) and convert in ascending deciles. The ~140 templates
   untouched in 60 days are near-zero-conflict and are 55% of scope. The top decile goes
   **last, one file per PR, landing inside an hour.**
2. **`git rerere` on, rebase not merge.** Main squash-merges, so every rebase re-presents
   the same conflicts.
3. **A conflict checklist in the PR template**: for every conflicted hunk, diff the
   *rendered* output of both sides, not the source. Any conflict in a file whose `main`
   side changed logic gets re-derived from `main`, never merged by hand.

**Early warning:** a daily CI rebase-dry-run on the migration branch reporting conflicted
file count. Above ~15 files, stop adding scope and land what you have.

### R2 — A 234-file diff is rubber-stamped, not reviewed
**Likelihood: certain. Blast radius: everything R3/R4 would otherwise catch. Rank: 2.**

Mitigation is the six-PR stack plus the **rendered-diff CI artefact** (§5.6). If that job
cannot be built in a day, the big bang is not reviewable and the batching must get finer
instead.

### R3 — Visual regressions no test can catch
**Likelihood: high. Blast radius: user-visible, found by users. Rank: 3.**

Only 11 pre-existing tests assert on Bootstrap markup, and the components emit the same
classes, so they pass either way. Not caught by any test: a dropped `ms-2`/`mb-0`;
`<div class="badge">` → `<span>` changing a line box; the `.alert-icon` flex contract
breaking if icon and body stop being direct children; flash messages gaining icons; the
`aria-current` removal across 119 pages.

**Mitigation:** the golden harness (§5.1) plus a **scripted class-token diff** — extract
the multiset of CSS classes per page before and after and assert equality. That catches
every dropped utility class mechanically, which eyeballing 234 files will not.

**Early warning:** run the class-token diff on the first 10 converted files. If it is not
empty, the rewrite is lossy and the remaining 224 will be lossy the same way.

### R4 — Silent cotton failures on shapes the gates don't know about
**Likelihood: medium-high. Blast radius: inert controls that spend credits. Rank: 4.**

The gates are real and enforced (§2.6), and both were verified to fail on planted
violations. The residual risk is that **gates only catch shapes that existed when they
were written**, and `main` invents shapes weekly — one arrived today. Plus two gaps:
`check_cotton.sh` is CI-only, not pre-commit (§5.3), and cotton fails open (§2.7) — verify
Cloud Build actually runs `manage check` before deploy or that guard is decorative.

**Early warning:** any gate failure on a file `main` touched recently — that is a new
shape, and it means the inventory is stale.

### R5 — The print sheet, which shares markup with the hot path and has no tests
**Likelihood: medium. Blast radius: silent until a user prints. Rank: 5.**

**21 templates** gate markup on `print`/`compact`. `list_print.html` reuses the entire
fighter-card stack via `{% include "core/includes/list.html" with print=True %}`, with
three independent flag consumers. The flag changes real markup, not just CSS
(`fighter_card_cost.html` swaps `text-bg-secondary` → `text-body border fw-normal`), and
`print.scss` is 7 lines, so print correctness lives entirely in the templates.

**Mitigation:** the `ghost` variant exists for exactly this. Do not migrate any of the 21
in the mechanical batches — they go in `HOT1`/`HOT2` with before/after PDF comparison on a
20-fighter gang.

### R6 — Two orphaned component namespaces are in the tree right now
**Likelihood: already happened. Blast radius: dead code shipped. Rank: 6.**

`gyrinx/templates/cotton/zb/` (3 files) and `cotton/c3/` (10 files) are parallel agents'
candidate variants, divergent from the chosen set: `badge.html` 100 lines vs
`zb/badge.html` 52; `callout.html` 111 vs `c3/callout.html` 29; `box.html` 71 vs
`c3/box.html` 3. **Verified: nothing outside those directories references them.** If a
rewrite script is aimed at the wrong prefix, or if they ship, you get a dead second design
system on day one.

**Mitigation:** delete both before PR 1 (batch `DEL0`). Add a test asserting the component
directory contains no unreferenced components.

> **Two corrections to this risk, both verified 2026-07-21.**
>
> 1. **`cotton/form/actions.html` does NOT hand-roll `btn btn-{{ variant }}`.** Read the
>    file: after `{% submit_variant intent as variant %}` it renders
>    `<c-btn type="submit" variant="{{ variant }}" size="{{ size }}" …>` and
>    `<c-cancel url="{{ cancel }}" text="{{ cancel_text }}" />`. It delegates correctly.
>    The `btn-success`/`btn-danger`/`btn-primary` strings the grep found are in its
>    **API-doc comment** describing the intent→variant map. There is no follow-up to point
>    at it. (`submit_variant` in `form_tags.py` is where those literals actually live —
>    Python, not a template, and outside the ratchet either way.)
> 2. **The early-warning grep is wrong twice over.** `grep -c 'btn-'
>    gyrinx/templates/cotton/*.html` names **six** files today — `btn.html`, `box.html`,
>    `callout.html`, `cancel.html`, `confirm.html` — and misses the subdirectories
>    entirely (`form/actions.html`, `form/stepper.html`, `filter/query.html`,
>    `c3/callout.html` all contain it). Most hits are comments; `callout.html:107` is a
>    **real emitted `class="btn-close"`**, which is correct — the dismiss button is part of
>    the alert's anatomy, not a `c-btn`. **Either drop the "only file with `btn-`"
>    invariant (recommended — it was never true) or restate it as: no file under
>    `gyrinx/templates/cotton/` may emit `btn btn-<variant>` outside `btn.html`, checked
>    against renderable lines only, `rg -g '!c3' -g '!zb' --multiline`, with `btn-close`
>    whitelisted.** As written, the grep would fail on day one and be disabled.
>
> Also: `gyrinx/templates/cotton/{menu,act,btn}/` exist on disk but are **empty
> directories**. §7 lists them as containing out-of-scope components; they contain
> nothing. Git does not track empty directories, so they will not ship — but `rmdir` them
> in `DEL0` so nobody looks for the components §7 promised.

### R7 — Performance in the two loops that matter
**Likelihood: low-medium. Blast radius: slow pickers. Rank: 7.**

Fighter card: negligible (§2.8). The pickers: 300–900 components per request, 3–8 ms,
probably fine — but there is no render-timing guard in this repo, so nothing would tell
you. **Mitigation:** measure before/after on an unfiltered weapons-edit page for a
`can_buy_any` house; add `DEBUG_TOOLBAR_CONFIG = {"SKIP_TEMPLATE_PREFIXES": ("cotton/",)}`.
**Early warning:** local dev feels slow on the gear picker. Nothing automated will tell you.

### R8 — allauth: low interaction risk, one specific trap
**Likelihood: low. Blast radius: total if it breaks. Rank: 8.**

Measured: **222 `{% element %}` uses across 40 vendored templates**; we vendor 21 element
templates, upstream ships 22 (`details.html` is not vendored); **39 upstream templates**
call `{% element button %}` and resolve our override from `DIRS`.

The adapter approach is right and already done. The trap that was closed: upstream
`account/base_confirm_code.html:42` is `{% element button form="resend" %}` with **no
type**, relying on HTML's implicit `submit`; `c-btn` omits an empty `type`, which
preserves it. Residual risk is that these flows are not in the golden harness. Cheap
insurance: smoke tests on `/accounts/login/`, `/accounts/signup/`,
`/accounts/password/reset/` asserting 200 and no `b"<c-"`.

**Do not migrate the 219 `{% element %}` call sites** — they are re-vendored on every
allauth upgrade; migrating converts a re-vendor into a re-migration, forever.

### R9 — Rollback is all-or-nothing if it is one PR
**Likelihood: low. Blast radius: defines your worst day. Rank: 9.**

Mitigated by §5.6. Note `COTTON_STRICT_COMPONENTS = DEBUG` means **production is lenient**
— a mis-wired call site degrades quietly in prod while erroring in dev. That is the right
choice for uptime; just know prod will not tell you.

### R10 — Email and string-rendered templates
**Likelihood: nil for email. Rank: 10.**

All 56 `.txt` templates are allauth email bodies; no HTML email templates exist; no
`EmailMultiAlternatives`/`html_message` in non-test code. Out of scope by construction.
**The thing to check:** cotton compiles in the loader, so `Template(string)` /
`from_string()` pass `<c-*>` through verbatim and silently. If any notification or
admin-authored content is ever rendered from a string, components are unusable there — and
fail without an error.

---

## 7. Explicitly out of scope

### Never migrated — ~32 non-allauth files (the "17" caption was wrong)

The table below names 28 distinct file tokens, several of them globs; expanded, that is
roughly **32 concrete non-allauth files plus ~24 allauth templates**. Counted 2026-07-21.

**Correction to the Django-admin claim.** The maintenance group (6 files) genuinely
returns **zero** hits for `btn btn-`/`badge text-bg`/`alert alert-`/`form-control`/
`border rounded` — re-verified. The `core/admin/` group does **not**:
`core/admin/show_verification_links.html:47` carries `class="form-control"`. Exclusion is
still correct (it is Django-admin chrome and converting it buys nothing), but "zero hits"
is false and should not be repeated as the reason.

| Files | Why |
|---|---|
| `core/admin/{add_users_to_group,remove_users_from_group,show_verification_links}.html`, `content/copy_selected_to.html`, `admin/core/notification/broadcast.html`, `templates/admin/{base_site,gyrinx_change_form}.html` | Django-admin CSS vocabulary. Bootstrap components would visually break the admin. |
| `gyrinx/maintenance/templates/admin/maintenance/*.html` (6) | Page-local `<style>`, `mt-*` classes, 0 Bootstrap hits |
| `gyrinx/analytics/templates/analytics/admin/dashboard.html` | Django-admin, 0 hits |
| `gyrinx/templates/404.html`, `500.html`, `errors/error.html` | **Error tree.** Rendered by `handler404`/`handler500` when the app may be degraded; a component-resolution failure would 500 the 500 page. `500.html` also has no `{% extends %}`, its own `<head>`, and no guarantee that context processors ran. |
| `core/list_performance.html` | Behind the repo's only SQL perf guard. Contains **one** low-value site (`:7`, a `border rounded … p-2` box) — **not zero, as previously stated**. Nothing to gain, a 74-query snapshot to break. |
| `core/widgets/color_radio_{option,select}.html`, `pages/forms/widgets/bs_*.html` (6+) | **Django widget templates**, reached via `widget.template_name`, not `{% include %}`. `color_radio_option.html` depends on an adjacent-sibling SCSS selector. Cannot be components without rewriting the widget classes. |
| `core/includes/classic_card.html`, `classic_sheet.html` | 226 lines of print markup, **zero** target patterns, 810 lines of dedicated SCSS |
| `core/layouts/foundation.html`, `base_print.html` | Pure document scaffolding, zero target patterns |
| `core/templates/{account,mfa,usersessions}/**` (~24) | allauth-shaped; covered by the `A1` adapters. Migrating them costs ~⅓ of the button work for zero user benefit on templates re-vendored on every allauth upgrade. |
| `core/includes/site_banner.html` | Every axis DB-driven, alert chrome deliberately stripped, JS-hooked dismiss. Recommend leaving as a bespoke include (§3.3). |
| `pages/forms/widgets/bs_checkbox_select_compact.html:8`, `core/pack/includes/weapon_profile_stats_form.html:27` | **Excluded by name**: conditional `id=` attribute inside the tag, which fails non-deterministically. Both carry the `id` that `index.js` queries for the filter widget. |

### Deleted, not migrated — 3 + 13 files

`core/includes/{alert,_alert_inner,empty_state}.html` — **zero call sites**, verified.
Their prop names are already lifted into `c-callout`. Plus `cotton/zb/` (3) and
`cotton/c3/` (10) — orphaned candidate variants (R6).

### The ~72 pure-layout bordered boxes

Grid parents, scroll containers, responsive rows, form wrappers. They carry no callout
semantics; converting them buys nothing and each is a chance to regress a grid or flex
container. Only the ~28 notice-shaped boxes are in scope.

### Deferred, not excluded — recommend a separate PR after the big bang settles

**1. The fighter-card stack** (`HOT1`/`HOT2`). Highest render multiplier (8× median, 36×
max); **the only markup shared between screen and print**, gated by a hand-threaded flag
with three consumers; `rule.html`'s output is cached in LocMem for 300 s via `{% ref %}`,
so component edits are masked for up to five minutes per worker — a genuine debugging
trap mid-migration. Ship the big bang without it, let it settle a week, then convert it as
its own PR with printed-sheet verification.

**2. The equipment/skill pickers** (`PICK1`/`PICK2`). The only place a single request
instantiates 300–900 components. Converting them blind is the one perf bet that could
lose.

**3. `core/debug/design_system.html`** — convert deliberately, not mechanically. 140
target lines, 4 commits in 60 days: hot *and* densest. Its raw class strings **are** the
documentation, and four of the 104 `border rounded` hits are prose. **Add a parallel
component-API section rather than rewriting the showcase.** It is simultaneously the ideal
canary (`DS1`) — one page, debug-gated, every variant in one render.

### Components in the tree that are not part of this plan

`cotton/` also contains `note.html`, `confirm.html`, `disclosure.html`, `icon.html`,
`filter/{option,query,toggle}.html` and
`form/{act,actions,cell,choices,edit,errors,search,stepper}.html`
— a wider inventory built by parallel streams. (`menu/`, `act/` and `btn/` were listed
here too; they are **empty directories** — see R6. `icon.html` is *not* optional: it is
a hard dependency of `c-callout`.) **They are not in scope for the four-family
migration.** Use `c-disclosure` where `PK1`'s `<details>` boxes need it and `c-note` where
a coloured non-alert aside is genuinely wanted; otherwise leave them, and audit them for
orphans before PR 1 alongside `zb/`/`c3/`.

---

## 8. Open decisions for the maintainer

Each has a recommendation, so it can be resolved by assent.

### D1 — djlint `custom_html`: correct nesting vs ~1,000 extra diff lines
`custom_html = "c-[\w.-]+"` nests component children correctly but expands
`<c-btn>Save</c-btn>` to three lines and stacks long attribute lists. Dropping it keeps
one-line call sites and preserves adjacent-component whitespace byte-for-byte, at the cost
of flat indentation inside multi-child components. Measured both ways; both are idempotent.
The badge stream measured that dropping it is strictly better *for badges*; the setting is
shared with callouts and forms.

> **Recommendation: keep `custom_html`.** Correct nesting is worth more than compactness
> when the reviewer's problem is comprehension, and the whitespace risk is already covered
> by the harness's Tier-3 gap comparison. Budget ~1,000 extra diff lines and say so in the
> PR. **Decide before the first diff is generated** — flipping later re-churns every file.

### D2 — Flash messages gain icons
Routing both message loops through `c-callout` gives flash messages the pinned variant icon
and the `alert-icon` class they currently lack — which is what `docs/DESIGN-SYSTEM.md`
§ Feedback and the demos at `design_system.html:709` already specify. It is a visible change
on every page that flashes a message.

> **Recommendation: accept it and call it out in the PR with a screenshot.** It closes a
> documented drift. To ship without it, add `icon="none"` to the `c-callout` inside
> `messages.html` — one line, revertible in one commit.

### D3 — The three form-field visual changes on the 30 `{{ form }}` pages
Labels gain `form-label` (margin `.5rem` vs `.25rem`) and lose the trailing colon; legends
gain `form-label mb-1 float-none w-auto`; field errors move from before to after the widget
and render in `invalid-feedback d-block`. Each is pinned by a test.

> **Recommendation: accept all three.** They converge the whole-form pages onto the anatomy
> the 36 include sites already use, and #2 is a genuine improvement (Bootstrap's floated
> full-width legend default looks wrong at those sites). Screenshot `theme_color`,
> `participants` and a pack rules picker at Checkpoint 1.

### D4 — What `design_system.html` documents
Its raw class strings are the documentation, and its prose literally instructs readers to
"Use `text-bg-*` format". Migrating it makes the page document the component; leaving it
raw makes it lie about house style.

> **Recommendation: keep the raw-markup showcase verbatim and ADD a parallel "Component
> API" section** showing `<c-btn>`/`<c-badge>`/`<c-callout>`/`<c-form.field>` beside the raw
> markup. Deny-list the file for any script. Separately: `design_system.html:862` ("Never
> use `btn-success` in toolbars") **contradicts** `docs/DESIGN-SYSTEM.md` § Buttons, which
> says lifecycle actions are `btn-success btn-sm`. The component cannot encode both — it
> stays a mechanical variant+size API and the policy lives in docs. **Please reconcile the
> two documents.**

### D5 — Merge commit vs squash
`main` has zero merge commits in 60 days. Squashing this branch destroys the bisectability
the six-PR stack exists to provide.

> **Recommendation: merge each of the six PRs normally (squash is fine per PR, since each
> is coherent), but do NOT collapse the six into one.** Land them separately, in order,
> same-day each. That preserves per-PR revert without asking for a repo-wide policy change.

### D6 — Should `HOT1`/`HOT2`/`PICK1`/`PICK2` be in this migration at all?
Section 7 recommends deferring all four to a follow-up PR after the big bang settles.
That leaves the fighter card and the pickers on raw markup for a week or two, so the
ratchet cannot go to zero and the "only file with `btn-`" invariant is not yet true
estate-wide.

> **Recommendation: defer them.** They are 4 of 33 batches and carry three of the four
> BLOCKER ratings. Deferring removes the print risk, the render-budget dependency and the
> highest-churn files from a diff that already needs a novel review mechanism. Ship the
> other 29 batches, prove the components in production for a week, then take these four as
> a focused PR with printed-sheet and render-budget verification.

### D7 — The xdist race in the gate tests *(diagnosis corrected — this is no longer a decision, just a fix)*
The original entry said parallel workers collide on scratch **filenames**. They do not:
`test_cotton_badge.py:47` already uses `uuid.uuid4().hex`, and the gate already filters
`_cotton_test*` / `_probe*` / `_cotton_test_host/` and swallows `FileNotFoundError`. The
real hole is that the gate scans `TEMPLATE_ROOTS = [gyrinx/]`, which includes
`gyrinx/core/templates/cotton_test/` — the badge harness's scratch directory, named in
**none** of the exclusions. Planting one forbidden shape there took the gate module from
10 passed to 2 failed. See §2.9 for the full write-up and the caveat that the flake was
**not reproduced** in seven `-n auto` runs today.

> **Recommendation: fix before GATE0 signs off — this needs no maintainer decision.** Add
> `cotton_test` to the gate's exclusion list and to `scripts/check_cotton.py`. Do **not**
> add `os.getpid()`; it addresses a collision that does not exist. A flaky gate is worse
> than no gate — it teaches people to re-run until green, which is exactly how a real
> violation gets through.

### D9 — `c-btn` ships with no unit tests *(new — genuinely the maintainer's call)*
232 tests pass, but **none of them test `c-btn`**. `test_cotton_btn.py` does not exist;
§3.1's "unit-test plan" is unwritten. `c-btn` has ~530 call sites, the most branching of
any component (element selection, four `disabled` behaviours, tooltip/dropdown collision,
`raw_attrs`), and is the component whose failures are silent-and-inert rather than visible.

> **Recommendation: write it as part of `GATE0`, before `DS1`.** It is the one piece of
> missing work that is squarely on the critical path: `DS1` is the canary precisely
> because it exercises every button variant, and running the canary against an untested
> component wastes the canary. §3.1 already specifies exactly what to cover. **But this is
> a schedule call given D8's "land PR 1 immediately" — if the maintainer prefers to ship
> components-only first and backfill, say so explicitly rather than letting it drift.**

### D8 — Ship speed vs polish
Given `main` moves 9×/day with 76% file overlap, **time-in-flight is the dominant risk
variable, not diff quality.** A branch that is 95% right and lands today beats one that is
100% right in a week.

> **Recommendation: land PR 1 (components only, zero call sites) immediately** — it cannot
> conflict with anything, and every hour it sits unlanded is wasted. Size every subsequent
> batch to a single working day; anything that cannot be reviewed and merged same-day is
> mis-sized. Accept cosmetic imperfection (attribute order, `&amp;`, djlint expansion) and
> normalise it in the harness rather than arguing about it in review. **Freeze scope once
> PR 3 opens** — new shapes will keep arriving on `main`, and chasing them is how a big
> bang becomes a permanent branch. The failure mode to fear is not a bad component; it is a
> six-week-old branch nobody dares merge.
