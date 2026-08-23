# Commit and PR title style

We squash-merge, so the PR title becomes the permanent commit subject. It is
what anyone scanning `git log`, a blame, or a release page has to work from,
long after the PR page has stopped being interesting. It is worth a minute.

This file is the authority on title style for this repository. Read it instead
of copying the phrasing of recent commits — the log has drifted before and may
have drifted again.

## The test

**Name the thing that changed and what now happens to it.** Someone who has
never seen the change should be able to guess which files it touches.

## Rules

- Open with the conventional-commit prefix — `feat:`, `fix:`, `refactor:`,
  `perf:`, `docs:`, `test:`, `chore:`, `build:`, `ci:`, `style:` — then say what
  changed.
- **Name at least one real, findable thing**: the page, the model class, the
  management command, the admin screen, the URL, the setting, the flag. If the
  title contains no noun you could grep this codebase for, it fails.
- **Never open with an article or "what" followed by a generic noun.** "the
  sweep", "a question", "what the conversions left standing" read as riddles,
  because the subject is a pronoun wearing a hat. This is by far our most common
  failure.
- **Don't give code intentions.** Code does not own up, admit, want or decide.
  Say what it now does.
- Under 72 characters where you can manage it.
- Plain, natural English is right. Vagueness is not — the two are not the same
  thing, and titles here have failed by confusing them.

## Titles that work

Real examples from this repository:

```
fix: show weapon profiles on equipment list item removal page
perf: stop the equipment admin page rebuilding its dropdowns per row
feat: nominate any fighter as leader when the gang's leader dies
fix: replace leaky persistent DB connections with a psycopg connection pool
feat: add admin action to recompute fighter cost caches from facts
perf: fix N+1 query explosions in List and ListFighter admin
fix: serve a real robots.txt and stop counting crawlers as engagement
fix: show house-additional gear on the stash card
```

Note how conversational most of these are. "Stop the equipment admin page
rebuilding its dropdowns per row" is not stiff or robotic — it just names the
page and the behaviour.

## Titles that failed, and why

All shipped to `main`. Each one names nothing you could look up.

| Shipped | Should have been |
|---|---|
| `fix: the sweep owns up to the one word it moves` | `fix: let the archived-answer sweep reword "archetype" to "gang legacy"` |
| `feat: what the conversions left standing can be deleted` | `feat: maintenance op to delete empty Specialisation/Archetype/SkillTree rows` |
| `feat: the answers a doubled click left behind can be cleared` | `feat: maintenance op to delete duplicate Assignments from double-clicked Choose` |
| `fix: a question keeps one answer, however fast the second arrives` | `fix: lock the Gang row in choose() so a double click can't duplicate a pick` |
| `fix: the page the gangs pager cannot turn to is dead, not a link to nowhere` | `fix: disable prev/next on the n26 gangs pager (cotton attrs take no expressions)` |
| `perf: the app serves on one core, because it only ever used one` | `perf: cut Cloud Run to --cpu=1 — p99.9 use was 0.86 vCPU, saves ~£20/mo` |

The pattern is the same every time: the change is described by its effect while
the thing it happened to goes unnamed. Keep the effect, add the subject.

## A note on our other language rules

`CLAUDE.md` asks you to describe changes by their user-visible effect and to
avoid internal shorthand. Various notes ban particular nouns in product copy
("shelf", "shop", "row" for an assignment, and others).

**None of that means "avoid naming the thing."** Avoiding internal shorthand
means explaining a term rather than assuming it; the noun bans govern product
copy, UI strings and identifiers, not commit titles. A title is allowed — and
expected — to say `ListFighterEquipmentAssignment`, `choose()`, `--cpu=1`, or
"the gangs pager". Those are the words that make it findable.

## Bodies

The same instinct applies to PR bodies: describe the effect, but name the
subject. A body that says "34 of the 399 answers moved a word" is telling you
something happened without telling you to what.
