"""The Gang supertype — which House a gang belongs to, as a hidden pick.

A journal's territory boon applies "if the Territory is held by a Goliath
gang", and an Outcast gang that chose House Goliath counts as one
(design/house-and-territory-tables.md). The fact a rule reads is a pick
on the gang: a hidden **Gang supertype** slot, drawing from a picklist of
six marker pickables — Goliath, Escher, Orlock, Van Saar, Delaque and
Cawdor — that carry no boon logic of their own. A rule keys on the pick
(``targets_gang_alone(has_gang_pickable(goliath))``) rather than hanging
off it.

A gang gets its supertype two ways, and this seed writes both:

* Each Clan House gang type builds the slot in with its own House as the
  starting pick, so founding a Goliath gang writes the pick, and built-in
  propagation gives it to every Goliath gang already founded.
* Each Outcast Clan House pickable — House Goliath and the rest, on the
  Outcast gang's own Clan House slot — carries a modifier that gives the
  gang the supertype slot with the matching pick, so a Clan House Goliath
  Outcast gang matches "has picked Goliath" as a Goliath gang does.

Nothing here is staged: the slot is hidden, so the supertype is invisible
to players by construction.

The Venator Gang Legacy picks already hold the bare names Goliath, Escher
and the rest, and a pickable's name is unique in its pack whatever its
slot type, so the six markers carry the qualifier "Gang supertype" —
author-facing only; the name a condition prints is the bare House.

Everything is matched on its natural key — pack and name — and left
alone if it is already there, so this can run against a database that
has some of it, and running it twice changes nothing the second time.
It runs through the authoring verbs, which file the propagation pass a
built-in member is owed, so it works on live model classes only: run it
as a maintenance operation after a deploy, never from a migration.
"""

from dataclasses import dataclass, field

from django.conf import settings

SLOT_TYPE = "Gang supertype"
SLOT_TYPE_PLURAL = "Gang supertypes"
PICKLIST = "Gang supertypes"
SLOT = "Gang supertype"
#: The six Clan Houses, each the name of a gang type and of its marker
#: pickable, in the order the rules list them.
HOUSES = ("Goliath", "Escher", "Orlock", "Van Saar", "Delaque", "Cawdor")
#: The Outcast gang's Clan House choice: a slot type whose name carries
#: this word, and one pickable per House named as below.
CLAN_HOUSE = "Clan"


@dataclass
class Outcome:
    """What a seed did, in words: one line per row it created, and one per
    row it looked for and left alone or could not find. Kept apart so a
    rerun that creates nothing can say so, whatever it skipped."""

    created: list = field(default_factory=list)
    skipped: list = field(default_factory=list)

    def extend(self, other):
        self.created.extend(other.created)
        self.skipped.extend(other.skipped)

    @property
    def lines(self):
        return [*self.created, *self.skipped]


def clan_house_pickable_name(house):
    """What the Outcast Clan House pickable for this House is called."""
    return f"House {house}"


def supertype_pick(house):
    """The marker pickable for this House, or None where the seed has not run."""
    from n26.library.models import Pickable

    return Pickable.objects.filter(
        pack__slug=settings.DEFAULT_CONTENT_PACK_SLUG,
        slot_type__name__iexact=SLOT_TYPE,
        name__iexact=house,
    ).first()


def seed_gang_supertypes():
    """Create what is missing of the Gang supertype, and return
    ``(outcome, picks)``: what was created and what was skipped, in
    words, and the six marker pickables by House name, so the journal
    seed can key its boons on them.

    A gang type or an Outcast Clan House pickable that is not there is
    skipped and named on the record — a fresh database has neither, and
    this creates no gang list content of its own.
    """
    from n26.library.authoring import (
        add_built_in,
        add_picklist_member,
        create_pickable,
        create_picklist,
        create_slot,
        create_slot_type,
        ef_adds,
        modifier,
        targets_gang_alone,
    )
    from n26.library.models import (
        DefaultAssignment,
        GangType,
        Pickable,
        Picklist,
        Slot,
        SlotType,
    )
    from n26.library.models.pack import get_default_pack

    outcome = Outcome()
    lines = outcome.created
    pack = get_default_pack()
    in_pack = {"pack": pack}

    slot_type = SlotType.objects.filter(pack=pack, name__iexact=SLOT_TYPE).first()
    if slot_type is None:
        slot_type = create_slot_type(
            SLOT_TYPE,
            plural_name=SLOT_TYPE_PLURAL,
            allows_repeats=False,
            **in_pack,
        )
        lines.append(f"created the {SLOT_TYPE} slot type")

    picks = {}
    for house in HOUSES:
        pick = Pickable.objects.filter(
            pack=pack, slot_type=slot_type, name__iexact=house
        ).first()
        if pick is None:
            pick = create_pickable(house, slot_type, qualifier=SLOT_TYPE, **in_pack)
            lines.append(f"created the {house} pickable")
        picks[house] = pick

    picklist = Picklist.objects.filter(pack=pack, name__iexact=PICKLIST).first()
    if picklist is None:
        picklist = create_picklist(PICKLIST, slot_type, **in_pack)
        lines.append(f"created the {PICKLIST} picklist")
    for house in HOUSES:
        if not picklist.members.filter(pickable=picks[house]).exists():
            add_picklist_member(picklist, picks[house], **in_pack)
            lines.append(f"listed {house} on {PICKLIST}")

    slot = Slot.objects.filter(pack=pack, name__iexact=SLOT, qualifier="").first()
    if slot is None:
        slot = create_slot(
            SLOT,
            slot_type,
            picklist,
            min_picks=1,
            max_picks=1,
            assigned_to="gang",
            hidden=True,
            **in_pack,
        )
        lines.append(f"created the hidden {SLOT} slot")

    for house in HOUSES:
        gang_type = GangType.objects.filter(
            pack=pack, name__iexact=house, qualifier="", archived=False
        ).first()
        if gang_type is None:
            outcome.skipped.append(f"skipped {house}: no gang type of that name")
            continue
        # Archived members count: an author who took the slot out of a
        # type's built-ins on purpose is not overruled by a rerun.
        member = None
        if gang_type.built_ins_id is not None:
            member = DefaultAssignment.objects.filter(
                default_set_id=gang_type.built_ins_id, slot=slot
            ).first()
        if member is None:
            add_built_in(gang_type, slot, default_pickable=picks[house], **in_pack)
            lines.append(f"built the {SLOT} slot into {house}, picked {house}")
        elif member.archived:
            outcome.skipped.append(
                f"skipped {house}: its built-in {SLOT} slot member is archived, "
                "so it was left as it is"
            )
        elif member.default_pickable_id != picks[house].pk:
            outcome.skipped.append(
                f"skipped {house}: its built-in {SLOT} slot starts on "
                f"{member.default_pickable}, not {house}, so it was left as it is"
            )

    for house in HOUSES:
        clan_pick = Pickable.objects.filter(
            pack=pack,
            slot_type__name__icontains=CLAN_HOUSE,
            name__iexact=clan_house_pickable_name(house),
            qualifier="",
            archived=False,
        ).first()
        if clan_pick is None:
            outcome.skipped.append(
                f"skipped {clan_house_pickable_name(house)}: no Outcast Clan House "
                "pickable of that name"
            )
            continue
        given = clan_pick.modifiers.filter(
            adds_assignable__slot=slot, adds_assignable__with_pick=picks[house]
        ).exists()
        if given:
            continue
        modifier(
            f"{clan_pick.name}: gives the {SLOT} slot, picked {house}",
            targets_gang_alone(),
            ef_adds(slot, with_pick=picks[house]),
            attach_to=clan_pick,
            **in_pack,
        )
        lines.append(f"{clan_pick.name} now gives the {SLOT} slot, picked {house}")

    return outcome, picks
