"""The Cawdor Paths conversion — the pilot system.

Today: a hidden "Path" (built into the Cawdor gang type) carries a
gang-scoped *offers a choice of affiliation* over the "Paths" menu
collection; two affiliations (Path of the Fanatic, Path of the Pious)
each carry the gang rules their path grants.

After: a "Path" slot type with the two paths as pickables on a "Paths"
picklist, one gang slot; the hidden grants the slot instead of carrying
the offer; every stored path pick becomes a pick of the pickable,
settling the slot it already hangs from.
"""

from n26.library.conversion.base import (
    CreatePickable,
    CreatePicklist,
    CreateSlot,
    CreateSlotType,
    Plan,
    Retire,
    RewritePick,
    SwapCarrier,
)

CARRIER_NAME = "Path"
OFFER_LABEL = "Path"
SLOT_TYPE = "Path"
PICKLIST = "Paths"


def plan_paths():
    from n26.core.models import Assignment
    from n26.library.models import Hidden, SlotType

    problems = []

    if SlotType.objects.filter(name=SLOT_TYPE, archived=False).exists():
        # Applied already — the slot type is this conversion's own mark.
        return Plan(system="paths", nothing_here=True)

    hiddens = list(Hidden.objects.filter(name=CARRIER_NAME, archived=False))
    if not hiddens:
        return Plan(system="paths", nothing_here=True)
    if len(hiddens) > 1:
        return Plan(
            system="paths",
            problems=(f"{len(hiddens)} hiddens named “{CARRIER_NAME}” — expected one",),
        )
    carrier = hiddens[0]

    offers = [
        m
        for m in carrier.modifiers.all()
        if getattr(m, "offers_choice", None) is not None
        and m.offers_choice.label == OFFER_LABEL
    ]
    if len(offers) != 1:
        return Plan(
            system="paths",
            problems=(
                f"the “{CARRIER_NAME}” hidden carries {len(offers)} offers "
                f"labelled “{OFFER_LABEL}” — expected one",
            ),
        )
    offer = offers[0]
    from n26.library.conversion.base import carriers_of

    other_carriers = [
        f"{kind} “{row}”"
        for kind, row in carriers_of(offer)
        if not (kind == "Hidden" and row.pk == carrier.pk)
    ]
    if other_carriers:
        return Plan(
            system="paths",
            problems=(
                "the Path offer is shared — also carried by "
                + ", ".join(other_carriers),
            ),
        )
    section = offer.offers_choice.from_section
    if section is None:
        return Plan(
            system="paths",
            problems=("the Path offer names no menu section",),
        )
    menu = section.collection

    entries = list(
        menu.entries.filter(affiliation__isnull=False)
        .select_related("affiliation")
        .order_by("position", "affiliation__name")
    )
    old_paths = [entry.affiliation for entry in entries]
    if len(old_paths) != 2:
        problems.append(
            f"the “{menu.name}” menu lists {len(old_paths)} affiliations — expected exactly the two paths"
        )

    # Archived picks too: a gang that switched its path keeps the row it
    # took back, still naming the affiliation — left behind, it would
    # PROTECT the retirement. The same rewrite keeps the history coherent.
    picks = list(
        Assignment.objects.filter(affiliation__in=old_paths)
        .select_related("affiliation", "gang_root")
        .order_by("created")
    )
    unanchored = [str(pick.pk) for pick in picks if pick.caused_by_id is None]
    if unanchored:
        problems.append(
            "picks with no caused_by to settle against: " + ", ".join(unanchored)
        )
    # A pick hanging from anything but the carrier answers a question
    # this slot does not ask: rewritten, it would name the slot while
    # nothing drew it as that slot's answer. Refuse it by name — the
    # plan knows, and saying so beats leaving it to the page proof.
    strays = [
        str(pick.pk)
        for pick in picks
        if pick.caused_by_id is not None and pick.caused_by.hidden_id != carrier.pk
    ]
    if strays:
        problems.append(
            "picks anchored on something other than the carrier: " + ", ".join(strays)
        )

    if problems:
        return Plan(system="paths", problems=tuple(problems))

    steps = [
        CreateSlotType(name=SLOT_TYPE, plural_name="Paths"),
        *[
            CreatePickable(
                name=old.name,
                slot_type=SLOT_TYPE,
                moved_modifier_ids=tuple(m.pk for m in old.modifiers.all()),
                moved_from=("library.Affiliation", old.pk),
            )
            for old in old_paths
        ],
        CreatePicklist(
            name=PICKLIST,
            slot_type=SLOT_TYPE,
            members=tuple(old.name for old in old_paths),
        ),
        CreateSlot(
            name=SLOT_TYPE,
            slot_type=SLOT_TYPE,
            picklist=PICKLIST,
            assigned_to="gang",
            # The offer never nagged an open choice, so neither may the
            # slot: every converted system arrives expecting no picks.
            # Tightening a minimum is a content decision for later,
            # never the conversion's.
            min_picks=0,
        ),
        SwapCarrier(
            carrier=("library.Hidden", carrier.pk),
            carrier_name=f"the “{carrier.name}” hidden",
            drop_modifier_id=offer.pk,
            drop_modifier_name=offer.name,
            grant_name="Path: the gang is asked its Path",
            slot=SLOT_TYPE,
            reach="gang_alone",
        ),
        *[
            RewritePick(
                assignment_id=pick.pk,
                old_column="affiliation",
                pickable=pick.affiliation.name,
                slot=SLOT_TYPE,
                gang=str(pick.gang_root),
            )
            for pick in picks
        ],
        # The menu and the old rows, last: nothing references them once
        # the picks are rewritten and the modifiers moved. Deleting the
        # collection takes its entries and sections with it.
        Retire(model="library.Collection", pk=menu.pk, name=menu.name),
        *[
            Retire(model="library.Affiliation", pk=old.pk, name=old.name)
            for old in old_paths
        ],
    ]

    gang_ids = sorted(
        {
            *(
                Assignment.objects.filter(archived=False, hidden=carrier)
                .values_list("gang_root_id", flat=True)
                .distinct()
            ),
            *(pick.gang_root_id for pick in picks),
        },
        key=str,
    )
    return Plan(system="paths", steps=tuple(steps), gang_ids=tuple(gang_ids))
