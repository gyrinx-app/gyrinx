"""Splitting the Outcast archetypes in two, one set for each choice.

An Outcast gang's Archetype is picked by the Leader and held by the
gang, so it reaches every member. A Champion picks an Archetype too, and
that one belongs to the Champion alone. Both choices drew from a single
picklist, so each of the five archetypes carried the two readings at
once: the gang's, which places skill sets for every model, and the
Champion's, which places them for the one model carrying the pick. No
modifier can be scoped for both. Scoped to the model carrying it, it
does nothing at all on a pick the gang holds; scoped to every model, it
reaches the whole gang from a pick a Champion made.

So the two are split. The Champion's slot gets a picklist of its own,
holding five pickables of its own — the same names a card prints, told
apart for authors by their qualifier — and each takes the modifiers that
were only ever the Champion's. Which ones those are follows from the
same argument: a modifier reaching the model carrying it can do nothing
from a pick the gang holds, so it was written for the Champion's pick.

Three of Wyrd's modifiers are not sorted by that rule, and each is named
here: one that adds the Wyrd subtype to every Champion in the gang, one
that offers a power to Champions and Leaders alike, and one that puts
Wyrd Powers under Primary for everybody. The first belongs to the
Champion's pick and becomes a modifier about the one model; the other
two say something for each of the two picks, so each ends up with a
modifier of its own.

Everything here is found by id, and finding nothing is a normal outcome:
a database with no Outcast content is left exactly as it stands.
"""

#: The Champion's own Archetype choice — the slot a Champion entry is
#: granted, whose pick lands on the Champion.
CHAMPION_SLOT = "01M0G9384562YPMERG9WG66GAJ"

#: The five archetypes as the gang's Leader picks them, in the order the
#: Leader's picklist prints them.
ARCHETYPES = (
    ("Brawler", "01M0G937MFA7PQQ09MF5BVF50C"),
    ("Gunslinger", "01M0G937Q8PS2XCMAWC9HJE4ZK"),
    ("Mastermind", "01M0G937SXCCQ20DQ8FGHKERSE"),
    ("Survivor", "01M0G937WKKC28RHJM25T3GQ5S"),
    ("Wyrd", "01M0G937Z5EJSVP5JPY3EZJ2T8"),
)

#: The Champion's copies keep the name a card prints and carry the
#: qualifier that tells an author which of the two is which.
QUALIFIER = "Champion Archetype"

#: The list the Champion's slot draws from once the two are split.
PICKLIST = "Champion Archetypes"

#: The two ranks the Wyrd modifiers name.
CHAMPION_SUBTYPE = "01KZGCRX75B135MSF88R921GW2"
LEADER_SUBTYPE = "01KZGCRX9H75M4J0P90J69SH5S"

#: Wyrd's three modifiers that the bearer rule does not sort.
#: Adds the Wyrd subtype to every Champion in the gang — the Champion's
#: own business, so it becomes a modifier about the model carrying it.
WYRD_ADDS_TO_CHAMPIONS = "01KZYEVBEDD8ZRH12Z9ZBPQY39"
#: Offers a power to Champions and Leaders alike, reaching only the
#: model carrying it — from a gang-held pick that is nobody, so the
#: Leader's copy has to reach every model and narrow to Leaders.
WYRD_OFFERS_A_POWER = "01M146XA0E11JD9ZX570DKKFYB"
#: Puts Wyrd Powers under Primary for every model in the gang, Champions
#: included; the gang's pick governs everyone except Champions.
WYRD_POWERS_ARE_PRIMARY = "01KZV4BPS7V1QB9CCB974TV9T8"

#: What the two modifiers written for the Leader's and the Champion's
#: Wyrd are called. Both follow the wording already on their neighbours.
LEADER_OFFER = (
    "Wyrd: Leader models — offers a choice of power from Primary (Skills & Powers)"
)
CHAMPION_WYRD_POWERS = (
    "Wyrd: Champion (own pick) — puts Wyrd Powers under Primary (Skills & Powers)"
)

#: The reach values, spelled here rather than imported: this runs against
#: whatever model classes it is handed, historical ones included.
BEARER = "bearer"
EVERY_MODEL = "every_model"


def make_champion_archetypes(apps):
    """Give the Champion's Archetype choice pickables of its own.

    ``apps`` is any model registry — the real one, or a migration's
    historical one. Returns the lines describing what changed; running
    it again finds the split already made and returns one line saying so.
    """
    Pickable = apps.get_model("library", "Pickable")
    Picklist = apps.get_model("library", "Picklist")
    PicklistMember = apps.get_model("library", "PicklistMember")
    Slot = apps.get_model("library", "Slot")
    Subtype = apps.get_model("library", "Subtype")
    Modifier = apps.get_model("library", "Modifier")

    slot = Slot.objects.filter(pk=CHAMPION_SLOT).first()
    if slot is None:
        return ["nothing to split — this library holds no Champion Archetype slot"]
    leaders = {}
    for name, pk in ARCHETYPES:
        leader = Pickable.objects.filter(pk=pk, slot_type_id=slot.slot_type_id).first()
        if leader is None:
            return [f"nothing to split — this library holds no {name} archetype"]
        leaders[name] = leader

    report = []
    picklist = Picklist.objects.filter(
        slot_type_id=slot.slot_type_id, name__iexact=PICKLIST
    ).first()
    if picklist is None:
        picklist = Picklist.objects.create(
            name=PICKLIST, slot_type_id=slot.slot_type_id, pack_id=slot.pack_id
        )
        report.append(f"created the {PICKLIST} picklist")

    champions = {}
    for position, (name, _) in enumerate(ARCHETYPES):
        leader = leaders[name]
        champion = Pickable.objects.filter(
            slot_type_id=slot.slot_type_id,
            name__iexact=name,
            qualifier__iexact=QUALIFIER,
        ).first()
        if champion is None:
            champion = Pickable.objects.create(
                name=leader.name,
                qualifier=QUALIFIER,
                slot_type_id=leader.slot_type_id,
                pack_id=leader.pack_id,
                category_id=leader.category_id,
                position=leader.position,
            )
            report.append(f"created {name} for the Champion's own pick")
        champions[name] = champion
        if not PicklistMember.objects.filter(
            picklist=picklist, pickable=champion
        ).exists():
            PicklistMember.objects.create(
                picklist=picklist, pickable=champion, position=position
            )

    report.extend(_wyrd_before_the_move(leaders["Wyrd"], Modifier))
    for name, _ in ARCHETYPES:
        moved = _move_what_only_the_champion_reads(leaders[name], champions[name])
        if moved:
            report.append(
                f"{name}: moved {moved} modifier{'' if moved == 1 else 's'} "
                "onto the Champion's pickable"
            )
    report.extend(
        _wyrd_after_the_move(
            apps, leaders["Wyrd"], champions["Wyrd"], Modifier, Subtype
        )
    )

    if slot.picklist_id != picklist.pk:
        slot.picklist_id = picklist.pk
        slot.save(update_fields=["picklist"])
        report.append(f"{slot.name} now draws from {PICKLIST}")

    if not report:
        return ["nothing to split — the Champion archetypes are already there"]
    return report


def _move_what_only_the_champion_reads(leader, champion):
    """Hand over every modifier reaching only the model carrying it.

    From a pick the gang holds such a modifier reaches nobody, so it can
    only have been written for the pick a Champion makes. The rows
    themselves are reused: what changes is which pickable carries them.
    """
    theirs = list(leader.modifiers.filter(targets_miniature__reach=BEARER))
    for row in theirs:
        leader.modifiers.remove(row)
        champion.modifiers.add(row)
    return len(theirs)


def _wyrd_before_the_move(wyrd, Modifier):
    """Narrow the Wyrd subtype grant to the model carrying it.

    It reaches every Champion in the gang, which from the gang's own
    pick makes every Champion a Wyrd. Once it reaches only the model
    carrying it, the ordinary hand-over takes it to the Champion's
    pickable with the rest.
    """
    adds = Modifier.objects.filter(
        pk=WYRD_ADDS_TO_CHAMPIONS, targets_miniature__isnull=False
    ).first()
    if adds is None or not wyrd.modifiers.filter(pk=adds.pk).exists():
        return []
    scope = adds.targets_miniature
    if scope.reach == BEARER:
        return []
    scope.reach = BEARER
    scope.save(update_fields=["reach"])
    return [f"{adds.name} now reaches the model carrying it"]


def _wyrd_after_the_move(apps, wyrd, champion_wyrd, Modifier, Subtype):
    """Give each of the two Wyrd picks its own reading of the two
    modifiers that speak for both."""
    HasSubtypes = apps.get_model("library", "HasSubtypes")
    TargetsMiniature = apps.get_model("library", "TargetsMiniature")
    OffersChoice = apps.get_model("library", "OffersChoice")
    PlacesCategory = apps.get_model("library", "PlacesCategory")

    champion_rank = Subtype.objects.filter(pk=CHAMPION_SUBTYPE).first()
    leader_rank = Subtype.objects.filter(pk=LEADER_SUBTYPE).first()
    report = []

    offer = Modifier.objects.filter(
        pk=WYRD_OFFERS_A_POWER,
        offers_choice__isnull=False,
        targets_miniature__isnull=False,
    ).first()
    if (
        offer is not None
        and champion_rank is not None
        and leader_rank is not None
        and champion_wyrd.modifiers.filter(pk=offer.pk).exists()
    ):
        for row in offer.targets_miniature.has_subtypes.all():
            row.subtypes.set([champion_rank])
        if not Modifier.objects.filter(
            pack_id=offer.pack_id, name__iexact=LEADER_OFFER
        ).exists():
            scope = TargetsMiniature.objects.create(reach=EVERY_MODEL)
            narrowing = HasSubtypes.objects.create(scope=scope)
            narrowing.subtypes.set([leader_rank])
            source = offer.offers_choice
            wyrd.modifiers.add(
                Modifier.objects.create(
                    name=LEADER_OFFER,
                    pack_id=offer.pack_id,
                    targets_miniature=scope,
                    offers_choice=OffersChoice.objects.create(
                        of_kind_id=source.of_kind_id,
                        from_section_id=source.from_section_id,
                        label=source.label,
                        will_be_assigned_to=source.will_be_assigned_to,
                    ),
                )
            )
            report.append(f"created {LEADER_OFFER}")

    powers = Modifier.objects.filter(
        pk=WYRD_POWERS_ARE_PRIMARY,
        places_category__isnull=False,
        targets_miniature__isnull=False,
    ).first()
    if (
        powers is not None
        and champion_rank is not None
        and wyrd.modifiers.filter(pk=powers.pk).exists()
    ):
        scope = powers.targets_miniature
        if not scope.has_subtypes.exists():
            # The gang's pick governs every Outcast model except the
            # Champions, who read their own pick instead.
            narrowing = HasSubtypes.objects.create(scope=scope, negate=True)
            narrowing.subtypes.set([champion_rank])
            report.append(f"{powers.name} now reaches every model except Champions")
        if not Modifier.objects.filter(
            pack_id=powers.pack_id, name__iexact=CHAMPION_WYRD_POWERS
        ).exists():
            source = powers.places_category
            wyrd_only = TargetsMiniature.objects.create(reach=BEARER)
            champion_wyrd.modifiers.add(
                Modifier.objects.create(
                    name=CHAMPION_WYRD_POWERS,
                    pack_id=powers.pack_id,
                    targets_miniature=wyrd_only,
                    places_category=PlacesCategory.objects.create(
                        category_id=source.category_id,
                        the_chosen=source.the_chosen,
                        section_id=source.section_id,
                    ),
                )
            )
            report.append(f"created {CHAMPION_WYRD_POWERS}")

    return report
