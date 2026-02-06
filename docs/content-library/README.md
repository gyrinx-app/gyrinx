# Content Library

The content library is the game data that powers Gyrinx. It contains all the fighter types, equipment, weapons, skills, rules, and other definitions from Necromunda that users draw from when building their lists. Everything in the content library is managed through the Django admin interface.

When a user creates a list and adds fighters to it, they're selecting from templates defined in the content library. The content library defines *what's available*; users create their own instances of that content in their lists.

## How this section is organised

Each document covers a distinct area of the content library, including the models involved, how they appear in the admin, how they affect the user-facing application, and common administrative tasks.

| Document | What it covers |
|----------|---------------|
| [Houses & Factions](houses-and-factions.md) | Gang factions, the `generic` and `legacy` flags, house-specific cost overrides |
| [Fighters & Fighter Types](fighters.md) | Fighter archetypes, categories, default equipment loadouts, category terminology |
| [Stats & Statlines](stats-and-statlines.md) | Stat definitions, statline types, the legacy vs custom statline system |
| [Skills, Rules & Psyker Powers](skills-rules-and-psyker-powers.md) | Skill trees, special rules, psyker disciplines and powers |
| [Equipment & Weapons](equipment-and-weapons.md) | Equipment items, weapon profiles, traits, accessories, upgrades, rarity |
| [Equipment Availability & Restrictions](equipment-availability.md) | Fighter-specific equipment lists, category restrictions, availability presets |
| [Equipment List Expansions](equipment-list-expansions.md) | Conditional equipment unlocked by attributes, house, or fighter category |
| [Modifiers](modifiers.md) | The polymorphic modifier system that changes stats, traits, rules, and skills |
| [Injuries](injuries.md) | Injury groups, outcomes, and how injuries affect fighters during campaigns |
| [Gang Attributes](gang-attributes.md) | List-level attributes (Alignment, Alliance, Affiliation) and their effects |
| [Advancements](advancements.md) | Equipment advancements fighters can purchase with XP during campaigns |
| [Content Packs](content-packs.md) | User-created custom content collections and the pack filtering system |
| [Reference Library](reference-library.md) | Book and page references used for in-app tooltips |

## Key ideas

**Content vs user data.** The content library (`ContentFighter`, `ContentEquipment`, etc.) defines templates. User data (`ListFighter`, `ListFighterEquipmentAssignment`, etc.) holds the instances users create from those templates. Content is managed by admins; user data is created by users through the application.

**Cost propagation.** When you change a cost in the content library, the system automatically marks affected user data for recalculation. See [Equipment & Weapons](equipment-and-weapons.md) for details on how this works.

**Modifiers.** Equipment, upgrades, accessories, and injuries can all carry modifiers that change fighter stats, weapon stats, traits, rules, skills, and more. The [Modifiers](modifiers.md) documentation explains the full system.

**Pack filtering.** Content that belongs to a custom content pack is hidden from normal queries by default. The [Content Packs](content-packs.md) documentation explains how this works.
