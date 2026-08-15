# Slots & Pickables — language review

Every entry below is a direct quote from the diff (`git diff main...HEAD`),
tagged with the file and line it lives at. This version reflects the
vocabulary-correction round (commit `13dc224f`, "the pages speak the
spec's five nouns, and nothing coined"): the pages now use only the
spec's five nouns — **slot type**, **pickable**, **picklist**, **slot**,
**pick** — with every improvised coinage ("domain", "option", "list of
options", "choice-for-slot") removed from shipped copy, and unmigrated
kinds (Archetype, Affiliation) no longer cited as examples of the
vocabulary — only Gang Legacy, the one slot type actually built, is.

Edit any entry in place — change the quoted text, leave a note, whatever's
fastest — and the edits will be integrated back to the file:line noted.

---

## 1. Authoring index & family

| What | Text | File:line |
|---|---|---|
| Family label (menu heading) | `"Slots & Pickables"` | `n26/library/models/assignable.py:48` |
| `Family.CHOICE`'s own comment (says what the menu groups) | "A slot type and its parts: the type itself, its pickables, the picklists they are offered on, and the slots that offer them. Four kinds that only mean anything together, so the menu keeps them together." | `n26/library/models/assignable.py:44-47` |

Kind menu descriptions — each model's docstring first line, which is what
`kind_summary()` renders as the menu row description (`n26/library/views.py:885-889`):

| Kind | First line | File:line |
|---|---|---|
| SlotType | "What is chosen: Gang Legacy is the first, and new ones are authored, never coded." | `n26/library/models/slots.py:39` |
| Pickable | "One pickable a choice offers: Cawdor, Aranthian, Outcast Leader." | `n26/library/models/slots.py:90` |
| Picklist | "The pickables behind a choice: a flat, ordered list of them." | `n26/library/models/slots.py:137` |
| Slot | "A choice put on a card: a picklist, a label, and how many picks." | `n26/library/models/slots.py:256` |
| HasPickable (condition) | "Condition: the model has one of these picked." | `n26/library/models/modifier.py:386` |

---

## 2. Model docstrings (full text, verbatim)

**Module docstring**, `n26/library/models/slots.py:1-23`:

> Slots and picks — a choice made from a curated list, authored not coded.
>
> A new slot type is four rows and no code. A **slot type** names what is
> chosen (Gang Legacy is the first). **Pickables** are what may
> be picked in it, each an ordinary assignable carrying ordinary modifiers.
> A **picklist** is the flat, ordered list of them a choice draws from. A
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

**`SlotType`**, `n26/library/models/slots.py:39-44`:

> What is chosen: Gang Legacy is the first, and new ones are authored, never coded.
>
> Ties a slot, its picklist and its pickables together — all three name
> one of these, and authoring refuses a mismatch. Whether the same
> pickable may be picked twice over is a fact about the slot type, so it
> is stated here once rather than on every slot.

**`Pickable`**, `n26/library/models/slots.py:90-100`:

> One pickable a choice offers: Cawdor, Aranthian, Outcast Leader.
>
> A named value of its slot type that carries whatever it means as
> ordinary modifiers — an equipment list opened, a subtype granted, a
> further choice offered.
>
> It never draws a row of its own: it appears under its slot's choice
> row as the answer. **Without its slot it shows nothing and does
> nothing** — a pickable nobody was offered is not a thing the holder
> has. So it arrives chosen, given, or as a slot's starting value, and
> never as a bare built-in.

**`Picklist`**, `n26/library/models/slots.py:137-143`:

> The pickables behind a choice: a flat, ordered list of them.
>
> One slot type throughout, no headings and no prices — where a
> collection is a catalogue, this is a menu. Two slots may draw from one
> picklist, and one slot type may have several: the legacies a House
> fighter chooses from and the one a Squat fighter does are two
> picklists over one slot type.

**`PicklistMember`**, `n26/library/models/slots.py:191-195`:

> One pickable on one list, in its place.
>
> The pickable says what it is and what it does; this says that this
> list offers it, where in the order, and — where one list calls it
> something else — under what wording.

**`Slot`**, `n26/library/models/slots.py:256-269`:

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

**`HasPickable`** (condition model), `n26/library/models/modifier.py:386-395`:

> Condition: the model has one of these picked.
>
> "Models with the Cawdor legacy" — one condition serving every slot
> type ever authored, because what was picked is an ordinary
> assignment and picking it is an ordinary possession. Any-of within
> the row; negated, it is everyone who picked something else.
>
> A pick with no slot behind it is not a possession, so it is not
> matched here either: a pickable nobody was offered says nothing about
> the model holding it.

**Reworded docstrings on touched models** (existing model, changed sentence):

`Family` (assignable.py) — the enum's own docstring, extended:

> "...says what *sort* of thing a kind is, so the menu can read as the
> author thinks — the plumbing, the model's own qualities, the kit it
> carries, the gang-scale picks, **the slot types**. A discovering
> test refuses any authorable kind without one."

— `n26/library/models/assignable.py:26-34` (the bolded clause is new;
supersedes the previous edition's "the domains of choice" wording)

`HasSubtypes` — one sentence appended:

> "'Leaders and Champions each select a skill' is one row naming both —
> any-of within the row. Wanting Mounted *and* Wyrd is two rows.
> **Negated, it is the same row read the other way: everyone the row
> does not name.**"

— `n26/library/models/modifier.py:299-306`

`AssignableChoice.accepts` docstring — one clause appended to the
existing sentence about the affiliation carrier (the method is called
`accepts`, not `compatible_with_kind` as an earlier draft of this
review had it):

> "...but has no type line, no skills row, and holds no weapons, so
> nothing else can land there. **A slot may land on either: a gang is
> asked its affiliation, a fighter their legacy.**"

— `n26/library/models/modifier.py:830-843`

`ef_adds()` docstring — first line extended:

> "Grants the target a subtype, skill, trait, collection, rule, weapon
> **— or a further choice, which is how one pick opens the next.**"

— `n26/library/authoring.py:1527-1529`

`ChoiceSlot` dataclass docstring — substantially rewritten to cover a
slot-borne choice as well as a modifier's offer (quoted here for
completeness; the render/effects internals are in section 6):

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

— `n26/core/effects.py:148-159`

---

## 3. Field help texts

Every `help_text=` the branch adds on a model field (both migrations —
`0057_choices_are_authored_as_slots_and_picks.py` and
`0059_slots_and_picks_say_slot_type_and_pickable.py` — mirror these
verbatim, auto-generated from the model source rather than a separate
authoring decision, so only the model-file location is given):

| Model.field | Text | File:line |
|---|---|---|
| `_negatable()` helper (shared by `HasSubtypes.negate`, `IsProfile.negate`, `HasPickable.negate`) | "Reach everything this does not name — every model except these. Other conditions still narrow it further." | `n26/library/models/modifier.py:278-281` |
| `HasPickable.pickables` | "The model must have picked at least one of these." | `n26/library/models/modifier.py:406` |
| `DefaultAssignment.default_pickable` | "A slot's starting pick — what the choice arrives already settled on. Changing it later is the ordinary rechoose." | `n26/library/models/defaults.py:218-221` |
| `SlotType.name` | `'What is chosen, e.g. "Gang Legacy".'` | `n26/library/models/slots.py:51` |
| `SlotType.plural_name` | `'What several of them are called, e.g. "Gang Legacies". Blank adds an s.'` | `n26/library/models/slots.py:57-59` |
| `SlotType.allows_repeats` | "Whether one holder may pick the same pickable for two slots of this type. Turned off, the card says when they have — it never stops them." | `n26/library/models/slots.py:63-67` |
| `Pickable.slot_type` | "The slot type this pickable belongs to." | `n26/library/models/slots.py:118` |
| `Picklist.slot_type` | "The slot type these pickables belong to." | `n26/library/models/slots.py:152` |
| `Picklist.name` | `'What this picklist is called, e.g. "Gang Legacies".'` | `n26/library/models/slots.py:156` |
| `PicklistMember.label_override` | "What this list calls the pickable, where that differs from its own name. Blank uses the name." | `n26/library/models/slots.py:212-215` |
| `PicklistMember.position` | "Where it sits in the list. Ties fall back to name." | `n26/library/models/slots.py:219` |
| `Slot.slot_type` | "The slot type this choice is in." | `n26/library/models/slots.py:300` |
| `Slot.picklist` | "The picklist this choice draws on." | `n26/library/models/slots.py:306` |
| `Slot.label` | `'What the card calls this choice, e.g. "Gang Legacy". Blank uses this slot\'s own name.'` | `n26/library/models/slots.py:312-315` |
| `Slot.min_picks` | "How many picks the card expects. Fewer is a note on the card, never a refusal. Nought asks for nothing." | `n26/library/models/slots.py:319-322` |
| `Slot.max_picks` | "How many picks the choice holds. The picker stops offering here." | `n26/library/models/slots.py:326` |
| `Slot.assigned_to` | "Where the pick lands. Almost always the bearer; assigned to the gang, the pick is the gang's and is broadcast to every member, whoever was asked." | `n26/library/models/slots.py:332-336` |
| `Slot.hidden` | "Draw no choice row at all. What is picked still applies — this is how several things arrive together under one name." | `n26/library/models/slots.py:340-343` |
| `Slot.position` | "Order among the slots on one card. Ties fall back to name." | `n26/library/models/slots.py:347` |
| Field `Assignment.chosen_for` / `chosen_for_slot` | *(no help_text — comments only, see below)* | `n26/core/models/assignment.py:249-269` |

*Count: 19 distinct help_text strings.*

---

## 4. Authoring page furniture

**Family / slot-type index page** — no separate page copy beyond the
family label and kind summaries already listed in section 1.

**Slot-type page** (`n26/library/templates/authoring/slot_type.html`, new file):

| Element | Text | Line |
|---|---|---|
| Section heading (own-fields) | "This slot type" | 40 |
| Save button (own fields) | "Save changes" | 45 |
| Delete link | "Delete this slot type…" | 51 |
| "Add a/an X" heading | `"Add {{ section.part_article }} {{ section.part_name }}"` → renders "Add a pickable" / "Add a picklist" / "Add a slot" | 84 |
| Add-form submit label | `"Add {{ section.part_name }}"` | 95 |

Section titles/descriptions/empty-states (`SLOT_TYPE_PARTS`,
`n26/library/views.py:3005-3058`):

| Part | Title | Description | Empty state | Lines |
|---|---|---|---|---|
| Pickables | "Pickables" | "The values a choice of this slot type can settle on. A pickable does nothing until a modifier hangs on it, which is done on its own page." | "No pickables yet — a choice of this slot type has nothing to offer." | 3011-3021 |
| Picklists | "Picklists" | "The pickables behind one choice, in order. A slot type may have several picklists: what a leader chooses from and what a champion chooses from are two lists over one slot type." | "No picklists yet — a choice draws its pickables from one of these." | 3028-3038 |
| Slots | "Slots" | "One named use of this slot type: a picklist, a label, and how many picks. Building one into a profile is what puts the choice on that fighter's card." | "No slots yet — nothing puts this slot type's pickables in front of a player." | 3045-3056 |

Flashes and errors (`n26/library/views.py`, `slot_type_page`):

| Element | Text | Line |
|---|---|---|
| Success flash (own-fields save) | `f"Saved {slot_type}."` | 3114 |
| Success flash (part created) | `f"Created {made}."` | 3135 |
| Duplicate-name error (own fields) | `f"A slot type named “{edit_form.cleaned_data['name']}” already exists in this pack."` | 3110-3111 |
| Duplicate-name error (parts: pickable/picklist/slot) | `f"{spec.creates._meta.verbose_name.capitalize()} “{form.cleaned_data[spec.identity]}” already exists in this pack."` | 3128-3130 |

Both duplicate-name errors now use curly quotes (`“…”`); the rest of the
authoring pages' duplicate-name errors (e.g. the generic `create` view,
`views.py:1140-1143` and `1471-1474`) already did.

**Generic detail page** (`n26/library/templates/authoring/detail.html`):

| Element | Text | Line |
|---|---|---|
| "Add a/an X" heading, now grammatical | `"Add {{ section.part_article }} {{ section.part_verbose_name }}"` | 191 |

**Picklist part on the generic detail page** (`n26/library/views.py:264-293`,
`DETAIL_KINDS["picklist"]`):

| Element | Text | Line |
|---|---|---|
| `parts_label` | "pickables" | 275 |
| `part_name` | "pickable" | 278 |
| `parts_description` | "What a choice drawing on this list offers, in the order a player reads them. Taking one off changes only what is offered next: the pickable itself stays in the library, and anyone who already picked it keeps it." | 279-284 |
| `nothing_yet` | "No pickables yet — a choice drawing on this list has nothing to offer." | 285-287 |

**Picklist-member remove page**
(`n26/library/templates/authoring/picklist_member_remove.html`, new file
— built on the shared `<c-n26.form-page>` shell):

| Element | Text | Line |
|---|---|---|
| Page title (`head_title`) | `"Remove {{ label }}"` | 11 |
| Form title | `"Stop offering {{ label }}?"` | 14 |
| Lead | `"{{ picklist }} will no longer offer it. The pickable itself stays in the library, and on every other list that offers it."` | 15 |
| Submit label | "Stop offering it" | 16 |
| Breadcrumb: content library link | "Content library" | 21 |
| Breadcrumb: current | "Stop offering" | 26 |
| Info callout title | "Nothing already chosen changes" | 31 |
| Info callout body | "Anyone who has picked it keeps it. This changes what the next player is offered." | 32-33 |
| Success flash | `f"{picklist} no longer offers {said}."` | `n26/library/views.py:2941` (`picklist_member_remove` view) |

**Related-content section on a picklist's detail page** (new —
`DETAIL_RELATED`, `n26/library/views.py:1354-1366`; the generic loop that
draws it lives in `detail.html:225-251`):

| Element | Text |
|---|---|
| Section title | "Slots drawing on this picklist" |
| Section description | "Every slot that offers this list. A picklist nothing draws on is never put in front of a player." |
| Empty state | "No slot draws on this picklist yet, so nothing offers it." |

**Row notes in listings** (`n26/library/views.py`):

| Function | Notes produced | Line |
|---|---|---|
| `_describe_picklist_member` (docstring + note) | `f"the {member.pickable} pickable, under another name"` (when a list overrides a label) | 145-154 |
| `_describe_slot_type` | `f"{n} pickables"`, `f"{n} picklists"`, `f"{n} slots"`, and `"no repeats"` if `allows_repeats` is off | 743-753 |
| `_pickable_notes` | `f"on {n} list{'s' if n != 1}"` or `"on no list yet"` | 756-765 |
| `_picklist_notes` | `f"{n} pickable{'s' if n != 1}"` | 768-771 |
| `_describe_pickable` | slot type name + `_pickable_notes` | 774-776 |
| `_describe_picklist` | slot type name + `_picklist_notes` | 779-781 |
| `_picks_said` | `"one pick"` / `f"{n} picks"` / `f"{min} to {max} picks"` | 784-788 |
| `_slot_terms` | `_picks_said(...)`, `"the gang holds the pick"` (if assigned to gang), `"draws no row"` (if hidden) | 791-804 |
| `_slot_notes` | `f"from {picklist.name}"` + `_slot_terms(...)` | 807-809 |
| `_describe_slot` | slot type name + `_slot_notes` | 812-814 |

Verbose names (singular/plural) for the five top-level kinds plus the
condition model:

| Model | Singular | Plural | File:line |
|---|---|---|---|
| SlotType | "slot type" | "slot types" | `slots.py:71-72` |
| Pickable | "pickable" | "pickables" | `slots.py:122-123` |
| Picklist | "picklist" | "picklists" | `slots.py:160-161` |
| PicklistMember | "picklist member" | "picklist members" | `slots.py:223-224` |
| Slot | "slot" | "slots" | `slots.py:351-352` |
| HasPickable (condition, not a top-level kind) | "has pickable" | "has pickable" (same both ways) | `modifier.py:410-411` |

*Section count: 39 authoring furniture rows across the tables above (the
three `SLOT_TYPE_PARTS` rows each bundle three strings — title,
description, empty state — so 9 of the 39 are compound) + 6
verbose-name pairs.*

---

## 5. Refusals and validation messages

| Situation | Message | File:line |
|---|---|---|
| Bare pickable built into something with no slot (`_refuse_a_bare_pickable`) | "A pickable without its slot shows nothing and does nothing. Build in the slot, or a slot-with-default." | `n26/library/authoring.py:989-1001` (message at 998-1000) |
| `add_picklist_member`: pickable's slot type doesn't match the picklist's | `f"{pickable} belongs to {pickable.slot_type}, and {picklist} lists {picklist.slot_type} pickables."` | `n26/library/authoring.py:603-606` |
| `create_slot`: picklist's slot type doesn't match the slot's | `f"{picklist} lists {picklist.slot_type} pickables, and this is a {slot_type} choice."` | `n26/library/authoring.py:652-655` |
| `PicklistMember.clean()`: pickable/picklist slot-type mismatch | `f"{pickable} belongs to {pickable.slot_type}, and {picklist} lists {picklist.slot_type} pickables."` | `n26/library/models/slots.py:243-252` |
| `Slot.clean()`: picklist/slot_type mismatch | `f"{picklist} lists {picklist.slot_type} pickables, and this is a {slot_type} choice."` | `n26/library/models/slots.py:376-385` |
| `DefaultAssignment.clean()`: starting pick with no slot named | "A starting pick belongs to a slot. Name the slot this pick settles." | `n26/library/models/defaults.py:244-251` |
| `DefaultAssignment.clean()`: starting pick's slot type doesn't match the slot's | `f"{self.default_pickable} belongs to {self.default_pickable.slot_type}, and {self.slot} offers {self.slot.slot_type} pickables."` | `n26/library/models/defaults.py:252-261` |
| `NotOnOffer` default message (pre-existing, unchanged, shown for context — now overridable via a `message=` kwarg) | `f"{anchor.assignable} does not offer a choice of {type(chosen)._meta.verbose_name}."` | `n26/core/operations.py:173-176` |
| `NotOnOffer` new slot-specific message (`_choose_for_slot`, wrong slot type) | `f"{chosen} cannot settle {slot.choice_label} — that choice takes {slot.slot_type} pickables."` | `n26/core/operations.py:824-831` |
| `ValidationError` from an authoring verb, surfaced on the form | *(no new string — `form.add_error(None, refused)` shows the verb's own message from the rows above)* | `n26/library/views.py:1129`, `1510`, `3132` |

*Count: 9 distinct refusal/validation strings (2 are duplicated across a
helper function/verb and the model's own `clean()`).*

---

## 6. Player-facing strings (the choose page)

| Element | Text | File:line |
|---|---|---|
| Choose button label + accessible name | `aria-label="Choose {{ option.name }}"` … `>Choose</c-ui.button>` | `n26/core/templates/cotton/n26/choice_picks.html:90` |
| Remove button label + accessible name | `aria-label="Remove {{ option.name }}"` … `>Remove</c-ui.button>` | `n26/core/templates/cotton/n26/choice_picks.html:83` |
| Empty state (choice-picks component default) | "Nothing is on offer here yet." | `n26/core/templates/cotton/n26/choice_picks.html:46` |
| Empty state (single-pick offer, unchanged text, now conditionally rendered) | "Nothing is on offer here yet. This slot draws on lists that other picks open up, so making those choices first fills it in." | `n26/core/templates/n26/choose.html:87` |
| Flash: chosen or removed | `f"{said} {picked.name} — {offer.label}."` where `said = "Chose"` or `"Removed"` | `n26/core/views/choose.py:231-232` |
| Stale-page error (pre-existing text, now also covers a take-back with nothing behind it) | "That is not one of the things on offer." | `n26/core/views/choose.py:192` |
| Taken-mark on an option ("already chosen for X") | `f"already chosen for {self.taken_for}"` (joined into `Choosable.remark` with " · ") | `n26/core/render.py:323-327` (`Choosable.remark` property) |

**Card remark ("… — 0 of 1 chosen")**:

| Element | Text | File:line |
|---|---|---|
| Shortfall note | `f"{slot.kind_label} — {len(slot.picks)} of {slot.min_picks} chosen"` | `n26/core/effects.py:1171` (`_shortfall_notes`) |
| Duplicate-pick note (now scoped to slot types that don't allow repeats) | `f"{thing} is chosen for both {held.source} and {slot.source}"` | `n26/core/effects.py:1147-1149` (`_repeat_notes`) |

*Count: 9 player-facing strings.*

---

## 7. Prose sentences and hints (the About column)

All from `n26/library/prose.py`.

**`_asks(slot)`** — what a choice says about itself, before its modifiers:

| Case | Sentence text | Hint | Line |
|---|---|---|---|
| Hidden slot | `f"Holds {count} {named} from {slot.picklist}, and asks nothing."` | "No choice row is drawn. What is picked still does everything it does, which is how several things arrive together under one name." | 640-647 |
| Ordinary slot | `f"Asks for {count} {named}, chosen from {slot.picklist}."` (+ `" What is chosen belongs to the gang, not to whoever was asked."` when assigned to the gang) | `f"The choice stays on the card until it is made, and making it late costs nothing. {bounds}"` where `bounds = f"Fewer than {min} is a note on the card, never a refusal, and the picker stops offering at {max}."` | 648-658 |
| `_picks_asked` wording | `"one"` / `str(max_picks)` / `f"{min} to {max}"` | — | 616-620 |

**`_listed(edges)`** — the picklists that offer a pickable:

> Sentence text: `f"Listed in {picklist}."`
> Hint: "The pickables behind a choice. Everything on this list is offered wherever a choice draws on it."

`n26/library/prose.py:1044-1061`

**`_offered_by_a_choice(edges)`** — the slots that draw on a picklist
holding this pickable:

> Sentence text: `f"May be chosen for {_named(slot)}."`
> Hint: "The choice is on the card while whatever asks it is, and this is one of the pickables it offers."

`n26/library/prose.py:1064-1086`

**`_started_with(edges)`** — a pickable that arrives as a slot's starting
pick:

> Sentence text: `f"Chosen from the start for {_named(reference.row.slot)}."`
> Hint: "Arrives already picked, the moment the choice does. Changing it afterwards is the ordinary rechoose."

`n26/library/prose.py:1089-1109`

*Count: 5 distinct `Sentence(...)` call sites, 5 hints.*

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

`n26/designsystem/catalog.py:1632-1655`

**Demo titles and notes** (front-matter comments in the demo templates):

| File | Title | Note |
|---|---|---|
| `n26/designsystem/templates/designsystem/demos/choice-picks/10-part-way.html` | "A choice part-way made" | "What the choice already holds is taken back; what it does not is added. Each option's own act, so there is nothing to save at the end. The muted line is what the option has to say about itself — here, the other choice that has already had it." |
| `n26/designsystem/templates/designsystem/demos/choice-picks/20-full.html` | "With no room left" | "A full choice lists only what it holds. The rest stop being offered rather than one of them being pushed out unasked — the way to something else is to take a pick back." |

**Sample-data strings feeding the gallery** (`n26/designsystem/sampledata.py`):

| Item | Text | Line |
|---|---|---|
| `sample_about()`'s existing "It asks the gang…" sentence, reworded off the retired "one affiliation" example | "It asks the gang to make the choice — the card says Choose until they pick." | 876 |
| `choice_offer()` label | "Primary skill" | 893 |
| `choice_offer()`'s existing "Backstab" option, now marked as taken elsewhere | `taken_for="Second skill"` | 906-910 |
| `choice_picks_offer()` label | "Gang Legacy" | 953 |
| Held option | `name="Cawdor"`, `control="remove"` | 931-936 |
| Held option | `name="Escher"`, `control="remove"` | 937-942 |
| Not-yet-taken option | `name="Ironhead Squats"`, `control="choose"`, `taken_for="Second legacy"` | 944-950 |
| CHANGELOG "Outcasts" entry text, reworded off the retired archetype/affiliation example | "Gang legacies, chained picks, and the ratio notes that come with them. Said, never enforced." | 1875-1877 |

*Count: 1 catalog component entry, 2 demo title/note pairs, 8 sample-data
string changes.*

---

## 9. The two doc drafts (in full)

Both are marked as drafts within the source files themselves (`> Draft, for
review.`), reproduced here in full since they're the primary review
surface.

### `n26/library/concepts.md` — new sections (lines 184-234)

> ### Slot type
>
> > Draft, for review.
>
> *What is chosen — Gang Legacy is the first — and everything authored in it.*
>
> Fields of its own: a **plural** (what several of them are called, so a page can say "Gang Legacies"), and **allows repeats** (whether one holder may pick the same pickable for two slots of this type).
>
> Not an assignable: nothing holds a slot type. It is what the other three name, and authoring refuses a mismatch between them — a picklist of one slot type cannot sit behind another type's choice. Which slot type a pickable, a picklist or a slot belongs to is settled when it is made and not offered again afterwards: moving one would leave a picklist offering pickables its slot could not take, and every pick already made answering nothing. Something in the wrong slot type is a new one, made in the right one. Its page is where the whole slot type is built: its pickables, its picklists, and the slots that draw on them.
>
> ### Pickable
>
> > Draft, for review.
>
> *One pickable a choice offers: Cawdor, Ironhead Squat, Ogryn.*
>
> Fields of its own: the **slot type** it belongs to — plus the shared assignable set, so whatever the pickable means rides it as ordinary modifiers.
>
> It never draws a row of its own: it appears under its slot's choice row as the answer. Without its slot it shows nothing and does nothing — a pickable nobody was offered is not something the holder has — so it arrives chosen, given, or as a slot's starting value, and the authoring form refuses one built in on its own. Reach: whatever its own modifiers say, from wherever the pick landed.
>
> ### Picklist
>
> > Draft, for review.
>
> *The pickables behind a choice: a flat, ordered list of them, all of one slot type.*
>
> Fields of its own: a **slot type** and a **name**. Each pickable on it carries its place in the order and, where this list calls it something else, a wording of its own.
>
> No sections, no placements, no prices — where a collection is a catalogue, this is a menu. One slot type may have several picklists: what a leader chooses from and what a champion chooses from are two lists over one slot type. Not an assignable; a slot names it.
>
> ### Slot
>
> > Draft, for review.
>
> *A choice put on a card: a picklist, a label, and how many picks.*
>
> Fields of its own: its **slot type** and **picklist**; the **label** the card calls the choice by; **min** and **max picks**; **assigned to** (whether the pick lands on the bearer or on the gang); **hidden**; and a position among the slots on one card.
>
> Assigning one is what puts the choice on a card — built into a profile, given by a modifier, or brought by an option when something is bought. The card draws the label with what has been picked, or a control to pick, on the holder's own card and nowhere else: a choice the gang holds is asked once rather than on every fighter. Fewer picks than the minimum is a note on the card, never a refusal (no page prints these notes yet), and the picker stops offering at the maximum. A choice of one is settled by picking, and picking again replaces the pick; a choice of several is made a pick at a time, each pickable on the picker adding or taking back its own — full, it offers the rest again once one has been taken back. A choice of nought asks nothing. **Hidden** draws no choice row at all while what is picked still applies, which is how several things arrive together under one name.
>
> ### Picks
>
> > Draft, for review.
>
> *Not a type: the assignment that settles a choice.*
>
> Choosing writes an ordinary assignment — the pickable, hosted where the slot says it lands, caused by the slot's own assignment and pointing back at it, and naming the choice row it settles. So removing the slot removes the pick and everything the pickable gave; two slots of one slot type on one holder stay independent, even where one thing opened both; and nothing is worked out from what kind of thing was chosen. A pick is free and adds nothing to any rating.
>
> A pick the gang holds is a fact about every model in it: a rule reaching "models with the Cawdor legacy" reaches them all, the fighter who was asked included.
>
> Where the slot type takes one pickable once, the picker marks the pickables already spent on another slot, and the card notes when one pickable is picked for two (no page prints these notes yet). Marks and notes, never locks: the narrowing informs, and an owner may still hand over a pickable no picklist offered.

### `n26/library/recipes.md` — new recipe (lines 101-150)

> ## A Gang Legacy
>
> > Draft, for review. The shape below is the authoring one; everything in
> > square brackets is a fact about the rules rather than about the app,
> > and is still to be filled in.
>
> A gang legacy is a choice a fighter makes once, each pickable opening an
> equipment list to whoever picks it. The same six steps build any slot
> type; this one is worth writing down because it uses all of them.
>
> 1. Create a **slot type** named "Gang Legacy" — what is being chosen —
>    and give it a plural, so a page can say several of them. Set *allows
>    repeats* to [whether one gang may hold the same legacy twice].
>    Everything below is built on its page.
> 2. Add a **pickable** for each legacy: [the legacies the rules give].
> 3. On each pickable's page, attach a **modifier**: targets the model,
>    *gives* that legacy's equipment list. The list is an ordinary
>    collection at its own prices, so a fighter who picks a legacy buys
>    from that list at that list's prices. [Anything else a legacy grants
>    — something scoped to a rank, something reaching the gang — is a
>    further modifier on the same pickable.]
> 4. Add a **picklist** holding what a fighter may choose from. Add more
>    than one where [different fighters are offered different legacies]:
>    a slot type may have as many picklists as it needs, and a fighter is
>    offered exactly the one their slot draws on.
> 5. Add a **slot** per picklist, labelled "Gang Legacy", taking [how many
>    picks], assigned to [the bearer — or the gang, where what is picked
>    belongs to the gang rather than to whoever was asked].
> 6. Build the matching slot into each fighter entry that may take one.
>    An entry with no legacy carries no slot at all, and its card asks
>    nothing.
>
> A fighter hired from an entry carrying the slot arrives with an open
> "Gang Legacy" row on their card. Clicking it offers that picklist;
> picking one opens the legacy's equipment list on their equip page and
> changes nothing else. The pick is free and adds nothing to the gang's
> rating.
>
> A picklist with one pickable on it is still a choice: the row stays open
> until the player picks, and nothing is written for them.
>
> To have an entry arrive with its legacy already settled, build the slot
> in and name a **starting pick** beside it. The player changes it
> afterwards the way they would change any choice.
>
> Two things this build cannot do yet. A gang cannot be given something
> for one of its fighters holding a legacy — a condition reads what a
> model has, never what anyone in the gang has. And a picklist cannot say
> that it is only for a particular moment; it is open whenever the
> fighter's equip page is.

---

## Completeness check

Ran `grep -n "^+.*<pattern>"` over `git diff main...HEAD` for each of
`help_text=`, `messages\.`, `ValidationError`, `Refusal`, `Sentence(`,
`hint=`, `title=`, `label=`, and `empty` (case-insensitive). Every hit
either:

- appears verbatim above, or
- is in a migration file that mirrors a model-source string already
  listed (`0057_choices_are_authored_as_slots_and_picks.py` and
  `0059_slots_and_picks_say_slot_type_and_pickable.py` regenerate every
  `help_text` from the model definitions — not a separate authoring
  decision; 0059 is itself the vocabulary-correction migration, so its
  strings match the corrected model source exactly), or
- is in a test file (`test_slots.py`, `test_authoring_views.py`,
  `test_admin.py`, `test_gang_legacy.py`, `test_prose.py`,
  `test_slots_and_picks.py`, `test_outcast_affiliation_shape.py`,
  `test_outcast_archetype_shape.py`, `designsystem/tests.py`,
  `sandbox/actions.py`) asserting against strings already listed above,
  or supplying arbitrary test fixture labels ("Legacy 1", "Legacy 2",
  "Tree one", "Tree two", "Aa", "Zz", "First legacy", "Second legacy",
  etc.) that aren't shipped copy, or
- is plumbing with no user-facing string (e.g. `kind_label=slot.choice_label`
  passing a property through, `chosen_for`/`chosen_for_slot` field names,
  `ChoiceOffer(label=slot.kind_label, ...)`, the `messages.success(request,
  f"Added {said}.")` in `detail()`'s part-add flow, which is pre-existing
  and only moved inside a new `try`/`except`).

No string was found that I could not attribute to a file:line.
