# The chosen-kinds map: what slots-and-picks is migrating

Surveyed 2026-08-16 against the production content library (replicated into
`gyrinx_main` via the fixed sync) and production player data (read-only).
The four target kinds — Affiliation, Archetype, SkillTree, Specialisation —
turn out to be **eight authored systems**, two of which (Variants, Gang
Legacy) are the label-system hacks the migration exists to retire.

## The shape authors built, once per system

Every system is the same four pieces, hand-assembled:

| slots-and-picks concept | what authors built instead |
|---|---|
| slot type | an `offers a choice` **label** ("Variant", "Gang Legacy", "Skill Tree 1"…) |
| picklist | a **collection + section** used as a menu |
| slot | a **hidden** (or a modifier straight on a gang type / profile / subtype) carrying the offer |
| pickable | an **Affiliation / Archetype / SkillTree / Specialisation** row carrying payload modifiers |

## The eight systems

### 1. Outcast Affiliation (the original)

- Hidden **"Affiliation"** built into gang type **Outcast** → gang-scoped offer,
  label **"Affiliation"**, menu *Affiliations* (Clanless, Clan House, Mutant,
  Aranthian), pick lands on the **gang**.
- **Chained**: *Clan House* carries a gang-scoped offer, label **"Clan House"**,
  menu *Clan Houses* (House Cawdor/Delaque/Escher/Goliath/Orlock/Van Saar),
  lands on the gang.
- Payloads: Aranthian and each House X open an equipment list to
  `all models` narrowed by rank subtypes; Mutant opens Mutations to
  Leader/Champion/Ganger; Clanless carries nothing.
- ⚠ Prod data gives Aranthian's list to **Champion or Ganger or Leader**;
  the rules say Leaders and Champions only (maintainer's earlier ruling —
  content correction outstanding).

### 2. Variants — hack #1

- **One shared modifier** ("Offer Variants", gang-scoped) carried by **seven
  gang types** (Cawdor, Delaque, Escher, Goliath, Orlock, Palanite Enforcers,
  Van Saar) *and* by a vestigial hidden **"Variant"** that nothing builds in
  and nobody holds (0 live assignments).
- Label **"Variant"**, menu *Variants*: Chaos Corrupted, Genestealer Cult
  Corrupted, Malstrain Corrupted, and a literal **"None"** affiliation — the
  explicit nothing-option, and the most-picked row in production (82 live).
- Payloads: each corruption adds its collection gang-wide (Malstrain and GSC
  say it twice — once at the gang, once at all models); Chaos Corrupted also
  **removes** Gang Brutes and Pets and **chains** to…

### 3. Chaos God (two doors, one menu)

- …*Chaos Corrupted*'s chained offer, label **"Chaos God"**, menu *Chaos
  Gods* (Architect of Fate, Blood God, Dark Prince, Plague Lord — all four
  carry **no payload**; the pick is pure record).
- The same menu is offered directly by hidden **"Chaos God" [Helots]** built
  into gang type **Chaos Helot Cult**.

### 4. Cawdor Paths

- Hidden **"Path"** built into gang type **Cawdor** → gang offer, label
  **"Path"**, menu *Paths* (Path of the Fanatic, Path of the Pious).
- Payloads: each adds two rules to the gang (Fanatic Warriors + Fanatical;
  Pious Warriors + Without Number).
- Note Cawdor therefore asks **two** gang questions: Path and Variant.

### 5. Outcast Archetype

- **Five separate modifiers** carry the same offer (label **"Archetype"**,
  menu *Outcast Archetypes*: Brawler, Gunslinger, Mastermind, Survivor,
  Wyrd): one per Leader profile (Leader 1–4, pick lands on the **gang**) and
  one on the Champion profile (lands on the **bearer** — the own-pick).
- Payloads per archetype: skill-tier placements — Leader/Hive Scum rows
  reach `all models` narrowed by subtype or named profile; Champion rows
  reach only **the model carrying it** (inert in the gang's copy, active on
  a Champion's own pick). Wyrd additionally grants the Wyrd subtype
  (three rank-scoped rows) and places Wyrd Powers as Primary for everyone.

### 6. Venator Gang Legacy — hack #2

- **One shared modifier** on **twelve** Venator profiles (Leaders 1–4,
  Champions 1–4, Hunters 1–4): offers **archetype**, label **"Gang
  Legacy"**, menu *Venator Gang Legacies* (six house-named archetypes:
  Cawdor, Delaque, Escher, Goliath, Orlock, Van Saar), pick lands on the
  **bearer** — each fighter picks their own.
- Payloads: each house "archetype" adds that house's equipment list. This
  WORKS today: the pick is bearer-held, rides the bearer's card, and the
  payload reaches them. The `all models` reach label merely overstates it —
  visibility clamps it to the bearer — and the migration makes it an honest
  bearer reach with no behaviour change.

### 7. Venator Skill Trees

- **Four hiddens** ("Skill Tree 1–4") built into gang type **Venators**,
  each carrying: a gang-scoped **whole-kind** skilltree offer (label =
  the hidden's name) + one or two **puts-the-chosen** placements scoped by
  long `is_profile` lists (24, 16, 24 and 8 named profiles!) filing the
  picked tree under Primary or Secondary; Skill Tree 2 has an extra
  Specialist-subtype row at Secondary.
- The six SkillTree rows themselves carry nothing — the meaning lives
  entirely in the offering hiddens' placements. This is the purest
  "slot with per-slot config" case: four slots of one slot type.
  Repeats are possible today and merely noted — the maintainer calls
  that a bug; the slot type gets `allows_repeats` off.

### 8. Specialisation

- Subtype **"Specialist"** carries a bearer whole-kind offer (blank label →
  reads "Specialisation"). 939 live picks across 358 gangs — the
  highest-volume system by far.
- Payloads: each of the eight specialisations adds one skill to the bearer.
- Two orphan hiddens duplicate the offer: **"Specialisation Offer"
  [(general)]** (nothing holds it, 0 live) and **"Specialisation offer"
  [(Subjugator Patrol Officer)]** with a narrowed 3-item menu — nothing
  builds it in, but **1 live assignment** exists (hand-given by an owner).

## Production player data (live assignments)

| kind | picks | gang-hosted | model-hosted | gangs touched | note |
|---|---|---|---|---|---|
| affiliation | 200 | 200 | 0 | 163 | "None" 82, Clan House 14, Chaos Corrupted 14, Paths 26, … |
| archetype | 112 | 24 | 88 | 46 | gang-hosted = Outcast leader picks; model-hosted = Venator legacies + Champion own-picks (Wyrd 25, Van Saar 17, …) |
| skill_tree | 79 | 79 | 0 | 23 | Venators only |
| specialisation | 939 | 0 | 939 | 358 | the volume case |
| **total** | **1,330** | | | | every one has `caused_by` set (the offering carrier's assignment) |

Slots-and-picks itself: 2 live slot assignments, 2 live picks (early prod
experiments).

## Dead and orphaned content

- Unattached offer modifiers ×3: "Affiliation: offers a choice of
  affiliation" (whole kind), "Corruption" (Affiliations menu, bearer),
  and a duplicate of the Gang Legacy offer.
- Hidden "Variant" (superseded by the gang-type-carried modifier),
  hidden "Specialisation Offer (general)" — nothing references either.
- Archetype **"Ironhead Squat"** is on **no menu**: unreachable by any
  offer (its Squats list payload is authored but dead).
- The "None" affiliation exists solely because offers cannot say
  "picking nothing is fine".

## What cannot happen today (and shapes the target design)

- **Nothing can condition on a chosen thing.** The scope conditions are
  has_subtypes / is_profile / has_pickable / counter_at_least — there is no
  "has this affiliation". Every "if the gang picked X" behaviour is
  therefore hung on X itself. `has_pickable` closes this gap post-migration.
- **Offers cannot be optional** — hence the "None" row (maps to
  `min_picks=0` + the picker's None row).
- **Per-slot placement config needs a hidden each** — hence four Skill
  Tree hiddens where slots-and-picks wants four slots of one type.
- **A shared offer modifier on 7 gang types / 12 profiles** is the
  substitute for building one slot into many carriers.

## Straw target: the slot types this maps onto

| slot type | picklists | slots | notes |
|---|---|---|---|
| Affiliation | Affiliations | 1 gang slot (Outcast) | chained: Clan House pickable grants the House slot |
| Clan House | Clan Houses | granted by the Clan House pickable, gang | |
| Variant | Variants (minus "None") | 1 gang slot built into 7 gang types, `min_picks=0` | "None" row replaces the None affiliation |
| Chaos God | Chaos Gods | one granted by Chaos Corrupted; one built into Chaos Helot Cult | two slots, one type |
| Path | Paths | 1 gang slot (Cawdor) | |
| Archetype | Outcast Archetypes | 1 gang slot (leader-carried, assigned to gang) + 1 bearer slot (Champion) | `allows_repeats` question: champion may re-pick the gang's |
| Gang Legacy | Venator Gang Legacies (later: House/Ogryn/Squat lists per maintainer's rules dump) | 1 bearer slot built into 12 profiles | Ironhead Squat pickable rejoins via a picklist |
| Specialisation | Specialisations (+ the Subjugator 3-item list) | 1 bearer slot on the Specialist subtype; 1 narrowed variant | subtype-carried slot = a grant, needs #2181? No — the subtype is model-held, grants land locally ✓ |
| Skill Tree | (whole kind → one picklist of the 6 trees) | 4 gang slots of one type, `allows_repeats` OFF (maintainer ruling: repeats-noted today is a bug) | per-slot placements become modifiers ON THE SLOTS (slots are assignables); verify places-the-chosen reads a slot-borne pick |

## Open design questions the plan must answer

1. **Per-slot payloads — direction settled: on the slot.** The tier is a
   fact about which slot was picked for (Combat is Primary via Skill Tree 1,
   Secondary via Skill Tree 3), so the placement modifiers hang on the SLOT,
   which is an assignable and carries modifiers. To verify in the engine:
   `places the chosen` reading a slot-borne pick (it was built for
   offers-choice carriers).
2. **Player-data rewrite.** 1,330 live choices must become pickable-column
   picks with `chosen_for`/`chosen_for_slot` pointing at **new slot
   assignments that do not exist yet** (today's anchors are the offering
   carriers' assignments). Founding wrote those carriers; a migration must
   plant slot assignments per gang/fighter and rewrite each pick's anchor —
   through the ledger discipline, gang by gang.
3. **Kind collapse — DECIDED (maintainer, 2026-08-16): concrete pickables.**
   The four kinds' rows become Pickable rows of new slot types; the old
   kinds retire. 1,330 live picks move to the pickable column, the seven
   menu collections become picklists, collection entries stop naming these
   kinds, OFFERABLE_KINDS shrinks.
4. **Sequencing.** Specialisation (939 picks, simplest payloads) is the
   riskiest by volume but simplest by shape; Variants/Paths/Chaos God are
   simplest by volume; Skill Trees need question 1 answered first.
