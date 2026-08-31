---
name: microcopy
description: >
  Rules for writing user- and author-facing strings: template text, button
  labels, headings, empty states, form labels and help_text, messages.*,
  validation errors, model verbose_name and docstrings shown in authoring
  pages, emails, notifications, and admin/maintenance screens. Load this
  skill BEFORE writing or editing any such string, and when reviewing a
  diff that touches one. This is the canonical home of the project's word
  bans and copy anti-patterns.
---

# Microcopy

The reader is mid-task and will not give the words a second read. Every string
must hand over its meaning in one pass: the real noun, the plain verb, the
concrete fact. Anything that makes the reader decode — cleverness, metaphor,
personification, compression, drama — taxes them to make the writing look
good. Spend nothing of the reader's attention on the writing itself.

A wordy-but-plain sentence beats a short-but-clever one. "That is not one of
the things available to pick." is fine. "Nought asks for nothing." is not.

## Scope

Every string a person reads in the product, whoever they are:

- Template text, headings, button labels, tooltips, empty states, table headers
- Python-side strings: `messages.success/error/info`, form `label` and
  `help_text`, `verbose_name`, choices labels, validation errors
- Model help text (in `n26/library` the model field is the only legal home for
  help text) and model docstrings — library docstrings render on the authoring
  pages, so they are product copy
- Emails and notifications
- Admin and maintenance screens (staff are readers too)

Not in scope: commit titles and PR descriptions (see
`.github/COMMIT_STYLE.md`), code comments, log lines.

## Base rules

**Sentences.** One idea per sentence. Active voice. Instructions are
imperative ("Upload one first."). Short, common words: use, not utilise;
about, not approximately; help, not assist.

**Address the reader as "you".** "You can change this later."

**Contractions are fine, negatives are not.** "you'll" is fine; always spell
out "do not", "cannot", "will not" — a missed negative changes the meaning.

**Full stop on messages.** Every message, confirmation, and help-text sentence
ends with one: "Battle recorded." Never an exclamation mark, anywhere.

**Sentence case, lowercase domain nouns.** gang, fighter, campaign, battle,
weapon, territory are common nouns: "Delete gang", "Add a gang to this
campaign". Capitalise only true proper nouns (Necromunda, Gyrinx, Patreon).
This supersedes the old n23 rule that title-cased domain nouns; changed n23
strings follow this rule too (fix on touch — do not sweep untouched copy).

**Buttons: bare verb where the object is obvious.** "Save", "Add", "Remove"
when the screen leaves no doubt; verb + object when it could be ambiguous
("Add fighter"). A `success` button ends a form; a `primary` button starts
one (see `n26/CLAUDE.md`).

**Name the specific noun when the code knows it.** "That weapon is not one of
the options here." Generic wording ("thing", "item") only when the type
genuinely varies at that call site.

**Success messages state the fact.** "Battle recorded." "Sold Bolt pistol for
45¢." Never "successfully", never "has been Xed!".

**Refusals state the rule.** "Only the campaign owner can edit this battle."
— the reader learns who can, not just that they cannot. Never bare jargon
("Invalid flow parameters.") and never apology ("We are sorry, but…").

**Empty states say what is absent and what fills it.** "No sheets uploaded
yet. Upload one first." "No gangs in this campaign yet." The "yet" marks a
normal starting state, not an error.

**Help text: the fact first, detail after.** Fragments are fine: "Optional —
you can name them later." "The gang's story. Shown on the lore page, never
printed."

**No "please", no emoji.** Icons come from the icon system; emoji never appear
in product strings. Em-dashes are house punctuation and are allowed — but not
as a way to bolt on a dramatic aside.

**British spelling** in prose and our own names (colour, organise); names that
mirror CSS or a package API keep that API's spelling.

## Anti-patterns

These are the failure modes of "clever" copy. Each has appeared in this
codebase; the before strings below are real.

### Personification

The app, the rules, a number, a collection, or code never asks, knows,
refuses, wants, sells, or decides. Say what happens or what the reader can do.

| Wrong | Right |
| --- | --- |
| The conversion refuses: … | The conversion cannot run: … |
| Fighter or Vehicle — the rules know no other Type. | Type is Fighter or Vehicle. |
| How many picks expected. Nought asks for nothing. | How many picks to ask for. 0 means none. |
| This collection sells lasguns. | This collection contains lasguns. |

### Saying what isn't

Negation riddles and drama in place of the plain fact. State what is true, or
what the reader can and cannot do, directly.

| Wrong | Right |
| --- | --- |
| There is no way back from here | You cannot undo this |
| …the rules know no other Type. | Type is Fighter or Vehicle. |

### Quaint vocabulary

Archaic, literary, or twee word choices. Use the ordinary word.

| Wrong | Right |
| --- | --- |
| Nobody by that name. | No users match that name. |
| {name} had already gone. | {name} was already removed. |
| Nought | 0 |

### Over-compression

Dropped words that force the reader to decode. The test is one-pass
comprehension, not length: "Ties fall back to name." is fine (the meaning
arrives whole); "How many picks expected." is not (expected by whom? decode
required). When in doubt, put the words back.

### Marketing-speak and AI tells

The feature is described, never sold. Ban outright: "successfully", trailing
"!", "Get started", "Ready to…" headings, "powerful", "seamless", "robust",
"leverage", "unlock", "delve", "We are sorry". Also the shapes: false
antithesis ("It's not X, it's Y"), staccato triads ("Clear. Simple. Done."),
rule-of-three adjective padding.

## Word bans

These govern product copy, UI strings, and identifiers. They do not apply to
commit titles (see `.github/COMMIT_STYLE.md`). This list is the canonical
record — other files that mention "noun bans recorded elsewhere" mean this one.

| Banned | Use instead | Why |
| --- | --- | --- |
| cost | price (what a surface asks now) or rating (what a purchase added to the gang's worth) | The two numbers part company at the first discount. n26-wide; a test enforces it (`n26/tests/sandbox/test_money_words.py`). |
| row (for an assignment) | assignment | "Row" is presentation, not the thing. |
| shelf, shop | section, category, or the boring relational name | Commerce metaphors invent a noun the domain does not have. |
| till | the real name of the payment point | Same. Also never "till" for "until". |
| sells (a collection or the trading post) | contains, includes | A collection represents membership; it is not a merchant. |
| sow | create | |
| pressed | clicked | |
| obligation, debt | name the mechanism that tracks what is owed | Banned in the built-ins programme wording. |
| answer | pick or choose (see below) | Speech metaphor. |
| spoken, said (in identifiers) | name the mechanism | Speech metaphors hide what the code does. |
| SKU | assignable | |
| Get started, successfully, "!" | state the fact | See anti-patterns. |

**pick vs choose are precise domain verbs, never interchanged:** *pick* is the
option-groups verb (picking from a picklist's options); *choose* is the
offers-a-choice verb (resolving a choice an offer puts on a card). Player
copy keeps the distinction.

Beyond this table, use the words in `n26/design/glossary.md` and
`n26/library/concepts.md` (maintainer's checkout only — if absent, follow this
file and the models' own vocabulary). A term in neither is a design
conversation, not a naming choice. Never invent a noun.

## Calibration corpus

Strings that pass, verbatim from the codebase — match this register:

- "Battle recorded."
- "Nothing changed."
- "You can change this later."
- "Leave blank to spend as much as you like."
- "That item is not on this list."
- "Say whether you are accepting or declining."
- "No gangs in this campaign yet."
- "Paste the link a player sent you, or the gang's id."
- "Where it sits in the list. Ties fall back to name."
- "Only the campaign owner can edit this battle."

## Cold read

Before finishing, read every new or changed string as a stranger mid-task who
will read it exactly once. If any phrase draws attention to itself — a smile,
a nice turn, a pause to decode — rewrite it until there is nothing to notice.

`scripts/check_microcopy.py` warns (never blocks) about the greppable subset
of these rules; run it over changed files, or let the PostToolUse hook do it.
For a full pass over a diff, run the **copywriter** agent
(`.claude/agents/copywriter.md`).
