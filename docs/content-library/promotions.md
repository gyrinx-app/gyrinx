# Promotions

## Overview

Promotions represent fighters rising through the ranks of their gang over the course of a Necromunda campaign: a Ganger becoming a Specialist, a Juve earning their place as a full gang member, or a Prospect being elevated to one of their house's Champion types. The `ContentPromotionPath` model captures these paths as content, so content administrators can add and adjust promotions through the content library without code changes.

The rules are consistent about what a promotion does — and, just as importantly, what it does not do. When a fighter is promoted, their category changes, and for type-changing promotions they "count as" the new fighter type *for the purposes of determining which equipment and skill sets they can access*, gaining that type's special rules. Their existing characteristics do not change, and Gyrinx follows this faithfully: a promotion never alters a fighter's statline or base cost. The only cost impact is the flat `cost_increase` configured on the path (for example, +20 credits for Ganger to Specialist), and where the rules are silent on cost — as they are for the house Juve and Prospect promotions — the path is configured with no cost increase at all.

Some promotions offer a choice: most houses' Prospects can be promoted into *either* of two Champion types (a Goliath Forge-born becomes a Forge Boss or a Stimmer, as the controlling player wishes). Promotion paths support this directly through their `targets`, and the app asks the player to pick during the advancement flow.

## Key Concepts

**Promotion Path** (`ContentPromotionPath`): A named promotion a fighter can take through the advancement flow, defining who it is offered to, what they become, and what it costs.

**Kind — Category relabel vs Type change**: A *category relabel* changes only the fighter's category label (the core Ganger → Specialist promotion — "they are still a Ganger, but from now on gain all the benefits of being a Specialist"). A *type change* additionally makes the fighter count as a specific target fighter type for equipment lists, skill-set access, and special rules — the pattern used by the house Juve and Prospect promotions.

**Targets**: For type changes, the fighter type (or types) the fighter can be promoted into. A path with one target applies it automatically; a path with two or more presents the player with a choice during the advancement flow. Targets are chosen from the catalogue's fighter types — the two Champion entries of the same house, for example.

**Source — category or specific fighter**: A path is offered either to every fighter of a category (`from_category`, used by the generic core paths) or only to fighters of one specific type (`source_fighter`, used by house-specific paths such as "the Orlock Wrecker's promotion"). When `source_fighter` is set, it takes precedence over the category match.

**Rank**: The seniority of the promotion (Specialist-level paths use rank 1, Champion-level paths rank 2). When a promotion is deleted from a fighter's advancement history, the fighter falls back to the highest-ranked promotion they still hold — rank is what makes that ordering data-driven.

**Rolls**: The 2d6 totals that offer this promotion in the Ganger roll-driven advancement flow. The core Ganger → Specialist path is configured with rolls 2 and 12, matching the rulebook's advancement table.

**Advancements threshold and timing**: Guidance from the rules about when the promotion happens — most house promotions require the fighter to have five or more advancements (three for some houses, per errata) and take place during Downtime. Gyrinx surfaces these as guidance rather than hard gates: campaigns houserule these details constantly, so the app warns rather than blocks.

## Models

### `ContentPromotionPath`

#### Fields

| Field | Type | Description |
|-------|------|-------------|
| `name` | CharField (255) | The name shown to players in the advancement selection form, e.g. "Promote to Specialist" or "Promotion (Forge Boss or Stimmer)". |
| `kind` | CharField (choices) | `RELABEL` (category relabel) or `TYPE_CHANGE` (the fighter counts as a target type for access). |
| `from_category` | CharField (choices) | The fighter category this promotion is offered to (e.g. `GANGER`, `JUVE`, `PROSPECT`). Used when `source_fighter` is not set. |
| `source_fighter` | ForeignKey to `ContentFighter` (nullable) | When set, the path is offered only to fighters of this specific type — the house-specific pattern. Uses an autocomplete in the admin. |
| `to_category` | CharField (choices, blank) | The category the fighter is relabelled to. Required for relabels; optional for type changes, where the chosen target's own category applies (this matters because not every promotion target is a Champion — one house's Juve promotes into a Ganger type). |
| `targets` | ManyToManyField to `ContentFighter` (blank) | The target types for a type change. One target applies automatically; two or more give the player a choice. Uses an autocomplete in the admin. |
| `rank` | PositiveIntegerField (default: 0) | Promotion seniority, used to recompute a fighter's category when a promotion is removed. Specialist-level paths use 1, Champion-level 2. |
| `xp_cost` | PositiveIntegerField | The XP cost to take this promotion (6 for the core Specialist path, 12 for Champion, 0 where the rules attach no XP cost). |
| `cost_increase` | IntegerField (default: 0) | The flat credit increase applied to the fighter's rating. This is the promotion's *only* cost effect — base cost never changes. |
| `rolls` | JSONField (list) | The 2d6 totals that offer this promotion in the Ganger roll flow. Rendered as checkboxes (2–12) in the admin. |
| `grants_skill` | CharField (choices) | Which skill, if any, the promotion bundles: none, or a random/chosen Primary/Secondary/Any-set skill. The core Ganger and Specialist promotions grant a random Primary skill; the house Juve and Prospect promotions grant none. |
| `advancements_threshold` | PositiveIntegerField (nullable) | The number of advancements the rules say the fighter should have first (5 for most house promotions, 3 for some). Guidance only. |
| `timing` | CharField (choices) | When the rules say the promotion happens: post-battle sequence, Downtime, at gang founding, or on leader death. Informational. |
| `restricted_to_houses` | ManyToManyField to `ContentHouse` (blank) | If set, only fighters in lists belonging to these houses are offered the path. Usually unnecessary — `source_fighter` already pins a path to one house's fighter type. |

#### Validation Rules

- A relabel must name a `to_category`, and it must differ from `from_category`.
- `to_category` must be a promotable category (Leader, Champion, Ganger, Juve, Prospect, or Specialist) — never Stash, Vehicle, or the other structural categories.
- `rolls` must be a duplicate-free list of whole numbers between 2 and 12 (the admin's checkboxes make invalid input impossible; the model validates it for programmatic writes too).
- A promotion target can never be a stash or vehicle fighter type. This is enforced when the promotion is applied.

#### Admin Configuration

The admin form is organised into four fieldsets:

1. **Main fields** — `name`, `kind`, `from_category`, `source_fighter`, `to_category`, `targets`, and `rank`. Both fighter lookups are autocompletes, and they only offer catalogue fighters — fighters that belong to user content packs are excluded, since a globally-visible promotion path must never reference one user's pack content.
2. **Cost** — `xp_cost` and `cost_increase`.
3. **Behaviour** — `grants_skill`, the `rolls` checkboxes, `advancements_threshold`, and `timing`.
4. **Restrictions** (collapsed by default) — `restricted_to_houses`.

The list view shows `name`, `kind`, the from/to categories, `rank`, the costs, and the skill grant, and can be filtered by kind, timing, category, and house restriction.

## How It Works in the Application

### Offering promotions

When a fighter opens the advancement flow, Gyrinx offers every promotion path whose source matches them — by specific fighter type if `source_fighter` is set, otherwise by their current category (which follows earlier promotions, so a Ganger promoted to Specialist is offered Specialist paths). House restrictions apply on top. The path appears in the advancement type list under its `name`, with the skill grant appended where there is one ("Promote to Specialist (Random Primary Skill)").

In the Ganger roll-driven flow, a 2d6 roll whose total appears in a path's `rolls` pre-selects that promotion — so a rolled 2 or 12 offers "Promote to Specialist", exactly per the rulebook's table.

### Choosing a target

If the selected path has two or more targets, the flow adds a step asking the player which type their fighter becomes. Single-target paths skip this step. If the path bundles a skill, the usual skill selection follows; otherwise the flow goes straight to confirmation.

### What changes when a promotion is applied

- The fighter's **category** is relabelled (to `to_category`, or the chosen target's own category).
- For type changes, the fighter **counts as the target type** from then on: future equipment purchases price against the target's equipment list, skill access comes from the target's skill trees, and the fighter's special rules are the target's (swapped wholesale, per the rules).
- The path's `xp_cost` is deducted and its `cost_increase` added to the fighter's rating.
- Any bundled skill is added.

### What never changes

- The fighter's **statline** — characteristics stay exactly as they were, including any earned advancements.
- The fighter's **base cost** — a promoted Prospect does not suddenly cost what a Champion costs to hire.
- The fighter's **equipment** — everything they own is kept, at the price that was paid for it. Only *future* purchases use the new type's equipment list.

### Interaction with legacy fighters

A fighter can have both a legacy fighter and a promotion. For equipment-list pricing, the order of precedence is: the legacy fighter's price, then the promoted type's, then the fighter's own. Legacy fighters never affect skills, special rules, statlines, or cost — they remain an equipment-list-only mechanic.

### Removing a promotion

Deleting a promotion from a fighter's advancement history restores the XP, reverses the rating increase, removes any bundled skill, and recomputes the fighter's category and counts-as type from the highest-ranked promotion they still hold. A fighter with no remaining promotions returns to their hired category and type.

### Promotions and fighter copies

Promotion state survives every flow that copies a fighter: entering a campaign (which clones the whole list), and the duplicate-fighter form — where the existing "Clone as {category}" checkbox governs whether the promotion travels; the category label and the counts-as type always travel together.

## Common Admin Tasks

### Adding a house Juve promotion (single target, no skill)

The standard pattern for "Promotion (X Specialist)" special rules on house Juves:

1. Navigate to Promotion paths in the admin and click "Add".
2. Set `name` to match the rulebook special rule, e.g. "Promotion (Escher Specialist)".
3. Set `kind` to Type change, and `source_fighter` to the house's Juve fighter type (e.g. the Escher Little Sister).
4. Set `to_category` to Specialist, and add the house's Specialist fighter type (e.g. "Sister (Specialist)") as the single target.
5. Set `rank` 1, `xp_cost` 0, `cost_increase` 0, `grants_skill` none.
6. Set `advancements_threshold` 5 (or 3 where the house's rule says three) and `timing` Downtime.
7. Save. Eligible Juves see the promotion immediately.

### Adding a Prospect promotion with a choice of Champions

The "Promotion (X or Y)" pattern:

1. Add a path named after the rule, e.g. "Promotion (Forge Boss or Stimmer)".
2. Set `kind` to Type change and `source_fighter` to the Prospect type (e.g. the Goliath Forge-born).
3. Leave `to_category` blank — each target's own category applies — and add **both** Champion types as targets.
4. Set `rank` 2, costs 0/0, `grants_skill` none, threshold 5 (or 3), timing Downtime.
5. Save. Eligible Prospects are asked which type they become when they take the promotion.

### Adjusting the core promotions

The two core paths (Ganger → Specialist on a roll of 2 or 12, +20 credits and a random Primary skill; Specialist → Champion for 12 XP, +40 credits) are seeded automatically on deployment. They can be edited like any other path, but their costs match the rulebook's advancement tables — change them only deliberately, as the values apply to every gang.

### Auditing the configuration

- Filter the list view by `kind` to separate relabels from type changes.
- A type change with **no** targets applies only its category relabel — usually a sign the target still needs to be added.
- Use the from/to category filters to check each house's Juve and Prospect paths exist after a new house's content is entered.
