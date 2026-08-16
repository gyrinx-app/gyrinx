"""The Specialisation conversion — the volume system.

Today: the "Specialist" subtype carries a bearer offer of the whole
specialisation kind; eight specialisations each add one skill to the
bearer. Two hiddens are the fossil of an abandoned narrowing
experiment: "Specialisation Offer" [(general)] — held by nothing,
granted by a modifier nothing carries, and removed by a live no-op on
the Subjugator Patrol Officer profile — and "Specialisation offer"
[(Subjugator Patrol Officer)], whose narrowed menu is still held by
whoever an owner gave it to.

After: a "Specialisation" slot type; the eight as pickables on one
picklist; a bearer slot granted by the same subtype. The Subjugator
hidden keeps its purpose — its offer becomes a grant of a second slot
over its own narrow picklist, so a holder's page asks the same
question. The general hidden and both menu collections retire.

This system ships without a migration: proving several hundred gangs
inside the container-boot window would gamble with the startup probe's
ceiling, so production runs the rehearsal command itself, as a one-off
Cloud Run job, after the code deploys.
"""

from n26.library.conversion.base import (
    CreatePickable,
    CreatePicklist,
    CreateSlot,
    CreateSlotType,
    DropModifier,
    Plan,
    Retire,
    RetireModifier,
    RewritePick,
    SwapCarrier,
    carriers_of,
)

SUBTYPE = "Specialist"
SLOT_TYPE = "Specialisation"
PICKLIST = "Specialisations"
NARROW_HIDDEN = "Specialisation offer"
GENERAL_HIDDEN = "Specialisation Offer"


def _the_offer(carrier, problems, said):
    """The carrier's one specialisation offer, or a stated problem."""
    offers = [
        m
        for m in carrier.modifiers.all()
        if getattr(m, "offers_choice", None) is not None
        and m.offers_choice.of_kind.model == "specialisation"
    ]
    if len(offers) != 1:
        problems.append(
            f"{said} carries {len(offers)} specialisation offers — expected one"
        )
        return None
    return offers[0]


def plan_specialisation():
    from n26.core.models import Assignment
    from n26.library.models import Hidden, SlotType, Specialisation, Subtype

    problems = []

    if SlotType.objects.filter(name=SLOT_TYPE, archived=False).exists():
        return Plan(system="specialisation", nothing_here=True)

    subtypes = list(Subtype.objects.filter(name=SUBTYPE, archived=False))
    if not subtypes:
        return Plan(system="specialisation", nothing_here=True)
    if len(subtypes) > 1:
        return Plan(
            system="specialisation",
            problems=(f"{len(subtypes)} subtypes named “{SUBTYPE}” — expected one",),
        )
    subtype = subtypes[0]

    offer = _the_offer(subtype, problems, f"the “{SUBTYPE}” subtype")
    if offer is not None:
        if offer.offers_choice.from_section_id is not None:
            problems.append(
                "the Specialist offer names a section — expected the whole kind"
            )
        others = [
            f"{kind} “{row}”"
            for kind, row in carriers_of(offer)
            if not (kind == "Subtype" and row.pk == subtype.pk)
        ]
        if others:
            problems.append(
                "the Specialist offer is shared — also carried by " + ", ".join(others)
            )

    old_rows = list(Specialisation.objects.filter(archived=False).order_by("name"))
    if not old_rows:
        problems.append("no specialisations to convert")

    picks = list(
        Assignment.objects.filter(specialisation__isnull=False)
        .select_related("specialisation", "gang_root")
        .order_by("created")
    )
    unanchored = [str(pick.pk) for pick in picks if pick.caused_by_id is None]
    if unanchored:
        problems.append(
            "picks with no caused_by to settle against: " + ", ".join(unanchored)
        )

    # The Subjugator fossil: kept, converted — its holder's page must go
    # on asking the same narrowed question.
    narrow = Hidden.objects.filter(name=NARROW_HIDDEN, archived=False).first()
    narrow_offer = None
    narrow_menu = None
    narrow_names = []
    if narrow is not None:
        narrow_offer = _the_offer(narrow, problems, f"the “{NARROW_HIDDEN}” hidden")
        if narrow_offer is not None:
            section = narrow_offer.offers_choice.from_section
            if section is None:
                problems.append(f"the “{NARROW_HIDDEN}” offer names no menu")
            else:
                narrow_menu = section.collection
                narrow_names = [
                    entry.specialisation.name
                    for entry in narrow_menu.entries.filter(
                        specialisation__isnull=False
                    ).select_related("specialisation")
                ]
                strangers = set(narrow_names) - {row.name for row in old_rows}
                if strangers:
                    problems.append(
                        "the narrow menu lists specialisations the kind does "
                        "not: " + ", ".join(sorted(strangers))
                    )

    # The general fossil: retired — the plan must know nothing holds it,
    # nothing grants it, and every stray reference is itself dead.
    general = Hidden.objects.filter(name=GENERAL_HIDDEN, archived=False).first()
    general_offer = None
    general_menu = None
    stray_effects = []
    if general is not None:
        if Assignment.objects.filter(hidden=general).exists():
            problems.append(
                f"the “{GENERAL_HIDDEN}” hidden is held by someone — it cannot retire"
            )
        general_offer = _the_offer(general, problems, f"the “{GENERAL_HIDDEN}” hidden")
        if general_offer is not None and general_offer.offers_choice.from_section_id:
            general_menu = general_offer.offers_choice.from_section.collection
        # The abandoned narrowing experiment left wiring behind that
        # still names the hidden, and would protect it from retiring. A
        # bare effect row, or a whole modifier nothing carries, is dead
        # and retires with it. A carried modifier that only *removes*
        # the hidden is a read-time no-op — nothing grants the hidden
        # and nobody holds it, both proven above — so it drops from its
        # carrier without changing a page. A carried modifier that
        # grants the hidden is live wiring, and a problem.
        from n26.library.models import AddsAssignable, Modifier, RemovesAssignable

        for model, label, column in (
            (AddsAssignable, "library.AddsAssignable", "adds_assignable"),
            (RemovesAssignable, "library.RemovesAssignable", "removes_assignable"),
        ):
            for row in model.objects.filter(hidden=general):
                alive = Modifier.objects.filter(**{column: row}).first()
                if alive is None:
                    stray_effects.append(Retire(model=label, pk=row.pk, name=str(row)))
                    continue
                holders = carriers_of(alive)
                if not holders:
                    stray_effects.append(
                        RetireModifier(modifier_id=alive.pk, modifier_name=alive.name)
                    )
                elif column == "removes_assignable" and len(holders) == 1:
                    kind, holder = holders[0]
                    stray_effects.append(
                        DropModifier(
                            carrier=(f"library.{kind}", holder.pk),
                            carrier_name=f"the “{holder}” {kind.lower()}",
                            modifier_id=alive.pk,
                            modifier_name=alive.name,
                        )
                    )
                else:
                    problems.append(
                        f"“{alive.name}” still names the “{GENERAL_HIDDEN}” "
                        "hidden — it cannot retire"
                    )

    if problems:
        return Plan(system="specialisation", problems=tuple(problems))

    steps = [
        CreateSlotType(name=SLOT_TYPE, plural_name="Specialisations"),
        *[
            CreatePickable(
                name=row.name,
                slot_type=SLOT_TYPE,
                moved_modifier_ids=tuple(m.pk for m in row.modifiers.all()),
                moved_from=("library.Specialisation", row.pk),
            )
            for row in old_rows
        ],
        CreatePicklist(
            name=PICKLIST,
            slot_type=SLOT_TYPE,
            members=tuple(row.name for row in old_rows),
        ),
        CreateSlot(
            name=SLOT_TYPE,
            slot_type=SLOT_TYPE,
            picklist=PICKLIST,
            assigned_to="bearer",
            min_picks=0,
        ),
        SwapCarrier(
            carrier=("library.Subtype", subtype.pk),
            carrier_name=f"the “{SUBTYPE}” subtype",
            drop_modifier_id=offer.pk,
            drop_modifier_name=offer.name,
            grant_name="Specialist: the model is asked its Specialisation",
            slot=SLOT_TYPE,
            reach="model",
        ),
    ]
    if narrow is not None and narrow_offer is not None:
        steps += [
            CreatePicklist(
                name="Subjugator Patrol Officer options",
                slot_type=SLOT_TYPE,
                members=tuple(narrow_names),
            ),
            CreateSlot(
                name="Specialisation (Subjugator Patrol Officer)",
                slot_type=SLOT_TYPE,
                picklist="Subjugator Patrol Officer options",
                label="Specialisation",
                assigned_to="bearer",
                min_picks=0,
            ),
            SwapCarrier(
                carrier=("library.Hidden", narrow.pk),
                carrier_name=f"the “{NARROW_HIDDEN}” hidden",
                drop_modifier_id=narrow_offer.pk,
                drop_modifier_name=narrow_offer.name,
                grant_name=(
                    "Subjugator Patrol Officer: the model is asked its Specialisation"
                ),
                slot="Specialisation (Subjugator Patrol Officer)",
                reach="model",
            ),
        ]
    steps += [
        RewritePick(
            assignment_id=pick.pk,
            old_column="specialisation",
            pickable=pick.specialisation.name,
            slot=SLOT_TYPE,
            gang=str(pick.gang_root),
        )
        for pick in picks
    ]
    if general is not None:
        if general_offer is not None:
            steps.append(
                DropModifier(
                    carrier=("library.Hidden", general.pk),
                    carrier_name=f"the “{GENERAL_HIDDEN}” hidden",
                    modifier_id=general_offer.pk,
                    modifier_name=general_offer.name,
                )
            )
        steps += stray_effects
        if general_menu is not None:
            steps.append(
                Retire(
                    model="library.Collection",
                    pk=general_menu.pk,
                    name=general_menu.name,
                )
            )
        steps.append(Retire(model="library.Hidden", pk=general.pk, name=str(general)))
    if narrow_menu is not None:
        steps.append(
            Retire(model="library.Collection", pk=narrow_menu.pk, name=narrow_menu.name)
        )
    steps += [
        Retire(model="library.Specialisation", pk=row.pk, name=row.name)
        for row in old_rows
    ]

    gang_ids = sorted(
        {
            *(
                Assignment.objects.filter(archived=False, subtype=subtype)
                .values_list("gang_root_id", flat=True)
                .distinct()
            ),
            *(pick.gang_root_id for pick in picks),
            *(
                Assignment.objects.filter(
                    archived=False, hidden__in=[h for h in (narrow,) if h]
                ).values_list("gang_root_id", flat=True)
            ),
        },
        key=str,
    )
    return Plan(system="specialisation", steps=tuple(steps), gang_ids=tuple(gang_ids))
