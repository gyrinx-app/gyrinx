"""Authoring verbs — the one vocabulary for building library content.

These verbs are the authoring API, and the admin's forms compile to
exactly these calls — a form that can't be expressed as a verb here
can't exist, and a verb here is what a spec describes
(design/authoring.md).

The grammar (design/authoring-build-plan.md):

* **Scopes** say who a modifier reaches, and take nested **conditions**::

      targets_model(has_subtypes(leader, champion))
      targets_model(counter_at_least(xp, 75))
      targets_weapons(has_traits(melee))

* **Effects** carry a prefix saying *when they happen*: ``ef_`` is
  worked out at read time, ``op_`` writes once at purchase time.

* **Glue**: ``modifier(name, scope, effect, attach_to=…)`` builds one
  rule; ``attach_modifiers_to(assignable, modifiers)`` hangs reusable
  rules on further carriers.

Everything is pack-aware: omit ``pack`` and it lands in the default
pack, exactly as admin ingestion would. Nothing here stores rules text —
see CLAUDE.md.
"""

import re

from django.core.exceptions import ValidationError

from n26.library.models import (
    GangType,
    Profile,
    ProfileType,
    Stat,
    Statline,
    StatlineStat,
    StatlineType,
    StatlineTypeStat,
)


def create_pack(name, slug=None, **kwargs):
    """A content pack. Slug defaults to a lowercased, hyphenated name."""
    from n26.library.models import ContentPack

    return ContentPack.objects.create(
        name=name, slug=slug or name.lower().replace(" ", "-"), **kwargs
    )


def create_gang_type(
    name,
    starting_credits=None,
    icon_url="",
    foundable=True,
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """A kind of gang. The name is the whole of what a player sees when
    the create-gang page offers it, so a blank one is refused here rather
    than drawn as an empty card — whatever path asked for it. Stored
    stripped, since a padded name draws with the padding.
    """
    name = (name or "").strip()
    if not name:
        raise ValidationError("A gang type needs a name.")
    return GangType.objects.create(
        name=name,
        starting_credits=starting_credits,
        icon_url=icon_url,
        foundable=foundable,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )


def create_stat(
    short_name,
    full_name,
    is_inches=False,
    is_target=False,
    is_inverted=False,
    is_modifier=False,
    **kwargs,
):
    """A stat definition, e.g. ``create_stat("M", "Movement", is_inches=True)``.

    The internal ``field_name`` is derived from the full name.
    """
    return Stat.objects.create(
        short_name=short_name,
        full_name=full_name,
        is_inches=is_inches,
        is_target=is_target,
        is_inverted=is_inverted,
        is_modifier=is_modifier,
        **kwargs,
    )


def create_statline_type(name, stats=(), **kwargs):
    """A statline shape — the columns a profile prints in.

    ``stats`` is an ordered list of :class:`Stat`, and list order
    becomes print position. Given none, the shape starts bare and
    stats are added with ``add_stat_to_statline_type``: print order
    matters, and a multi-select cannot express it.
    """
    statline_type = StatlineType.objects.create(name=name, **kwargs)
    for position, stat in enumerate(stats):
        add_stat_to_statline_type(statline_type, stat, position=position, **kwargs)
    return statline_type


def add_stat_to_statline_type(
    statline_type,
    stat,
    position=None,
    short_name_override="",
    is_highlighted=False,
    is_first_of_group=False,
    **kwargs,
):
    """Put one characteristic in a shape, at the end unless placed.

    ``short_name_override`` heads the column with something other than
    the stat's own abbreviation, for a shape that prints it differently.
    """
    if position is None:
        position = statline_type.stats.count()
    return StatlineTypeStat.objects.create(
        statline_type=statline_type,
        stat=stat,
        position=position,
        short_name_override=short_name_override,
        is_highlighted=is_highlighted,
        is_first_of_group=is_first_of_group,
        **kwargs,
    )


def create_profile_type(name, statline_type, lasting_effect_term="Injury", **kwargs):
    return ProfileType.objects.create(
        name=name,
        statline_type=statline_type,
        lasting_effect_term=lasting_effect_term,
        **kwargs,
    )


def create_profile(
    name,
    profile_type,
    gang_type,
    price=0,
    category=None,
    hireable=True,
    qualifier="",
    library_author_help="",
    **kwargs,
):
    return Profile.objects.create(
        name=name,
        profile_type=profile_type,
        gang_type=gang_type,
        price=price,
        category=category,
        hireable=hireable,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )


def set_statline(owner, pack=None, **values):
    """Give a fighter profile or weapon profile a statline.

    Values are keyed by stat field name.

    ``set_statline(juve, movement=4, weapon_skill=3, toughness=3)``

    Settable twice, which is what the name promises: a second call
    writes the characteristics it names over the ones already there and
    leaves the rest as they are. A statline is one row per owner, so
    founding a second would not be an alternative reading — it would be
    an error.

    Raises ``KeyError`` if a name isn't part of the profile's statline type,
    so a typo fails loudly rather than silently doing nothing.
    """
    extra = {"pack": pack} if pack else {}
    statline = getattr(owner, "statline", None)
    if statline is None:
        statline = Statline.objects.create(owner=owner, **extra)

    by_field_name = {
        type_stat.field_name: type_stat
        for type_stat in owner.statline_type.stats.select_related("stat")
    }
    if unknown := set(values) - set(by_field_name):
        raise KeyError(
            f"{owner.statline_type} has no stat named "
            f"{', '.join(sorted(unknown))}. Known: {', '.join(sorted(by_field_name))}"
        )

    for field_name, value in values.items():
        StatlineStat.objects.update_or_create(
            statline=statline,
            statline_type_stat=by_field_name[field_name],
            defaults={"value": str(value), **extra},
        )
    return statline


def revise(row, **fields):
    """Write the named columns of a row that already exists, and save.

    The other verbs make things; changing one is a write to the columns
    the kind already names, so this takes no spec of its own — its
    parameters are the row's own fields, and the row's kind is what
    describes those. One write path, shared by the authoring pages and
    by a re-import of a changed spreadsheet, so the two cannot come to
    disagree about what editing means.

    A many-to-many field is refused rather than assigned. A set is
    replaced by the verb that owns it (``set_traits``,
    ``set_usable_by``, ``set_statline``), because replacing a set is a
    decision — what happens to a member the new value does not name —
    and ``setattr`` has no way to express one.
    """
    for name, value in fields.items():
        if row._meta.get_field(name).many_to_many:
            raise ValueError(
                f"{name} is a set, so revise cannot write it — use the "
                f"set_ verb that owns it and says what leaving means"
            )
        setattr(row, name, value)
    row.save()
    return row


def set_traits(weapon_profile, traits):
    """The traits printed on a firing line, replaced.

    The statlines sheet is the whole statement about a line's traits,
    and a card prints them, so a trait the sheet stops naming goes.
    Added to instead, a line rewritten from Rapid Fire (1) to Rapid
    Fire (2) would print both forever.
    """
    weapon_profile.traits.set(traits)
    return weapon_profile


# --- Assignables ---------------------------------------------------------


def create_wargear(
    name,
    price=0,
    trade_point_price=None,
    is_exclusive=False,
    category=None,
    usable_by_profile_types=(),
    usable_by_subtypes=(),
    usable_by_profiles=(),
    usable_by_specialisations=(),
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """Equipment a model carries. A thing that bolts onto a weapon is a
    weapon accessory, not this.

    The ``usable_by_*`` lists are the bracket the book prints after the
    name, true of this wherever it is listed. Empty means everyone; a
    restriction only one list prints belongs on that list's entry
    instead (``add_entry``).
    """
    from n26.library.models import Wargear

    return set_usable_by(
        Wargear.objects.create(
            name=name,
            price=price,
            trade_point_price=trade_point_price,
            is_exclusive=is_exclusive,
            category=category,
            qualifier=qualifier,
            library_author_help=library_author_help,
            **kwargs,
        ),
        usable_by_profile_types=usable_by_profile_types,
        usable_by_subtypes=usable_by_subtypes,
        usable_by_profiles=usable_by_profiles,
        usable_by_specialisations=usable_by_specialisations,
    )


def create_weapon_accessory(
    name,
    price=0,
    trade_point_price=None,
    is_exclusive=False,
    category=None,
    fits_category=None,
    fits_asterisked=False,
    usable_by_profile_types=(),
    usable_by_subtypes=(),
    usable_by_profiles=(),
    usable_by_specialisations=(),
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """Something bolted onto a weapon, with the bracket saying what it
    fits — ``fits_category`` for "(Las Weapons Only)",
    ``fits_asterisked`` for "(Weapons Marked With * Only)".

    The two brackets answer different questions and both are stored: the
    ``fits_*`` pair is which weapons this goes on, the ``usable_by_*``
    lists which models may use it. Empty means everyone.
    """
    from n26.library.models import WeaponAccessory

    return set_usable_by(
        WeaponAccessory.objects.create(
            name=name,
            price=price,
            trade_point_price=trade_point_price,
            is_exclusive=is_exclusive,
            category=category,
            fits_category=fits_category,
            fits_asterisked=fits_asterisked,
            qualifier=qualifier,
            library_author_help=library_author_help,
            **kwargs,
        ),
        usable_by_profile_types=usable_by_profile_types,
        usable_by_subtypes=usable_by_subtypes,
        usable_by_profiles=usable_by_profiles,
        usable_by_specialisations=usable_by_specialisations,
    )


def create_subtype(name, qualifier="", library_author_help="", **kwargs):
    from n26.library.models import Subtype

    return Subtype.objects.create(
        name=name,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )


def create_skill(
    name,
    category=None,
    usable_by_profile_types=(),
    usable_by_subtypes=(),
    usable_by_profiles=(),
    usable_by_specialisations=(),
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """A skill, homed in its set — ``create_skill("Catfall", agility)``.

    The ``usable_by_*`` lists are the bracket the book prints in a
    skill's heading — "(Fighter Or Walker Only)". Empty means everyone,
    and it gates the advancement table's free pick as well as the
    listing.
    """
    from n26.library.models import Skill

    return set_usable_by(
        Skill.objects.create(
            name=name,
            category=category,
            qualifier=qualifier,
            library_author_help=library_author_help,
            **kwargs,
        ),
        usable_by_profile_types=usable_by_profile_types,
        usable_by_subtypes=usable_by_subtypes,
        usable_by_profiles=usable_by_profiles,
        usable_by_specialisations=usable_by_specialisations,
    )


def create_lasting_effect(name, qualifier="", library_author_help="", **kwargs):
    """What a Lasting Injury or Lasting Damage table deals out — the
    profile type's term decides what a card calls it."""
    from n26.library.models import LastingEffect

    return LastingEffect.objects.create(
        name=name,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )


def create_power(
    name,
    annotation="",
    category=None,
    usable_by_profile_types=(),
    usable_by_subtypes=(),
    usable_by_profiles=(),
    usable_by_specialisations=(),
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """A Wyrd power — ``create_power("Force Blast", "(Free), Continuous")``.

    The ``usable_by_*`` lists are the bracket a power's heading prints,
    read the same way a skill's is. Empty means everyone.
    """
    from n26.library.models import Power

    return set_usable_by(
        Power.objects.create(
            name=name,
            annotation=annotation,
            category=category,
            qualifier=qualifier,
            library_author_help=library_author_help,
            **kwargs,
        ),
        usable_by_profile_types=usable_by_profile_types,
        usable_by_subtypes=usable_by_subtypes,
        usable_by_profiles=usable_by_profiles,
        usable_by_specialisations=usable_by_specialisations,
    )


def split_annotation(text):
    """``"Leash (3\\")"`` → ``("Leash", '3"')``; ``"Melee"`` → ``("Melee", "")``.

    How a printed name in brackets is read, in one place, because two
    writers use it: the importer reading a sheet cell, and the authoring
    forms reading what a person typed. They must agree — a rule's
    annotation is part of its identity, so ``Leash`` + ``3"`` and a rule
    literally named ``Leash (3")`` are different rows that print the
    same, which is precisely the duplicate the annotation prevents.
    """
    smart = {"“": '"', "”": '"', "’": "'", "‘": "'"}
    for curly, plain in smart.items():
        text = text.replace(curly, plain)
    text = re.sub(r"\s*\(", " (", text.strip())
    match = re.match(r"^(.*?)\s*\((.*)\)$", text)
    if match:
        return match.group(1), match.group(2)
    return text, ""


def create_rule(name, annotation="", qualifier="", library_author_help="", **kwargs):
    """A named special rule — the name only, never the rules text."""
    from n26.library.models import Rule

    return Rule.objects.create(
        name=name,
        annotation=annotation,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )


def create_hidden(name, effects=(), qualifier="", library_author_help="", **kwargs):
    """A carrier for effects that draws no row of its own; ``effects``
    are (scope, effect) pairs."""
    from n26.library.models import Hidden

    carrier = Hidden.objects.create(
        name=name,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )
    for scope, effect in effects:
        modifier(
            name=f"{name}: {effect}", scope=scope, effect=effect, attach_to=carrier
        )
    return carrier


def create_skill_tree(name, category, qualifier="", library_author_help="", **kwargs):
    """A pickable skill set: a token whose home names the set it stands for."""
    from n26.library.models import SkillTree

    return SkillTree.objects.create(
        name=name,
        category=category,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )


def create_archetype(name, effects=(), qualifier="", library_author_help="", **kwargs):
    """A chosen carrier; ``effects`` are (scope, effect) pairs."""
    from n26.library.models import Archetype

    carrier = Archetype.objects.create(
        name=name,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )
    for scope, effect in effects:
        modifier(
            name=f"{name}: {effect}", scope=scope, effect=effect, attach_to=carrier
        )
    return carrier


def create_affiliation(
    name, effects=(), qualifier="", library_author_help="", **kwargs
):
    """As ``create_archetype``, for where the gang's loyalties lie."""
    from n26.library.models import Affiliation

    carrier = Affiliation.objects.create(
        name=name,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )
    for scope, effect in effects:
        modifier(
            name=f"{name}: {effect}", scope=scope, effect=effect, attach_to=carrier
        )
    return carrier


# --- Slots and picks: a slot type, authored ----------------------------------


def create_slot_type(name, plural_name="", allows_repeats=True, **kwargs):
    """What is chosen — Gang Legacy, Affiliation, Archetype.

    The first thing built: its pickables, its picklists and the slots
    themselves all name it, and authoring refuses a mismatch.
    """
    from n26.library.models import SlotType

    return SlotType.objects.create(
        name=name,
        plural_name=plural_name,
        allows_repeats=allows_repeats,
        **kwargs,
    )


def create_pickable(
    name,
    slot_type,
    effects=(),
    qualifier="",
    library_author_help="",
    category=None,
    **kwargs,
):
    """One pickable a choice offers; ``effects`` are (scope, effect) pairs.

    Everything the pickable *means* rides it as ordinary modifiers — an
    equipment list opened, a subtype granted, a further choice given —
    except a linked ``category``, consulted for categorisation
    decisions: a rule placing "the chosen set" reads it to learn which
    category the pick means, which is how a Skill Tree pick stands for
    the set it names.
    """
    from n26.library.models import Pickable

    pickable = Pickable.objects.create(
        name=name,
        slot_type=slot_type,
        qualifier=qualifier,
        library_author_help=library_author_help,
        category=category,
        **kwargs,
    )
    for scope, effect in effects:
        modifier(
            name=f"{name}: {effect}", scope=scope, effect=effect, attach_to=pickable
        )
    return pickable


def create_picklist(name, slot_type, members=(), **kwargs):
    """A flat, ordered list of one slot type's pickables.

    ``members`` are pickables, in order, or ``(pickable, "wording")``
    where this list calls one of them something else.
    """
    from n26.library.models import Picklist

    picklist = Picklist.objects.create(name=name, slot_type=slot_type, **kwargs)
    for member in members:
        pickable, label = member if isinstance(member, tuple) else (member, "")
        add_picklist_member(picklist, pickable, label_override=label, **kwargs)
    return picklist


def add_picklist_member(picklist, pickable, label_override="", position=None, **kwargs):
    """One more pickable on a list, at the end unless placed.

    Refused where the pickable belongs to another slot type: a list
    offers one slot type's pickables and a choice reading it has to be
    settleable by every one of them.
    """
    from n26.library.models import PicklistMember

    if pickable.slot_type_id != picklist.slot_type_id:
        raise ValidationError(
            f"{pickable} belongs to {pickable.slot_type}, and {picklist} "
            f"lists {picklist.slot_type} pickables."
        )
    if position is None:
        position = picklist.members.count()
    return PicklistMember.objects.create(
        picklist=picklist,
        pickable=pickable,
        label_override=label_override,
        position=position,
        **kwargs,
    )


def remove_picklist_member(member):
    """Stop offering one pickable on one list.

    The pickable itself stays in the library and on every other list
    that offers it; anyone who already picked it keeps it, because a
    pick is an assignment and this is only what is offered next.
    """
    member.delete()


def create_slot(
    name,
    slot_type,
    picklist,
    label="",
    min_picks=1,
    max_picks=1,
    assigned_to="bearer",
    hidden=False,
    position=0,
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """One named use of a slot type: the choice a card actually asks.

    Assign one — built into a fighter entry, given by something else —
    and the card draws ``label`` (or this slot's name) with what has been
    picked. ``assigned_to="gang"`` is the Leader-picks-for-the-gang
    arrow, and ``hidden=True`` asks nothing while the pick still applies.
    """
    from n26.library.models import Slot

    if picklist.slot_type_id != slot_type.pk:
        raise ValidationError(
            f"{picklist} lists {picklist.slot_type} pickables, and this is a "
            f"{slot_type} choice."
        )
    return Slot.objects.create(
        name=name,
        slot_type=slot_type,
        picklist=picklist,
        label=label,
        min_picks=min_picks,
        max_picks=max_picks,
        assigned_to=assigned_to,
        hidden=hidden,
        position=position,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )


def create_trait(name, annotation="", qualifier="", library_author_help="", **kwargs):
    from n26.library.models import Trait

    return Trait.objects.create(
        name=name,
        annotation=annotation,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )


def create_weapon(
    name,
    profiles=(),
    slots=1,
    statline_type=None,
    price=0,
    trade_point_price=None,
    is_exclusive=False,
    category=None,
    usable_by_profile_types=(),
    usable_by_subtypes=(),
    usable_by_profiles=(),
    usable_by_specialisations=(),
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """A weapon, and optionally its profiles in one go.

    ``profiles`` is an ordered list of ``(name, price)`` or
    ``(name, price, [traits])``. Given any, the first must be free —
    that's the mandatory one every weapon has. Given none, the weapon
    starts bare and profiles are added with ``add_weapon_profile``:
    a weapon mid-authoring is a legitimate state, and the surfaces
    that read one say so rather than refusing to exist.

    The ``usable_by_*`` lists are the bracket the book prints after the
    name — "Wyld bow (Wyld Runner only)" — true of the gun wherever it
    is listed. Empty means everyone; a restriction only one list prints
    belongs on that list's entry instead (``add_entry``).
    """
    from n26.library.models import Weapon

    if profiles and profiles[0][1] != 0:
        raise ValueError("A weapon's first profile is mandatory and free")

    # Extra kwargs (price, category, is_exclusive…) describe the weapon;
    # only the pack is shared with its profile rows.
    shared = {"pack": kwargs["pack"]} if "pack" in kwargs else {}
    weapon = Weapon.objects.create(
        name=name,
        slots=slots,
        statline_type=statline_type,
        price=price,
        trade_point_price=trade_point_price,
        is_exclusive=is_exclusive,
        category=category,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )
    for position, entry in enumerate(profiles):
        profile_name, price, *rest = entry
        add_weapon_profile(
            weapon,
            profile_name,
            price=price,
            traits=rest[0] if rest else (),
            position=position,
            **shared,
        )
    return set_usable_by(
        weapon,
        usable_by_profile_types=usable_by_profile_types,
        usable_by_subtypes=usable_by_subtypes,
        usable_by_profiles=usable_by_profiles,
        usable_by_specialisations=usable_by_specialisations,
    )


def add_weapon_profile(
    weapon,
    name="",
    price=0,
    trade_point_price=None,
    is_exclusive=False,
    annotation=None,
    traits=(),
    position=None,
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """One firing line of a weapon — the gun's own, or a paid ammo type.

    ``name`` is only for a line the book names: leave it blank for the
    weapon's own line, which prints as the weapon. ``annotation``
    defaults to the weapon's name, which is what a named line prints in
    brackets. ``position`` defaults to the end.
    """
    from n26.library.models import WeaponProfile

    if position is None:
        position = weapon.profiles.count()
    profile = WeaponProfile.objects.create(
        name=name,
        annotation=weapon.name if annotation is None else annotation,
        weapon=weapon,
        price=price,
        trade_point_price=trade_point_price,
        is_exclusive=is_exclusive,
        position=position,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )
    if traits:
        profile.traits.set(traits)
    return profile


def create_specialisation(
    name, grants_skill=None, qualifier="", library_author_help="", **kwargs
):
    """A specialisation; optionally wire the skill it grants."""
    from n26.library.models import Specialisation

    specialisation = Specialisation.objects.create(
        name=name,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )
    if grants_skill is not None:
        modifier(
            name=f"{name} grants {grants_skill.name}",
            scope=targets_model(),
            effect=ef_adds(grants_skill),
            attach_to=specialisation,
            **kwargs,
        )
    return specialisation


def create_counter(name, qualifier="", library_author_help="", **kwargs):
    from n26.library.models import Counter

    return Counter.objects.create(
        name=name,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )


def restrict_use(thing, *allowed):
    """Who may use this — ProfileType, Subtype, Profile or Specialisation.

    ``restrict_use(wyld_bow, wyld_runner)`` is "Wyld bow (Wyld Runner
    only)": a whole fighter entry, and a fact about the bow wherever it
    is listed. ``restrict_use(rad_beamer, gunner)`` is "(Gunner
    specialist only)" — the field a Specialist chose.

    ``thing`` may equally be a collection entry, which narrows that one
    list's offer and leaves every other list that names the item alone.
    The four lists are the same shape on both, so this writes either.
    """
    from n26.library.models import Profile, ProfileType, Specialisation, Subtype

    for item in allowed:
        if isinstance(item, ProfileType):
            thing.usable_by_profile_types.add(item)
        elif isinstance(item, Subtype):
            thing.usable_by_subtypes.add(item)
        elif isinstance(item, Profile):
            thing.usable_by_profiles.add(item)
        elif isinstance(item, Specialisation):
            thing.usable_by_specialisations.add(item)
        else:
            raise ValueError(f"{type(item).__name__} cannot restrict use")
    return thing


def set_usable_by(
    thing,
    usable_by_profile_types=None,
    usable_by_subtypes=None,
    usable_by_profiles=None,
    usable_by_specialisations=None,
):
    """Who may use this, replaced — the write ``revise`` refuses.

    Each list handed over is the whole statement about its own arm: what
    it does not name may no longer use this. That is what a form's
    multi-select carries, and what a re-imported sheet means, so the
    decision is stated here once rather than at each writer. ``None``
    says nothing about an arm and leaves it as it was — different from an
    empty list, which opens that arm to everyone.

    ``restrict_use`` is the other half of the pair: it adds one allowed
    thing at a time, which is what building content up line by line
    wants. Both write the same four lists, on an item or on the
    collection entry offering it.
    """
    lists = {
        "usable_by_profile_types": usable_by_profile_types,
        "usable_by_subtypes": usable_by_subtypes,
        "usable_by_profiles": usable_by_profiles,
        "usable_by_specialisations": usable_by_specialisations,
    }
    for name, allowed in lists.items():
        if allowed is not None:
            getattr(thing, name).set(allowed)
    return thing


# --- Default sets and options ----------------------------------------------


def create_default_set(name, members=(), price=0, **kwargs):
    """A set of things a profile can come with. ``members`` are assignables, or
    ``(assignable, {extras})`` — ``(xp, {"amount": 61})`` for a counter's
    opening value."""
    from n26.library.models import DefaultAssignment, DefaultAssignmentSet

    default_set = DefaultAssignmentSet.objects.create(name=name, price=price, **kwargs)
    for position, member in enumerate(members):
        assignable, extras = member if isinstance(member, tuple) else (member, {})
        _refuse_a_bare_pickable(assignable)
        DefaultAssignment.objects.create(
            default_set=default_set,
            assignable=assignable,
            position=position,
            **extras,
            **kwargs,
        )
    return default_set


def _free_set_name(carrier, phrase="built-ins", **shared):
    """A name for a set of this carrier's, ending in ``phrase``, that
    nothing else in the pack has taken.

    The set is named after the thing that comes with it, so an author
    reading a list of sets can tell whose is whose. But a name is not an
    identity: an exotic beast is both a piece of wargear a gang buys and
    the model that arrives when it does, and both are called the same
    thing — while a set name may appear only once in a pack. So the kind
    goes in when the plain name is spoken for, and a number after that.

    ``phrase`` says which of the carrier's sets this is: the things it
    always comes with, or the wording of one alternative it offers. Both
    are read by authors alone, which is what lets a name grow a kind and
    a number without anybody minding.
    """
    from itertools import chain, count

    from n26.library.models import DefaultAssignmentSet
    from n26.library.models.pack import default_pack_id

    label = getattr(carrier, "authoring_label", None) or str(carrier)
    kind = carrier._meta.verbose_name
    pack = shared.get("pack") or default_pack_id()
    taken = DefaultAssignmentSet.objects.filter(pack=pack)

    # Chained rather than collected: the numbered names never run out,
    # and a tuple of them would never finish being built.
    tries = chain(
        (f"{label} {phrase}", f"{label} ({kind}) {phrase}"),
        (f"{label} ({kind}) {phrase} {number}" for number in count(2)),
    )
    return next(name for name in tries if not taken.filter(name__iexact=name).exists())


def add_built_in(
    carrier, thing, amount=0, default_pickable=None, position=None, **kwargs
):
    """Something ``carrier`` always comes with, materialised when it is
    acquired — a profile's equipment list, its starting kit, its
    opening XP. Founds the carrier's built-ins set on first use, so an
    author never makes the set by hand.

    A **slot** built in is a choice the thing arrives asking;
    ``default_pickable`` is the answer it arrives with, changed
    afterwards by the ordinary rechoose.

    Refused for a kind that only ever arrives by being *chosen*: nothing
    acquires one, so nothing would ever hand the items over.
    """
    from n26.library.models import DefaultAssignmentSet

    _refuse_a_bare_pickable(thing)
    if not getattr(carrier, "takes_built_ins", True):
        raise ValidationError(
            f"A {carrier._meta.verbose_name} is chosen rather than acquired, "
            f"so nothing would ever hand over items built into it. What a "
            f"chosen thing brings rides it as modifiers instead — gives, "
            f"brings a model, moves a counter."
        )
    if carrier.built_ins is None:
        shared = {"pack": kwargs["pack"]} if "pack" in kwargs else {}
        carrier.built_ins = DefaultAssignmentSet.objects.create(
            name=_free_set_name(carrier, **shared), **shared
        )
        carrier.save()
    return add_default_member(
        carrier.built_ins,
        thing,
        amount=amount,
        default_pickable=default_pickable,
        position=position,
        **kwargs,
    )


def _refuse_a_bare_pickable(thing):
    """A pickable built into something, with no slot behind it, in words.

    It would sit in the library unread: a pick's slot is what puts it on
    a card and what gives it its meaning.
    """
    from n26.library.models import Pickable

    if isinstance(thing, Pickable):
        raise ValidationError(
            "A pickable without its slot shows nothing and does nothing. "
            "Build in the slot, or a slot-with-default."
        )


def add_default_member(
    default_set, thing, amount=0, default_pickable=None, position=None, **kwargs
):
    """One more thing in a set of defaults, at the end unless placed.

    The set is named rather than the carrier, which is what a re-import
    of a fighter whose sheet has grown a rule needs: the set is already
    there and only the new member is missing.

    ``default_pickable`` is a slot member's starting pick, and belongs to
    nothing else.
    """
    from n26.library.models import DefaultAssignment

    _refuse_a_bare_pickable(thing)
    if position is None:
        position = default_set.members.filter(archived=False).count()
    member = DefaultAssignment(
        default_set=default_set,
        assignable=thing,
        amount=amount,
        default_pickable=default_pickable,
        position=position,
        **kwargs,
    )
    if default_pickable is not None:
        # A starting pick has to belong to the slot beside it, and only
        # this row knows both — the database cannot say it.
        member.clean()
    member.save()
    return member


def remove_default_member(member):
    """Take one thing back out of a set of defaults.

    Only the membership goes, and it is archived rather than deleted:
    every copy it materialised names it as its provenance, so the row
    must survive for those copies' sake. The thing named — the weapon,
    the skill, the equipment list — stays in the library untouched, and
    so does the set, even when this was its last member: a carrier that
    comes with nothing still has somewhere to put the next thing.

    Ammo lines go with their gun (``dependent_members``), because a
    weapon profile left behind names a weapon nothing brings.

    What has already been acquired keeps it: built-ins are materialised
    when a carrier is acquired, and nothing retracts an assignment. This
    changes what future acquisitions come with.
    """
    for dependent in member.dependent_members:
        dependent.archive()
    member.archive()


def offer_option(
    carrier,
    name,
    price=0,
    thing=None,
    amount=0,
    default_pickable=None,
    group=None,
    position=None,
    default_set=None,
    **kwargs,
):
    """Add an alternative offered when ``carrier`` is acquired.

    ``carrier`` is a profile (offered at hire) or a wargear (offered when
    bought). ``name`` is what a player is offered — "with razor-sharp
    talons" — and ``price`` what taking it adds.

    Founds the set of things this brings on first use, so an author
    never makes the set by hand: pass ``thing`` for what it brings, and
    add any others to the same set afterwards. The set's own name is
    derived and read by authors alone, because set names are unique
    across a pack while two profiles may perfectly well both offer "As
    standard". Pass ``default_set`` to offer kit that already exists,
    and the set's own price stands.

    Omit ``group`` for the carrier's main pick-one set; pass one for a
    further set (``create_option_group``). New options go to the end of
    whichever set they join, so the first one an author adds to a
    pick-one set is the one taken unasked.

    ``amount`` and ``default_pickable`` are what the thing being brought
    asks for where it asks for anything — a counter's opening value, a
    slot's starting pick — and reach the member rather than the option.
    """
    from n26.library.models import Option

    if default_set is None:
        default_set = create_default_set(
            _free_set_name(carrier, phrase=name, **kwargs), price=price, **kwargs
        )
    if position is None:
        position = carrier.options.filter(group=group).count()
    option = Option.objects.create(
        assignable=carrier,
        name=name,
        default_set=default_set,
        position=position,
        group=group,
        **kwargs,
    )
    if thing is not None:
        add_default_member(
            default_set,
            thing,
            amount=amount,
            default_pickable=default_pickable,
            **kwargs,
        )
    return option


def stop_offering(option):
    """Take one alternative back off what a carrier offers.

    The set of things it brought goes with it when nothing else holds
    it: a set founded for one option is that option, and left behind it
    is a bag nothing can reach. A set shared with something else stays,
    and so does everything it names — a weapon offered as an option is
    still a weapon.

    What has already been acquired keeps it. An option is materialised
    at the moment of hiring, and nothing retracts an assignment; this
    changes what future acquisitions may choose.
    """
    from django.db.models import ProtectedError

    default_set = option.default_set
    option.delete()
    try:
        default_set.delete()
    except ProtectedError:
        # Everything that can hold a set holds it under protection, so
        # the refusal is the answer: another option offers the same kit,
        # or something always comes with it. Asking each kind in turn
        # would be the same question with a list to keep up to date.
        pass


def create_option_group(carrier, name, choose="one", position=None, **kwargs):
    """A further set of options — ``choose`` is "one" or "any".

    The name is the author's alone; a player is shown the options and
    never the set's label. New sets go after the ones already there.
    """
    from n26.library.models import OptionGroup

    if position is None:
        position = carrier.option_groups.count()
    return OptionGroup.objects.create(
        assignable=carrier, name=name, choose=choose, position=position, **kwargs
    )


def remove_option_group(group):
    """Take a set of options off a carrier, and the options in it.

    The options go with their set, which is what makes them
    alternatives to each other; loose in the main pick they would
    compete with the standard loadout instead, which is a different
    offer from the one the author wrote.
    """
    for option in list(group.options.all()):
        stop_offering(option)
    group.delete()


# --- Collections -----------------------------------------------------------


def create_section(name, position=0, **kwargs):
    """One heading of the taxonomy — the level above categories."""
    from n26.library.models import Section

    return Section.objects.create(name=name, position=position, **kwargs)


def create_category(section, name, position=0, **kwargs):
    """A category under its heading. ``section`` is a Section row, or a
    name — named headings are found or founded, so the example suites
    keep reading ``create_category("Skills", "Combat")``."""
    from n26.library.models import Category, Section

    if not isinstance(section, Section):
        shared = {"pack": kwargs["pack"]} if "pack" in kwargs else {}
        section, _ = Section.objects.get_or_create(name=section, **shared)
    return Category.objects.create(
        section=section, name=name, position=position, **kwargs
    )


def section_of(collection, name, position, is_default=False, **kwargs):
    """One of a collection's own sections —
    ``section_of(skills, "Primary", 0)``."""
    from n26.library.models import CollectionSection

    return CollectionSection.objects.create(
        collection=collection,
        name=name,
        position=position,
        is_default=is_default,
        **kwargs,
    )


def create_collection(
    name,
    entries=(),
    contains=(),
    prices_its_entries=True,
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """A collection. ``entries`` are assignables, or
    ``(assignable, {overrides})`` pairs for priced ones; ``contains``
    are selector sweeps — model classes, or ``(model, category)`` to
    narrow."""
    from n26.library.models import Collection, CollectionEntry, CollectionSelector

    # Extra kwargs describe the collection; only the
    # pack is shared with its rows.
    shared = {"pack": kwargs["pack"]} if "pack" in kwargs else {}
    collection = Collection.objects.create(
        name=name,
        prices_its_entries=prices_its_entries,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )
    for position, sweep in enumerate(contains):
        model, category = sweep if isinstance(sweep, tuple) else (sweep, None)
        CollectionSelector.of(
            collection, model, category=category, position=position, **shared
        )
    for position, item in enumerate(entries):
        thing, overrides = item if isinstance(item, tuple) else (item, {})
        CollectionEntry.objects.create(
            collection=collection,
            assignable=thing,
            position=position,
            **overrides,
            **shared,
        )
    return collection


def delete_content(row):
    """Take an authored row out of the library for good.

    The database refuses wherever anything still points at it — an
    assignment on somebody's gang, a collection entry, an option's kit
    — because every such reference protects its target: content that
    has been used is history, not clutter. The caller turns that
    refusal into words. Reusable modifiers attached to the row survive
    it — they may be carried elsewhere, so they are not this row's to
    take.
    """
    row.delete()


def add_entry(
    collection,
    thing,
    price_override=None,
    trade_point_override=None,
    usable_by_profile_types=(),
    usable_by_subtypes=(),
    usable_by_profiles=(),
    usable_by_specialisations=(),
    position=None,
    **kwargs,
):
    """One more item a collection lists — the curated entry.

    The overrides are what an entry may state; left blank, the item
    is priced at its own reference. New entries go to the end.

    The ``usable_by_*`` lists narrow who this list offers the item to —
    a Goliath list's "Heavy rock saw (Forge-born only)", where two other
    gangs list the same saw plainly. Empty offers it to everyone, and
    whatever the item itself restricts still holds. ``restrict_use``
    writes the same lists an item at a time, on an entry as on an item.
    """
    from n26.library.models import CollectionEntry

    if position is None:
        position = collection.entries.count()
    entry = CollectionEntry.objects.create(
        collection=collection,
        assignable=thing,
        price_override=price_override,
        trade_point_override=trade_point_override,
        position=position,
        **kwargs,
    )
    narrowing = {
        "usable_by_profile_types": usable_by_profile_types,
        "usable_by_subtypes": usable_by_subtypes,
        "usable_by_profiles": usable_by_profiles,
        "usable_by_specialisations": usable_by_specialisations,
    }
    for name, allowed in narrowing.items():
        if allowed:
            getattr(entry, name).set(allowed)
    return entry


def remove_entry(entry):
    """Stop listing one item. The thing named stays in the library and
    on every other list that names it — only this collection's entry
    goes."""
    entry.delete()


def add_section(collection, name, is_default=False, position=None, **kwargs):
    """One more section of a collection's own — "Primary", "Affiliations".

    New sections go after the ones already there; ``is_default`` marks
    where unplaced categories fall, at most one per collection.
    """
    if position is None:
        position = collection.sections.count()
    return section_of(collection, name, position, is_default=is_default, **kwargs)


def create_trading_post(name="Trading Post", contains=None, entries=(), **kwargs):
    """A collection whose membership is *having a trade point price*:
    every weapon and wargear with a TP set, swept in — never listed by
    hand — plus entries for anything it prices its own way. Nothing
    here is about charging: browse it with ``browse(post, TRADING_POST)``
    and the *terms* charge Trade Points."""
    from n26.library.models import CollectionSelector

    shared = {"pack": kwargs["pack"]} if "pack" in kwargs else {}
    collection = create_collection(name, entries=entries, **kwargs)
    if contains is None:
        # What the post sells is standard content's to say, so a bare
        # call builds the real one rather than a subset that quietly
        # leaves a kind out of the post.
        from n26.library.standard_content import trading_post_sweeps

        contains = trading_post_sweeps()
    sweeps = contains
    for position, sweep in enumerate(sweeps):
        model, category = sweep if isinstance(sweep, tuple) else (sweep, None)
        CollectionSelector.of(
            collection,
            model,
            category=category,
            position=position,
            with_trade_point_price=True,
            **shared,
        )
    return collection


# --- Conditions: how a scope narrows ---------------------------------------
#
# Condition verbs return unsaved rows; the scope verb they nest inside
# saves them against the scope it creates. A new way of narrowing is a
# new condition model plus a verb here — the scope verbs don't change.


def has_subtypes(*subtypes, negate=False):
    """Condition: the model has one of these subtypes — any-of within
    the row. ``targets_model(has_subtypes(leader, champion))``.

    ``negate=True`` reads the row the other way: every model *except*
    these, which is how the books scope as often as by inclusion."""
    from n26.library.models import HasSubtypes

    condition = HasSubtypes(negate=negate)
    condition._pending_m2m = {"subtypes": subtypes}
    return condition


def is_profile(*profiles, negate=False):
    """Condition: the model is one of these profiles, named outright —
    ``targets_model(is_profile(champion))``, or several for any-of.
    ``negate=True`` reaches every entry except these."""
    from n26.library.models import IsProfile

    condition = IsProfile(negate=negate)
    condition._pending_m2m = {"profiles": profiles}
    return condition


def has_pickable(*pickables, negate=False):
    """Condition: the model has one of these picked —
    ``targets_model(has_pickable(cawdor))`` for "models with the Cawdor
    legacy". ``negate=True`` reaches everyone who picked something else.

    One condition serving every slot type ever authored: what was
    picked is an ordinary possession."""
    from n26.library.models import HasPickable

    condition = HasPickable(negate=negate)
    condition._pending_m2m = {"pickables": pickables}
    return condition


def counter_at_least(counter, at_least):
    """Condition: the model's counter has reached this value —
    ``targets_model(counter_at_least(xp, 75))``."""
    from n26.library.models import CounterAtLeast

    return CounterAtLeast(counter=counter, at_least=at_least)


def _weapon_conditions():
    """The condition kinds that narrow weapons rather than models."""
    from n26.library.models import HasTraits, InCategories, IsOneOf

    return (HasTraits, InCategories, IsOneOf)


def has_traits(*traits):
    """Condition: only weapons carrying one of these traits —
    ``targets_weapons(has_traits(melee))``, or several for any-of."""
    from n26.library.models import HasTraits

    condition = HasTraits()
    condition._pending_m2m = {"traits": traits}
    return condition


def in_categories(*categories):
    """Condition: only weapons homed in one of these categories —
    ``targets_weapons(in_categories(las_weapons))`` for "all Las weapons"."""
    from n26.library.models import InCategories

    condition = InCategories()
    condition._pending_m2m = {"categories": categories}
    return condition


def is_one_of(*weapons):
    """Condition: only these weapons, named outright —
    ``targets_weapons(is_one_of(helamite_claws))``.

    For a rule about a particular gun, where no trait or category picks
    it out: the Dustback Helamite's claws gain a trait, and nothing
    else the fighter carries does.
    """
    from n26.library.models import IsOneOf

    condition = IsOneOf()
    condition._pending_m2m = {"weapons": weapons}
    return condition


def _attach_condition(condition, scope):
    condition.scope = scope
    condition.save()
    for field, values in getattr(condition, "_pending_m2m", {}).items():
        getattr(condition, field).set(values)


# --- Scopes: who a modifier reaches -----------------------------------------


def targets_model(*conditions):
    """The model carrying it — only the model the carrier is directly
    assigned to, narrowed by nested conditions —
    ``targets_model(has_subtypes(leader), counter_at_least(xp, 5))``.

    Never reached through the gang's broadcast: an archetype assigned to
    a Champion applies to that Champion alone. For everyone in the gang,
    use ``targets_every_model``.
    """
    from n26.library.models import TargetsMiniature

    return _model_scope(TargetsMiniature.Reach.BEARER, conditions)


def targets_every_model(*conditions):
    """All models in the gang, however the carrier is held, narrowed by
    the same nested conditions — ``targets_every_model(has_subtypes(x))``.

    The reach a thing the gang holds has: a chosen alliance, a founding
    rule. Compute is per card, so a fighter-held carrier's modifiers are
    seen only where that carrier is — the gang-held carrier is the case
    this is for.
    """
    from n26.library.models import TargetsMiniature

    return _model_scope(TargetsMiniature.Reach.EVERY_MODEL, conditions)


def _model_scope(reach, conditions):
    from n26.library.models import TargetsMiniature

    scope = TargetsMiniature.objects.create(reach=reach)
    for condition in conditions:
        if isinstance(condition, _weapon_conditions()):
            raise ValueError(
                f"{type(condition).__name__} narrows weapons — use targets_weapons"
            )
        _attach_condition(condition, scope)
    return scope


def targets_weapons(*conditions):
    """The bearer's weapons, narrowed by nested conditions —
    ``targets_weapons(has_traits(melee))`` for "your Melee weapons",
    ``targets_weapons(in_categories(las))`` for "all Las weapons",
    ``targets_weapons(is_one_of(claws))`` for one named gun.

    Given several conditions, a weapon must satisfy all of them; given
    several values in one condition, any of them will do.
    """
    from n26.library.models import TargetsWeapons

    scope = TargetsWeapons.objects.create()
    for condition in conditions:
        if not isinstance(condition, _weapon_conditions()):
            raise ValueError(f"targets_weapons cannot take {condition!r}")
        _attach_condition(condition, scope)
    return scope


def targets_attached_weapon():
    """The one weapon the carrier is bolted to — a telescopic sight."""
    from n26.library.models import TargetsAttachedWeapon

    return TargetsAttachedWeapon.objects.create()


def targets_gang():
    """The gang carrying it and all models: affects the gang and all
    models, in a different way per effect.

    Deprecated on the composer — kept for existing content. Prefer
    assigning a hidden item to the gang that carries ``targets_every_model``
    modifiers, which says the same thing legibly."""
    from n26.library.models import TargetsGang

    return TargetsGang.objects.create()


def targets_gang_alone():
    """The gang carrying it: applied only to the gang, and what it gives
    the gang does not reach the models."""
    from n26.library.models import TargetsGang

    return TargetsGang.objects.create(echoes=False)


# --- Effects: what a modifier does (ef_ at read, op_ at purchase) -----------


def ef_adds(thing):
    """Grants the target a subtype, skill, trait, collection, rule, weapon
    — or a further choice, which is how one pick opens the next.

    A granted weapon is free kit: it arrives with its free firing lines,
    adds nothing to the gang's rating, and goes when its granter goes.

    **A granted weapon arrives too late for its carrier's unfiltered
    rules.** Scopes are asked in order of how conditional they are, so a
    narrow rule sees what a broad one did — and a scope with no
    conditions is asked at the same time as the grant, which means
    before it. A carrier that hands over a weapon and also says "all my
    bearer's weapons gain this" arms every weapon except the one it just
    handed over. Name the weapon (``targets_weapons(is_one_of(…))``) and
    the rule is asked afterwards, of a card the weapon is already on.
    """
    from n26.library.models import AddsAssignable

    return AddsAssignable.objects.create(**_assignable_kwarg(thing))


def ef_removes(thing):
    """Takes one away, computed — Death of a Leader."""
    from n26.library.models import RemovesAssignable

    return RemovesAssignable.objects.create(**_assignable_kwarg(thing))


def ef_changes_stat(stat, mode="worsen", amount=1):
    """Shifts or sets one characteristic."""
    from n26.library.models import ChangesStat

    return ChangesStat.objects.create(stat=stat, mode=mode, amount=amount)


def ef_offers_choice(model, from_section=None, label="", will_be_assigned_to="bearer"):
    """Puts an open question on the bearer's card —
    ``ef_offers_choice(Skill, from_section=primary)`` for "a skill from a
    set that is Primary for this fighter".
    ``will_be_assigned_to="gang"`` is the Leader-picks-for-the-gang arrow."""
    from n26.library.models import OffersChoice

    return OffersChoice.of(
        model,
        from_section=from_section,
        label=label,
        will_be_assigned_to=will_be_assigned_to,
    )


def ef_changes_category(category):
    """The bearer sorts under this category's heading on the gang sheet —
    ``ef_changes_category(leaders)`` for a fighter selected as Leader."""
    from n26.library.models import ChangesCategory

    return ChangesCategory.objects.create(category=category)


def ef_places(category, section):
    """For the bearer, that set sits under this section of its
    collection — ``ef_places(powers, skills_primary)``."""
    from n26.library.models import PlacesCategory

    return PlacesCategory.objects.create(category=category, section=section)


def ef_places_choice(section):
    """The carrier-relative placement: whatever set the carrier's chosen
    thing is homed in sits under this collection section — a Venator
    rank slot."""
    from n26.library.models import PlacesCategory

    return PlacesCategory.objects.create(the_chosen=True, section=section)


def ef_requires_companions(for_each, at_least, of):
    """A composition ask, said on the gang sheet and never enforced —
    ``ef_requires_companions(champion, 3, hive_scum)``."""
    from n26.library.models import RequiresCompanions

    return RequiresCompanions.objects.create(
        for_each=for_each, at_least=at_least, of=of
    )


def ef_allows_at_most(at_most, thing):
    """A ceiling, said on the sheet and never enforced —
    ``ef_allows_at_most(2, aberrant)``, and ``ef_allows_at_most(0, brute)``
    for a ban. Aimed at the gang it counts the roster; aimed at a model it
    counts that model's own assignments."""
    from n26.library.models import AllowsAtMost

    return AllowsAtMost.objects.create(at_most=at_most, **_countable_kwarg(thing))


def op_adds_model(profile):
    """A stored effect: assigning the carrier brings this model into the gang."""
    from n26.library.models import OpAddsMiniature

    return OpAddsMiniature.objects.create(profile=profile)


def op_changes_counter(counter, mode="set", amount=0):
    """A stored effect: assigning the carrier moves the bearer's counter,
    through the ledger — ``op_changes_counter(xp, "set", 61)`` for a
    selection whose sheet says it starts with 61 XP."""
    from n26.library.models import OpChangesCounter

    return OpChangesCounter.objects.create(counter=counter, mode=mode, amount=amount)


def _assignable_kwarg(thing):
    from n26.library.models import (
        Collection,
        Hidden,
        Power,
        Rule,
        Skill,
        Slot,
        Subtype,
        Trait,
        Weapon,
    )

    kinds = (
        (Subtype, "subtype"),
        (Skill, "skill"),
        (Trait, "trait"),
        (Collection, "collection"),
        (Rule, "rule"),
        (Power, "power"),
        (Weapon, "weapon"),
        (Hidden, "hidden"),
        (Slot, "slot"),
    )
    for model, name in kinds:
        if isinstance(thing, model):
            return {name: thing}
    raise ValueError(f"{type(thing).__name__} cannot be added or removed")


def _countable_kwarg(thing):
    from n26.library.models import Profile, Subtype, Wargear

    kinds = ((Subtype, "subtype"), (Profile, "profile"), (Wargear, "wargear"))
    for model, name in kinds:
        if isinstance(thing, model):
            return {name: thing}
    raise ValueError(f"{type(thing).__name__} cannot be counted")


# --- Glue -------------------------------------------------------------------


def _parts(scope, effect):
    """Which of a modifier's columns these two parts fill.

    The column a part goes in is the part's own kind, so the pairing is
    read off the class name rather than declared — a new scope or
    effect model is a column and nothing here.
    """
    from n26.library.models.modifier import EFFECT_FIELDS, SCOPE_FIELDS

    fields = {}
    for field_name in (*SCOPE_FIELDS, *EFFECT_FIELDS):
        for candidate in (scope, effect):
            if type(candidate).__name__.lower() == field_name.replace("_", ""):
                fields[field_name] = candidate
    return fields


def modifier(name, scope, effect, attach_to=None, **kwargs):
    """One scope plus one effect; optionally hung on an assignable."""
    from n26.library.models import Modifier

    row = Modifier.objects.create(name=name, **_parts(scope, effect), **kwargs)
    if attach_to is not None:
        attach_to.modifiers.add(row)
    return row


def recompose_modifier(row, name, scope, effect):
    """Say something else with a modifier that already exists.

    The new parts are built by the same verbs that build a new
    modifier's, and the old ones are dropped once nothing points at
    them. Written that way because a scope's narrowing is condition
    rows: changing it is a different set of rows, which no write to a
    column can express.

    Order is load-bearing. A modifier's columns *cascade from* its
    parts — deleting a scope deletes the modifier holding it — so the
    old parts may only go after the modifier points at the new ones.

    The kinds do not change: the caller passes a scope and an effect of
    the kinds already there, and a modifier reaching something else is
    a different modifier. The row keeps its identity, so every carrier
    holding it says the new sentence with nothing re-attached.
    """
    old_scope, old_effect = row.scope, row.effect
    parts = _parts(scope, effect)
    was = _parts(old_scope, old_effect)
    if set(parts) != set(was):
        raise ValueError(
            f"{row.name} is {', '.join(sorted(was))} and cannot be recomposed "
            f"as {', '.join(sorted(parts))} — delete it and compose the other."
        )
    revise(row, name=name, **parts)
    # The conditions go with the scope, which the database does.
    old_scope.delete()
    old_effect.delete()
    return row


def delete_modifier(row):
    """Remove a modifier, and the rows it is made of, from everywhere.

    Every carrier loses the behaviour: the many-to-many rows go with
    the modifier. Its scope and effect go too — the modifier holds the
    only reference to either, so leaving them would leave rows nothing
    can reach — and the scope takes its condition rows with it.
    """
    scope, effect = row.scope, row.effect
    row.delete()
    scope.delete()
    effect.delete()


def attach_modifiers_to(assignable, modifiers):
    """Hang already-built (reusable) modifiers on a further carrier."""
    assignable.modifiers.add(*modifiers)
    return assignable


def detach_modifier(assignable, modifier):
    """Take a modifier off one carrier. The modifier itself survives —
    it may hang on other carriers, or wait as a reusable."""
    assignable.modifiers.remove(modifier)
    return assignable
