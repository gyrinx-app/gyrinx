"""The Outcast Affiliation conversion — Affiliation and Clan House.

Today: the Outcast gang type builds in a Hidden that offers a choice of
the affiliation kind, narrowed to the Affiliations menu; one of those
affiliations (Clan House) itself offers a second choice of the six
Houses. Both answers land on the gang.

After: an "Affiliation" slot type and a "Clan House" slot type; the
menu's affiliations and houses as pickables carrying those same
modifiers, moved not copied; the Hidden grants the Affiliation slot;
the Clan House pickable grants the house slot; every stored choice —
live and archived — is re-said as a pick on its same anchor.

Nothing is deleted. Emptied affiliation rows, the menus, and any
detached fossil offer stay where they are.

The system is found by structure, not by production names: a live
affiliation-labelled offer carried by one Hidden, whose menu's live
entries become the top pickables, and among those the one that itself
offers affiliation labelled "clan house" is the house chain.

Production converts from the maintenance console, once, after the code
deploys — see :mod:`n26.maintenance`.
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
    refuse_if_granted,
    solely_carried,
    spread,
)

SYSTEM = "outcast_affiliation"
AFFILIATION_TYPE = "Affiliation"
AFFILIATION_PLURAL = "Affiliations"
AFFILIATION_SLOT = "Affiliation"
HOUSE_TYPE = "Clan House"
HOUSE_PLURAL = "Clan Houses"
HOUSE_SLOT = "Clan House"
OFFER_LABEL = "affiliation"
HOUSE_OFFER_LABEL = "clan house"
PROVEN = 15


def _affiliations_on(section):
    """Live affiliations on a live section, in the menu's own order."""
    if section is None:
        return []
    return [
        entry.affiliation
        for entry in section.collection.entries.filter(
            affiliation__isnull=False,
            affiliation__archived=False,
            archived=False,
        )
        .select_related("affiliation")
        .order_by("position", "affiliation__name")
    ]


def _offers_of_kind(carrier, kind, label):
    """The carrier's choice offers of one kind wearing this label."""
    wanted = label.casefold()
    return [
        m
        for m in carrier.modifiers.all()
        if getattr(m, "offers_choice", None) is not None
        and m.offers_choice.of_kind.model == kind
        and m.offers_choice.label.casefold() == wanted
    ]


def _qualifier_for(name, slot_type_name, pack, taken_pairs, problems):
    """Empty unless this name is already spoken for; then the slot type.

    A name is unique per pack and qualifier. When the empty qualifier is
    taken, this conversion qualifies as the slot type — author-facing
    only. If that pair is taken too, refuse rather than crash.
    """
    from django.db.models.functions import Lower

    from n26.library.models import Pickable

    folded = name.lower()
    standing = {
        (n.lower(), q.lower())
        for n, q in Pickable.objects.filter(pack_id=pack)
        .annotate(folded=Lower("name"), folded_q=Lower("qualifier"))
        .values_list("folded", "folded_q")
    }
    standing |= taken_pairs
    if (folded, "") not in standing:
        taken_pairs.add((folded, ""))
        return ""
    qualified = slot_type_name.lower()
    if (folded, qualified) in standing:
        problems.append(
            f"a pickable named “{name}” already stands"
            + (f", told apart as “{slot_type_name}”" if slot_type_name else "")
        )
        return slot_type_name
    taken_pairs.add((folded, qualified))
    return slot_type_name


def plan_outcast_affiliation():
    from n26.core.models import Assignment, Gang
    from n26.library.models import Modifier, Picklist, Slot, SlotType
    from n26.library.models.pack import default_pack_id

    problems = []

    # Live affiliation-labelled offers carried by something. A detached
    # one is a fossil: carried by nothing, it does nothing on any page,
    # and it is left where it lies. Offers wearing another label
    # (Variant, Chaos God, Corruption) are other systems.
    carried = []
    for modifier in Modifier.objects.filter(
        offers_choice__isnull=False,
        offers_choice__of_kind__model="affiliation",
    ).select_related("offers_choice", "offers_choice__from_section"):
        if modifier.offers_choice.label.casefold() != OFFER_LABEL:
            continue
        held = carriers_of(modifier)
        if held:
            carried.append((modifier, held))
    involves_hidden = [
        (modifier, held)
        for modifier, held in carried
        if any(kind == "Hidden" for kind, _ in held)
    ]
    if not involves_hidden:
        return Plan(system=SYSTEM, nothing_here=True)
    hidden_offers = [
        (modifier, held)
        for modifier, held in involves_hidden
        if len(held) == 1 and held[0][0] == "Hidden"
    ]
    if len(involves_hidden) != 1 or len(hidden_offers) != 1:
        problems.append(
            f"{len(involves_hidden)} Affiliation-labelled offer(s) involve a "
            "Hidden — expected one, carried by that Hidden alone"
        )
        return Plan(system=SYSTEM, problems=tuple(problems))

    offer, held = hidden_offers[0]
    hidden = held[0][1]
    solely_carried(offer, hidden, problems)
    refuse_if_granted(hidden, f"the “{hidden.name}” hidden", problems)

    section = offer.offers_choice.from_section
    if section is None:
        problems.append("the offer names no menu — expected the Affiliations list")
        top_rows = []
    else:
        top_rows = _affiliations_on(section)
        if not top_rows:
            problems.append("the menu offers no affiliations to convert")

    twice = duplicate_names(top_rows)
    if twice:
        problems.append("more than one live affiliation is called: " + ", ".join(twice))

    house_row = house_offer = house_section = None
    house_rows = []
    chained = []
    for row in top_rows:
        house_offers = _offers_of_kind(row, "affiliation", HOUSE_OFFER_LABEL)
        if house_offers:
            chained.append((row, house_offers))
    if len(chained) > 1:
        problems.append(
            f"{len(chained)} affiliations offer a Clan House choice — expected one"
        )
    elif not chained:
        problems.append("no affiliation on the menu offers a Clan House choice")
    else:
        house_row, house_offers = chained[0]
        if len(house_offers) != 1:
            problems.append(
                f"“{house_row.name}” carries {len(house_offers)} Clan House "
                "offers — expected one"
            )
        else:
            house_offer = house_offers[0]
            solely_carried(house_offer, house_row, problems)
            refuse_if_granted(
                house_row, f"the “{house_row.name}” affiliation", problems
            )
            house_section = house_offer.offers_choice.from_section
            if house_section is None:
                problems.append(
                    "the Clan House offer names no menu — expected the house list"
                )
            else:
                house_rows = _affiliations_on(house_section)
                if not house_rows:
                    problems.append("the Clan House menu offers no houses to convert")
                twice_houses = duplicate_names(house_rows)
                if twice_houses:
                    problems.append(
                        "more than one live house is called: " + ", ".join(twice_houses)
                    )

    both = duplicate_names([*top_rows, *house_rows])
    if both and not (duplicate_names(top_rows) or duplicate_names(house_rows)):
        problems.append(
            "a top affiliation and a house share a name: " + ", ".join(both)
        )

    pack = default_pack_id()
    if SlotType.objects.filter(name__iexact=AFFILIATION_TYPE, pack_id=pack).exists():
        problems.append(f"a slot type named “{AFFILIATION_TYPE}” already stands")
    if SlotType.objects.filter(name__iexact=HOUSE_TYPE, pack_id=pack).exists():
        problems.append(f"a slot type named “{HOUSE_TYPE}” already stands")

    top_picklist = (
        section.collection.name if section is not None else AFFILIATION_PLURAL
    )
    house_picklist = (
        house_section.collection.name if house_section is not None else HOUSE_PLURAL
    )
    if Picklist.objects.filter(pack_id=pack, name__iexact=top_picklist).exists():
        problems.append(f"a picklist named “{top_picklist}” already stands")
    if Picklist.objects.filter(pack_id=pack, name__iexact=house_picklist).exists():
        problems.append(f"a picklist named “{house_picklist}” already stands")
    for name in (AFFILIATION_SLOT, HOUSE_SLOT):
        if Slot.objects.filter(pack_id=pack, name__iexact=name).exists():
            problems.append(f"a slot named “{name}” already stands")

    taken_pairs = set()
    top_qualifiers = {
        row.pk: _qualifier_for(row.name, AFFILIATION_TYPE, pack, taken_pairs, problems)
        for row in top_rows
    }
    house_qualifiers = {
        row.pk: _qualifier_for(row.name, HOUSE_TYPE, pack, taken_pairs, problems)
        for row in house_rows
    }

    top_ids = {row.pk: row.name for row in top_rows}
    house_ids = {row.pk: row.name for row in house_rows}
    becoming = {**top_ids, **house_ids}

    live_picks = list(
        Assignment.objects.filter(affiliation__in=list(becoming), archived=False)
        .exclude(removes=True)
        .select_related("affiliation", "gang_root", "caused_by")
        .order_by("created")
    )
    answers, spares = one_answer_per_question(live_picks)
    archived_picks = list(
        Assignment.objects.filter(affiliation__in=list(becoming), archived=True)
        .exclude(removes=True)
        .select_related("affiliation", "gang_root", "caused_by")
        .order_by("created")
    )

    def slot_for(affiliation_id):
        return AFFILIATION_SLOT if affiliation_id in top_ids else HOUSE_SLOT

    for pick in [*answers, *archived_picks]:
        if pick.caused_by_id is None:
            problems.append(f"pick {pick.pk} has no caused_by to settle against")

    # A live pick of an affiliation the menus do not offer, hanging from
    # the Hidden or from a top-menu pick, would keep its line and lose
    # its question when the offer is swapped. Refuse rather than strand it.
    hidden_anchors = set(
        Assignment.objects.filter(hidden=hidden, archived=False)
        .exclude(removes=True)
        .values_list("pk", flat=True)
    )
    top_anchors = set(
        Assignment.objects.filter(affiliation__in=list(top_ids))
        .exclude(removes=True)
        .values_list("pk", flat=True)
    )
    strays = (
        Assignment.objects.filter(
            affiliation__isnull=False,
            archived=False,
            caused_by_id__in=hidden_anchors | top_anchors,
        )
        .exclude(removes=True)
        .exclude(affiliation__in=list(becoming))
        .select_related("affiliation")
    )
    for stray in strays:
        problems.append(
            f"pick {stray.pk} names “{stray.affiliation.name}”, which the menu "
            "does not offer — it would lose its question unanswered"
        )

    if problems:
        return Plan(system=SYSTEM, problems=tuple(problems))

    def pickable_steps(rows, slot_type, qualifiers):
        return [
            CreatePickable(
                name=row.name,
                slot_type=slot_type,
                moved_modifier_ids=tuple(m.pk for m in row.modifiers.all()),
                moved_from=("library.Affiliation", row.pk),
                qualifier=qualifiers[row.pk],
            )
            for row in rows
        ]

    # What the card calls each question today, taken from the offer that
    # asks it rather than guessed. A slot's ``choice_label`` lands where
    # an offer's ``kind_label`` did, so carrying the offer's own wording
    # across is the only way it survives whatever the authors typed: a
    # label is stored as written apart from its first letter, and to the
    # proof "Clan House" and "Clan house" are different words.
    top_label = offer.offers_choice.kind_label
    house_label = house_offer.offers_choice.kind_label

    steps = [
        CreateSlotType(
            name=AFFILIATION_TYPE,
            plural_name=AFFILIATION_PLURAL,
            allows_repeats=False,
        ),
        *pickable_steps(top_rows, AFFILIATION_TYPE, top_qualifiers),
        CreatePicklist(
            name=top_picklist,
            slot_type=AFFILIATION_TYPE,
            members=tuple(row.name for row in top_rows),
        ),
        CreateSlot(
            name=AFFILIATION_SLOT,
            slot_type=AFFILIATION_TYPE,
            picklist=top_picklist,
            label=top_label,
            assigned_to="gang",
            min_picks=0,
            max_picks=1,
        ),
        CreateSlotType(name=HOUSE_TYPE, plural_name=HOUSE_PLURAL, allows_repeats=False),
        *pickable_steps(house_rows, HOUSE_TYPE, house_qualifiers),
        CreatePicklist(
            name=house_picklist,
            slot_type=HOUSE_TYPE,
            members=tuple(row.name for row in house_rows),
        ),
        CreateSlot(
            name=HOUSE_SLOT,
            slot_type=HOUSE_TYPE,
            picklist=house_picklist,
            label=house_label,
            assigned_to="gang",
            min_picks=0,
            max_picks=1,
        ),
        SwapCarrier(
            carrier=("library.Hidden", hidden.pk),
            carrier_name=f"the “{hidden.name}” hidden",
            drop_modifier_id=offer.pk,
            drop_modifier_name=offer.name,
            grant_name=f"{hidden.name}: the gang is asked its Affiliation",
            slot=AFFILIATION_SLOT,
            reach="gang",
        ),
        SwapCarrier(
            carrier=("library.Affiliation", house_row.pk),
            carrier_name=f"the “{house_row.name}” pickable",
            drop_modifier_id=house_offer.pk,
            drop_modifier_name=house_offer.name,
            grant_name=f"{house_row.name}: the gang is asked its Clan House",
            slot=HOUSE_SLOT,
            reach="gang",
            made_pickable=house_row.name,
        ),
    ]
    steps += [
        RewritePick(
            assignment_id=pick.pk,
            old_column="affiliation",
            pickable=becoming[pick.affiliation_id],
            slot=slot_for(pick.affiliation_id),
            gang=str(pick.gang_root),
        )
        for pick in [*answers, *archived_picks]
    ]

    holders = set(
        Assignment.objects.filter(hidden=hidden, archived=False)
        .exclude(removes=True)
        .values_list("gang_root_id", flat=True)
        .distinct()
    )
    holders |= set(
        Assignment.objects.filter(affiliation__in=list(becoming))
        .exclude(removes=True)
        .values_list("gang_root_id", flat=True)
        .distinct()
    )
    holders.discard(None)

    live_holders = set(
        Gang.objects.filter(pk__in=holders, archived=False).values_list("pk", flat=True)
    )
    answered = {pick.gang_root_id for pick in answers}
    house_answered = {
        pick.gang_root_id for pick in answers if pick.affiliation_id in house_ids
    }
    clan_house_top = {
        pick.gang_root_id
        for pick in answers
        if house_row is not None and pick.affiliation_id == house_row.pk
    }
    archived_gangs = {pick.gang_root_id for pick in archived_picks}

    proven = spread(
        live_holders,
        [
            [pick.gang_root_id for pick in spares],
            sorted(archived_gangs, key=str),
            sorted(clan_house_top - house_answered, key=str),
            sorted(clan_house_top & house_answered, key=str),
            sorted(live_holders - answered, key=str),
            sorted(answered - clan_house_top, key=str),
        ],
        PROVEN,
    )
    return Plan(
        system=SYSTEM,
        steps=tuple(steps),
        gang_ids=tuple(proven),
        # Live gangs only: archived ones still have their picks rewritten,
        # but a stale archived gang must not lock or refuse the write.
        holder_ids=tuple(sorted(live_holders, key=str)),
        reaches=len(live_holders),
        left_alone=len(spares),
    )
