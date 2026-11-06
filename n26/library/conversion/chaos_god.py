"""Convert two Chaos God choice offers into slots sharing one slot type and picklist.

One offer belongs to a Hidden carrier and one to an Affiliation carrier.
Create separate qualified slots, replace their offers and rewrite live and
archived choices on their existing anchors. Preserve source content and
unrelated offers.

Identify offers by kind, case-insensitive label and exclusive carrier shape.
Run through n26.maintenance.
"""

from n26.library.conversion.affiliation import _affiliations_on, _qualifier_for
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

SYSTEM = "chaos_god"
SLOT_TYPE = "Chaos God"
SLOT_PLURAL = "Chaos Gods"
SLOT_NAME = "Chaos God"
OFFER_LABEL = "chaos god"
PROVEN = 15


def _door_qualifier(carrier):
    """Distinguish same-named slots using the carrier name, or its kind if names match."""
    if carrier.name.lower() == SLOT_NAME.lower():
        return type(carrier).__name__
    return carrier.name


def plan_chaos_god():
    from n26.core.models import Assignment, Gang
    from n26.library.models import Modifier, Picklist, Slot, SlotType
    from n26.library.models.pack import default_pack_id

    problems = []

    # Select live offers with this system's label and at least one carrier.
    # Leave detached offers and differently labelled systems unchanged.
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

    hidden_doors = []
    affiliation_doors = []
    for modifier, held in carried:
        if len(held) != 1:
            others = [f"{kind} “{row}”" for kind, row in held]
            problems.append(
                f"“{modifier.name}” is shared — also carried by " + ", ".join(others)
            )
            continue
        kind, row = held[0]
        if kind == "Hidden":
            hidden_doors.append((modifier, row))
        elif kind == "Affiliation":
            affiliation_doors.append((modifier, row))
        else:
            problems.append(
                f"“{modifier.name}” is carried by {kind} “{row}” — "
                "expected a Hidden or an Affiliation"
            )

    if len(hidden_doors) != 1 or len(affiliation_doors) != 1:
        problems.append(
            f"{len(hidden_doors)} Chaos God-labelled offer(s) on a Hidden "
            f"and {len(affiliation_doors)} on an Affiliation — expected "
            "one of each, each carried alone"
        )
        return Plan(system=SYSTEM, problems=tuple(problems))

    helot_offer, hidden = hidden_doors[0]
    corrupted_offer, corrupted = affiliation_doors[0]
    solely_carried(helot_offer, hidden, problems)
    solely_carried(corrupted_offer, corrupted, problems)
    refuse_if_granted(hidden, f"the “{hidden.name}” hidden", problems)
    refuse_if_granted(corrupted, f"the “{corrupted.name}” affiliation", problems)

    helot_section = helot_offer.offers_choice.from_section
    corrupted_section = corrupted_offer.offers_choice.from_section
    if helot_section is None:
        problems.append(
            f"the “{hidden.name}” hidden's offer names no menu — "
            "expected the Chaos Gods list"
        )
    if corrupted_section is None:
        problems.append(
            f"the “{corrupted.name}” affiliation's offer names no menu — "
            "expected the Chaos Gods list"
        )
    if (
        helot_section is not None
        and corrupted_section is not None
        and helot_section.pk != corrupted_section.pk
    ):
        problems.append("the two Chaos God offers name different menus")

    section = helot_section or corrupted_section
    god_rows = _affiliations_on(section) if section is not None else []
    if section is not None and not god_rows:
        problems.append("the menu offers no Chaos Gods to convert")
    twice = duplicate_names(god_rows)
    if twice:
        problems.append("more than one live Chaos God is called: " + ", ".join(twice))

    if hidden.name.lower() == corrupted.name.lower():
        problems.append(
            f"the Hidden and the Affiliation are both called “{hidden.name}” "
            "— the two slots could not be told apart"
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
    god_qualifiers = {
        row.pk: _qualifier_for(row.name, SLOT_TYPE, pack, taken_pairs, problems)
        for row in god_rows
    }
    becoming = {row.pk: row.name for row in god_rows}

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

    hidden_anchors = set(
        Assignment.objects.filter(hidden=hidden)
        .exclude(removes=True)
        .values_list("pk", flat=True)
    )
    corrupted_anchors = set(
        Assignment.objects.filter(affiliation=corrupted)
        .exclude(removes=True)
        .values_list("pk", flat=True)
    )
    door_anchors = hidden_anchors | corrupted_anchors

    for pick in [*answers, *archived_picks]:
        if pick.caused_by_id is None:
            problems.append(f"pick {pick.pk} has no caused_by to settle against")
        elif pick.caused_by_id not in door_anchors:
            problems.append(f"pick {pick.pk} does not hang from either Chaos God door")

    # Reject active choices absent from the source menu; replacing their offer
    # would otherwise leave an assignment without its original choice.
    strays = (
        Assignment.objects.filter(
            affiliation__isnull=False,
            archived=False,
            caused_by_id__in=door_anchors,
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

    # Keys in made.slots: the carrier's name. Qualifiers: told apart
    # from the slot name when the carrier is also called Chaos God.
    helot_key = hidden.name
    corrupted_key = corrupted.name
    helot_qualifier = _door_qualifier(hidden)
    corrupted_qualifier = _door_qualifier(corrupted)
    helot_label = helot_offer.offers_choice.kind_label
    corrupted_label = corrupted_offer.offers_choice.kind_label

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
                qualifier=god_qualifiers[row.pk],
            )
            for row in god_rows
        ],
        CreatePicklist(
            name=picklist_name,
            slot_type=SLOT_TYPE,
            members=tuple(row.name for row in god_rows),
        ),
        CreateSlot(
            name=SLOT_NAME,
            slot_type=SLOT_TYPE,
            picklist=picklist_name,
            label=helot_label,
            assigned_to="gang",
            min_picks=0,
            max_picks=1,
            qualifier=helot_qualifier,
            key=helot_key,
        ),
        CreateSlot(
            name=SLOT_NAME,
            slot_type=SLOT_TYPE,
            picklist=picklist_name,
            label=corrupted_label,
            assigned_to="gang",
            min_picks=0,
            max_picks=1,
            qualifier=corrupted_qualifier,
            key=corrupted_key,
        ),
        SwapCarrier(
            carrier=("library.Hidden", hidden.pk),
            carrier_name=f"the “{hidden.name}” hidden",
            drop_modifier_id=helot_offer.pk,
            drop_modifier_name=helot_offer.name,
            grant_name=f"{hidden.name}: the gang is asked its {SLOT_TYPE}",
            slot=helot_key,
            reach="gang",
        ),
        SwapCarrier(
            carrier=("library.Affiliation", corrupted.pk),
            carrier_name=f"the “{corrupted.name}” affiliation",
            drop_modifier_id=corrupted_offer.pk,
            drop_modifier_name=corrupted_offer.name,
            grant_name=f"{corrupted.name}: the gang is asked its {SLOT_TYPE}",
            slot=corrupted_key,
            reach="gang",
        ),
    ]

    def slot_for(pick):
        return helot_key if pick.caused_by_id in hidden_anchors else corrupted_key

    steps += [
        RewritePick(
            assignment_id=pick.pk,
            old_column="affiliation",
            pickable=becoming[pick.affiliation_id],
            slot=slot_for(pick),
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
        Assignment.objects.filter(affiliation=corrupted, archived=False)
        .exclude(removes=True)
        .values_list("gang_root_id", flat=True)
        .distinct()
    )
    holders |= set(
        Assignment.objects.filter(affiliation__in=list(becoming), archived=False)
        .exclude(removes=True)
        .values_list("gang_root_id", flat=True)
        .distinct()
    )
    holders.discard(None)

    live_holders = set(
        Gang.objects.filter(pk__in=holders, archived=False).values_list("pk", flat=True)
    )
    answered = {pick.gang_root_id for pick in answers}
    helot_live = (
        set(
            Assignment.objects.filter(hidden=hidden, archived=False)
            .exclude(removes=True)
            .values_list("gang_root_id", flat=True)
            .distinct()
        )
        & live_holders
    )
    corrupted_live = (
        set(
            Assignment.objects.filter(affiliation=corrupted, archived=False)
            .exclude(removes=True)
            .values_list("gang_root_id", flat=True)
            .distinct()
        )
        & live_holders
    )
    archived_gangs = {pick.gang_root_id for pick in archived_picks}

    proven = spread(
        live_holders,
        [
            [pick.gang_root_id for pick in spares],
            sorted(archived_gangs, key=str),
            sorted(helot_live - answered, key=str),
            sorted(helot_live & answered, key=str),
            sorted(corrupted_live - answered, key=str),
            sorted(corrupted_live & answered, key=str),
        ],
        PROVEN,
    )
    return Plan(
        system=SYSTEM,
        steps=tuple(steps),
        gang_ids=tuple(proven),
        # Rewrite archived picks but exclude archived gangs from locking and reconciliation.
        holder_ids=tuple(sorted(live_holders, key=str)),
        reaches=len(live_holders),
        left_alone=len(spares),
    )
