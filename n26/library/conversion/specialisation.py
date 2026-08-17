"""The Specialisation conversion — the volume system.

Today: the "Specialist" subtype carries a bearer offer of the whole
specialisation kind; eight specialisations each add one skill to the
bearer. A second, narrowed offer rides the "Specialisation offer"
hidden, which an owner gave to a Subjugator Patrol Officer.

After: a "Specialisation" slot type; the eight as pickables on one
picklist; a bearer slot granted by the same subtype. The narrowed
hidden keeps its purpose — its offer becomes a grant of a second slot
over its own narrow picklist, so a holder's page asks the same question.

**Nothing is deleted.** The switch is what the pages read from, and no
page reads anything from an old row once nothing offers it. Retiring
those rows is tidiness, and tidiness is what made this hard: every
protected reference, every fossil of an abandoned experiment, every
stray assignment nobody meant to make had to be reasoned about before a
single pick could move. Left alone, they go on saying exactly what they
say now, and can be cleared away later by someone with time to look at
them one at a time.

That is why a doubled answer — the same specialisation assigned twice,
which the page shows as the answer plus a spare line in the gear list —
needs nothing from this conversion. The answer becomes a pick; the spare
stays as it is and goes on drawing the line it draws today.

Production converts from the maintenance console, once, after the code
deploys — see :mod:`n26.maintenance`. Elsewhere the command does it
(``manage n26_convert specialisation``).
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
)

SUBTYPE = "Specialist"
SLOT_TYPE = "Specialisation"
PICKLIST = "Specialisations"
NARROW_HIDDEN = "Specialisation offer"
NARROW_PICKLIST = "Subjugator Patrol Officer options"
NARROW_SLOT = "Specialisation (Subjugator Patrol Officer)"

#: How many gangs the apply proves unchanged before committing.
#:
#: Not all of them, deliberately. Rendering every affected gang twice
#: takes minutes, and minutes inside a transaction on a live app is a
#: worse thing to be than incompletely proven — it holds rows players
#: are using and collides with what they do meanwhile. The failures this
#: has actually caught were all shaped by the content, not by one gang's
#: data, so they show up in any gang the change reaches; and the ones
#: that *are* particular to a gang are found by asking the database
#: plainly, which costs a second. So: a spread wide enough to include
#: every shape the system comes in, proven with the lock held for
#: seconds.
PROVEN = 25


def _offers_of(carrier):
    return [
        m
        for m in carrier.modifiers.all()
        if getattr(m, "offers_choice", None) is not None
        and m.offers_choice.of_kind.model == "specialisation"
    ]


def _the_offer(carrier, problems, said):
    """The carrier's one specialisation offer, or a stated problem."""
    offers = _offers_of(carrier)
    if len(offers) != 1:
        problems.append(
            f"{said} carries {len(offers)} specialisation offers — expected one"
        )
        return None
    return offers[0]


def _solely_carried(offer, carrier, problems):
    """Deleting an offer's modifier detaches it from every carrier at
    once, so the plan must know no third thing shares it — a sharer's
    gangs are outside the proven set and would lose their question
    unnoticed."""
    others = [
        f"{kind} “{row}”"
        for kind, row in carriers_of(offer)
        if not (kind == type(carrier).__name__ and row.pk == carrier.pk)
    ]
    if others:
        problems.append(
            f"“{offer.name}” is shared — also carried by " + ", ".join(others)
        )


def _answers(picks):
    """One pick per question, and the spares left behind.

    The same question answered twice — a click that landed twice — shows
    on the page as the answer plus a spare line in the gear list. Moving
    the answer keeps the page: the pick becomes a pick, and the spare
    goes on being the ordinary assignment it already is.
    """
    answers, spares, seen = [], [], set()
    for pick in picks:
        question = (pick.miniature_id, pick.caused_by_id)
        if question in seen:
            spares.append(pick)
        else:
            seen.add(question)
            answers.append(pick)
    return answers, spares


def _spread(gang_ids, kinds, limit):
    """A sample wide enough to hold every shape, in a stable order.

    Takes from each kind in turn so no one kind crowds the others out,
    and keeps the gangs that are odd in some way — the ones a wider
    sweep would have been for.
    """
    chosen, used = [], set()
    for wanted in kinds:
        for gang_id in wanted:
            if gang_id in used or gang_id not in gang_ids:
                continue
            used.add(gang_id)
            chosen.append(gang_id)
            if len(chosen) >= limit:
                return chosen
    return chosen


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
        _solely_carried(offer, subtype, problems)

    old_rows = list(Specialisation.objects.filter(archived=False).order_by("name"))
    if not old_rows:
        problems.append("no specialisations to convert")

    # Hidden names are unique only together with their qualifier, so a
    # name here must resolve to one row or the plan cannot know which it
    # is converting.
    def _the_hidden(name):
        found = list(Hidden.objects.filter(name=name, archived=False))
        if len(found) > 1:
            problems.append(f"{len(found)} hiddens named “{name}” — expected one")
            return None
        return found[0] if found else None

    narrow = _the_hidden(NARROW_HIDDEN)
    narrow_offer = None
    narrow_names = []
    if narrow is not None:
        narrow_offer = _the_offer(narrow, problems, f"the “{NARROW_HIDDEN}” hidden")
        if narrow_offer is not None:
            _solely_carried(narrow_offer, narrow, problems)
            section = narrow_offer.offers_choice.from_section
            if section is None:
                problems.append(f"the “{NARROW_HIDDEN}” offer names no menu")
            else:
                narrow_names = [
                    entry.specialisation.name
                    for entry in section.collection.entries.filter(
                        specialisation__isnull=False
                    ).select_related("specialisation")
                ]
                strangers = set(narrow_names) - {row.name for row in old_rows}
                if strangers:
                    problems.append(
                        "the narrow menu lists specialisations the kind does "
                        "not: " + ", ".join(sorted(strangers))
                    )

    # Only live answers move. An archived pick is history nothing draws,
    # and with no old row being deleted there is nothing to make it
    # follow.
    picks = list(
        Assignment.objects.filter(specialisation__isnull=False, archived=False)
        .exclude(removes=True)
        .select_related("specialisation", "gang_root", "caused_by")
        .order_by("created")
    )
    answers, spares = _answers(picks)

    # Each pick settles on the slot its own anchor grants.
    becoming = {row.name for row in old_rows}
    pick_slots = {}
    for pick in answers:
        if pick.specialisation.name not in becoming:
            problems.append(
                f"pick {pick.pk} names “{pick.specialisation.name}”, which is "
                "not becoming a pickable"
            )
        if pick.caused_by_id is None:
            problems.append(f"pick {pick.pk} has no caused_by to settle against")
        elif pick.caused_by.subtype_id == subtype.pk:
            pick_slots[pick.pk] = SLOT_TYPE
        elif narrow is not None and pick.caused_by.hidden_id == narrow.pk:
            pick_slots[pick.pk] = NARROW_SLOT
        else:
            problems.append(
                f"pick {pick.pk} is anchored on “{pick.caused_by}”, which the "
                "plan does not recognise"
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
                name=NARROW_PICKLIST,
                slot_type=SLOT_TYPE,
                members=tuple(narrow_names),
            ),
            CreateSlot(
                name=NARROW_SLOT,
                slot_type=SLOT_TYPE,
                picklist=NARROW_PICKLIST,
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
                slot=NARROW_SLOT,
                reach="model",
            ),
        ]
    steps += [
        RewritePick(
            assignment_id=pick.pk,
            old_column="specialisation",
            pickable=pick.specialisation.name,
            slot=pick_slots[pick.pk],
            gang=str(pick.gang_root),
        )
        for pick in answers
    ]

    # Every gang the change can reach, and then the spread actually
    # proven: one holding a doubled answer, one holding the narrowed
    # question, one that never answered, and ordinary ones.
    holders = set(
        Assignment.objects.filter(archived=False, subtype=subtype)
        .values_list("gang_root_id", flat=True)
        .distinct()
    )
    if narrow is not None:
        holders |= set(
            Assignment.objects.filter(archived=False, hidden=narrow).values_list(
                "gang_root_id", flat=True
            )
        )
    answered = {pick.gang_root_id for pick in answers}
    holders |= answered
    proven = _spread(
        holders,
        [
            [pick.gang_root_id for pick in spares],
            [
                pick.gang_root_id
                for pick in answers
                if pick_slots.get(pick.pk) == NARROW_SLOT
            ],
            sorted(holders - answered, key=str),
            sorted(answered, key=str),
        ],
        PROVEN,
    )
    return Plan(
        system="specialisation",
        steps=tuple(steps),
        gang_ids=tuple(proven),
        reaches=len(holders),
        left_alone=len(spares),
    )
