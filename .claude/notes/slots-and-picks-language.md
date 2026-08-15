# Slots & Pickables — language review

Every entry below is a direct quote from the diff (`git diff main...HEAD`, plus
the current working-tree rename in `n26/library/models/assignable.py`), tagged
with the file and line it lives at. Edit any entry in place — change the
quoted text, leave a note, whatever's fastest — and the edits will be
integrated back to the file:line noted. The family label is already
"Slots & Pickables" per your instruction (working tree, not yet committed).

---

## 1. Authoring index & family

| What | Text | File:line |
|---|---|---|
| Family label (menu heading) | `"Slots & Pickables"` | `n26/library/models/assignable.py:32` (working tree, uncommitted) |
| Family docstring (says what the menu groups) | "A domain of choice and its parts: the domain itself, its options, the lists they are offered on, and the choices that offer them. Four kinds that only mean anything together, so the menu keeps them together." | `n26/library/models/assignable.py:44-47` |

Kind menu descriptions — each model's docstring first line, which is what
`kind_summary()` renders as the menu row description (`n26/library/views.py`,
`kind_summary`):

| Kind | First line | File:line |
|---|---|---|
| SlotType | "A domain of choice: Gang Legacy, Affiliation, Archetype." | `n26/library/models/slots.py:20` |
| Pickable | "One option a choice offers: Cawdor, Aranthian, Outcast Leader." | `n26/library/models/slots.py:52` |
| Picklist | "The options behind a choice: a flat, ordered list of pickables." | `n26/library/models/slots.py:98` |
| Slot | "A choice put on a card: a picklist, a label, and how many picks." | `n26/library/models/slots.py:189` |
| HasPickable (condition) | "Condition: the model has one of these picked." | `n26/library/models/modifier.py:283` |

---

## 2. Model docstrings (full text, verbatim)

**Module docstring**, `n26/library/models/slots.py:1-22`:

> Slots and picks — a choice made from a curated list, authored not coded.
>
> A new domain of choice is four rows and no code. A **slot type** names the
> domain (Gang Legacy, Affiliation, Archetype). **Pickables** are its
> options, each an ordinary assignable carrying ordinary modifiers. A
> **picklist** is the flat, ordered list of them a choice draws from. A
> **slot** is one named use of the type — a picklist, a label, how many
> picks, and where the pick lands — and it is an assignable, so putting the
> choice on a card is an ordinary assignment.
>
> What is chosen is an ordinary assignment too: the pickable, hosted per the
> slot's `assigned_to`, caused by the slot's assignment and pointing back at
> it through `Assignment.chosen_for`. Resolution reads that link, so two
> slots of one type on one holder stay independent and nothing is inferred
> from kinds.
>
> Two of the rules here are shaped by the rest of the app rather than by the
> game. A pickable draws no row of its own and does nothing at all until its
> slot is present — so a pickable built into something, with no slot to
> answer, would sit in the library unread, and the authoring pages refuse
> one. And a hidden slot draws no choice row while its pick still does
> everything it does: that is how a bundle of behaviour arrives under one
> name.

**`SlotType`**, `n26/library/models/slots.py:24-30`:

> A domain of choice: Gang Legacy, Affiliation, Archetype.
>
> Ties a slot, its picklist and its options together — all three name
> one of these, and authoring refuses a mismatch. Whether the same
> option may be picked twice over is a fact about the domain, so it is
> stated here once rather than on every slot.

**`Pickable`**, `n26/library/models/slots.py:52-63`:

> One option a choice offers: Cawdor, Aranthian, Outcast Leader.
>
> A named value of its slot type that carries whatever it means as
> ordinary modifiers — an equipment list opened, a subtype granted, a
> further choice offered.
>
> It never draws a row of its own: it appears under its slot's choice
> row as the answer. **Without its slot it shows nothing and does
> nothing** — an option nobody was offered is not a thing the holder
> has. So it arrives chosen, given, or as a slot's starting value, and
> never as a bare built-in.

**`Picklist`**, `n26/library/models/slots.py:98-105`:

> The options behind a choice: a flat, ordered list of pickables.
>
> One slot type throughout, no headings and no prices — where a
> collection is a catalogue, this is a menu. Two slots may draw from one
> picklist, and one slot type may have several: the Outcast archetypes
> a leader chooses from and the ones a champion does are two lists over
> the same type.

**`PicklistMember`**, `n26/library/models/slots.py:151-155`:

> One option on one list, in its place.
>
> The pickable says what it is and what it does; this says that this
> list offers it, where in the order, and — where one list calls it
> something else — under what wording.

**`Slot`**, `n26/library/models/slots.py:189-203`:

> A choice put on a card: a picklist, a label, and how many picks.
>
> Assigning one is what asks the question. The card draws the label
> with what has been picked, or a control to pick — on the holder's own
> card and nowhere else, so a slot the gang holds is asked once rather
> than on every fighter.
>
> How many picks sit between the minimum and the maximum. Under the
> minimum is a note on the card, never a refusal, and the picker stops
> offering at the maximum.
>
> **Hidden** draws no choice row at all: the pick still arrives and
> still does everything it does, which is how a bundle of behaviour is
> given one name.

**`HasPickable`** (condition model), `n26/library/models/modifier.py:283-291`:

> Condition: the model has one of these picked.
>
> "Models with the Cawdor legacy" — one condition serving every domain
> of choice ever authored, because what was picked is an ordinary
> assignment and picking it is an ordinary possession. Any-of within
> the row; negated, it is everyone who picked something else.
>
> A pick with no slot behind it is not a possession, so it is not
> matched here either: an option nobody was offered says nothing about
> the model holding it.

**Reworded docstrings on touched models** (existing model, changed sentence):

`Family` (assignable.py) — the family enum's own docstring, first sentence
extended:

> "...says what *sort* of thing a kind is, so the menu can read as the
> author thinks — the plumbing, the model's own qualities, the kit it
> carries, the gang-scale picks, **the domains of choice**. A discovering
> test refuses any authorable kind without one."

— `n26/library/models/assignable.py:29-34` (the bolded clause is new)

`HasSubtypes` — one sentence appended:

> "'Leaders and Champions each select a skill' is one row naming both —
> any-of within the row. Wanting Mounted *and* Wyrd is two rows.
> **Negated, it is the same row read the other way: everyone the row
> does not name.**"

— `n26/library/models/modifier.py:299-304`

`AssignableChoice.compatible_with_kind` docstring — one clause appended to
the existing sentence about the affiliation carrier:

> "...but has no type line, no skills row, and holds no weapons, so
> nothing else can land there. **A slot may land on either: a gang is
> asked its affiliation, a fighter their legacy.**"

— `n26/library/models/modifier.py:838-844`

`ef_adds()` docstring — first line extended:

> "Grants the target a subtype, skill, trait, collection, rule, weapon
> **— or a further choice, which is how one pick opens the next.**"

— `n26/library/authoring.py:1523-1524`

`ChoiceSlot` dataclass docstring — substantially rewritten (see section 6
for the render/effects internals, quoted here for completeness):

> "A choice on a card, resolved or not.
>
> Two things ask one: a modifier that offers a choice of a kind, and a
> `Slot` assigned to the holder. Either way the row is computed —
> present while whatever asks it is — and only what was chosen is
> stored. Unresolved is the absence of that assignment: nothing
> pending is written.
>
> A slot-borne choice may hold several picks and reads them off
> `Assignment.chosen_for`, which names the assignment that asked;
> nothing is inferred from what kind of thing was chosen."

— `n26/core/effects.py:147-160`

---

## 3. Field help texts

Every `help_text=` the branch adds (the migration file mirrors these
verbatim — auto-generated from the model source, not a separate authoring
decision — so only the model-file location is given):

| Model.field | Text | File:line |
|---|---|---|
| `_negatable()` helper (shared by HasSubtypes.negate, IsProfile.negate, HasPickable.negate) | "Reach everything this does not name — every model except these. Other conditions still narrow it further." | `n26/library/models/modifier.py:271-274` |
| `HasPickable.pickables` | "The model must have picked at least one of these." | `n26/library/models/modifier.py:294` (via shared field def, see `modifier.py:151`) |
| `DefaultAssignment.default_pickable` | "A slot's starting pick — what the choice arrives already settled on. Changing it later is the ordinary rechoose." | `n26/library/models/defaults.py:220-223` |
| `SlotType.name` | `'The domain of the choice, e.g. "Gang Legacy".'` | `n26/library/models/slots.py:33-35` |
| `SlotType.plural_name` | `'What several of them are called, e.g. "Gang Legacies". Blank adds an s.'` | `n26/library/models/slots.py:36-41` |
| `SlotType.allows_repeats` | "Whether one holder may pick the same option for two slots of this type. Turned off, the card says when they have — it never stops them." | `n26/library/models/slots.py:42-47` |
| `Pickable.slot_type` | "The domain this is an option in." | `n26/library/models/slots.py:79-81` |
| `Picklist.slot_type` | "The domain these options belong to." | `n26/library/models/slots.py:103-105` |
| `Picklist.name` | `'What this list of options is called, e.g. "Gang Legacies".'` | `n26/library/models/slots.py:106-108` |
| `PicklistMember.label_override` | "What this list calls the option, where that differs from its own name. Blank uses the name." | `n26/library/models/slots.py:159-163` |
| `PicklistMember.position` | "Where it sits in the list. Ties fall back to name." | `n26/library/models/slots.py:164-166` |
| `Slot.slot_type` | "The domain this choice is in." | `n26/library/models/slots.py:216-218` |
| `Slot.picklist` | "The list of options this choice offers." | `n26/library/models/slots.py:219-221` |
| `Slot.label` | `'What the card calls this choice, e.g. "Gang Legacy". Blank uses this slot\'s own name.'` | `n26/library/models/slots.py:222-227` |
| `Slot.min_picks` | "How many picks the card expects. Fewer is a note on the card, never a refusal. Nought asks for nothing." | `n26/library/models/slots.py:228-232` |
| `Slot.max_picks` | "How many picks the choice holds. The picker stops offering here." | `n26/library/models/slots.py:233-235` |
| `Slot.assigned_to` | "Where the pick lands. Almost always the bearer; a Leader's archetype pick is carried by the gang, not the Leader." | `n26/library/models/slots.py:236-241` |
| `Slot.hidden` | "Draw no choice row at all. What is picked still applies — this is how several things arrive together under one name." | `n26/library/models/slots.py:242-246` |
| `Slot.position` | "Order among the slots on one card. Ties fall back to name." | `n26/library/models/slots.py:247-249` |
| Spec field `assignment.chosen_for` / `chosen_for_slot` | *(no help_text — comments only, see section 7 code comments if wanted)* | `n26/core/models/assignment.py:249-269` |

*Count: 18 distinct help_text strings.*

---

## 4. Authoring page furniture

**Family / slot-type index page** — no separate page copy beyond the family
label and kind summaries already listed in section 1.

**Slot-type page** (`n26/library/templates/authoring/slot_type.html`, new file):

| Element | Text | Line |
|---|---|---|
| Section heading (own-fields) | "This slot type" | 21 |
| Delete link | "Delete this slot type…" | 30 |
| Section titles (from `SLOT_TYPE_PARTS`, `n26/library/views.py:2913-2969`) | "Options" / "Lists of options" / "Choices" | views.py 2917, 2932, 2947 |
| Section descriptions | "The values a choice in this domain can settle on. An option does nothing until a modifier hangs on it, which is done on its own page." | views.py 2919-2922 |
| | "The options behind one choice, in order. A domain may have several lists: what a leader chooses from and what a champion chooses from are two lists over one domain." | views.py 2934-2937 |
| | "One named use of this domain: a list, a label, and how many picks. Building one into a profile is what puts the choice on that fighter's card." | views.py 2949-2952 |
| Empty states (`nothing_yet`) | "No options yet — a choice in this domain has nothing to offer." | views.py 2923 |
| | "No lists yet — a choice draws its options from one of these." | views.py 2938 |
| | "No choices yet — nothing puts this domain's options in front of a player." | views.py 2953-2955 |
| "Add a/an X" heading | `"Add {{ section.part_article }} {{ section.part_name }}"` → renders "Add an option" / "Add a list" / "Add a choice" | template line 42, `n26/library/views.py` `_article_for()` line 633-639 |
| Add-form submit label | `"Add {{ section.part_name }}"` | template line 46 |
| Save button (own fields) | "Save changes" | template line 24 |
| Success flash (own-fields save) | `f"Saved {slot_type}."` | `n26/library/views.py:6253` (≈ views.py `slot_type_page`) |
| Success flash (part created) | `f"Created {made}."` | `n26/library/views.py:6274` |
| Duplicate-name error (own fields) | `f"A slot type named "{edit_form.cleaned_data['name']}" already exists in this pack."` | `n26/library/views.py` (in `slot_type_page`, ~6247-6250) |
| Duplicate-name error (parts: pickable/picklist/slot) | `f"{spec.creates._meta.verbose_name.capitalize()} "{form.cleaned_data[spec.identity]}" already exists in this pack."` | `n26/library/views.py` (in `slot_type_page`, ~6265-6269) |

**Generic detail page** (`n26/library/templates/authoring/detail.html`):

| Element | Text | Line |
|---|---|---|
| "Add a/an X" heading, now grammatical | `"Add {{ section.part_article }} {{ section.part_verbose_name }}"` | line 179 |

**Picklist part on the generic detail page** (`n26/library/views.py:264-291`,
`DETAIL_KINDS["picklist"]`):

| Element | Text |
|---|---|
| `parts_label` | "options" |
| `part_name` | "option" |
| `parts_description` | "What a choice drawing on this list offers, in the order a player reads them. Taking one off changes only what is offered next: the option itself stays in the library, and anyone who already picked it keeps it." |
| `nothing_yet` | "No options yet — a choice drawing on this list has nothing to offer." |

**Picklist-member remove page**
(`n26/library/templates/authoring/picklist_member_remove.html`, new file):

| Element | Text | Line |
|---|---|---|
| Page title | `"Remove {{ label }}"` | 9 |
| Form title | `"Stop offering {{ label }}?"` | 12 |
| Lead | `"{{ picklist }} will no longer offer it. The option itself stays in the library, and on every other list that offers it."` | 13 |
| Submit label | "Stop offering it" | 14 |
| Breadcrumb: content library link | "Content library" | 19 |
| Breadcrumb: current | "Stop offering" | 23-25 |
| Info callout title | "Nothing already chosen changes" | 33 |
| Info callout body | "Anyone who has picked it keeps it. This changes what the next player is offered." | 34-35 |
| Success flash | `f"{picklist} no longer offers {said}."` | `n26/library/views.py:6118` (`picklist_member_remove` view) |

**Row notes in listings** (`n26/library/views.py`, `LEAF_DESCRIBE` /
`_slot_type_rows` helpers):

| Function | Notes produced |
|---|---|
| `_describe_slot_type` | `f"{n} options"`, `f"{n} lists"`, `f"{n} choices"`, and `"no repeats"` if `allows_repeats` is off | `views.py:723-733` |
| `_pickable_notes` | `f"on {n} list{'s' if n != 1}"` or `"on no list yet"` | `views.py:735-744` |
| `_picklist_notes` | `f"{n} option{'s' if n != 1}"` | `views.py:746-748` |
| `_describe_pickable` | domain name + `_pickable_notes` | `views.py:750-752` |
| `_describe_picklist` | domain name + `_picklist_notes` | `views.py:754-756` |
| `_picks_said` | `"one pick"` / `f"{n} picks"` / `f"{min} to {max} picks"` | `views.py:758-762` |
| `_slot_notes` | `f"from {picklist.name}"`, `_picks_said(...)`, `"the gang holds the pick"` (if assigned to gang), `"draws no row"` (if hidden) | `views.py:764-773` |
| `_describe_slot` | domain name + `_slot_notes` | `views.py:775-777` |
| `_describe_picklist_member` (docstring + note) | `f"the {member.pickable} option, under another name"` (when a list overrides a label) | `views.py:145-153` |

Verbose names (singular/plural) for the five kinds:

| Model | Singular | Plural | File:line |
|---|---|---|---|
| SlotType | "slot type" | "slot types" | `slots.py:37-38` |
| Pickable | "pickable" | "pickables" | `slots.py:73-74` |
| Picklist | "picklist" | "picklists" | `slots.py:117-118` |
| PicklistMember | "picklist member" | "picklist members" | `slots.py:169-170` |
| Slot | "slot" | "slots" | `slots.py:254-255` |
| HasPickable (condition, not a top-level kind) | "has pickable" | "has pickable" (same both ways) | `modifier.py:288-289` |

*Section count: 18 authoring furniture entries + duplicate-error templates + 6 verbose-name pairs.*

---

## 5. Refusals and validation messages

| Situation | Message | File:line |
|---|---|---|
| Bare pickable built into something with no slot (`_refuse_a_bare_pickable`) | "A pickable without its slot shows nothing and does nothing. Build in the slot, or a slot-with-default." | `n26/library/authoring.py` (`_refuse_a_bare_pickable`, ~line 1004-1009) |
| `add_picklist_member`: pickable's domain doesn't match the picklist's domain | `f"{pickable} belongs to {pickable.slot_type}, and {picklist} lists {picklist.slot_type} options."` | `n26/library/authoring.py:594-597` |
| `create_slot`: picklist's domain doesn't match the slot's domain | `f"{picklist} lists {picklist.slot_type} options, and this is a {slot_type} choice."` | `n26/library/authoring.py:684-687` |
| `PicklistMember.clean()`: pickable/picklist domain mismatch | `f"{pickable} belongs to {pickable.slot_type}, and {picklist} lists {picklist.slot_type} options."` | `n26/library/models/slots.py:181-187` |
| `Slot.clean()`: picklist/slot_type domain mismatch | `f"{picklist} lists {picklist.slot_type} options, and this is a {slot_type} choice."` | `n26/library/models/slots.py:378-384` |
| `DefaultAssignment.clean()`: starting pick with no slot named | "A starting pick belongs to a slot. Name the slot this pick settles." | `n26/library/models/defaults.py:245-251` |
| `DefaultAssignment.clean()`: starting pick's domain doesn't match the slot's domain | `f"{self.default_pickable} belongs to {self.default_pickable.slot_type}, and {self.slot} offers {self.slot.slot_type} options."` | `n26/library/models/defaults.py:252-258` |
| `NotOnOffer` default message (pre-existing, unchanged, shown for context) | `f"{anchor.assignable} does not offer a choice of {type(chosen)._meta.verbose_name}."` | `n26/core/operations.py:170-174` |
| `NotOnOffer` new slot-specific message (`_choose_for_slot`, wrong domain) | `f"{chosen} cannot settle {slot.choice_label} — that choice takes {slot.slot_type} options."` | `n26/core/operations.py` (`_choose_for_slot`, ~line 815-821) |

*Count: 8 distinct refusal/validation strings (2 are duplicated across a helper function and the model's own `clean()`).*

---

## 6. Player-facing strings (the choose page)

| Element | Text | File:line |
|---|---|---|
| Choose button label | "Choose" | `n26/core/templates/cotton/n26/choice_picks.html:88` |
| Choose button accessible name | `aria-label="Choose {{ option.name }}"` | choice_picks.html:87 |
| Remove button label | "Remove" | choice_picks.html:80 |
| Remove button accessible name | `aria-label="Remove {{ option.name }}"` | choice_picks.html:79 |
| Flash: chosen | `f"{said} {picked.name} — {offer.label}."` where `said = "Chose"` | `n26/core/views/choose.py:2189-2193` |
| Flash: removed | `f"{said} {picked.name} — {offer.label}."` where `said = "Removed"` | same, `said` set at `choose.py:2188` |
| Taken-mark on an option ("already chosen for X") | `f"already chosen for {self.taken_for}"` (joined into `Choosable.remark` with " · ") | `n26/core/render.py:311-313` (`Choosable.remark` property) |
| Empty state (single-pick offer, existing wording, shown for context — unchanged text but now conditionally rendered) | "Nothing is on offer here yet. This slot draws on lists that other picks open up, so making those choices first fills it in." | `n26/core/templates/n26/choose.html:85-88` |
| Empty state (choice-picks component default) | "Nothing is on offer here yet." | `n26/core/templates/cotton/n26/choice_picks.html:41` |
| Stale-page error (pre-existing, still applies to both single and multi picks) | "That is not one of the things on offer." | `n26/core/views/choose.py` (~line 192) |
| Card note: card is full-but-full-mark (via `_choosable`, `control` field) | *(no new player-visible string — mechanism only)* | `n26/core/render.py:918-957` |

**Card remark ("… — 0 of 1 chosen")**:

| Element | Text | File:line |
|---|---|---|
| Shortfall note | `f"{slot.kind_label} — {len(slot.picks)} of {slot.min_picks} chosen"` | `n26/core/effects.py` (`_shortfall_notes`, ~line 1174-1180) |
| Duplicate-pick note (pre-existing pattern, now scoped to slots that don't allow repeats) | `f"{thing} is chosen for both {held.source} and {slot.source}"` | `n26/core/effects.py` (`_repeat_notes`, ~line 1144-1153) |

*Count: 12 player-facing strings.*

---

## 7. Prose sentences and hints (the About column)

All from `n26/library/prose.py`.

**`_asks(slot)`** — what a choice says about itself, before its modifiers:

| Case | Sentence text | Hint | Line |
|---|---|---|---|
| Hidden slot | `f"Holds {count} {named} from {slot.picklist}, and asks nothing."` | "No choice row is drawn. What is picked still does everything it does, which is how several things arrive together under one name." | 632-639 |
| Ordinary slot | `f"Asks for {count} {named}, chosen from {slot.picklist}."` (+ `" What is chosen belongs to the gang, not to whoever was asked."` when assigned to the gang) | `f"The choice stays on the card until it is made, and making it late costs nothing. {bounds}"` where `bounds = f"Fewer than {min} is a note on the card, never a refusal, and the picker stops offering at {max}."` | 640-649 |
| `_picks_asked` wording | `"one"` / `str(max_picks)` / `f"{min} to {max}"` | — | 616-619 |

**`_listed(edges)`** — the lists that offer a pickable:

> Sentence text: `f"Listed in {picklist}."`
> Hint: "The options behind a choice. Everything on this list is offered wherever a choice draws on it."

`n26/library/prose.py:1051-1063`

**`_offered_by_a_choice(edges)`** — the choices that draw on a list holding
this pickable:

> Sentence text: `f"May be chosen for {_named(slot)}."`
> Hint: "The choice is on the card while whatever asks it is, and this is one of the options it offers."

`n26/library/prose.py:1067-1088`

**`_started_with(edges)`** — a pickable that arrives as a slot's starting
pick:

> Sentence text: `f"Chosen from the start for {_named(reference.row.slot)}."`
> Hint: "Arrives already picked, the moment the choice does. Changing it afterwards is the ordinary rechoose."

`n26/library/prose.py:1091-1109`

*Count: 5 distinct `Sentence(...)` call sites, 5 hints (one `_asks` case has an inline-built `bounds` fragment folded into its hint).*

---

## 8. Gallery text

**Design-system catalog entry** (`n26/designsystem/catalog.py`, new
`Component` for `choice-picks`):

> Summary: "A list of things to choose and unchoose one at a time."
>
> Notes: "The third way to draw the same structure, and a sibling of the
> other two for the reason they are siblings of each other: radios ask
> which one, boxes ask which of these, and a choice holding three picks
> asks neither. A mode of choice-offer is the obvious saving and the wrong
> one: the single selection a shared name keeps across the lot is exactly
> what must not happen here, so every branch in that template would be
> undoing what its radios do. Each option carries its own submit instead:
> the one that was clicked is the only one sent, which is how adding and
> taking back tell themselves apart with no script and no state to keep.
> What the choice holds draws with the act that takes it back; when it is
> full the rest are not listed at all, because the alternative is a click
> that silently drops a pick the reader made earlier. Which act an option
> gets is decided in Python and read off the option, so this never works
> out for itself what the choice is holding."

`n26/designsystem/catalog.py:1632-1653`

**Demo titles and notes** (front-matter comments in the demo templates):

| File | Title | Note |
|---|---|---|
| `n26/designsystem/templates/designsystem/demos/choice-picks/10-part-way.html` | "A choice part-way made" | "What the choice already holds is taken back; what it does not is added. Each option's own act, so there is nothing to save at the end. The muted line is what the option has to say about itself — here, the other choice that has already had it." |
| `n26/designsystem/templates/designsystem/demos/choice-picks/20-full.html` | "With no room left" | "A full choice lists only what it holds. The rest stop being offered rather than one of them being pushed out unasked — the way to something else is to take a pick back." |

**Sample-data labels feeding the gallery** (`n26/designsystem/sampledata.py`):

| Item | Text | Line |
|---|---|---|
| `choice_picks_offer()` label | "Gang Legacy" | 953 |
| Held options | "Cawdor", "Escher" | 940-950 |
| Not-yet-taken option | "Ironhead Squats" | 951-956 |
| `taken_for` example on `choice_offer()`'s existing "Backstab" option | "Second skill" | ~910-914 |
| `taken_for` on the not-yet-taken "Ironhead Squats" | "Second legacy" | 955 |

*Count: 1 catalog component entry, 2 demo title/note pairs, 5 sample-data strings.*

---

## 9. The two doc drafts (in full)

Both are marked as drafts within the source files themselves (`> Draft, for
review.`), reproduced here in full since they're the primary review
surface.

### `n26/library/concepts.md` — new sections (lines 184-236)

> ### Slot type
>
> > Draft, for review.
>
> *A domain of choice — Gang Legacy, Affiliation, Archetype — and everything authored in it.*
>
> Fields of its own: a **plural** (what several of them are called, so a page can say "Gang Legacies"), and **allows repeats** (whether one holder may pick the same option for two choices of this domain).
>
> Not an assignable: nothing holds a domain. It is what the other three name, and authoring refuses a mismatch between them — a list of Affiliations cannot sit behind a Gang Legacy choice. Which domain an option, a list or a choice belongs to is settled when it is made and not offered again afterwards: moving one would leave a list offering options its choice could not take, and every pick already made answering nothing. Something in the wrong domain is a new one, made in the right one. Its page is where the whole domain is built: its options, its lists, and the choices that draw on them.
>
> ### Pickable
>
> > Draft, for review.
>
> *One option a choice offers: Cawdor, Clanless, Brawler.*
>
> Fields of its own: the **slot type** it is an option in — plus the shared assignable set, so whatever the option means rides it as ordinary modifiers.
>
> It never draws a row of its own: it appears under its choice's row as the answer. Without its choice it shows nothing and does nothing — an option nobody was offered is not something the holder has — so it arrives chosen, given, or as a choice's starting value, and the authoring form refuses one built in on its own. Reach: whatever its own modifiers say, from wherever the pick landed.
>
> ### Picklist
>
> > Draft, for review.
>
> *The options behind a choice: a flat, ordered list of one domain's options.*
>
> Fields of its own: a **slot type** and a **name**. Each option on it carries its place in the order and, where this list calls the option something else, a wording of its own.
>
> No sections, no placements, no prices — where a collection is a catalogue, this is a menu. One domain may have several: what a leader chooses from and what a champion chooses from are two lists over one domain. Not an assignable; a choice names it.
>
> ### Slot
>
> > Draft, for review.
>
> *A choice put on a card: a list of options, a label, and how many picks.*
>
> Fields of its own: its **slot type** and **picklist**; the **label** the card calls the choice by; **min** and **max picks**; **assigned to** (whether the pick lands on the bearer or on the gang); **hidden**; and a position among the choices on one card.
>
> Assigning one is what puts the choice on a card — built into a profile, given by a modifier, or brought by an option when something is bought. The card draws the label with what has been picked, or a control to pick, on the holder's own card and nowhere else: a choice the gang holds is asked once rather than on every fighter. Fewer picks than the minimum is a note on the card, never a refusal, and the picker stops offering at the maximum. A choice of one is answered by picking, and picking again replaces the answer; a choice of several is made a pick at a time, each option on the picker adding or taking back its own — full, it offers the rest again once one has been taken back. A choice of nought asks nothing. **Hidden** draws no choice row at all while what is picked still applies, which is how several things arrive together under one name.
>
> ### Picks
>
> > Draft, for review.
>
> *Not a type: the assignment that settles a choice.*
>
> Choosing writes an ordinary assignment — the option, hosted where the choice says it lands, caused by the choice's own assignment and pointing back at it, and naming the choice row it settles. So removing the choice removes the pick and everything the option gave; two choices of one domain on one holder stay independent, even where one thing opened both; and nothing is worked out from what kind of thing was chosen. A pick is free and adds nothing to any rating.
>
> A pick the gang holds is a fact about every model in it: a rule reaching "models with the Cawdor legacy" reaches them all, the fighter who was asked included.
>
> Where the domain takes one option once, the picker marks the options already spent on another choice, and the card says when one option has answered two. Marks and notes, never locks: the narrowing informs, and an owner may still hand over an option no list offered.

### `n26/library/recipes.md` — new recipe (lines 101-150)

> ## A Gang Legacy
>
> > Draft, for review. The shape below is the authoring one; everything in
> > square brackets is a fact about the rules rather than about the app,
> > and is still to be filled in.
>
> A gang legacy is a choice a fighter makes once, each option opening an
> equipment list to whoever picks it. The same six steps build any domain
> of choice; this one is worth writing down because it uses all of them.
>
> 1. Create a **slot type** named "Gang Legacy" — a domain of choice —
>    and give it a plural, so a page can say several of them. Set *allows
>    repeats* to [whether one gang may hold the same legacy twice].
>    Everything below is built on its page.
> 2. Add an **option** for each legacy: [the legacies the rules give].
> 3. On each option's page, attach a **modifier**: targets the model,
>    *gives* that legacy's equipment list. The list is an ordinary
>    collection at its own prices, so a fighter who picks a legacy buys
>    from that list at that list's prices. [Anything else a legacy grants
>    — something scoped to a rank, something reaching the gang — is a
>    further modifier on the same option.]
> 4. Add a **list of options** holding what a fighter may choose from.
>    Add more than one where [different fighters are offered different
>    legacies]: a domain may have as many lists as it needs, and a
>    fighter is offered exactly the one their choice draws on.
> 5. Add a **choice** per list, labelled "Gang Legacy", taking [how many
>    picks], assigned to [the bearer — or the gang, where what is picked
>    belongs to the gang rather than to whoever was asked].
> 6. Build the matching choice into each fighter entry that may take one.
>    An entry with no legacy carries no choice at all, and its card asks
>    nothing.
>
> A fighter hired from an entry carrying the choice arrives with an open
> "Gang Legacy" row on their card. Clicking it offers that list; picking
> one opens the legacy's equipment list on their equip page and changes
> nothing else. The pick is free and adds nothing to the gang's rating.
>
> A list with one option on it is still a choice: the row stays open until
> the player picks, and nothing is written for them.
>
> To have an entry arrive with its legacy already settled, build the
> choice in and name a **starting pick** beside it. The player changes it
> afterwards the way they would change any choice.
>
> Two things this build cannot do yet. A gang cannot be given something
> for one of its fighters holding a legacy — a condition reads what a
> model has, never what anyone in the gang has. And a list cannot say
> that it is only for a particular moment; it is open whenever the
> fighter's equip page is.

---

## Completeness check

Ran `grep -n "^+.*<pattern>" git diff main...HEAD` for each of `help_text=`,
`messages\.`, `ValidationError`, `Refusal`, `Sentence(`, `hint=`, `title=`,
`label=`, and `empty` (case-insensitive), across the full diff. Every hit
either:

- appears verbatim above, or
- is in a migration file that mirrors a model-source string already listed
  (migration `0057_choices_are_authored_as_slots_and_picks.py` regenerates
  every `help_text` from the model definitions — not a separate authoring
  decision), or
- is in a test file (`test_slots.py`, `test_authoring_views.py`,
  `test_gang_legacy.py`, `test_prose.py`, `test_slots_and_picks.py`,
  `test_outcast_affiliation_shape.py`, `test_outcast_archetype_shape.py`,
  `designsystem/tests.py`) asserting against strings already listed above,
  or supplying arbitrary test fixture labels ("Legacy 1", "Tree one", "Aa",
  "Zz", etc.) that aren't shipped copy, or
- is plumbing with no user-facing string (e.g. `kind_label=slot.choice_label`
  passing a property through, `chosen_for`/`chosen_for_slot` field names,
  `ChoiceOffer(label=slot.kind_label, ...)`).

No string was found that I could not attribute to a file:line.
