# Issue #2070 — finish the stat-advancement cleanup, and tell affected players

Follow-up to PR #2069 (Track B of #1861), which converted 2,306 fighter/stat pairs
and deliberately left 155 alone. This handles the leftovers.

All counts are from production on 2026-07-26, after #2069 was deployed.

## Deliver as a management command, not a migration

`fix_stat_advancements`, defaulting to a dry run, with `--apply` to commit.

Reasons: this changes 46 stats that players can see and sends messages to real
people, so it needs a reviewable dry run first. It also can't sensibly be re-run
by a migration if something needs adjusting. #1962 set the precedent of a manually
run estate-fix command.

## The eight situations

Keyed on (fighter, stat). "L" = live legacy advancements, "M" = live mod-system ones.

| # | Situation | Count | Action | Notify |
|---|---|---|---|---|
| 1 | L>0, override is a manual edit (different number) | 61 | Back-compute override, flip to mod system | No |
| 2 | L>0, override is advancement output in old format | 2 | Clear override, flip to mod system | No |
| 3 | L>0, no override — advancement inert | 35 | Flip to mod system | **Yes** (gain) |
| 4 | Shadowed by `ListFighterStatOverride`, or stat absent from statline | 14 | Leave — belongs to Track C | No |
| 5 | L=0, override numerically equals mod output — inflating | 7 | Clear override | **Yes** (loss) |
| 6 | L=0, override matches a partial count — inflating | 4 | Clear override | **Yes** (loss) |
| 7 | L=0, override is a genuine manual edit | 31 | Nothing — legitimate | No |
| 8 | Base value unparseable (e.g. `7_`) | 1 | Nothing — needs manual data repair | No |

Groups 1–4 are what block retiring the legacy code. Groups 5–7 carry no legacy
rows; they are data tidying.

## Method

Reuse the approach that worked in #2069: never re-derive what the legacy code
would have written. Decide everything from what the mod system will actually
display, computed from `fighter.content_fighter_statline` with
`AdvancementStatMod` chained over it.

**Group 1 back-compute.** Set the override to what it must be so the advancements
restore today's displayed value: apply an `AdvancementStatMod` with `mode="worsen"`
L times to the current override. Then **round-trip verify** — improving that
result L times must give back the original override exactly. If it doesn't, leave
the pair alone. This is the guard that catches formatting asymmetry.

**Classifying 1 vs 2.** Compare the override to the mod-system output both as a
string (exact) and as a number with `"` / `+` stripped. Exact match was already
handled by #2069; same-number-different-format is group 2; neither is group 1.

**Writes.** Use `ListFighter.objects.filter(pk=...).update(...)`, never `save()`.
Saving fires post_save receivers that materialise child fighters and bump the
parent gang's modified timestamp, which would reorder every affected player's gang
list. Learned in #2069.

**Guard everything** that touches `apply()` with `try/except (ValueError, TypeError)`
— production holds unparseable stat values and one already crashed a migration.

## Notifications

One message per **owner**, not per gang and not per fighter, covering every
affected fighter across all their gangs. Only groups 3, 5 and 6 — 46 changes.
Use `notify(recipient=..., subject=..., content=..., notification_type=SYSTEM)`.
Content renders through `safe_rich_text|safe`, so simple HTML is fine.

Copy is in the issue thread. Rules that must survive implementation:

- Losses listed before gains. Bad news first, never buried under good news.
- Always state that rating and credits are unchanged — true in every case, and
  it's the first thing anyone will worry about.
- Always end with how to correct it themselves. These are judgement calls from
  incomplete data and some will be wrong.
- No apology, no explanation of the two storage mechanisms. Not the player's
  problem.

## Verification

1. Dry run against a template-forked local database; confirm counts and that the
   printed before/after values are sane.
2. Statline differential: dump every fighter's rendered stats before and after,
   and assert **only** the 46 intended pairs moved, each by exactly one step in
   the expected direction. Groups 1 and 2 must show a same-number result.
3. Tests: one per situation, plus round-trip failure leaves the pair alone, plus
   a malformed value survives, plus notification aggregation (one per owner,
   losses before gains).
4. Full local CI: `pytest -n auto`, ruff, djlint, prettier, migration checks, bandit.
5. Dry run against production read-only before applying anything.

## Not in scope

- The 14 in group 4 — Track C reconciles the two override stores.
- The 31 in group 7 — legitimate manual edits.
- Deleting the legacy code and column — needs groups 1–4 at zero first.
