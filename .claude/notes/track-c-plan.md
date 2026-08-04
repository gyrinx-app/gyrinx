# Track C — retire the legacy statline columns (#1861, final track)

Production state (2026-08-01):

| | Count |
|---|---|
| ListFighters with a legacy `*_override` value | 1,499 of 68,213 (2.2%) |
| ListFighters with EAV overrides (`ListFighterStatOverride`) | 39 (56 rows) |
| ContentFighters with a modern `ContentStatline` | 31 of 596 |
| Legacy advancement rows remaining | 19 |

Tracks A and B are done. The 1,499 remaining legacy overrides are genuine manual
edits. The 19 leftover advancement rows and their odd overrides (trapped legacy
values on custom-statline fighters, `+`, `7`-for-`7"`, WS on crew) are **not**
pre-work: no UI or admin form can even reach those fields. C2 resolves or
reports them, because it is code.

## Goal

One statline system: every ContentFighter has a real `ContentStatline`; every
fighter-level edit lives in `ListFighterStatOverride`; 12 columns dropped from
each of ListFighter and ContentFighter; the legacy advancement branch and
`uses_mod_system` deleted (Track B's tail rides along).

## Method commitments (lessons already paid for)

- **Verify by re-resolution, never prediction** — every stage ends with an
  estate-wide dump of rendered statlines, diffed byte-identical against before.
  Track C is display-preserving by construction: any visible change is a bug,
  so **no player notifications**.
- **The card's base is `content_fighter_statline`, never the legacy columns** —
  misread twice already, once in code and once in analysis.
- **Queued task chain, not request-time** (CLAUDE.md rule; the #2070 preview
  took >1 min in prod). Backfills via the maintenance admin: preview first,
  `Backfill` record before writes, compare-and-set, on_commit ordering as in
  the #2070 tool.
- **Loud-fail edits; every new test reverted-and-red once.**

## Stages

### C0 — decisions + content normalisation (DONE: swept 2026-08-01)

Sweep results (565 templates × 12 columns = 6,780 values): ok 6,121 ·
blank 481 · format-variant 162 · malformed 11 · dash 5. Fix list with admin
links: `c0-fix-list.md` (sent to Tom).

- **Malformed: 10 real fixes** (typos: `7_`, `*+`, `%"`, `6*`, `W`, wrong
  suffixes like movement `5+`). The 11th, Wilcox's movement `D6+1"`, is
  **legitimate content** — dice-expression stats exist and must never be
  "fixed" or validated away. `_apply_mods` already skips mods on them.
- **Format-variant 162** (suffix-less `4` for `4+` etc., ~20 templates): too
  many to hand-edit; proposed as a tiny preview-first backfill adding the
  suffix the ContentStat flags dictate. Visible cosmetic correction — needs
  Tom's go-ahead. C1's apply refuses to run while un-normalised values remain (explicit override checkbox to copy them verbatim anyway).
- **Blanks are the Stash templates** (~39, all-12-blank) plus ~17 BS-only
  blanks. REVISED after reading `sq_content_fighter_statline`: the annotated
  fast path drops missing rows from the card entirely, while the Python path
  renders `-`. So C1 creates a row for **every** stat, writing `-` for blanks
  (renders identically in all three paths), and does NOT skip Stash — every
  CF gets a statline, so C3/C4 leave zero legacy-branch users.
- **C2 input profiled**: 1,499 fighters' override values = ok 2,426 ·
  format-variant 938 · malformed 49 · dash 50. ALL copy verbatim — cards
  display these strings as-is today, so verbatim is the display-preserving
  choice; the 49 "malformed" include legitimate dice values (`D6"`) and player
  garbage (`3banans`) alike. Enumerate in the C2 record, change nothing.
- Decisions: historical-table column loss **accepted** (Tom, 2026-08-01);
  everyone moves to the EAV stats-edit form in C3.

### C1 — materialise ContentStatline for the 565 (BUILT 2026-08-04, PR pending)

Backfill: create a statline on the "Fighter" type (content.0156), copying the
12 column values verbatim. `content_fighter_statline` prefers the new statline
once it exists, so the differential proves the copy renders identically.
Check pack-sourced fighters resolve the new statlines.

### C2 — migrate the 1,499 fighter overrides to EAV

Backfill, per (fighter, stat):

- Non-empty legacy override, stat present in the fighter's statline type →
  create the EAV row (value verbatim), clear the legacy field (CAS on the read
  value).
- EAV row already exists (the 39 fighters) → EAV wins; drop the legacy value if
  equal, report if not.
- Stat absent from the statline type (e.g. WS on crew) → clear and report; the
  value was inert.
- Then extend the #2070 cleanup to back-compute EAV rows, re-run it, and drive
  the remaining legacy advancements to zero; anything unconvertible is
  enumerated in the record, not left silent.

### C3 — code swap (after C1+C2 verified)

Single read path: `statline` stops reading legacy `*_override`; the stats-edit
form writes EAV for every fighter (this closes the trapped-override gap — a
legacy override on a custom-statline fighter today displays on the card but is
invisible and uneditable in every UI including admin); `copy_attributes_to` /
`clone` drop the 12-field enumerations; the `sq_*` fast-path branches collapse;
`with_related_data` + `performance_view_queries.json` regenerated together.

### C4 — drops (a release after C3)

- `RemoveField` ×12 on ListFighter and ×12 on ContentFighter (+historical).
- Track B tail: delete the legacy branch in `apply_advancement`,
  `_calculate_stat_value`, the `uses_mod_system` filter in `_mods`; drop the
  column. A final data migration flips/archives any straggler rows first.

## Delivery

C0+C1 one PR → C2 one PR → C3 one PR → soak a release → C4. Each backfill has
its own preview and estate differential.
