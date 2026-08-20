"""The Archetype conversion — the Outcast system, and the last of them.

Today: the Outcast Leader profiles each carry their own offer of the
archetype kind, narrowed to the Outcast menu, whose answer lands **on
the gang**; the Champion profile carries the same offer landing on the
**bearer**. Each archetype on that menu carries its whole printed table
as ordinary modifiers — the rank placements, a granted subtype, a
powers family — including the bearer-only rows that say what a Champion
gets from picking it personally.

After: an "Archetype" slot type; the menu's archetypes as pickables
carrying those same modifiers, moved not copied; two slots — the gang's,
which every Leader profile grants, and the Champion's own — and every
stored choice re-said as a pick on its same anchor.

Four behaviours ride the modifiers rather than this conversion, and so
survive it by construction:

* the gang's archetype reaches every fighter except Champions, the
  tables naming the ranks it applies to;
* a Champion's own pick reaches that Champion alone, through the
  bearer-only rows, inert in the gang's radiated copy;
* the gang's archetype dies with the Leader, the pick hanging from the
  Leader's own line by a ``caused_by`` this conversion never moves;
* a Champion may pick what the gang already holds, silently — which is
  why the slot type allows repeats, where the Skill Tree one refuses
  them. An offer never remarks on a repeat, and this must not start.

**Nothing is deleted.** The emptied archetype rows, the menu
collection, and any detached fossil offer stay where they are.

The pickables take a qualifier. Two of these names already belong to
pickables of another slot type, and a name is unique per pack and
qualifier — so all of them take one, uniformly, and the cards go on
saying what they say. A qualifier is author-facing only and never
reaches a player.

Production converts from the maintenance console, once, after the code
deploys — see :mod:`n26.maintenance`. Elsewhere the command does it
(``manage n26_convert archetype``).
"""

from n26.library.conversion.base import (
    CreatePickable,
    CreatePicklist,
    CreateSlot,
    CreateSlotType,
    Plan,
    RewritePick,
    SwapCarrier,
    carriers_of,
    duplicate_names,
    one_answer_per_question,
    spread,
)

SLOT_TYPE = "Archetype"
PLURAL = "Archetypes"
PICKLIST = "Archetypes"
GANG_SLOT = "Archetype"
OWN_SLOT = "Archetype (Champion)"
OFFER_LABEL = "Archetype"
#: Told apart from the pickables of other slot types wearing these
#: names. Author-facing only.
QUALIFIER = "Archetype"

#: How many gangs the apply proves unchanged before committing — the
#: same reasoning as every conversion: a spread wide enough to hold
#: every shape the system comes in, proven with the lock held for
#: seconds, where proving everyone would hold rows players are using
#: for minutes.
PROVEN = 25


def plan_archetype():
    from django.db.models.functions import Lower

    from n26.core.models import Assignment
    from n26.library.models import (
        Modifier,
        OffersChoice,
        Pickable,
        Picklist,
        Slot,
        SlotType,
    )
    from n26.library.models.pack import default_pack_id

    problems = []

    # Every carried archetype offer wearing this system's label. A
    # detached one is a fossil: carried by nothing, it does nothing on
    # any page, and it is left where it lies.
    carried = [
        (m, carriers_of(m))
        for m in Modifier.objects.filter(
            offers_choice__isnull=False,
            offers_choice__of_kind__model="archetype",
        ).select_related("offers_choice", "offers_choice__from_section")
        if m.offers_choice.label == OFFER_LABEL
    ]
    live_offers = [(m, held) for m, held in carried if held]
    if not live_offers:
        return Plan(system="archetype", nothing_here=True)

    # Scoped to the default pack, where this builds: a custom pack's own
    # rows of these names are somebody's content, not a collision.
    pack = default_pack_id()
    # Names are unique per pack under ``Lower``, so these look the same
    # way the constraint does: an exact-match check calls a differently
    # cased row free, and the collision then arrives as a database error
    # where a sentence was promised.
    if SlotType.objects.filter(name__iexact=SLOT_TYPE, pack_id=pack).exists():
        problems.append(f"a slot type named “{SLOT_TYPE}” already stands")

    # Each offer must name a profile, and all of them the same menu:
    # two menus would be two systems, and this plan converts one.
    to_gang, to_bearer, sections = [], [], set()
    for offer, held in live_offers:
        strangers = sorted({kind for kind, _ in held if kind != "Profile"})
        if strangers:
            problems.append(
                f"“{offer.name}” is carried by things that are not "
                "profiles: " + ", ".join(strangers)
            )
        if len(held) != 1:
            # Every offer here is one profile's own. A shared one would
            # need the shared swap, and nothing in this system uses it.
            problems.append(
                f"“{offer.name}” is carried by {len(held)} things — "
                "expected one profile"
            )
        sections.add(offer.offers_choice.from_section_id)
        lands = offer.offers_choice.will_be_assigned_to
        if lands == OffersChoice.WillBeAssignedTo.GANG:
            to_gang.append((offer, held))
        else:
            to_bearer.append((offer, held))

    if len(sections) > 1:
        problems.append(
            f"the offers name {len(sections)} different menus — expected one"
        )
    section = live_offers[0][0].offers_choice.from_section
    if section is None:
        problems.append("the offer names no menu — expected the archetype list")
        old_rows = []
    else:
        # Live entries of live archetypes only: an archived row on the
        # menu is content somebody retired, and a conversion must not
        # resurrect it as a pickable.
        old_rows = sorted(
            (
                entry.archetype
                for entry in section.collection.entries.filter(
                    archetype__isnull=False,
                    archetype__archived=False,
                    archived=False,
                ).select_related("archetype")
            ),
            key=lambda row: row.name,
        )
        if not old_rows:
            problems.append("the menu offers no archetypes to convert")

    twice = duplicate_names(old_rows)
    if twice:
        problems.append("more than one live archetype is called: " + ", ".join(twice))

    # The names the steps would create must be free in the default pack,
    # under the qualifier they will wear — a collision would turn a
    # valid-looking plan into a mid-apply integrity error.
    wanted = {row.name.lower() for row in old_rows}
    taken = [
        name
        for name in Pickable.objects.filter(pack_id=pack)
        .annotate(folded=Lower("name"), folded_qualifier=Lower("qualifier"))
        .filter(folded__in=wanted, folded_qualifier=QUALIFIER.lower())
        .values_list("name", flat=True)
    ]
    if taken:
        problems.append(
            "pickables already wear these names and qualifier: "
            + ", ".join(sorted(taken))
        )
    if Picklist.objects.filter(pack_id=pack, name__iexact=PICKLIST).exists():
        problems.append(f"a picklist named “{PICKLIST}” already stands")
    for name in (GANG_SLOT, OWN_SLOT):
        if Slot.objects.filter(pack_id=pack, name__iexact=name).exists():
            problems.append(f"a slot named “{name}” already stands")

    # Only live answers move. An archived pick is history nothing draws,
    # and with no old row being deleted there is nothing to make it
    # follow.
    becoming = {row.pk: row.name for row in old_rows}
    picks = list(
        Assignment.objects.filter(archetype__in=list(becoming), archived=False)
        .exclude(removes=True)
        .select_related("archetype", "gang_root", "caused_by")
        .order_by("created")
    )
    answers, spares = one_answer_per_question(picks)

    # Which slot each pick settles, by the profile its anchor names —
    # the same profile that carries the offer it answered.
    gang_profiles = {row.pk for _, held in to_gang for _, row in held}
    own_profiles = {row.pk for _, held in to_bearer for _, row in held}
    # One profile carrying both a gang-landing offer and a bearer-landing
    # one asks two questions this plan cannot tell apart by anchor, and
    # its picks would settle on whichever slot the check reached first.
    both = gang_profiles & own_profiles
    if both:
        problems.append(
            f"{len(both)} profile(s) carry both a gang-landing offer and a "
            "bearer-landing one, so their picks cannot be told apart"
        )
    pick_slots = {}
    for pick in answers:
        if pick.caused_by_id is None:
            problems.append(f"pick {pick.pk} has no caused_by to settle against")
        elif pick.caused_by.profile_id in gang_profiles:
            pick_slots[pick.pk] = GANG_SLOT
        elif pick.caused_by.profile_id in own_profiles:
            pick_slots[pick.pk] = OWN_SLOT
        else:
            problems.append(
                f"pick {pick.pk} is anchored on “{pick.caused_by}”, which "
                "carries none of these offers"
            )

    # A live pick of an archetype the menu does not offer, anchored on a
    # carrying profile, would keep its line and lose its question when
    # the offer is swapped. Refuse rather than strand it.
    all_profiles = gang_profiles | own_profiles
    strays = (
        Assignment.objects.filter(
            archetype__isnull=False,
            archived=False,
            caused_by__profile__in=all_profiles,
        )
        .exclude(removes=True)
        .exclude(archetype__in=list(becoming))
        .select_related("archetype")
    )
    for stray in strays:
        problems.append(
            f"pick {stray.pk} names “{stray.archetype.name}”, which the menu "
            "does not offer — it would lose its question unanswered"
        )

    if problems:
        return Plan(system="archetype", problems=tuple(problems))

    steps = [
        # Repeats allowed: a Champion may pick what the gang holds, and
        # ten do. An offer never remarks on a repeat, and converting
        # must not start.
        CreateSlotType(name=SLOT_TYPE, plural_name=PLURAL, allows_repeats=True),
        *[
            CreatePickable(
                name=row.name,
                slot_type=SLOT_TYPE,
                moved_modifier_ids=tuple(m.pk for m in row.modifiers.all()),
                moved_from=("library.Archetype", row.pk),
                qualifier=QUALIFIER,
            )
            for row in old_rows
        ],
        CreatePicklist(
            name=PICKLIST,
            slot_type=SLOT_TYPE,
            members=tuple(row.name for row in old_rows),
        ),
        # The gang's question: asked on the Leader's card, answered on
        # the gang, and dying with the Leader through the anchor.
        CreateSlot(
            name=GANG_SLOT,
            slot_type=SLOT_TYPE,
            picklist=PICKLIST,
            assigned_to="gang",
            min_picks=0,
        ),
        # The Champion's own, which the cards call the same thing.
        CreateSlot(
            name=OWN_SLOT,
            slot_type=SLOT_TYPE,
            picklist=PICKLIST,
            label=OFFER_LABEL,
            assigned_to="bearer",
            min_picks=0,
        ),
    ]
    for offer, held in sorted(live_offers, key=lambda pair: pair[0].name):
        profile = held[0][1]
        slot = GANG_SLOT if profile.pk in gang_profiles else OWN_SLOT
        steps.append(
            SwapCarrier(
                carrier=("library.Profile", profile.pk),
                carrier_name=f"the “{profile.name}” profile",
                drop_modifier_id=offer.pk,
                drop_modifier_name=offer.name,
                grant_name=(
                    f"{profile.name}: "
                    + (
                        "the gang is asked its Archetype"
                        if slot == GANG_SLOT
                        else "the model is asked its Archetype"
                    )
                ),
                slot=slot,
                reach="model",
            )
        )
    steps += [
        RewritePick(
            assignment_id=pick.pk,
            old_column="archetype",
            pickable=becoming[pick.archetype_id],
            slot=pick_slots[pick.pk],
            gang=str(pick.gang_root),
        )
        for pick in answers
    ]

    # Every gang the change reaches: one holding a fighter of any
    # carrying profile, answered or not.
    holders = set(
        Assignment.objects.filter(archived=False, profile__in=all_profiles)
        .exclude(removes=True)
        .values_list("gang_root_id", flat=True)
        .distinct()
    )
    answered = {pick.gang_root_id for pick in answers}
    holders |= answered

    # The shapes worth proving: a gang asked twice over (two Leaders), a
    # Champion holding what the gang holds, a gang that never answered,
    # and ordinary ones.
    asked_twice, matching = [], []
    gang_choice = {}
    for pick in answers:
        if pick_slots[pick.pk] == GANG_SLOT:
            if pick.gang_root_id in gang_choice:
                asked_twice.append(pick.gang_root_id)
            gang_choice[pick.gang_root_id] = pick.archetype_id
    for pick in answers:
        if (
            pick_slots[pick.pk] == OWN_SLOT
            and gang_choice.get(pick.gang_root_id) == pick.archetype_id
        ):
            matching.append(pick.gang_root_id)

    proven = spread(
        holders,
        [
            [pick.gang_root_id for pick in spares],
            sorted(asked_twice, key=str),
            sorted(matching, key=str),
            sorted(holders - answered, key=str),
            sorted(answered, key=str),
        ],
        PROVEN,
    )
    return Plan(
        system="archetype",
        steps=tuple(steps),
        gang_ids=tuple(proven),
        reaches=len(holders),
        left_alone=len(spares),
    )
