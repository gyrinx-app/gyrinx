# Staged content

Staging lets you write new content, check it in the app exactly as players
will meet it, and put it live when the whole change is ready. A staged
thing is held back from every place a player adds to a gang. Players do
not see it there until you put it live; staff do, and the staged-content
flag can let chosen players in.

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
fighters, weapons and their profiles, wargear, weapon accessories,
skills, powers, subtypes, special rules, pickables, and campaign assets.

The lines of a list count too. An equipment list is made of entries — a
weapon at a price — and a picklist of member lines. A new line on a live
list is what puts a live thing in front of players, so the lines can be
staged as well, and an import holds back the lines it writes along with
the things.

An interstitial — the screen shown when a slot arrives — can be staged:
stage it while its words are being written, and put it live when they
read right. Its attachments to slots carry the flag as well, so an
import can hold one slot's attachment back while the rest go live and
the staged-content page lists it; the authoring page that attaches a
slot has no switch of its own, and a slot attached there to a live
interstitial is live at once.

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
5. If the book is not going ahead, open Staged content and delete
   everything staged. Your test gangs go with it. Live content is not
   touched.

## Deleting what you made

Deleting is for the unused. Anything that has a thing — a gang that
holds it, a list that offers it, an option that brings it — protects
it, and a delete page says what those are instead of deleting.

The one holder that goes with the thing is your own test gang. A gang
counts as a test gang when its owner is staff and it shares no
campaign and no battle with a player's gang. Deleting a gang from its
own page only takes it off your list, so a test gang keeps holding
everything you gave it until it is deleted with the content. The delete
page lists the test gangs it would take, with their owners, and the
button says how many. Each is deleted whole: its models, its gear, its
ledger and its history.

A delete that takes a gang runs after you confirm it, and the page you
land on reloads until it says Deleted or Not deleted, with the reason.

A player's gang is never deleted this way. If a player has a staged
thing — a live fighter's kit brought it, or you let them in with the
staged-content flag — the delete page names the gang and its owner, and
nothing is deleted. The same goes for a campaign a player is in.

A gang type cannot be deleted while fighters are written for it.
Delete the fighters first, or delete everything staged together, which
plans the whole set at once so that nothing refuses because of another
staged thing.

### A firing line fighters already have

A weapon's free lines arrive on every fighter that has the weapon:
nobody chose them and nobody paid. So a line added by mistake can be
deleted even after fighters have it. Its delete page lists the fighters,
by gang and owner, and the button says how many. The line is removed
from each of them, gang by gang, and then deleted. Their gangs are not
otherwise touched, and no money moves.

A line somebody paid for, or one with something under it, is not
removed this way: the page names the gang and the fighter, and nothing
is deleted.

### Two rows for one thing

Content imported twice, or a first attempt kept beside the corrected
one, leaves two rows that fighters have bought and lists offer. Open
the duplicate, choose **Merge it into another…**, and pick the row that
stays. The page says what merging would do: the gangs whose fighters
are pointed at the row that stays, the lines that follow by name, the
list lines and built-ins that move. Nobody's money moves, and each gang
is checked before and after.

A firing line follows by name, so every line on the duplicate needs a
line of the same name on the row that stays. One without stops the
merge and is named: add it to the row that stays, or delete it from the
duplicate first. Modifiers, use restrictions and built-ins on the
duplicate itself are yours to move or detach before merging; the merge
does not guess at them.
