"""The Gang Legacy conversion — the Venator house-legacy system.

Today: the twelve Venator hunt profiles share one offer of the
archetype kind, labelled "Gang Legacy" and narrowed to the "House
Legacies" menu; seven house-named archetype rows each carry one
modifier — that house's equipment list, granted to the bearer. The
kind is borrowed: when this was authored the concept had no kind of
its own, and the label papered over the name — the card says
"Gang Legacy" while the storage says archetype. The gang's history
never says the borrowed word (these picks stand as their own acts), so
no written story changes; where a surface asks a pick its sort, the
answer becomes the card's word.

After: a "Gang Legacy" slot type; the seven houses as pickables, each
carrying its equipment-list modifier — moved, not copied; one picklist;
one per-bearer slot granted by the same twelve profiles through one
shared modifier, preserving the factoring the authors chose. Every
stored choice is re-said as a pick on its same anchor.

**Nothing is deleted.** The emptied archetype rows, the old menu
collection, and the one detached fossil offer stay where they are,
saying what they say now.

This plan expects a clean field: the earlier slot pilot — a hollow
slot type of the same name — must be retired first (the console offers
that as its own operation), because slot-type and pickable names are
unique per pack and the pilot's rows hold them.

Production converts from the maintenance console, once, after the code
deploys — see :mod:`n26.maintenance`. Elsewhere the command does it
(``manage n26_convert gang_legacy``).
"""

from n26.library.conversion.base import (
    CreatePickable,
    CreatePicklist,
    CreateSlot,
    CreateSlotType,
    Plan,
    RewritePick,
    SwapSharedCarrier,
    carriers_of,
    duplicate_names,
    one_answer_per_question,
    spread,
)

SLOT_TYPE = "Gang Legacy"
PLURAL = "Gang Legacies"
PICKLIST = "House Legacies"
SLOT = "Gang Legacy"
OFFER_LABEL = "Gang Legacy"

#: How many gangs the apply proves unchanged before committing — the
#: same reasoning as every conversion: a spread wide enough to hold
#: every shape the system comes in, proven with the lock held for
#: seconds, where proving everyone would hold rows players are using
#: for minutes.
PROVEN = 25


def plan_gang_legacy():
    from n26.core.models import Assignment
    from n26.library.models import Modifier, SlotType

    problems = []

    # Every archetype-kind offer wearing this system's label, split into
    # the one the profiles carry and any detached fossils. The fossil is
    # left alone — carried by nothing, it does nothing on any page — but
    # it must not be mistaken for the offer being converted.
    wearing = [
        m
        for m in Modifier.objects.filter(
            offers_choice__isnull=False,
            offers_choice__of_kind__model="archetype",
        ).select_related("offers_choice", "offers_choice__from_section")
        if m.offers_choice.label == OFFER_LABEL
    ]
    carried = [(m, carriers_of(m)) for m in wearing]
    live_offers = [(m, held) for m, held in carried if held]

    if not live_offers:
        return Plan(system="gang_legacy", nothing_here=True)
    if len(live_offers) > 1:
        return Plan(
            system="gang_legacy",
            problems=(
                f"{len(live_offers)} carried offers wear the label "
                f"“{OFFER_LABEL}” — expected one",
            ),
        )
    offer, held_by = live_offers[0]

    # The pilot must be retired before this can build: the names are
    # unique per pack, and a half-built slot type standing in this one's
    # place would make every step below a collision.
    if SlotType.objects.filter(name=SLOT_TYPE).exists():
        problems.append(
            f"a slot type named “{SLOT_TYPE}” already stands — retire the "
            "pilot first (the console offers it)"
        )

    strangers = [kind for kind, _ in held_by if kind != "Profile"]
    if strangers:
        problems.append(
            "the offer is carried by things that are not profiles: "
            + ", ".join(sorted(set(strangers)))
        )
    profiles = sorted(
        (row for kind, row in held_by if kind == "Profile"),
        key=lambda row: row.name,
    )

    section = offer.offers_choice.from_section
    if section is None:
        problems.append("the offer names no menu — expected the house list")
        old_rows = []
    else:
        old_rows = sorted(
            (
                entry.archetype
                for entry in section.collection.entries.filter(
                    archetype__isnull=False
                ).select_related("archetype", "archetype__category")
            ),
            key=lambda row: row.name,
        )
        if not old_rows:
            problems.append("the house menu offers no archetypes to convert")
    twice = duplicate_names(old_rows)
    if twice:
        problems.append("more than one live house is called: " + ", ".join(twice))

    # No granted-carrier check here: a profile is never granted by a
    # modifier — a fighter arrives by hire (or as a pet's model), and
    # either way its line is an assignment the counting below sees.

    # Only live answers of the houses this menu offers move. Picks of
    # the other system sharing the column — the Outcast archetypes —
    # are not this conversion's to touch, and their anchors are how the
    # two are told apart.
    becoming = {row.pk: row.name for row in old_rows}
    profile_pks = {p.pk for p in profiles}
    picks = list(
        Assignment.objects.filter(archetype__in=list(becoming), archived=False)
        .exclude(removes=True)
        .select_related("archetype", "gang_root", "caused_by")
        .order_by("created")
    )
    answers, spares = one_answer_per_question(picks)
    for pick in answers:
        if pick.caused_by_id is None:
            problems.append(f"pick {pick.pk} has no caused_by to settle against")
        elif pick.caused_by.profile_id not in profile_pks:
            problems.append(
                f"pick {pick.pk} is anchored on “{pick.caused_by}”, which is "
                "not one of the profiles carrying the offer"
            )

    if problems:
        return Plan(system="gang_legacy", problems=tuple(problems))

    steps = [
        CreateSlotType(name=SLOT_TYPE, plural_name=PLURAL, allows_repeats=False),
        *[
            CreatePickable(
                name=row.name,
                slot_type=SLOT_TYPE,
                moved_modifier_ids=tuple(m.pk for m in row.modifiers.all()),
                moved_from=("library.Archetype", row.pk),
            )
            for row in old_rows
        ],
        CreatePicklist(
            name=PICKLIST,
            slot_type=SLOT_TYPE,
            members=tuple(row.name for row in old_rows),
        ),
        CreateSlot(
            name=SLOT,
            slot_type=SLOT_TYPE,
            picklist=PICKLIST,
            assigned_to="bearer",
            min_picks=0,
        ),
        SwapSharedCarrier(
            carriers=tuple(("library.Profile", p.pk) for p in profiles),
            carriers_said=f"the {len(profiles)} hunt profiles",
            drop_modifier_id=offer.pk,
            drop_modifier_name=offer.name,
            grant_name="Hunt profiles: the model is asked its Gang Legacy",
            slot=SLOT,
            reach="model",
        ),
        *[
            RewritePick(
                assignment_id=pick.pk,
                old_column="archetype",
                pickable=becoming[pick.archetype_id],
                slot=SLOT,
                gang=str(pick.gang_root),
            )
            for pick in answers
        ],
    ]

    # Every gang the change can reach: one holding a fighter of any of
    # the carrying profiles, whether or not it ever answered. A
    # detached fossil offer reaches nobody and is left alone.
    holders = set(
        Assignment.objects.filter(archived=False, profile__in=profile_pks)
        .exclude(removes=True)
        .values_list("gang_root_id", flat=True)
        .distinct()
    )
    answered = {pick.gang_root_id for pick in answers}
    holders |= answered

    by_gang = {}
    for pick in answers:
        by_gang.setdefault(pick.gang_root_id, []).append(pick)
    crowded = [gang_id for gang_id, held in by_gang.items() if len(held) >= 3]

    proven = spread(
        holders,
        [
            [pick.gang_root_id for pick in spares],
            sorted(crowded, key=str),
            sorted(holders - answered, key=str),
            sorted(answered, key=str),
        ],
        PROVEN,
    )
    return Plan(
        system="gang_legacy",
        steps=tuple(steps),
        gang_ids=tuple(proven),
        reaches=len(holders),
        left_alone=len(spares),
    )
