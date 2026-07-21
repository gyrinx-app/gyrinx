# Crew eligibility screen + selection flow — implementation plan

Source: expert call, 2026-07-20 (Granola notes not reachable from the headless
session; this plan is built from the maintainer's written spec in-chat). Builds
on #2015 (category exclusion + per-crew opt-in toggles, merged).

## Goal

Add an **eligibility** step before crew selection so random/hybrid draws stop
giving wrong results for gangs that have hired guns or ineligible fighters, and
so crew size is explicit.

## The three eligibility states (per fighter, defaulting per category)

| State | Meaning | Default for |
|---|---|---|
| **Eligible** | In the pool that Custom picks from / Random+Hybrid draw from | Leader, Champion, Ganger, Juve, Prospect, Specialist, Brute; any fighter with the "part of the crew" rule (unless downed) |
| **Always included** | In the crew regardless of method; **excluded from the random pool**; appended on top | Hired Gun, Bounty Hunter, House Agent, Dramatis Personae (Hive Scum? — TBC) |
| **Not eligible** | Excluded entirely | Hanger-on, Vehicle, Crew, Exotic Beast (child); captured / dead / in-recovery fighters |

Defaults are **per category** but the screen lets you change **per fighter**
(e.g. exclude a specific hired gun, or include a hanger-on).

## Crew size

- The eligibility screen sets **crew size** = how many fighters the scenario
  allows to be *selected* (not counting always-included). New `Crew.crew_size`
  (nullable int).
- **Open decision:** does `crew_size` drive the Random draw count, or does the
  existing `random_spec` (the "N / DX / DX+N")? The example "pick 6 + 3 hired
  guns = 9 total" implies crew_size = the selectable count, and always-included
  are extra. For Random, the draw count is likely `crew_size`; `random_spec`
  may be redundant or becomes the crew_size input. **Confirm with maintainer.**

## Selection flow (after eligibility)

Two-halved selection screen:
- **Top** — the eligible pool. Custom: tick who you want. Random: app draws N on
  confirm. Hybrid: pick some + app draws the remainder.
- **Bottom** — "always included" fighters, shown regardless, not part of the
  draw, appended to the crew.
- Crew **rating shows "?"** until the crew is confirmed (already true for
  pending random draws; extend to hybrid/whole reveal-on-confirm).

## What #2015 already gives us (reuse, don't rebuild)

- `eligible_crew_fighters(lst, *, included=())` in `handlers/crew.py` — already
  excludes stash / archived / non-active / child fighters, and excludes
  `{HANGER_ON, CREW}` unless opted in. This is the "eligible pool" minus the
  always-included split.
- `Crew.included_categories` (JSON) + the URL toggles — the per-crew opt-in.
  The eligibility screen **generalises** this: `included_categories` becomes one
  facet of a fuller eligibility model (per-fighter overrides + always-included +
  crew_size).
- `sync_linked_crew_members` — the pattern for "auto-enrol fighters that ride in
  regardless of the pick" (currently vehicles/beasts). **Always-included hired
  guns use the same mechanism** (a new `CrewMember.source` value).

## Build sequence

1. **[BUILT this session] Always-included categories** — hired guns / bounty
   hunters / house agents / dramatis personae auto-enrol in the crew and are
   excluded from the random/hybrid draw pool. This is the core "random gives
   wrong results" fix, decoupled from the screen UX. Default behaviour only; the
   screen (to override per-fighter) is a follow-up.
2. **[BUILT this session] Eligibility model + computation.** `Crew.crew_size`
   (nullable int — the *selected* count; always-included come on top) and
   `Crew.eligibility_overrides` (JSON `{fighter_id: state}`, only fighters the
   player moved off their default). `handlers/crew.py` gains the three state
   constants (`CREW_ELIGIBLE` / `CREW_ALWAYS_INCLUDED` / `CREW_NOT_ELIGIBLE`),
   `default_crew_eligibility_state(fighter, *, included_categories)` (captured /
   sold / dead / recovering → not-eligible; always-included cats → included;
   hangers-on & vehicle crew → not-eligible unless the category is opted in via
   `included_categories`; else eligible), and `crew_eligibility(crew)` → one
   `{fighter, default, effective}` row per independently-selectable gang fighter
   (children/stash excluded), applying stored overrides. `crew_size` has no
   consumer yet — the screen (step 3) sets it and wires the draw count.
3. **Eligibility screen** — a step before selection rendering `crew_eligibility`
   as a table: per-fighter default with a per-fighter override control + the
   crew-size input + the method picker. Sensible defaults make it a
   one-click-through in the common case. Persists overrides + crew_size on POST.
4. **Two-half selection UI** — split the form into pool (top) + always-included
   (bottom).
5. **"Part of the crew" rule** — look up the content special rule; a fighter
   with it defaults to eligible even if its category would exclude it. (Needs
   the rule's identity in `content` — find it.)
6. **Reveal-on-confirm rating "?"** for hybrid.

## Decisions needed from maintainer

- crew_size vs random_spec (which drives the draw count?).
- Is Hive Scum "always included" (it's a hired gun) or eligible?
- Does the eligibility state persist per-crew, or per-battle (shared across a
  gang's crews in that battle)? Spec implies per-crew.
- Should always-included fighters be *removable* only via the screen, or also
  inline on the selection page?
