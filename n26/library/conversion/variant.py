"""The Variant conversion — one shared offer, optional slot, no None.

Today: one affiliation-labelled offer, label casefold "variant", menu
Variants: Chaos Corrupted, Genestealer Cult Corrupted, Malstrain
Corrupted, and "None". The offer is shared across the house gang types
(and a vestigial Hidden that nothing holds). Chaos Corrupted already
grants the Chaos God slot.

After: a "Variant" slot type; the three corruptions as pickables
carrying those same modifiers, moved not copied; one picklist; one
slot, granted by exactly the offer's carriers as one shared grant;
every stored corruption pick — live and archived — is re-said as a
pick; every stored "None" pick is archived. No None pickable. The
question never nagged, so the slot does not either.

Nothing is deleted. Emptied affiliation rows, the menu, and the
vestigial Hidden stay where they are. The Hidden is a carrier of the
one swap, not a second door. Other affiliation-labelled offers
(Outcast, already slots; Chaos God, already slots; fossils) are other
systems and are left standing.

The system is found by structure, not by production names: a live
affiliation-labelled offer whose label casefolds to "variant", carried
by gang types. A second distinct Variant-labelled offer that is not
this shared one is a refusal.

Production converts from the maintenance console, once, after the code
deploys — see :mod:`n26.maintenance`.
"""

from n26.library.conversion.affiliation import (
    _affiliations_on,
    _offers_of_kind,
    _qualifier_for,
)
from n26.library.conversion.base import (
    ArchivePick,
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
    refuse_if_granted,
    spread,
)

SYSTEM = "variant"
SLOT_TYPE = "Variant"
SLOT_PLURAL = "Variants"
SLOT_NAME = "Variant"
OFFER_LABEL = "variant"
NONE_NAME = "none"
PROVEN = 15


def _said_carriers(held):
    """The carriers in preview words, gang types then hiddens."""
    types = sorted(
        (row for kind, row in held if kind == "GangType"),
        key=lambda row: row.name.lower(),
    )
    hiddens = sorted(
        (row for kind, row in held if kind == "Hidden"),
        key=lambda row: row.name.lower(),
    )
    bits = []
    if types:
        noun = "gang type" if len(types) == 1 else "gang types"
        bits.append(noun + " " + ", ".join(f"“{row.name}”" for row in types))
    if hiddens:
        noun = "hidden" if len(hiddens) == 1 else "hiddens"
        bits.append(noun + " " + ", ".join(f"“{row.name}”" for row in hiddens))
    return "the " + " and the ".join(bits)


def _is_none(row):
    return row.name.casefold() == NONE_NAME


def plan_variant():
    from n26.core.models import Assignment, Gang
    from n26.library.models import Modifier, Picklist, Slot, SlotType
    from n26.library.models.pack import default_pack_id

    problems = []

    # Live Variant-labelled offers carried by something. A detached one
    # is a fossil: carried by nothing, it does nothing on any page, and
    # it is left where it lies. Offers wearing another label
    # (Affiliation, Chaos God, Corruption) are other systems.
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
    if not carried:
        return Plan(system=SYSTEM, nothing_here=True)

    on_types = [
        (modifier, held)
        for modifier, held in carried
        if any(kind == "GangType" for kind, _ in held)
    ]
    if not on_types:
        return Plan(system=SYSTEM, nothing_here=True)

    distinct = []
    seen = set()
    for modifier, held in on_types:
        if modifier.pk in seen:
            continue
        seen.add(modifier.pk)
        distinct.append((modifier, held))
    if len(distinct) != 1:
        problems.append(
            f"{len(distinct)} distinct Variant-labelled offer(s) on gang "
            "types — expected one shared offer"
        )
        return Plan(system=SYSTEM, problems=tuple(problems))

    offer, held = distinct[0]
    others = [
        (modifier, other) for modifier, other in carried if modifier.pk != offer.pk
    ]
    if others:
        said = "; ".join(
            f"“{modifier.name}” carried by "
            + ", ".join(f"{kind} “{row}”" for kind, row in other)
            for modifier, other in others
        )
        problems.append("a second distinct Variant-labelled offer stands — " + said)

    unexpected = sorted(
        {kind for kind, _ in held if kind not in ("GangType", "Hidden")}
    )
    if unexpected:
        problems.append(
            f"“{offer.name}” is also carried by "
            + ", ".join(unexpected)
            + " — expected gang types, and optionally a Hidden"
        )

    for kind, row in held:
        if kind == "Hidden":
            refuse_if_granted(row, f"the “{row.name}” hidden", problems)

    section = offer.offers_choice.from_section
    if section is None:
        problems.append("the offer names no menu — expected the Variants list")
        menu_rows = []
    else:
        menu_rows = _affiliations_on(section)
        if not menu_rows:
            problems.append("the menu offers no Variants to convert")

    twice = duplicate_names(menu_rows)
    if twice:
        problems.append("more than one live Variant is called: " + ", ".join(twice))

    nones = [row for row in menu_rows if _is_none(row)]
    corruptions = [row for row in menu_rows if not _is_none(row)]
    if section is not None and not corruptions:
        problems.append("the menu offers no corruptions to convert")

    for row in corruptions:
        leftover = _offers_of_kind(row, "affiliation", "chaos god")
        if leftover:
            problems.append(
                f"“{row.name}” still offers a Chaos God choice — "
                "that door converts first"
            )

    pack = default_pack_id()
    if SlotType.objects.filter(name__iexact=SLOT_TYPE, pack_id=pack).exists():
        problems.append(f"a slot type named “{SLOT_TYPE}” already stands")

    picklist_name = section.collection.name if section is not None else SLOT_PLURAL
    if Picklist.objects.filter(pack_id=pack, name__iexact=picklist_name).exists():
        problems.append(f"a picklist named “{picklist_name}” already stands")
    if Slot.objects.filter(pack_id=pack, name__iexact=SLOT_NAME).exists():
        problems.append(f"a slot named “{SLOT_NAME}” already stands")

    taken_pairs = set()
    qualifiers = {
        row.pk: _qualifier_for(row.name, SLOT_TYPE, pack, taken_pairs, problems)
        for row in corruptions
    }
    becoming = {row.pk: row.name for row in corruptions}

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
    none_picks = list(
        Assignment.objects.filter(affiliation__in=[row.pk for row in nones])
        .exclude(removes=True)
        .select_related("affiliation", "gang_root")
        .order_by("created")
    )

    type_ids = [row.pk for kind, row in held if kind == "GangType"]
    hidden_ids = [row.pk for kind, row in held if kind == "Hidden"]
    type_anchors = set(
        Assignment.objects.filter(gang_type_id__in=type_ids)
        .exclude(removes=True)
        .values_list("pk", flat=True)
    )
    hidden_anchors = set(
        Assignment.objects.filter(hidden_id__in=hidden_ids)
        .exclude(removes=True)
        .values_list("pk", flat=True)
    )
    door_anchors = type_anchors | hidden_anchors
    menu_ids = [row.pk for row in menu_rows]

    for pick in [*answers, *archived_picks]:
        if pick.caused_by_id is None:
            problems.append(f"pick {pick.pk} has no caused_by to settle against")

    # A live pick of an affiliation the menu does not offer, hanging from
    # a carrier, would keep its line and lose its question when the
    # offer is swapped. Refuse rather than strand it.
    strays = (
        Assignment.objects.filter(
            affiliation__isnull=False,
            archived=False,
            caused_by_id__in=door_anchors,
        )
        .exclude(removes=True)
        .exclude(affiliation__in=menu_ids)
        .select_related("affiliation")
    )
    for stray in strays:
        problems.append(
            f"pick {stray.pk} names “{stray.affiliation.name}”, which the menu "
            "does not offer — it would lose its question unanswered"
        )

    if problems:
        return Plan(system=SYSTEM, problems=tuple(problems))

    slot_label = offer.offers_choice.kind_label
    sorted_held = sorted(
        held, key=lambda item: (item[0], item[1].name.lower(), str(item[1].pk))
    )
    carriers = tuple((f"library.{kind}", row.pk) for kind, row in sorted_held)

    steps = [
        CreateSlotType(
            name=SLOT_TYPE,
            plural_name=SLOT_PLURAL,
            allows_repeats=False,
        ),
        *[
            CreatePickable(
                name=row.name,
                slot_type=SLOT_TYPE,
                moved_modifier_ids=tuple(m.pk for m in row.modifiers.all()),
                moved_from=("library.Affiliation", row.pk),
                qualifier=qualifiers[row.pk],
            )
            for row in corruptions
        ],
        CreatePicklist(
            name=picklist_name,
            slot_type=SLOT_TYPE,
            members=tuple(row.name for row in corruptions),
        ),
        CreateSlot(
            name=SLOT_NAME,
            slot_type=SLOT_TYPE,
            picklist=picklist_name,
            label=slot_label,
            assigned_to="gang",
            min_picks=0,
            max_picks=1,
        ),
        SwapSharedCarrier(
            carriers=carriers,
            carriers_said=_said_carriers(held),
            drop_modifier_id=offer.pk,
            drop_modifier_name=offer.name,
            grant_name=f"Variants: the gang is asked its {SLOT_TYPE}",
            slot=SLOT_NAME,
            reach="gang_alone",
        ),
    ]
    steps += [
        RewritePick(
            assignment_id=pick.pk,
            old_column="affiliation",
            pickable=becoming[pick.affiliation_id],
            slot=SLOT_NAME,
            gang=str(pick.gang_root),
        )
        for pick in [*answers, *archived_picks]
    ]
    steps += [
        ArchivePick(
            assignment_id=pick.pk,
            gang=str(pick.gang_root),
            name=pick.affiliation.name,
        )
        for pick in none_picks
    ]

    holders = set(
        Assignment.objects.filter(gang_type_id__in=type_ids, archived=False)
        .exclude(removes=True)
        .values_list("gang_root_id", flat=True)
        .distinct()
    )
    holders |= set(
        Assignment.objects.filter(affiliation_id__in=menu_ids, archived=False)
        .exclude(removes=True)
        .values_list("gang_root_id", flat=True)
        .distinct()
    )
    holders.discard(None)

    live_holders = set(
        Gang.objects.filter(pk__in=holders, archived=False).values_list("pk", flat=True)
    )
    answered = {pick.gang_root_id for pick in answers}
    none_live = {
        pick.gang_root_id
        for pick in none_picks
        if not pick.archived and pick.gang_root_id in live_holders
    }
    unanswered = live_holders - answered - none_live
    archived_rechoice = {
        pick.gang_root_id
        for pick in archived_picks
        if pick.gang_root_id in live_holders
    }

    per_corruption = [
        sorted(
            {pick.gang_root_id for pick in answers if pick.affiliation_id == row.pk},
            key=str,
        )
        for row in corruptions
    ]
    chaining_pks = set()
    granted_slot_ids = []
    for row in corruptions:
        for modifier in row.modifiers.all():
            adds = getattr(modifier, "adds_assignable", None)
            if adds is not None and getattr(adds, "slot_id", None):
                chaining_pks.add(row.pk)
                granted_slot_ids.append(adds.slot_id)
    chained = []
    unchained = []
    if chaining_pks:
        chained_ids = {
            pick.gang_root_id for pick in answers if pick.affiliation_id in chaining_pks
        }
        god_answered = set()
        if granted_slot_ids:
            god_answered = set(
                Assignment.objects.filter(
                    chosen_for_slot_id__in=granted_slot_ids,
                    archived=False,
                )
                .exclude(removes=True)
                .values_list("gang_root_id", flat=True)
            )
        chained = sorted(chained_ids & god_answered, key=str)
        unchained = sorted(chained_ids - god_answered, key=str)

    proven = spread(
        live_holders,
        [
            [pick.gang_root_id for pick in spares],
            sorted(archived_rechoice, key=str),
            sorted(none_live, key=str),
            sorted(unanswered, key=str),
            chained,
            unchained,
            *per_corruption,
        ],
        PROVEN,
    )
    unanswered_as = tuple((slot_label, row.name) for row in nones)
    return Plan(
        system=SYSTEM,
        steps=tuple(steps),
        gang_ids=tuple(proven),
        # Live gangs only: archived ones still have their picks rewritten
        # and Nones archived, but a stale archived gang must not lock or
        # refuse the write.
        holder_ids=tuple(sorted(live_holders, key=str)),
        reaches=len(live_holders),
        left_alone=len(spares),
        unanswered_as=unanswered_as,
    )
