# Modifier reach: five explicit options

Decided with the maintainer, 2026-08-16. Reach becomes what the author said,
never what carriage implies. Branch `modifier-reach`, follows the slots-and-picks
merge (#2177).

## The five options (labels are the maintainer's, verbatim)

| Label | Verb | Storage | Semantics |
|---|---|---|---|
| The model carrying it | `targets_model` | `TargetsMiniature(reach="bearer")` | Only the model the carrier is directly assigned to. Never reached through the gang's broadcast. (Today's `when_directly_assigned=True`.) |
| All models in the gang | `targets_every_model` | `TargetsMiniature(reach="every_model")` | Every model in the gang, narrowable by the same conditions. The explicit form of today's silent gang-held broadcast. (Today's flag-off behaviour.) |
| The model's weapons | `targets_weapons` | unchanged | Kept as-is per maintainer. |
| The weapon it's fitted to | `targets_attached_weapon` | unchanged | Unchanged. |
| The gang carrying it and all models | `targets_gang` | `TargetsGang(echoes=True)` | Today's "The gang itself": lands on the gang, and what the gang is given echoes to every member. |
| The gang carrying it | `targets_gang_alone` | `TargetsGang(echoes=False)` | New: lands on the gang and stays there — what this modifier grants the gang does not ride member cards. |

`when_directly_assigned` retires into `reach`. Two verbs per model follows the
`ef_places`/`ef_places_choice` precedent (`_scope_verb` discriminates on the row).

Known limitation, stated in the module docstring: an "All models" modifier on a
*fighter-held* carrier reaches only the cards that can see it — the bearer's.
Compute is per-card and no cross-member channel exists; the gang-held carrier is
the case the option is for (a chosen alliance, a founding rule).

The no-echo variant controls **computed** echo (grants, guests). A stored
assignment the gang holds (a pick made for it) still rides member cards — that
is assignment-level broadcast, not this modifier's.

## Migration (one-time, behaviour-preserving, reported)

Prod audit 2026-08-16 (474 targets-model scopes):
- flag on (16: five archetypes' Champion-own-pick + 2 unattached Wyrd spares) → `bearer`
- carriers all fighter-side kinds (Profile/Wargear/Weapon/Subtype/Specialisation/
  Skill/SkillTree/Collection…) (172 carriers) → `bearer` (identical behaviour)
- carriers all gang-side kinds (Affiliation 10 / Archetype 12 / GangType 17) → `every_model`
- Rule/Hidden carriers (18): decide off live assignments — any gang-hosted use →
  `every_model`, else `bearer`; every decision printed
- no carriers → `bearer`, printed
- mixed gang+fighter kinds → `every_model`, printed loudly for the maintainer

`TargetsGang.echoes` added defaulting True — no gang-side conversion.

## Rides along

**The Water Guild fix.** `compute` refuses to record a granted slot's choice row
when the giver is broadcast/echoed, so a gang-held pick granting a per-model slot
is granted everywhere and asked nowhere. New rule: a granted slot is asked where
it *landed* — giver local: as now; giver broadcast/echoed and the scope reached
this card's model: recorded here, anchored on the broadcast carrier node (the
choose view's `_host` already lands picks for broadcast anchors).

## Order of work

1. Model field swap, verbs, specs (cards), forms plumbing, call-site updates.
2. Engine: `targets()` reads `reach`; `Contribution.echoes` threads the no-echo
   flag through `_from_the_gang`; the given-slot rule above.
3. Migration with the decision report (logic testable directly).
4. Prose reads reach where it changes the subject; card copy; sandbox suites
   (Water Guild end to end, no-echo gang, bearer/every-model matrix).
