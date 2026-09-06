# Staged content

Staging lets you write new content, check it in the app exactly as players
will meet it, and put it live when the whole change is ready. A staged
thing is held back from every place a player adds to a gang. Nobody but
authors sees it there until you put it live.

## What staging hides, and what it does not

A staged thing is left off every screen where a player picks content:
the cards offered when creating a gang or setting up a campaign, the hire
screen, equipment lists and the Trading Post, the ammo lines under a gun,
the skills screen, the pick screens and roll tables, the subtypes and
special rules boxes on a model's page, the accessory dialogs, and the
campaign asset picker. Typing a staged thing's id into a form does not
work either — the click is checked against the same list the screen drew.

It is not hidden anywhere else. Once a staged thing is on a gang — your
own test gang, say, or a live fighter whose kit brings it — it is drawn
for everyone who opens that gang's sheet. A roster is something players
send each other, and what it shows cannot depend on who is looking.

**Staging holds back new things. It does not hold back changes.** Reprice
a live weapon, attach a new rule to a live gang type, add an option to a
live fighter, and players see it at once, as they always have. To launch a
whole change together: stage everything new, check it, then put it all
live in one step. Corrections to live content stay immediate.

## What you can stage

Anything a player is offered somewhere: gang types, campaign types,
fighters, weapons and their firing lines, wargear, weapon accessories,
skills, powers, subtypes, special rules, pickables, and campaign assets.

The lines of a list count too. An equipment list is made of entries — a
weapon at a price — and a picklist of member lines. A new line on a live
list is what puts a live thing in front of players, so the lines can be
staged as well, and an import holds back the lines it writes along with
the things.

Things players are never offered directly — categories, statlines,
modifiers, collections themselves — cannot be staged and do not need to
be. They reach players only through something that can.

## Who sees staged content

Staff always see it, everywhere players would, exactly as players will
once it is live. That is how new content is checked: found a test gang on
the staged gang type, hire its fighters, buy from its lists.

Anyone else sees it through the **staged-content** feature flag in the
admin. Off, nobody but staff. On the allowlist, whoever is in the "N26
Staged content" group — add a few players there to try a new book with
them before it is released. Open to everyone, every signed-in player sees
it: a rehearsal of the release with a way back, because switching the
flag off hides it all again. Putting the rows live is the step that
cannot be taken back that way.

Players' screens carry no marker on staged things. The point is that
authors see exactly what players will; you tell staged from live on the
authoring pages, where a staged row carries a **Staged** badge.

## Where staging happens

- **Creating a thing.** Every creating form for a stageable kind has a
  **Staged** switch beside it, on by default. Switch it off to create the
  thing live.
- **A thing's own page** shows **Staged** or **Live** in its header, with
  the one button that changes it: **Put live** or **Stage**.
- **Importing.** The import preview has a **Stage what this import
  creates** switch, on by default. Only the rows the import creates are
  held back; rows it changes are live already and change at once.
- **Staged content**, linked from the library index, lists everything
  staged, kind by kind, with a **Put live** beside each row and a **Put
  everything live** button that releases all of it in one step. Nothing
  reaches players half-released: it all goes live together or none of it
  does.

## Working on a new book

1. Import the sheets with the staging switch on, or create the gang type
   with its switch on and everything for it after — new fighters, gear,
   lists and picks arrive staged.
2. Found a gang on the new type with your own account. Hire, equip,
   select skills, make its picks. Fix what is wrong; anything you edit
   is still staged.
3. Want other people to try it? Put them in the "N26 Staged content"
   group and set the flag to the allowlist.
4. When it is ready, open Staged content and put everything live.
