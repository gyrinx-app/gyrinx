"""The Skill Tree conversion — the Venator ranked-trees system.

Today: four "Skill Tree 1"–"Skill Tree 4" hiddens ride the gang, each
carrying a gang-wide offer of the whole skill tree kind and the per-rank
chosen-mode placements that turn the gang's picks into every fighter's
Primary and Secondary access. Six tree tokens exist to be chosen, each
homed in the skill category it stands for — the home *is* the payload:
a placement reads the chosen thing's category and nothing else.

After: a "Skill Tree" slot type refusing repeats; the six as pickables
on one picklist, homed where their tokens are homed; four slots named
as the hiddens' offers are, each granted by its own hidden. The
placements stay exactly where they are — they read whatever was chosen
through the same anchor before and after.

**Nothing is deleted.** The six tree tokens stay in the library saying
what they say now; only the offers come off the carriers, replaced by
grants of the slots. Repeats are refused on the slot type because the
game ranks four *different* trees — and because that is also what keeps
the page of a gang that picked one tree twice reading the same: an
offer always notes a doubled settling, and a slot only notes one where
its type refuses repeats.

Production converts from the maintenance console, once, after the code
deploys — see :mod:`n26.maintenance`. Elsewhere the command does it
(``manage n26_convert skill_tree``).
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
    one_answer_per_question,
    spread,
)

SLOT_TYPE = "Skill Tree"
PLURAL = "Skill Trees"
PICKLIST = "Skill Trees"
RANKS = (1, 2, 3, 4)
HIDDENS = tuple(f"Skill Tree {rank}" for rank in RANKS)

#: How many gangs the apply proves unchanged before committing — the
#: same reasoning as the Specialisation conversion: a spread wide enough
#: to hold every shape the system comes in, proven with the lock held
#: for seconds, where proving everyone would hold rows players are using
#: for minutes.
PROVEN = 25


def _offers_of(carrier):
    return [
        m
        for m in carrier.modifiers.all()
        if getattr(m, "offers_choice", None) is not None
        and m.offers_choice.of_kind.model == "skilltree"
    ]


def _the_offer(carrier, problems, said):
    """The carrier's one skill tree offer, or a stated problem."""
    offers = _offers_of(carrier)
    if len(offers) != 1:
        problems.append(
            f"{said} carries {len(offers)} skill tree offers — expected one"
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


def plan_skill_tree():
    from n26.core.models import Assignment
    from n26.library.models import (
        AddsAssignable,
        Hidden,
        Modifier,
        SkillTree,
        SlotType,
    )

    problems = []

    if SlotType.objects.filter(name=SLOT_TYPE, archived=False).exists():
        return Plan(system="skill_tree", nothing_here=True)

    # Hidden names are unique only together with their qualifier, so each
    # name must resolve to one row or the plan cannot know which it is
    # converting. All four or none: a database holding some of the rank
    # carriers is not one this plan understands.
    carriers = {}
    for name in HIDDENS:
        found = list(Hidden.objects.filter(name=name, archived=False))
        if len(found) > 1:
            problems.append(f"{len(found)} hiddens named “{name}” — expected one")
        elif found:
            carriers[name] = found[0]
    if not carriers and not problems:
        return Plan(system="skill_tree", nothing_here=True)
    if len(carriers) < len(HIDDENS):
        missing = [name for name in HIDDENS if name not in carriers]
        problems.append(
            "rank carriers missing: " + ", ".join(f"“{name}”" for name in missing)
        )

    offers = {}
    for name, carrier in carriers.items():
        offer = _the_offer(carrier, problems, f"the “{name}” hidden")
        if offer is None:
            continue
        if offer.offers_choice.from_section_id is not None:
            problems.append(
                f"the “{name}” offer names a menu — expected the whole kind"
            )
        _solely_carried(offer, carrier, problems)
        offers[name] = offer

    old_rows = list(
        SkillTree.objects.filter(archived=False)
        .select_related("category")
        .order_by("name")
    )
    if not old_rows:
        problems.append("no skill trees to convert")
    # A pick is matched to its pickable by name, and a name is only unique
    # within a pack and qualifier — so two live rows called the same thing
    # would quietly become one pickable, and half the picks would land on
    # the wrong one.
    names = [row.name for row in old_rows]
    twice = sorted({name for name in names if names.count(name) > 1})
    if twice:
        problems.append("more than one live skill tree is called: " + ", ".join(twice))
    homeless = [row.name for row in old_rows if row.category_id is None]
    if homeless:
        # The home is the whole payload: a token homed nowhere places
        # nothing today, and a pickable homed nowhere would carry that
        # nothing forward — but nobody has decided that is what it means.
        problems.append("skill trees homed nowhere: " + ", ".join(homeless))

    # Only live answers move. An archived pick is history nothing draws,
    # and with no old row being deleted there is nothing to make it
    # follow.
    picks = list(
        Assignment.objects.filter(skill_tree__isnull=False, archived=False)
        .exclude(removes=True)
        .select_related("skill_tree", "gang_root", "caused_by")
        .order_by("created")
    )
    answers, spares = one_answer_per_question(picks)

    # A carrier that arrives by grant has no assignment to find it by,
    # so the gangs it reaches cannot be counted and cannot be drawn into
    # the spread this proves. Refuse instead: nothing grants these today,
    # and whoever makes one should decide what this ought to do.
    for name, carrier in carriers.items():
        for granter in Modifier.objects.filter(
            adds_assignable__in=AddsAssignable.objects.filter(hidden=carrier)
        ):
            if carriers_of(granter):
                problems.append(
                    f"“{granter.name}” grants the “{name}” hidden, so the "
                    "gangs it reaches cannot be counted or proven"
                )

    # Each pick settles on the slot its own anchor grants.
    becoming = {row.name for row in old_rows}
    carrier_pks = {carrier.pk: name for name, carrier in carriers.items()}
    pick_slots = {}
    for pick in answers:
        if pick.skill_tree.name not in becoming:
            problems.append(
                f"pick {pick.pk} names “{pick.skill_tree.name}”, which is "
                "not becoming a pickable"
            )
        if pick.caused_by_id is None:
            problems.append(f"pick {pick.pk} has no caused_by to settle against")
        elif pick.caused_by.hidden_id in carrier_pks:
            pick_slots[pick.pk] = carrier_pks[pick.caused_by.hidden_id]
        else:
            problems.append(
                f"pick {pick.pk} is anchored on “{pick.caused_by}”, which the "
                "plan does not recognise"
            )

    if problems:
        return Plan(system="skill_tree", problems=tuple(problems))

    steps = [
        # Repeats refused: the game ranks four different trees, and a
        # doubled pick keeps drawing the note it draws today — an offer
        # always notes one, a slot only where its type refuses them.
        CreateSlotType(name=SLOT_TYPE, plural_name=PLURAL, allows_repeats=False),
        *[
            CreatePickable(
                name=row.name,
                slot_type=SLOT_TYPE,
                moved_modifier_ids=tuple(m.pk for m in row.modifiers.all()),
                moved_from=("library.SkillTree", row.pk),
                homed_in=(row.category_id, row.category.name),
            )
            for row in old_rows
        ],
        CreatePicklist(
            name=PICKLIST,
            slot_type=SLOT_TYPE,
            members=tuple(row.name for row in old_rows),
        ),
        *[
            CreateSlot(
                name=name,
                slot_type=SLOT_TYPE,
                picklist=PICKLIST,
                assigned_to="bearer",
                min_picks=0,
            )
            for name in HIDDENS
        ],
        *[
            SwapCarrier(
                carrier=("library.Hidden", carriers[name].pk),
                carrier_name=f"the “{name}” hidden",
                drop_modifier_id=offers[name].pk,
                drop_modifier_name=offers[name].name,
                grant_name=f"{name}: the gang is asked its skill tree",
                slot=name,
                reach="gang_alone",
            )
            for name in HIDDENS
        ],
        *[
            RewritePick(
                assignment_id=pick.pk,
                old_column="skill_tree",
                pickable=pick.skill_tree.name,
                slot=pick_slots[pick.pk],
                gang=str(pick.gang_root),
            )
            for pick in answers
        ],
    ]

    # Every gang the change can reach, and then the spread actually
    # proven: one holding a repeated tree, one holding a doubled answer,
    # one that answered some ranks but not all, one that never answered,
    # and ordinary ones. Removal machinery is not a holding: a hidden
    # taken away would otherwise read as one held, and count a gang the
    # change never reaches.
    holders = set(
        Assignment.objects.filter(
            archived=False, hidden__in=[c for c in carriers.values()]
        )
        .exclude(removes=True)
        .values_list("gang_root_id", flat=True)
        .distinct()
    )
    answered = {pick.gang_root_id for pick in answers}
    holders |= answered

    by_gang = {}
    for pick in answers:
        by_gang.setdefault(pick.gang_root_id, []).append(pick)
    repeated = [
        gang_id
        for gang_id, held in by_gang.items()
        if len({p.skill_tree_id for p in held}) < len(held)
    ]
    partial = [gang_id for gang_id, held in by_gang.items() if len(held) < len(HIDDENS)]

    proven = spread(
        holders,
        [
            repeated,
            [pick.gang_root_id for pick in spares],
            sorted(partial, key=str),
            sorted(holders - answered, key=str),
            sorted(answered, key=str),
        ],
        PROVEN,
    )
    return Plan(
        system="skill_tree",
        steps=tuple(steps),
        gang_ids=tuple(proven),
        reaches=len(holders),
        left_alone=len(spares),
    )
