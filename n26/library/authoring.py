"""Authoring verbs — the one vocabulary for building library content.

These verbs are the authoring API, and the admin's forms compile to
exactly these calls — a form that can't be expressed as a verb here
can't exist, and a verb here is what a spec describes
(design/authoring.md).

The grammar (design/authoring-build-plan.md):

* **Scopes** say who a modifier reaches, and take nested **conditions**::

      targets_model(has_subtypes(leader, champion))
      targets_model(counter_at_least(xp, 75))
      targets_weapons(has_trait(melee))

* **Effects** carry a prefix saying *when they happen*: ``ef_`` is
  worked out at read time, ``op_`` writes rows at purchase time.

* **Glue**: ``modifier(name, scope, effect, attach_to=…)`` builds one
  rule; ``attach_modifiers_to(assignable, modifiers)`` hangs reusable
  rules on further carriers.

Everything is pack-aware: omit ``pack`` and it lands in the default
pack, exactly as admin ingestion would. Nothing here stores rules text —
see CLAUDE.md.
"""

import re
from dataclasses import dataclass

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
    qualifier="",
    library_author_help="",
    **kwargs,
):
    return GangType.objects.create(
        name=name,
        starting_credits=starting_credits,
        icon_url=icon_url,
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
    is_highlighted=False,
    is_first_of_group=False,
    **kwargs,
):
    """Put one characteristic in a shape, at the end unless placed."""
    if position is None:
        position = statline_type.stats.count()
    return StatlineTypeStat.objects.create(
        statline_type=statline_type,
        stat=stat,
        position=position,
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
    ``set_statline``), because replacing a set is a decision — what
    happens to a member the new value does not name — and ``setattr``
    has no way to express one.
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
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """Equipment a model carries. A thing that bolts onto a weapon is a
    weapon accessory, not this."""
    from n26.library.models import Wargear

    return Wargear.objects.create(
        name=name,
        price=price,
        trade_point_price=trade_point_price,
        is_exclusive=is_exclusive,
        category=category,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )


def create_weapon_accessory(
    name,
    price=0,
    trade_point_price=None,
    is_exclusive=False,
    category=None,
    fits_category=None,
    fits_asterisked=False,
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """Something bolted onto a weapon, with the bracket saying what it
    fits — ``fits_category`` for "(Las Weapons Only)",
    ``fits_asterisked`` for "(Weapons Marked With * Only)"."""
    from n26.library.models import WeaponAccessory

    return WeaponAccessory.objects.create(
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
    )


def create_subtype(name, qualifier="", library_author_help="", **kwargs):
    from n26.library.models import Subtype

    return Subtype.objects.create(
        name=name,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )


def create_skill(name, category=None, qualifier="", library_author_help="", **kwargs):
    """A skill, homed in its set — ``create_skill("Catfall", agility)``."""
    from n26.library.models import Skill

    return Skill.objects.create(
        name=name,
        category=category,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
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
    name, annotation="", category=None, qualifier="", library_author_help="", **kwargs
):
    """A Wyrd power — ``create_power("Force Blast", "(Free), Continuous")``."""
    from n26.library.models import Power

    return Power.objects.create(
        name=name,
        annotation=annotation,
        category=category,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
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
    """An invisible effect carrier; ``effects`` are (scope, effect) pairs."""
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
    return weapon


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
    only)": a whole fighter entry, which is how a shared house list
    narrows a few of its lines. ``restrict_use(rad_beamer, gunner)`` is
    "(Gunner specialist only)" — the field a Specialist chose.
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


# --- Default sets and options ----------------------------------------------


def create_default_set(name, members=(), price=0, **kwargs):
    """A set of things a profile can come with. ``members`` are assignables, or
    ``(assignable, {extras})`` — ``(xp, {"amount": 61})`` for a counter's
    opening value."""
    from n26.library.models import DefaultAssignment, DefaultAssignmentSet

    default_set = DefaultAssignmentSet.objects.create(name=name, price=price, **kwargs)
    for position, member in enumerate(members):
        assignable, extras = member if isinstance(member, tuple) else (member, {})
        DefaultAssignment.objects.create(
            default_set=default_set,
            assignable=assignable,
            position=position,
            **extras,
            **kwargs,
        )
    return default_set


def add_built_in(carrier, thing, amount=0, position=None, **kwargs):
    """Something ``carrier`` always comes with, materialised when it is
    acquired — a profile's equipment list, its starting kit, its
    opening XP. Founds the carrier's built-ins set on first use, so an
    author never makes the set by hand."""
    from n26.library.models import DefaultAssignmentSet

    if carrier.built_ins is None:
        shared = {"pack": kwargs["pack"]} if "pack" in kwargs else {}
        label = getattr(carrier, "authoring_label", None) or str(carrier)
        carrier.built_ins = DefaultAssignmentSet.objects.create(
            name=f"{label} built-ins", **shared
        )
        carrier.save()
    return add_default_member(
        carrier.built_ins, thing, amount=amount, position=position, **kwargs
    )


def add_default_member(default_set, thing, amount=0, position=None, **kwargs):
    """One more thing in a set of defaults, at the end unless placed.

    The set is named rather than the carrier, which is what a re-import
    of a fighter whose sheet has grown a rule needs: the set is already
    there and only the new member is missing.
    """
    from n26.library.models import DefaultAssignment

    if position is None:
        position = default_set.members.count()
    return DefaultAssignment.objects.create(
        default_set=default_set,
        assignable=thing,
        amount=amount,
        position=position,
        **kwargs,
    )


def remove_default_member(member):
    """Take one thing back out of a set of defaults.

    Only the membership goes. The thing named — the weapon, the skill,
    the equipment list — stays in the library untouched, and so does
    the set, even when this was its last member: a carrier that comes
    with nothing still has somewhere to put the next thing.

    Ammo lines go with their gun (``dependent_members``), because a
    weapon profile left behind names a weapon nothing brings.

    What has already been acquired keeps it: built-ins are materialised
    when a carrier is acquired, and nothing retracts an assignment. This
    changes what future acquisitions come with.
    """
    for dependent in member.dependent_members:
        dependent.delete()
    member.delete()


def offer_option(carrier, default_set, position=0, group=None, **kwargs):
    """Add an alternative offered when ``carrier`` is acquired.

    ``carrier`` is a profile (offered at hire) or a wargear (offered when
    bought). Omit ``group`` for the carrier's default one-of axis; pass
    one for a further axis (``create_option_group``).
    """
    from n26.library.models import Option

    return Option.objects.create(
        assignable=carrier,
        default_set=default_set,
        position=position,
        group=group,
        **kwargs,
    )


def create_option_group(carrier, name, choose="one", position=0, **kwargs):
    """A further axis of choice — ``choose`` is "one" or "any"."""
    from n26.library.models import OptionGroup

    return OptionGroup.objects.create(
        assignable=carrier, name=name, choose=choose, position=position, **kwargs
    )


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
    """One tier of a collection's schema — ``section_of(skills, "Primary", 0)``."""
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
        # leaves a kind off the shelf.
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


def has_subtypes(*subtypes):
    """Condition: the model has one of these subtypes — any-of within
    the row. ``targets_model(has_subtypes(leader, champion))``."""
    from n26.library.models import HasSubtypes

    condition = HasSubtypes()
    condition._pending_m2m = {"subtypes": subtypes}
    return condition


def counter_at_least(counter, at_least):
    """Condition: the model's counter has reached this value —
    ``targets_model(counter_at_least(xp, 75))``."""
    from n26.library.models import CounterAtLeast

    return CounterAtLeast(counter=counter, at_least=at_least)


@dataclass(frozen=True)
class _HasTrait:
    """Condition: the weapon carries this trait.

    Not (yet) a stored row: ``TargetsWeapons`` keeps its ``with_trait``
    column until a second weapon condition forces the rows shape, so
    this is a marker the scope verb folds into the column. The verb
    grammar is already the final one.
    """

    trait: object


def has_trait(trait):
    """Condition: only weapons carrying this trait —
    ``targets_weapons(has_trait(melee))``."""
    return _HasTrait(trait)


def _attach_condition(condition, scope):
    condition.scope = scope
    condition.save()
    for field, values in getattr(condition, "_pending_m2m", {}).items():
        getattr(condition, field).set(values)


# --- Scopes: who a modifier reaches -----------------------------------------


def targets_model(*conditions, when_directly_assigned=False):
    """The carrier's model, narrowed by nested conditions —
    ``targets_model(has_subtypes(leader), counter_at_least(xp, 5))``.

    ``when_directly_assigned`` limits the scope to the model the carrier
    is directly assigned to, never reached through the gang's broadcast —
    an archetype's Champion row applies to a Champion who picked it.
    """
    from n26.library.models import TargetsMiniature

    scope = TargetsMiniature.objects.create(
        when_directly_assigned=when_directly_assigned
    )
    for condition in conditions:
        if isinstance(condition, _HasTrait):
            raise ValueError("has_trait narrows weapons — use targets_weapons")
        _attach_condition(condition, scope)
    return scope


def targets_weapons(*conditions):
    """The bearer's weapons, narrowed by nested conditions —
    ``targets_weapons(has_trait(melee))`` for "your Melee weapons"."""
    from n26.library.models import TargetsWeapons

    trait = None
    for condition in conditions:
        if not isinstance(condition, _HasTrait):
            raise ValueError(f"targets_weapons cannot take {condition!r}")
        if trait is not None:
            raise ValueError("targets_weapons takes at most one has_trait")
        trait = condition.trait
    return TargetsWeapons.objects.create(with_trait=trait)


def targets_attached_weapon():
    """The one weapon the carrier is bolted to — a telescopic sight."""
    from n26.library.models import TargetsAttachedWeapon

    return TargetsAttachedWeapon.objects.create()


def targets_gang():
    """The gang carrying the assignable — the gang itself, not its members."""
    from n26.library.models import TargetsGang

    return TargetsGang.objects.create()


# --- Effects: what a modifier does (ef_ at read, op_ at purchase) -----------


def ef_adds(thing):
    """Grants the target a subtype, skill, trait, collection or rule."""
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


def ef_offers_choice(model, from_section=None, label="", answer_host="bearer"):
    """Puts an open question on the bearer's card —
    ``ef_offers_choice(Skill, from_section=primary)`` for "a skill from a
    set that is Primary for this fighter".
    ``answer_host="gang"`` is the Leader-picks-for-the-gang arrow."""
    from n26.library.models import OffersChoice

    return OffersChoice.of(
        model, from_section=from_section, label=label, answer_host=answer_host
    )


def ef_places(category, section):
    """For the bearer, that set sits under this tier of the section's
    collection — ``ef_places(powers, skills_primary)``."""
    from n26.library.models import PlacesCategory

    return PlacesCategory.objects.create(category=category, section=section)


def ef_places_choice(section):
    """The carrier-relative placement: whatever set the carrier's answered
    choice is homed in sits under this tier — a Venator rank slot."""
    from n26.library.models import PlacesCategory

    return PlacesCategory.objects.create(the_chosen=True, section=section)


def ef_requires_companions(for_each, at_least, of):
    """A composition ask, said on the gang sheet and never enforced —
    ``ef_requires_companions(champion, 3, hive_scum)``."""
    from n26.library.models import RequiresCompanions

    return RequiresCompanions.objects.create(
        for_each=for_each, at_least=at_least, of=of
    )


def op_adds_model(profile):
    """A stored effect: assigning the carrier brings this model into the gang."""
    from n26.library.models import OpAddsMiniature

    return OpAddsMiniature.objects.create(profile=profile)


def _assignable_kwarg(thing):
    from n26.library.models import Collection, Rule, Skill, Subtype, Trait

    kinds = (
        (Subtype, "subtype"),
        (Skill, "skill"),
        (Trait, "trait"),
        (Collection, "collection"),
        (Rule, "rule"),
    )
    for model, name in kinds:
        if isinstance(thing, model):
            return {name: thing}
    raise ValueError(f"{type(thing).__name__} cannot be added or removed")


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
