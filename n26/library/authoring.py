"""Create and update library content through the authoring API.

Specs describe these functions and generated forms call them. Scope functions
accept condition objects; modifiers combine one scope with one effect.
Effects prefixed ``ef_`` are computed when content is read. Effects prefixed
``op_`` write player data when their carrier is acquired.

An omitted pack uses the model's default pack. See design/authoring.md and
design/authoring-build-plan.md for the authoring pipeline.
"""

import re

from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Max

from n26.library.income_choices import preserves_income_choices
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
from n26.write_pause import guarded_write


@guarded_write
def create_pack(name, slug=None, **kwargs):
    """A content pack. Slug defaults to a lowercased, hyphenated name."""
    from n26.library.models import ContentPack

    return ContentPack.objects.create(
        name=name, slug=slug or name.lower().replace(" ", "-"), **kwargs
    )


@guarded_write
def create_gang_type(
    name,
    starting_credits=None,
    icon_url="",
    foundable=True,
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """Create a gang type with a trimmed, non-empty name.

    The name labels the gang type on the founding page.
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


# --- Campaign types and assets ---------------------------------------------


@guarded_write
def create_campaign_type(
    name, qualifier="", description="", library_author_help="", **kwargs
):
    """Create a campaign type with a trimmed, non-empty name.

    Add its asset types with ``add_asset_type`` and their assets with
    ``create_asset``. The description appears during campaign founding;
    ``library_author_help`` is shown to content authors.
    """
    from n26.library.models import CampaignType

    name = (name or "").strip()
    if not name:
        raise ValidationError("A campaign type needs a name.")
    return CampaignType.objects.create(
        name=name,
        qualifier=qualifier,
        description=description,
        library_author_help=library_author_help,
        **kwargs,
    )


@guarded_write
def add_asset_type(
    campaign_type,
    label_singular,
    ownership,
    label_plural="",
    position=None,
    display_group="",
    **kwargs,
):
    """Add an asset type, appending it unless ``position`` is supplied.

    Labels must be unique within the campaign type, ignoring case.
    The asset type inherits its campaign type's pack unless overridden.
    """
    from n26.library.models import AssetType

    if "pack" not in kwargs and "pack_id" not in kwargs:
        kwargs["pack_id"] = campaign_type.pack_id
    label_singular = (label_singular or "").strip()
    if not label_singular:
        raise ValidationError("An asset type needs a label.")
    if campaign_type.asset_types.filter(label_singular__iexact=label_singular).exists():
        raise ValidationError(
            f"{campaign_type} already has an asset type called “{label_singular}”."
        )
    if position is None:
        last = campaign_type.asset_types.aggregate(last=Max("position"))["last"]
        position = 0 if last is None else last + 1
    return AssetType.objects.create(
        campaign_type=campaign_type,
        label_singular=label_singular,
        label_plural=label_plural,
        display_group=display_group.strip(),
        ownership=ownership,
        position=position,
        **kwargs,
    )


@guarded_write
def remove_asset_type(asset_type):
    """Delete an asset type only when it has no assets.

    Raise ``ValidationError`` naming the remaining assets before database
    protection would reject the deletion.
    """
    count = asset_type.assets.count()
    if count:
        noun = "asset is" if count == 1 else "assets are"
        them = "it" if count == 1 else "them"
        raise ValidationError(
            f"{count} {noun} of the asset type {asset_type}. Delete {them} before "
            f"removing {asset_type}."
        )
    asset_type.delete()


@guarded_write
def create_asset(
    name,
    asset_type,
    annotation="",
    income=0,
    qualifier="",
    library_author_help="",
    given_by=None,
    given_to_every_gang=True,
    **kwargs,
):
    """Create a named asset in its asset type's pack unless overridden.

    ``income`` creates its Income contribution; zero creates no contribution.
    When automatic distribution is enabled for an inherent asset, add it to
    ``given_by`` or the asset type's campaign type. The giver must share the
    asset's pack, so campaign-specific assets use their campaign's additions type.
    """
    from n26.library.models import Asset, AssetType

    if "pack" not in kwargs and "pack_id" not in kwargs:
        kwargs["pack_id"] = asset_type.pack_id
    name = (name or "").strip()
    if not name:
        raise ValidationError("An asset needs a name.")
    giver = None
    if asset_type.ownership == AssetType.Ownership.POSSESSION and given_to_every_gang:
        giver = given_by if given_by is not None else asset_type.campaign_type
        pack_id = kwargs["pack"].pk if "pack" in kwargs else kwargs["pack_id"]
        # Validate the giver before inserting the asset to avoid a partial write.
        if giver.pack_id != pack_id:
            raise ValueError(
                f"{name} would be in a different pack from {giver}. The "
                "campaign type that gives a possession to every gang has to "
                "be in the asset's own pack."
            )
    asset = Asset.objects.create(
        name=name,
        asset_type=asset_type,
        given_to_every_gang=given_to_every_gang,
        annotation=annotation,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )
    if asset.base_income_modifier_id:
        asset.full_clean()
    if income:
        set_income(asset, income)
    if giver is not None:
        add_built_in(giver, asset, pack=asset.pack)
    return asset


@guarded_write
def set_given_to_every_gang(asset, enabled):
    """Change whether joining gangs receive this inherent asset."""
    from n26.library.possessions import give_back

    asset.given_to_every_gang = enabled
    asset.save(update_fields=["given_to_every_gang"])
    if enabled:
        give_back(asset)
    else:
        take_out_of_built_ins(asset)


def take_out_of_built_ins(thing):
    """Remove an asset or table from every live built-in set.

    Archive memberships already issued to gangs; delete unused memberships.
    Existing assignments remain. Future joining gangs stop receiving the asset
    or table. Holdings have no built-in memberships.
    """
    from n26.library.models import DefaultAssignment

    members = DefaultAssignment.objects.filter(
        **_default_member_kwarg(thing), archived=False
    )
    for member in members:
        remove_default_member(member)


def _default_member_kwarg(thing):
    """Return the ``DefaultAssignment`` field naming this content kind."""
    from n26.library.models import DefaultAssignment

    for name in DefaultAssignment.ASSIGNABLE_FIELDS:
        if DefaultAssignment._meta.get_field(name).related_model is type(thing):
            return {name: thing}
    raise ValueError(f"A {type(thing).__name__} is never built in")


@guarded_write
def create_asset_table(
    name,
    asset_type,
    dice="",
    qualifier="",
    library_author_help="",
    given_by=None,
    **kwargs,
):
    """Create a table for a Holding asset type, rejecting inherent-asset types.

    Use the asset type's pack unless overridden. ``dice`` selects a rolled table;
    blank creates an ordered selection list. Add entries with
    ``add_asset_table_entry``.

    Build the table into ``given_by`` or the asset type's campaign type.
    The giver must share the table's pack, so campaign-specific tables use
    their campaign's additions type.
    """
    from n26.library.models import AssetTable

    if "pack" not in kwargs and "pack_id" not in kwargs:
        kwargs["pack_id"] = asset_type.pack_id
    name = (name or "").strip()
    if not name:
        raise ValidationError("A table needs a name.")
    if not asset_type.is_holding:
        raise ValidationError(
            f"{asset_type} is an inherent asset type: every gang has its own, "
            "so there is nothing to roll for. A table lists a transferable asset type."
        )
    giver = given_by if given_by is not None else asset_type.campaign_type
    pack_id = kwargs["pack"].pk if "pack" in kwargs else kwargs["pack_id"]
    # Validate the giver before inserting the table to avoid a partial write.
    if giver.pack_id != pack_id:
        raise ValueError(
            f"{name} would be in a different pack from {giver}. The campaign "
            "type that gives a table to every gang has to be in the table's "
            "own pack."
        )
    table = AssetTable.objects.create(
        name=name,
        asset_type=asset_type,
        dice=dice or "",
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )
    add_built_in(giver, table, pack=table.pack)
    return table


@guarded_write
def add_asset_table_entry(
    table, asset, position=None, roll_low=None, roll_high=None, **kwargs
):
    """Add an asset to a table of the same asset type.

    Append unless ``position`` is supplied. On a rolled table, ``roll_low`` and
    ``roll_high`` define an inclusive band; omit the upper bound for one result.
    """
    from n26.library.models import AssetTableEntry
    from n26.library.models.slots import band_problem

    if asset.asset_type_id != table.asset_type_id:
        raise ValidationError(
            f"{asset} is a {asset.asset_type}, and {table} lists "
            f"{table.asset_type.plural}."
        )
    if roll_low is not None and not table.dice:
        raise ValidationError(
            f"{table} names no dice, so a band here would never be rolled. "
            "Give the table its dice first."
        )
    if position is None:
        position = table.entries.count()
    if roll_low is not None and roll_high is None:
        roll_high = roll_low
    if problem := band_problem(roll_low, roll_high):
        raise ValidationError(problem)
    if "pack" not in kwargs and "pack_id" not in kwargs:
        kwargs["pack_id"] = table.pack_id
    return AssetTableEntry.objects.create(
        table=table,
        asset=asset,
        position=position,
        roll_low=roll_low,
        roll_high=roll_high,
        **kwargs,
    )


@guarded_write
def remove_asset_table_entry(entry):
    """Remove a table entry without deleting its asset or existing holdings."""
    entry.delete()


@guarded_write
@preserves_income_choices
def set_income(asset, amount):
    """Set the asset's Income contribution in its own pack.

    Update the existing modifier so held assets use the new amount on their
    next read. Zero removes a direct contribution but preserves a declared
    Income option's modifier and per-holding overrides. Combine multiple direct
    contributions into the first; keep independent additions to declared choices.
    Return the modifier, or ``None`` when no contribution remains.
    """
    from n26.library.income import (
        ensure_income_counter,
        income_modifier_name,
        income_modifiers,
    )
    from n26.library.models import Modifier

    amount = max(int(amount or 0), 0)
    if asset.base_income_modifier_id:
        from n26.library.income_choices import validate_income_choice

        choice = validate_income_choice(asset)
        effect = choice.modifier.contributes_to_counter
        effect.amount = amount
        effect.save(update_fields=["amount"])
        return choice.modifier
    standing = income_modifiers(asset)
    if amount == 0:
        for row in standing:
            delete_modifier(row)
        return None
    if standing:
        kept, *surplus = standing
        effect = kept.contributes_to_counter
        if effect.amount != amount:
            effect.amount = amount
            effect.save(update_fields=["amount"])
        for row in surplus:
            delete_modifier(row)
        return kept
    return modifier(
        income_modifier_name(asset, Modifier, asset.pack_id),
        targets_gang_alone(),
        ef_contributes_to_counter(ensure_income_counter(), amount),
        attach_to=asset,
        pack_id=asset.pack_id,
    )


@guarded_write
def set_base_income_modifier(asset, modifier):
    """Identify the contribution carried by this asset's Income option.

    The option and its visible single-pick gang choice must already be
    attached. The ordinary Income editor then changes this contribution,
    including a real zero, without detaching the option.
    """
    from n26.library.income_choices import validate_income_choice

    if modifier is None and asset.base_income_modifier_id:
        raise ValidationError(
            "An asset with selectable income must keep its base income modifier."
        )
    asset.base_income_modifier = modifier
    validate_income_choice(asset)
    asset.save(update_fields=["base_income_modifier", "modified"])
    return asset


@guarded_write
def create_stat(
    short_name,
    full_name,
    is_inches=False,
    is_target=False,
    is_inverted=False,
    is_modifier=False,
    minimum=None,
    maximum=None,
    **kwargs,
):
    """A stat definition, e.g. ``create_stat("M", "Movement", is_inches=True)``.

    The internal ``field_name`` is derived from the full name. ``minimum``
    and ``maximum`` are the values a change stops at, as the rulebook
    prints them: 6 for a 6+ Save. Leave them blank where the stat has no
    limit.
    """
    return Stat.objects.create(
        short_name=short_name,
        full_name=full_name,
        is_inches=is_inches,
        is_target=is_target,
        is_inverted=is_inverted,
        is_modifier=is_modifier,
        minimum=minimum,
        maximum=maximum,
        **kwargs,
    )


@guarded_write
def create_statline_type(name, stats=(), **kwargs):
    """Create a statline type with characteristics in ``stats`` order.

    An empty type can be populated with ``add_stat_to_statline_type``.
    A multi-select cannot represent the required characteristic order.
    """
    statline_type = StatlineType.objects.create(name=name, **kwargs)
    for position, stat in enumerate(stats):
        add_stat_to_statline_type(statline_type, stat, position=position, **kwargs)
    return statline_type


@guarded_write
def add_stat_to_statline_type(
    statline_type,
    stat,
    position=None,
    short_name_override="",
    is_highlighted=False,
    is_first_of_group=False,
    **kwargs,
):
    """Add a characteristic, appending unless positioned.

    ``short_name_override`` replaces its abbreviation on this statline type.
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


@guarded_write
def create_profile_type(name, statline_type, **kwargs):
    return ProfileType.objects.create(
        name=name,
        statline_type=statline_type,
        **kwargs,
    )


@guarded_write
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


@guarded_write
def set_statline(owner, pack=None, **values):
    """Set the supplied characteristics on a fighter or weapon profile.

    Values use stat field names, for example ``set_statline(juve, movement=4)``.
    Repeated calls update those characteristics and preserve unspecified values.
    Each owner has one statline. Raise ``KeyError`` for a characteristic outside
    its statline type.
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


@guarded_write
@preserves_income_choices
def revise(row, **fields):
    """Update scalar fields on existing content through the shared write path.

    Authoring forms and ingest use this function. Many-to-many fields require
    their replacement function, such as ``set_traits`` or ``set_usable_by``,
    which defines how omitted members are handled.
    """
    for name, value in fields.items():
        if row._meta.get_field(name).many_to_many:
            raise ValueError(
                f"{name} is a set, so revise cannot write it — use the "
                f"set_ verb that owns it and says what leaving means"
            )
        setattr(row, name, value)
    from n26.library.models import Asset, ContributesToCounter, PicklistMember
    from n26.library.models.assignable import D6Rollable

    if isinstance(row, D6Rollable):
        return _save_rollable(row)
    if isinstance(row, (Asset, ContributesToCounter, PicklistMember)):
        row.full_clean()
    row.save()
    return row


def stage(row):
    """Mark content as staged so ordinary player discovery excludes it.

    Users with staged-content access can preview it through the same surfaces.
    See ``n26.library.staged``.
    """
    return revise(row, staged=True)


def put_live(row):
    """Release a staged row to players."""
    return revise(row, staged=False)


@guarded_write
def stage_all(rows):
    """Stage several records with one update per content kind.

    Also update the supplied instances so callers see their new staged state.
    """
    from collections import defaultdict

    from django.utils import timezone

    by_model = defaultdict(list)
    for row in rows:
        row.staged = True
        by_model[type(row)].append(row.pk)
    now = timezone.now()
    with transaction.atomic():
        for model, pks in by_model.items():
            model.objects.filter(pk__in=pks).update(staged=True, modified=now)
    return rows


@guarded_write
def put_selected_live(selection):
    """Release explicit model:ULID selections atomically, excluding campaign packs.

    Already-live content is unchanged so repeating a submission is harmless.
    Every selection is validated before any content is released.
    """
    from collections import defaultdict

    from django.utils import timezone

    from n26.library.staged import content_kinds

    kinds = {model._meta.model_name: model for model in content_kinds()}
    selected = defaultdict(set)
    for value in selection:
        name, _, pk = value.partition(":")
        model = kinds.get(name)
        if model is None:
            raise ValidationError("That content cannot be put live here.")
        try:
            selected[name].add(model._meta.pk.to_python(pk))
        except ValueError, ValidationError:
            raise ValidationError("That content cannot be put live here.") from None
    if not selected:
        raise ValidationError("Select content to put live.")

    locked = []
    for name, pks in sorted(selected.items()):
        model = kinds[name]
        rows = list(
            model.objects.outside_campaign_packs()
            .filter(pk__in=pks)
            .order_by("pk")
            .select_for_update(of=("self",))
        )
        if len(rows) != len(pks):
            raise ValidationError(
                "Some selected content is no longer available. Review your selection."
            )
        locked.append((model, pks))

    now = timezone.now()
    return sum(
        model.objects.filter(pk__in=pks, staged=True).update(staged=False, modified=now)
        for model, pks in locked
    )


@guarded_write
def set_traits(weapon_profile, traits):
    """Replace a weapon profile's complete trait set.

    Ingest treats the sheet's traits as the complete set. Replacing Rapid Fire
    (1) with Rapid Fire (2) must remove the old trait.
    """
    weapon_profile.traits.set(traits)
    return weapon_profile


# --- Assignables ---------------------------------------------------------


@guarded_write
def create_wargear(
    name,
    price=0,
    trade_point_price=None,
    is_exclusive=False,
    category=None,
    usable_by_profile_types=(),
    usable_by_subtypes=(),
    usable_by_profiles=(),
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """Create equipment carried by a model.

    Use ``create_weapon_accessory`` for equipment attached to a weapon.
    The ``usable_by_*`` lists restrict the item everywhere it is offered;
    empty lists permit everyone. Restrictions specific to a collection belong
    on its entry through ``add_entry``.
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
    )


@guarded_write
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
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """Create equipment attached to a compatible weapon.

    ``fits_category`` and ``fits_asterisked`` restrict weapons.
    The independent ``usable_by_*`` lists restrict models; empty lists permit everyone.
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
    )


@guarded_write
def create_subtype(name, qualifier="", library_author_help="", **kwargs):
    from n26.library.models import Subtype

    return Subtype.objects.create(
        name=name,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )


def _save_rollable(row):
    from n26.library.models import Category

    # Serialise numbered writes within a category, including across kinds.
    if row.category_id:
        Category.objects.select_for_update().get(pk=row.category_id)
    row.full_clean()
    row.save()
    return row


@guarded_write
def restore_rollable(row):
    """Restore a skill or power only if its D6 number is available."""
    row.archived = False
    row.archived_at = None
    _save_rollable(row)
    for related in getattr(row, "archive_with", []):
        if hasattr(related, "unarchive"):
            related.unarchive()
    return row


@guarded_write
def create_skill(
    name,
    category=None,
    usable_by_profile_types=(),
    usable_by_subtypes=(),
    usable_by_profiles=(),
    qualifier="",
    library_author_help="",
    position=0,
    **kwargs,
):
    """Create a skill in its category, for example ``create_skill("Catfall", agility)``.

    The ``usable_by_*`` restrictions apply to both listings and free advancement
    picks. Empty restrictions permit every model.
    """
    from n26.library.models import Skill

    return set_usable_by(
        _save_rollable(
            Skill(
                name=name,
                category=category,
                position=position,
                qualifier=qualifier,
                library_author_help=library_author_help,
                **kwargs,
            )
        ),
        usable_by_profile_types=usable_by_profile_types,
        usable_by_subtypes=usable_by_subtypes,
        usable_by_profiles=usable_by_profiles,
    )


@guarded_write
def create_power(
    name,
    annotation="",
    category=None,
    usable_by_profile_types=(),
    usable_by_subtypes=(),
    usable_by_profiles=(),
    qualifier="",
    library_author_help="",
    position=0,
    **kwargs,
):
    """Create a Wyrd power with optional use restrictions.

    The ``usable_by_*`` lists behave as they do for skills; empty lists permit
    every model.
    """
    from n26.library.models import Power

    return set_usable_by(
        _save_rollable(
            Power(
                name=name,
                annotation=annotation,
                category=category,
                position=position,
                qualifier=qualifier,
                library_author_help=library_author_help,
                **kwargs,
            )
        ),
        usable_by_profile_types=usable_by_profile_types,
        usable_by_subtypes=usable_by_subtypes,
        usable_by_profiles=usable_by_profiles,
    )


def split_annotation(text):
    """Split a printed name into its name and parenthesised annotation.

    ``"Leash (3\")"`` becomes ``("Leash", '3"')``. Ingest and inline authoring
    share this parsing because a rule's annotation forms part of its identity.
    """
    smart = {"“": '"', "”": '"', "’": "'", "‘": "'"}
    for curly, plain in smart.items():
        text = text.replace(curly, plain)
    text = re.sub(r"\s*\(", " (", text.strip())
    match = re.match(r"^(.*?)\s*\((.*)\)$", text)
    if match:
        return match.group(1), match.group(2)
    return text, ""


@guarded_write
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


@guarded_write
def create_hidden(name, effects=(), qualifier="", library_author_help="", **kwargs):
    """Create an undisplayed modifier carrier from ``(scope, effect)`` pairs."""
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


@guarded_write
def create_affiliation(
    name, effects=(), qualifier="", library_author_help="", **kwargs
):
    """Create an affiliation for compatibility with existing content.

    Use slot types for new gang-level choices. ``effects`` contains
    ``(scope, effect)`` pairs.
    """
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


@guarded_write
@transaction.atomic
def create_rank_table(
    name,
    counter,
    thresholds=(),
    qualifier="",
    library_author_help="",
    *,
    initial_title="",
    **kwargs,
):
    """A counter schedule a fighter may hold; thresholds are positive values."""
    from n26.library.models import RankTable

    table = RankTable.objects.create(
        name=name,
        counter=counter,
        initial_title=initial_title,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )
    for threshold in thresholds:
        add_rank_threshold(table, threshold, **kwargs)
    return table


@guarded_write
def add_rank_threshold(rank_table, threshold, title="", **kwargs):
    """Add one titled counter threshold to a rank table."""
    from n26.library.models import RankThreshold

    member = RankThreshold(
        rank_table=rank_table, threshold=threshold, title=title, **kwargs
    )
    member.full_clean()
    member.save()
    return member


@guarded_write
@transaction.atomic
def create_action(
    name,
    timing,
    outcomes=(),
    use_price=(),
    allowance_rule=None,
    recruitment_allowance_rule=None,
    rank_allowance_rule=None,
    battle_allowance_rule=None,
    usable_by_profile_types=(),
    usable_by_subtypes=(),
    usable_by_profiles=(),
    price=0,
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """A fighter action with ordered outcomes and a price for each use."""
    from n26.library.models import (
        Action,
        ActionOutcome,
        ActionPriceComponent,
        BattleAllowanceRule,
        RankAllowanceRule,
        RecruitmentAllowanceRule,
    )

    rules = [
        rule
        for rule in (
            allowance_rule,
            recruitment_allowance_rule,
            rank_allowance_rule,
            battle_allowance_rule,
        )
        if rule is not None
    ]
    if len(rules) > 1:
        raise ValidationError("An action can have only one allowance rule.")
    allowance_rule = rules[0] if rules else None
    if allowance_rule is not None and use_price:
        raise ValidationError(
            "An action with an allowance rule cannot also have a use price."
        )
    rule_kwargs = {}
    if allowance_rule is not None:
        fields = {
            RecruitmentAllowanceRule: "recruitment_allowance_rule",
            RankAllowanceRule: "rank_allowance_rule",
            BattleAllowanceRule: "battle_allowance_rule",
        }
        field = fields[type(allowance_rule)]
        rule_kwargs[field] = allowance_rule
    action = Action.objects.create(
        name=name,
        timing=timing,
        price=price,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **rule_kwargs,
        **kwargs,
    )
    for position, outcome in enumerate(outcomes):
        ActionOutcome.objects.create(
            action=action, outcome=outcome, position=position, **kwargs
        )
    for position, component in enumerate(use_price):
        ActionPriceComponent.objects.create(
            action=action, position=position, **component, **kwargs
        )
    return set_usable_by(
        action,
        usable_by_profile_types=usable_by_profile_types,
        usable_by_subtypes=usable_by_subtypes,
        usable_by_profiles=usable_by_profiles,
    )


@guarded_write
def add_action_outcome(action, outcome, position=None, **kwargs):
    """Add one possible result to an action, at the end unless placed."""
    from n26.library.models import ActionOutcome

    if position is None:
        position = action.outcomes.count()
    return ActionOutcome.objects.create(
        action=action, outcome=outcome, position=position, **kwargs
    )


@guarded_write
def add_action_price_component(
    action, resource, payer, amount, counter=None, position=None, **kwargs
):
    """Add one required resource to the price paid for each use."""
    from n26.library.models import ActionPriceComponent

    if action.allowance_rule is not None:
        raise ValidationError(
            "An action with an allowance rule cannot also have a use price."
        )
    if position is None:
        position = action.use_price.count()
    component = ActionPriceComponent(
        action=action,
        resource=resource,
        payer=payer,
        counter=counter,
        amount=amount,
        position=position,
        **kwargs,
    )
    component.full_clean()
    component.save()
    return component


@guarded_write
def create_outcome(
    name,
    operation=None,
    augment_carried_item=None,
    resolve_advancement=None,
    apply_changes=None,
    **kwargs,
):
    """A reusable named result with one typed operation configuration."""
    from n26.library.models import Outcome

    fields = {
        "AugmentCarriedItem": "augment_carried_item",
        "ResolveAdvancement": "resolve_advancement",
        "ApplyChanges": "apply_changes",
    }
    configured = {
        "augment_carried_item": augment_carried_item,
        "resolve_advancement": resolve_advancement,
        "apply_changes": apply_changes,
    }
    if operation is not None:
        field = fields.get(type(operation).__name__)
        if field is None:
            raise ValueError(f"{type(operation).__name__} is not an outcome operation")
        configured[field] = operation
    if sum(value is not None for value in configured.values()) != 1:
        raise ValidationError("An outcome needs exactly one operation.")
    return Outcome.objects.create(name=name, **configured, **kwargs)


@guarded_write
def augment_carried_item(slot_type, **kwargs):
    from n26.library.models import AugmentCarriedItem

    return AugmentCarriedItem.objects.create(slot_type=slot_type, **kwargs)


@guarded_write
def resolve_advancement(slot, **kwargs):
    from n26.library.models import ResolveAdvancement

    return ResolveAdvancement.objects.create(slot=slot, **kwargs)


@guarded_write
@transaction.atomic
def add_advancement_promotion(
    advancement,
    from_subtype,
    threshold,
    slot,
    replaces_advancement=True,
    optional_profiles=(),
    requires_rule=None,
    requires_hidden=None,
    stash_weapons_for=(),
    keep_weapon_trait=None,
    **kwargs,
):
    from n26.library.models import AdvancementPromotion

    if stash_weapons_for and keep_weapon_trait is None:
        raise ValidationError(
            {"keep_weapon_trait": "Choose the trait for weapons the model keeps."}
        )
    promotion = AdvancementPromotion(
        advancement=advancement,
        from_subtype=from_subtype,
        threshold=threshold,
        slot=slot,
        replaces_advancement=replaces_advancement,
        requires_rule=requires_rule,
        requires_hidden=requires_hidden,
        keep_weapon_trait=keep_weapon_trait,
        **kwargs,
    )
    promotion.full_clean()
    promotion.save()
    set_promotion_profiles(
        promotion,
        optional_profiles=optional_profiles,
        stash_weapons_for=stash_weapons_for,
    )
    return promotion


@guarded_write
def set_promotion_profiles(promotion, *, optional_profiles, stash_weapons_for):
    """Replace the profiles that may decline a promotion or must stash weapons."""
    if stash_weapons_for and promotion.keep_weapon_trait_id is None:
        raise ValidationError(
            {"keep_weapon_trait": "Choose the trait for weapons the model keeps."}
        )
    promotion.optional_profiles.set(optional_profiles)
    promotion.stash_weapons_for.set(stash_weapons_for)


@guarded_write
def apply_changes(*changes, **kwargs):
    from n26.library.models import ApplyChange, ApplyChanges, CounterChange

    result = ApplyChanges.objects.create(**kwargs)
    for position, change in enumerate(changes):
        field = (
            "counter_change" if isinstance(change, CounterChange) else "remove_picks"
        )
        ApplyChange.objects.create(
            apply_changes=result, position=position, **{field: change}, **kwargs
        )
    return result


@guarded_write
def add_apply_change(apply_changes, change, position=None, **kwargs):
    """Add one typed mutation to an apply-changes operation."""
    from n26.library.models import ApplyChange, CounterChange

    if position is None:
        position = apply_changes.changes.count()
    field = "counter_change" if isinstance(change, CounterChange) else "remove_picks"
    return ApplyChange.objects.create(
        apply_changes=apply_changes, position=position, **{field: change}, **kwargs
    )


@guarded_write
def counter_change(counter, mode, amount=0, **kwargs):
    from n26.library.models import CounterChange

    return CounterChange.objects.create(
        counter=counter, mode=mode, amount=amount, **kwargs
    )


@guarded_write
def remove_picks(slot_type, **kwargs):
    from n26.library.models import RemovePicks

    return RemovePicks.objects.create(slot_type=slot_type, **kwargs)


@guarded_write
def recruitment_allowance_rule(**kwargs):
    from n26.library.models import RecruitmentAllowanceRule

    return RecruitmentAllowanceRule.objects.create(**kwargs)


@guarded_write
def battle_allowance_rule(minimum_xp=5, **kwargs):
    """Earn one use for a qualifying XP award in one battle."""
    from n26.library.models import BattleAllowanceRule

    rule = BattleAllowanceRule(minimum_xp=minimum_xp, **kwargs)
    rule.full_clean()
    rule.save()
    return rule


@guarded_write
def rank_allowance_rule(counter, **kwargs):
    from n26.library.models import RankAllowanceRule

    return RankAllowanceRule.objects.create(counter=counter, **kwargs)


@guarded_write
def create_slot_type(
    name, plural_name="", allows_repeats=True, is_lasting_effect=False, **kwargs
):
    """Create a type of choice, such as Gang Legacy or Specialisation.

    Its pickables, picklists and slots must all reference this slot type.
    """
    from n26.library.models import SlotType

    return SlotType.objects.create(
        name=name,
        plural_name=plural_name,
        allows_repeats=allows_repeats,
        is_lasting_effect=is_lasting_effect,
        **kwargs,
    )


@guarded_write
def create_pickable(
    name,
    slot_type,
    effects=(),
    qualifier="",
    library_author_help="",
    category=None,
    rating_contribution=0,
    summary="",
    record_only=False,
    **kwargs,
):
    """Create a choice option with ``(scope, effect)`` modifier pairs.

    Modifiers supply its effects. A linked ``category`` supplies the category
    used by placement rules, such as the skill set represented by a Skill Tree
    pick. ``rating_contribution`` adds to the holding model's rating in credits.
    Gang-held picks add no rating, and acquiring a pick spends no credits.
    """
    from n26.library.models import Pickable

    pickable = Pickable.objects.create(
        name=name,
        slot_type=slot_type,
        qualifier=qualifier,
        summary=summary,
        record_only=record_only,
        library_author_help=library_author_help,
        category=category,
        rating_contribution=rating_contribution,
        **kwargs,
    )
    for scope, effect in effects:
        modifier(
            name=f"{name}: {effect}", scope=scope, effect=effect, attach_to=pickable
        )
    return pickable


@guarded_write
def create_picklist(name, slot_type, members=(), dice="", roll_selects="", **kwargs):
    """A flat, ordered list of one slot type's pickables.

    ``members`` are pickables, in order, or ``(pickable, "wording")``
    where this list calls one of them something else. A list given
    ``dice`` is a roll table, and ``roll_selects`` says how a roll finds
    its row on it.
    """
    from n26.library.models import Picklist
    from n26.library.models.slots import ROLL_TABLE_IS_WHOLE

    if bool(dice) != bool(roll_selects):
        raise ValidationError(ROLL_TABLE_IS_WHOLE)
    picklist = Picklist.objects.create(
        name=name, slot_type=slot_type, dice=dice, roll_selects=roll_selects, **kwargs
    )
    for member in members:
        pickable, label = member if isinstance(member, tuple) else (member, "")
        add_picklist_member(picklist, pickable, label_override=label, **kwargs)
    return picklist


@guarded_write
@transaction.atomic
def clone_picklist(picklist, name):
    """Copy a picklist and its memberships, sharing the existing pickables.

    The copy keeps the original slot type, dice, result order, labels,
    roll bands and tier levels. Edit its memberships independently;
    changes to a shared pickable still apply wherever it is offered.
    """
    from n26.library.models import Picklist

    name = name.strip()
    if not name:
        raise ValidationError({"name": "Give the copy a name."})
    if Picklist.objects.filter(
        pack=picklist.pack, slot_type=picklist.slot_type, name__iexact=name
    ).exists():
        raise ValidationError(
            {"name": "A picklist with this name already exists for this slot type."}
        )
    copy = Picklist(
        name=name,
        pack=picklist.pack,
        slot_type=picklist.slot_type,
        dice=picklist.dice,
        roll_selects=picklist.roll_selects,
        staged=picklist.staged,
    )
    copy.full_clean()
    copy.save()
    for member in picklist.members.select_related("pickable").order_by(
        "position", "pk"
    ):
        add_picklist_member(
            copy,
            member.pickable,
            label_override=member.label_override,
            position=member.position,
            roll_low=member.roll_low,
            roll_high=member.roll_high,
            level=member.level,
            pack=member.pack,
            staged=member.staged,
            archived=member.archived,
        )
    return copy


@guarded_write
@preserves_income_choices
def add_picklist_member(
    picklist,
    pickable,
    label_override="",
    position=None,
    roll_low=None,
    roll_high=None,
    level=None,
    **kwargs,
):
    """Add a pickable of the list's slot type, appending unless positioned.

    On a roll table, ``roll_low`` and ``roll_high`` define an inclusive band;
    omit the upper bound for a single result.
    """
    from n26.library.models import PicklistMember

    if pickable.slot_type_id != picklist.slot_type_id:
        raise ValidationError(
            f"{pickable} belongs to {pickable.slot_type}, and {picklist} "
            f"lists {picklist.slot_type} pickables."
        )
    if picklist.slots.filter(mode="tier_ladder").exists() and level is None:
        raise ValidationError("Every member of a tier ladder needs a numeric level.")
    if roll_low is not None and not picklist.dice:
        raise ValidationError(
            f"{picklist} names no dice, so a band here would never be "
            "rolled. Give the list its dice first."
        )
    if position is None:
        position = picklist.members.count()
    if roll_low is not None and roll_high is None:
        roll_high = roll_low
    from n26.library.models.slots import band_problem

    if problem := band_problem(roll_low, roll_high):
        raise ValidationError(problem)
    member = PicklistMember(
        picklist=picklist,
        pickable=pickable,
        label_override=label_override,
        position=position,
        roll_low=roll_low,
        roll_high=roll_high,
        level=level,
        **kwargs,
    )
    member.full_clean()
    member.save()
    return member


@guarded_write
@preserves_income_choices
def remove_picklist_member(member):
    """Remove a picklist membership without deleting the pickable or existing picks."""
    member.delete()


@guarded_write
@preserves_income_choices
def create_slot(
    name,
    slot_type,
    picklist,
    label="",
    min_picks=1,
    max_picks=1,
    assigned_to="bearer",
    hidden=False,
    follows_status=False,
    mode="standard",
    position=0,
    qualifier="",
    library_author_help="",
    introduction="",
    allow_dismissal=True,
    pick_rating_override=None,
    **kwargs,
):
    """Create a choice that displays its label and selected pickables on a card.

    Assign the slot directly, through built-ins, or through a grant.
    ``assigned_to="gang"`` stores the picks on the gang. A hidden slot applies
    its picks without displaying the choice.
    """
    from n26.library.models import Slot

    if picklist.slot_type_id != slot_type.pk:
        raise ValidationError(
            f"{picklist} lists {picklist.slot_type} pickables, and this is a "
            f"{slot_type} choice."
        )
    slot = Slot(
        name=name,
        slot_type=slot_type,
        picklist=picklist,
        label=label,
        introduction=introduction,
        min_picks=min_picks,
        max_picks=max_picks,
        assigned_to=assigned_to,
        hidden=hidden,
        allow_dismissal=allow_dismissal,
        pick_rating_override=pick_rating_override,
        follows_status=follows_status,
        mode=mode,
        position=position,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )
    slot.full_clean()
    slot.save()
    return slot


@guarded_write
def create_interstitial(
    name,
    title="",
    description="",
    skippable=False,
    position=0,
    slots=(),
    **kwargs,
):
    """Create an explanation screen for the supplied slots, in order.

    Founding, hiring or choosing content that introduces a linked slot displays
    the screen before the destination page.
    """
    from n26.library.models import Interstitial

    interstitial = Interstitial.objects.create(
        name=name,
        title=title,
        description=description,
        skippable=skippable,
        position=position,
        **kwargs,
    )
    for slot in slots:
        attach_interstitial(interstitial, slot, **kwargs)
    return interstitial


@guarded_write
def attach_interstitial(interstitial, slot, position=None, **kwargs):
    """Attach an interstitial to a slot, appending unless positioned.

    Duplicate attachments raise ``ValidationError``; a database constraint also
    rejects concurrent duplicates. The attachment inherits the interstitial's
    pack unless overridden.
    """
    from django.db import IntegrityError, transaction

    from n26.library.models import InterstitialSlot

    already = f"{interstitial} is already attached to {slot}."
    if InterstitialSlot.objects.filter(interstitial=interstitial, slot=slot).exists():
        raise ValidationError(already)
    if position is None:
        # Append after archived attachments too, preserving every existing position.
        from django.db.models import Max

        last = interstitial.attachments.aggregate(last=Max("position"))["last"]
        position = 0 if last is None else last + 1
    if "pack" not in kwargs and "pack_id" not in kwargs:
        kwargs["pack_id"] = interstitial.pack_id
    try:
        with transaction.atomic():
            return InterstitialSlot.objects.create(
                interstitial=interstitial, slot=slot, position=position, **kwargs
            )
    except IntegrityError:
        # After rollback, translate only a confirmed duplicate pair into this error.
        # Re-raise unrelated integrity failures, such as a concurrently deleted slot.
        if InterstitialSlot.objects.filter(
            interstitial=interstitial, slot=slot
        ).exists():
            raise ValidationError(already) from None
        raise


@guarded_write
def detach_interstitial(attachment):
    """Remove one slot attachment while preserving the interstitial and other links."""
    attachment.delete()


@guarded_write
def create_trait(name, annotation="", qualifier="", library_author_help="", **kwargs):
    from n26.library.models import Trait

    return Trait.objects.create(
        name=name,
        annotation=annotation,
        qualifier=qualifier,
        library_author_help=library_author_help,
        **kwargs,
    )


@guarded_write
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
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """Create a weapon with optional profiles in their supplied order.

    Profiles are ``(name, price)`` or ``(name, price, traits)`` tuples.
    When supplied, the first must be free. Otherwise profiles can be added later
    with ``add_weapon_profile``.

    ``usable_by_*`` restrictions apply wherever the weapon is offered.
    Collection-specific restrictions belong on the entry through ``add_entry``.
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
    )


@guarded_write
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
    usable_by_profile_types=(),
    usable_by_subtypes=(),
    usable_by_profiles=(),
    **kwargs,
):
    """One profile of a weapon — the gun's own, or a paid ammo type.

    ``name`` is only for a line the book names: leave it blank for the
    weapon's own line, which prints as the weapon. ``annotation``
    defaults to the weapon's name, which is what a named line prints in
    brackets. ``position`` defaults to the end.

    The ``usable_by_*`` lists are the bracket the book prints after one
    round and not the gun — "krak grenades (Stimmer only)" — true of
    that profile wherever it is offered. Empty means everyone.
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
    # Skip empty restriction writes on newly created records.
    if usable_by_profile_types or usable_by_subtypes or usable_by_profiles:
        set_usable_by(
            profile,
            usable_by_profile_types=usable_by_profile_types,
            usable_by_subtypes=usable_by_subtypes,
            usable_by_profiles=usable_by_profiles,
        )
    return profile


@guarded_write
def create_counter(
    name, qualifier="", drawn=True, library_author_help="", minimum=0, **kwargs
):
    from n26.library.models import Counter

    return Counter.objects.create(
        name=name,
        qualifier=qualifier,
        drawn=drawn,
        minimum=minimum,
        library_author_help=library_author_help,
        **kwargs,
    )


@guarded_write
def restrict_use(thing, *allowed):
    """Add a permitted profile type, subtype or fighter profile to an item's use lists.

    The same fields on a collection entry restrict only that listing.
    Item-level restrictions apply wherever the item is offered.
    """
    from n26.library.models import Profile, ProfileType, Subtype

    for item in allowed:
        if isinstance(item, ProfileType):
            thing.usable_by_profile_types.add(item)
        elif isinstance(item, Subtype):
            thing.usable_by_subtypes.add(item)
        elif isinstance(item, Profile):
            thing.usable_by_profiles.add(item)
        else:
            raise ValueError(f"{type(item).__name__} cannot restrict use")
    return thing


@guarded_write
def set_usable_by(
    thing,
    usable_by_profile_types=None,
    usable_by_subtypes=None,
    usable_by_profiles=None,
):
    """Replace supplied use-restriction lists on an item or collection entry.

    ``None`` preserves a list; an empty iterable clears its restriction.
    Use ``restrict_use`` to add individual permitted types or profiles.
    """
    lists = {
        "usable_by_profile_types": usable_by_profile_types,
        "usable_by_subtypes": usable_by_subtypes,
        "usable_by_profiles": usable_by_profiles,
    }
    for name, allowed in lists.items():
        if allowed is not None:
            getattr(thing, name).set(allowed)
    return thing


# --- Default sets and options ----------------------------------------------


@guarded_write
def create_default_set(name, members=(), price=0, **kwargs):
    """A set of things a profile can come with. ``members`` are assignables, or
    ``(assignable, {extras})`` — ``(xp, {"amount": 61})`` for a counter's
    opening value."""
    from django.db import transaction

    from n26.library.models import DefaultAssignmentSet, WeaponProfile

    staged = [
        (position, *(member if isinstance(member, tuple) else (member, {})))
        for position, member in enumerate(members)
    ]
    # Create guns before their profiles so anchors resolve against the complete set.
    # Preserve supplied positions and roll back the entire set on refusal.
    with transaction.atomic():
        default_set = DefaultAssignmentSet.objects.create(
            name=name, price=price, **kwargs
        )
        for adding_lines in (False, True):
            for position, assignable, extras in staged:
                if isinstance(assignable, WeaponProfile) != adding_lines:
                    continue
                add_default_member(
                    default_set, assignable, position=position, **extras, **kwargs
                )
    return default_set


def _free_set_name(carrier, phrase="built-ins", **shared):
    """Find an unused author-only default-set name within the carrier's pack.

    Start with its name and ``phrase``, then add the kind and a numeric suffix
    as needed. Same-named profiles and wargear can require distinct sets.
    """
    from itertools import chain, count

    from n26.library.models import DefaultAssignmentSet
    from n26.library.models.pack import default_pack_id

    label = getattr(carrier, "authoring_label", None) or str(carrier)
    kind = carrier._meta.verbose_name
    pack = shared.get("pack") or default_pack_id()
    taken = DefaultAssignmentSet.objects.filter(pack=pack)

    # Generate suffix candidates lazily because the numeric sequence is unbounded.
    tries = chain(
        (f"{label} {phrase}", f"{label} ({kind}) {phrase}"),
        (f"{label} ({kind}) {phrase} {number}" for number in count(2)),
    )
    return next(name for name in tries if not taken.filter(name__iexact=name).exists())


@guarded_write
@preserves_income_choices
def add_built_in(
    carrier,
    thing,
    amount=0,
    default_pickable=None,
    position=None,
    gun_member=None,
    **kwargs,
):
    """Add content materialised whenever the carrier is acquired.

    Create the default set on first use. ``default_pickable`` supplies a slot's
    starting pick; ``gun_member`` anchors an additional weapon profile.
    Reject carriers acquired only by choosing because they do not materialise
    built-in sets.
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
        gun_member=gun_member,
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


# Commit the member and its propagation task together, even without an outer transaction.
@guarded_write
@transaction.atomic
@preserves_income_choices
def add_default_member(
    default_set,
    thing,
    amount=0,
    default_pickable=None,
    position=None,
    gun_member=None,
    **kwargs,
):
    """Add content to an existing default set, appending unless positioned.

    ``default_pickable`` is valid only for a slot member.
    For an additional weapon profile, ``gun_member`` must be a matching weapon
    member of this set. If omitted, use the unique match, reject multiple
    matches, or leave it null to use an already-held matching weapon.
    """
    from n26.library.models import DefaultAssignment, WeaponProfile

    _refuse_a_bare_pickable(thing)
    if isinstance(thing, WeaponProfile) and gun_member is None:
        gun_member = _the_one_gun_member(default_set, thing)
    if position is None:
        # Append after archived positions as well; live counts could create ordering ties.
        last = default_set.members.aggregate(last=Max("position"))["last"]
        position = 0 if last is None else last + 1
    member = DefaultAssignment(
        default_set=default_set,
        assignable=thing,
        amount=amount,
        default_pickable=default_pickable,
        position=position,
        gun_member=gun_member,
        **kwargs,
    )
    if default_pickable is not None or gun_member is not None:
        # Validate starting-pick type and weapon-member ownership together;
        # these cross-record constraints cannot be expressed by database checks.
        member.clean()
    member.save()
    # Schedule propagation for existing holders in the same transaction as the new member.
    from n26.core.propagation import file_propagation_task

    file_propagation_task(default_set)
    return member


def gun_members_bringing(default_set, weapon):
    """Find this set's live weapon members that can anchor a matching profile."""
    return default_set.members.filter(archived=False, weapon=weapon)


def _the_one_gun_member(default_set, weapon_profile):
    """Return the unique live matching weapon member, or ``None`` if absent.

    Reject multiple matches rather than choosing a gun implicitly.
    """
    matches = list(gun_members_bringing(default_set, weapon_profile.weapon))
    if len(matches) > 1:
        raise ValidationError(
            f"{default_set.name} brings {weapon_profile.weapon} "
            f"{len(matches)} times, so there is no saying which gun "
            f"{weapon_profile} lands under. Add the profile from that "
            f"gun's own row instead."
        )
    return matches[0] if matches else None


@guarded_write
def remove_default_member(member):
    """Remove a default membership and its dependent weapon-profile memberships.

    Archive members referenced by issued copies to preserve provenance; delete
    unused members so invisible archives do not retain protected content.
    Keep the default set, referenced library content and existing assignments.
    Only future acquisitions stop receiving the removed members.
    """
    for dependent in list(member.dependent_members):
        remove_default_member(dependent)
    if _something_materialised(member):
        member.archive()
    else:
        member.delete()


def _something_materialised(member):
    """Whether any copy in any gang came from this membership.

    Provenance answers outright for every kind the estate tags. Ammo is
    the one kind outside that regime — a granted profile is written in
    the same shape as a weapon's own free profiles and never carries
    provenance — so for a weapon-profile member any free-granted copy of
    the same profile still counts, and the member is archived rather
    than deleted so those copies keep their anchor.
    """
    from n26.core.models import Assignment, Reason
    from n26.library.models import WeaponProfile

    if Assignment.objects.filter(materialised_from=member).exists():
        return True
    assignable = member.assignable
    if not isinstance(assignable, WeaponProfile):
        return False
    return Assignment.objects.filter(
        materialised_from__isnull=True,
        ledger_entry__reason=Reason.DEFAULT,
        weapon_profile=assignable,
    ).exists()


@guarded_write
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
    """Add an acquisition option for a profile or piece of wargear.

    ``name`` labels the option and ``price`` sets the acquisition surcharge on a newly created default set.
    A supplied ``default_set`` retains its stored price.
    Create the set when needed, or pass an existing ``default_set``.
    ``thing`` adds a member; ``amount`` and ``default_pickable`` configure that
    member rather than the option.

    Append to ``group`` or the main pick-one set. Its first option is the default.
    Default-set names are derived and author-facing to avoid pack-wide collisions.
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


@guarded_write
def stop_offering(option):
    """Remove an option and delete its default set if nothing else references it.

    Shared default sets and their content remain. Existing assignments remain;
    the change affects options offered on future acquisitions.
    """
    from django.db.models import ProtectedError

    default_set = option.default_set
    option.delete()
    try:
        default_set.delete()
    except ProtectedError:
        # ProtectedError means another option or carrier still references this set.
        pass


@guarded_write
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


@guarded_write
def remove_option_group(group):
    """Delete an option group and its options.

    Moving its options into the main group would change which choices compete
    with the standard loadout, so the options are removed with their group.
    """
    for option in list(group.options.all()):
        stop_offering(option)
    group.delete()


# --- Collections -----------------------------------------------------------


@guarded_write
def create_section(name, position=0, **kwargs):
    """One heading of the taxonomy — the level above categories."""
    from n26.library.models import Section

    return Section.objects.create(name=name, position=position, **kwargs)


@guarded_write
def create_category(section, name, position=0, draws_its_own_row=False, **kwargs):
    """Create a category under a Section instance or a named section.

    A named section is found or created in the supplied pack.
    ``draws_its_own_row`` displays the category separately on model cards.
    It is an explicit parameter so generated forms can read its default.
    """
    from n26.library.models import Category, Section

    if not isinstance(section, Section):
        shared = {"pack": kwargs["pack"]} if "pack" in kwargs else {}
        section, _ = Section.objects.get_or_create(name=section, **shared)
    return Category.objects.create(
        section=section,
        name=name,
        position=position,
        draws_its_own_row=draws_its_own_row,
        **kwargs,
    )


@guarded_write
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


@guarded_write
def create_collection(
    name,
    entries=(),
    contains=(),
    prices_its_entries=True,
    position=0,
    qualifier="",
    library_author_help="",
    **kwargs,
):
    """Create a collection with ordered entries and selector sweeps.

    ``entries`` contains assignables or ``(assignable, overrides)`` pairs.
    ``contains`` contains model classes or ``(model, category)`` pairs.
    ``position`` orders held collections, lowest first.
    """
    from n26.library.models import Collection, CollectionEntry, CollectionSelector

    # Extra kwargs describe the collection; only the
    # pack is shared with its rows.
    shared = {"pack": kwargs["pack"]} if "pack" in kwargs else {}
    collection = Collection.objects.create(
        name=name,
        prices_its_entries=prices_its_entries,
        position=position,
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


# Delete generated memberships and their asset atomically; restore both on refusal.
@guarded_write
@transaction.atomic
@preserves_income_choices
def delete_content(row):
    """Delete library content subject to database reference protection.

    Preserve reusable carried modifiers. Remove generated asset or table default
    memberships in the same transaction, but existing issued assignments still
    protect their content. Callers convert protected-reference errors into
    appropriate messages.
    """
    from n26.library.models import Asset, AssetTable

    if isinstance(row, (Asset, AssetTable)):
        take_out_of_built_ins(row)
    row.delete()


@guarded_write
def add_entry(
    collection,
    thing,
    price_override=None,
    trade_point_override=None,
    usable_by_profile_types=(),
    usable_by_subtypes=(),
    usable_by_profiles=(),
    position=None,
    **kwargs,
):
    """Append content to a curated collection with optional price and use overrides.

    Blank prices use the item's reference values. Entry restrictions narrow only
    this listing; item-wide restrictions continue to apply.
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
    }
    for name, allowed in narrowing.items():
        if allowed:
            getattr(entry, name).set(allowed)
    return entry


@guarded_write
def remove_entry(entry):
    """Remove one collection entry while preserving content and other memberships."""
    entry.delete()


def add_section(collection, name, is_default=False, position=None, **kwargs):
    """One more section of a collection's own — "Primary", "Affiliations".

    New sections go after the ones already there; ``is_default`` marks
    where unplaced categories fall, at most one per collection.
    """
    if position is None:
        position = collection.sections.count()
    return section_of(collection, name, position, is_default=is_default, **kwargs)


@guarded_write
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
        # Use standard content's complete offerable kinds when no explicit subset is supplied.
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


def is_profile_type(*profile_types, negate=False):
    """Condition: the model's Type — Fighter or Vehicle — is one of these.
    ``targets_every_model(is_profile_type(fighter))`` reaches every
    fighter in the gang and no vehicle. ``negate=True`` reads the row
    the other way."""
    from n26.library.models import IsProfileType

    condition = IsProfileType(negate=negate)
    condition._pending_m2m = {"profile_types": profile_types}
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


def has_status(status):
    """Condition: the model has this current status."""
    from n26.core.status import Status
    from n26.library.models import HasStatus

    return HasStatus(status=Status(status))


def counter_at_least(counter, at_least):
    """Condition: the model's counter has reached this value —
    ``targets_model(counter_at_least(xp, 75))``."""
    from n26.library.models import CounterAtLeast

    return CounterAtLeast(counter=counter, at_least=at_least)


def has_gang_pickable(*pickables, negate=False):
    """Condition: the gang has one of these picked —
    ``targets_gang_alone(has_gang_pickable(goliath))`` for "gangs that
    have picked Goliath". ``negate=True`` reaches every gang except those.

    Read against the gang's own facts, so a pick the gang made and a
    pick it was given count the same: a Clan House Goliath Outcast gang
    matches it just as a Goliath gang does."""
    from n26.library.models import GangHasPickable

    condition = GangHasPickable(negate=negate)
    condition._pending_m2m = {"pickables": pickables}
    return condition


def _weapon_conditions():
    """The condition kinds that narrow weapons rather than models."""
    from n26.library.models import HasTraits, InCategories, IsOneOf

    return (HasTraits, InCategories, IsOneOf)


def _gang_conditions():
    """The condition kinds that narrow the gang rather than models."""
    from n26.library.models import GangHasPickable

    return (GangHasPickable,)


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


@guarded_write
def targets_model(*conditions):
    """The model carrying it — only the model the carrier is directly
    assigned to, narrowed by nested conditions —
    ``targets_model(has_subtypes(leader), counter_at_least(xp, 5))``.

    Never reached through the gang's broadcast: an affiliation
    assigned to a Champion applies to that Champion alone. For everyone
    in the gang, use ``targets_every_model``.
    """
    from n26.library.models import TargetsMiniature

    return _model_scope(TargetsMiniature.Reach.BEARER, conditions)


@guarded_write
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

    # Validate all conditions before inserting the scope.
    for condition in conditions:
        if isinstance(condition, _weapon_conditions()):
            raise ValueError(
                f"{type(condition).__name__} narrows weapons — use targets_weapons"
            )
        if isinstance(condition, _gang_conditions()):
            raise ValueError(
                f"{type(condition).__name__} narrows the gang — use targets_gang "
                "or targets_gang_alone; for the models of such a gang, use "
                "has_pickable"
            )
    scope = TargetsMiniature.objects.create(reach=reach)
    for condition in conditions:
        _attach_condition(condition, scope)
    return scope


@guarded_write
def targets_weapons(*conditions):
    """The bearer's weapons, narrowed by nested conditions —
    ``targets_weapons(has_traits(melee))`` for "your Melee weapons",
    ``targets_weapons(in_categories(las))`` for "all Las weapons",
    ``targets_weapons(is_one_of(claws))`` for one named gun.

    Given several conditions, a weapon must satisfy all of them; given
    several values in one condition, any of them will do.
    """
    from n26.library.models import TargetsWeapons

    for condition in conditions:
        if not isinstance(condition, _weapon_conditions()):
            raise ValueError(f"targets_weapons cannot take {condition!r}")
    scope = TargetsWeapons.objects.create()
    for condition in conditions:
        _attach_condition(condition, scope)
    return scope


@guarded_write
def targets_attached_weapon():
    """The one weapon the carrier is bolted to — a telescopic sight."""
    from n26.library.models import TargetsAttachedWeapon

    return TargetsAttachedWeapon.objects.create()


@guarded_write
def targets_gang(*conditions):
    """The gang carrying it and all models: affects the gang and all
    models, in a different way per effect. Narrowed by nested conditions
    — ``targets_gang(has_gang_pickable(goliath))``.

    Deprecated on the composer — kept for existing content. Prefer
    assigning a hidden item to the gang that carries ``targets_every_model``
    modifiers, which says the same thing legibly."""
    return _gang_scope(True, conditions)


@guarded_write
def targets_gang_alone(*conditions):
    """The gang carrying it: applied only to the gang, and what it gives
    the gang does not reach the models. A pick given with a slot is the
    exception: what the gang has picked is a fact about every model in
    it, whichever way the pick arrived.

    Narrowed by nested conditions —
    ``targets_gang_alone(has_gang_pickable(goliath))`` for a boon that
    applies only to gangs that have picked Goliath."""
    return _gang_scope(False, conditions)


def _gang_scope(echoes, conditions):
    from n26.library.models import TargetsGang

    for condition in conditions:
        if not isinstance(condition, _gang_conditions()):
            raise ValueError(
                f"{type(condition).__name__} narrows models, not the gang — "
                "use targets_model or targets_every_model; for the gang, "
                "use has_gang_pickable"
            )
    scope = TargetsGang.objects.create(echoes=echoes)
    for condition in conditions:
        _attach_condition(condition, scope)
    return scope


# --- Effects: what a modifier does (ef_ at read, op_ at purchase) -----------


@guarded_write
def ef_adds(thing, with_pick=None):
    """Grants the target a subtype, skill, trait, collection, rule, weapon
    or wargear — or a further choice, which is how one pick opens the next.

    ``with_pick`` is the pick a granted slot arrives settled on —
    ``ef_adds(supertype_slot, with_pick=goliath)`` for a Clan House
    choice that makes the gang count as a Goliath gang. The pick lasts
    exactly as long as the slot. Only a hidden slot may carry one: a
    granted pick has no assignment of its own to remove.

    Granted weapons and wargear add zero rating and are removed when
    their source is removed. Their modifiers apply. Weapons include free
    profiles; built-ins and option sets require an assignment.

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

    grant = AddsAssignable(**_assignable_kwarg(thing), with_pick=with_pick)
    if with_pick is not None or grant.asset_id is not None:
        # Only the row knows whether the asset is inherent and whether a
        # starting pick belongs to its hidden slot.
        grant.clean()
    grant.save()
    return grant


@guarded_write
def ef_removes(thing):
    """Takes one away, computed — Death of a Leader."""
    from n26.library.models import RemovesAssignable

    effect = RemovesAssignable(**_assignable_kwarg(thing))
    effect.clean()
    effect.save()
    return effect


@guarded_write
def ef_excludes_campaign_assets(asset_type):
    """Exclude campaign-provided inherent assets of this type."""
    from n26.library.models import ExcludesCampaignAssets

    effect = ExcludesCampaignAssets(asset_type=asset_type)
    effect.clean()
    effect.save()
    return effect


@guarded_write
def ef_changes_stat(stat, mode="worsen", amount=1):
    """Shifts or sets one characteristic."""
    from n26.library.models import ChangesStat

    return ChangesStat.objects.create(stat=stat, mode=mode, amount=amount)


@guarded_write
def ef_contributes_to_counter(counter, amount=0, per_counter=None):
    """Adds to a counter's reading while the carrier is held —
    ``ef_contributes_to_counter(visit_tp, 2)`` for the 2 Trade Points a
    Leader brings to a Trading Post visit. Nothing is written down, so
    the contribution goes when the carrier does."""
    from n26.library.models import ContributesToCounter

    effect = ContributesToCounter(
        counter=counter, amount=amount, per_counter=per_counter
    )
    effect.full_clean()
    effect.save()
    return effect


@guarded_write
def ef_offers_choice(
    model,
    from_section=None,
    label="",
    will_be_assigned_to="bearer",
    mode="select",
    power_access_collection=None,
):
    """Offers one assignable for the bearer to select or roll randomly —
    ``ef_offers_choice(Skill, from_section=primary)`` for "a skill from a
    set that is Primary for this fighter".
    ``mode="random"`` records a roll against the chosen offered set;
    select mode lets the player choose from the offer.
    ``will_be_assigned_to="gang"`` is the Leader-picks-for-the-gang arrow."""
    from n26.library.models import OffersChoice

    return OffersChoice.of(
        model,
        from_section=from_section,
        label=label,
        will_be_assigned_to=will_be_assigned_to,
        mode=mode,
        power_access_collection=power_access_collection,
    )


@guarded_write
def ef_changes_category(category):
    """The bearer sorts under this category's heading on the gang sheet —
    ``ef_changes_category(leaders)`` for a fighter selected as Leader."""
    from n26.library.models import ChangesCategory

    return ChangesCategory.objects.create(category=category)


@guarded_write
def ef_hides_categories(collection, categories):
    """Hide categories from one equipment list for the targeted model."""
    from n26.library.models import HidesCategories

    categories = list(categories)
    if not categories:
        raise ValueError("Select at least one category to hide.")
    effect = HidesCategories.objects.create(collection=collection)
    effect.categories.set(categories)
    return effect


@guarded_write
def ef_randomises_skill_advancements(from_section):
    """Roll skill advancements from the named section randomly."""
    from n26.library.models import RandomisesSkillAdvancements

    return RandomisesSkillAdvancements.objects.create(from_section=from_section)


@guarded_write
def ef_places(category, section):
    """For the bearer, that set sits under this section of its
    collection — ``ef_places(powers, skills_primary)``."""
    from n26.library.models import PlacesCategory

    return PlacesCategory.objects.create(category=category, section=section)


@guarded_write
def ef_places_choice(section):
    """The carrier-relative placement: whatever set the carrier's chosen
    thing is homed in sits under this collection section — a Venator
    rank slot."""
    from n26.library.models import PlacesCategory

    return PlacesCategory.objects.create(the_chosen=True, section=section)


@guarded_write
def ef_draws_pick():
    """The pick the gang holds is drawn on the card of every model this
    reaches — ``modifier(name, targets_every_model(...), ef_draws_pick(),
    attach_to=archetype)``.

    Carried by the pickable, so the line goes wherever that pick goes.
    It is a fact on the card and not a control: the choice stays where
    it was asked."""
    from n26.library.models import DrawsPick

    return DrawsPick.objects.create()


@guarded_write
def ef_requires_companions(for_each, at_least, of):
    """A composition ask, said on the gang sheet and never enforced —
    ``ef_requires_companions(champion, 3, hive_scum)``."""
    from n26.library.models import RequiresCompanions

    return RequiresCompanions.objects.create(
        for_each=for_each, at_least=at_least, of=of
    )


@guarded_write
def ef_allows_at_most(at_most, thing):
    """A ceiling, said on the sheet and never enforced —
    ``ef_allows_at_most(2, aberrant)``, and ``ef_allows_at_most(0, brute)``
    for a ban. Aimed at the gang it counts the roster; aimed at a model it
    counts that model's own assignments."""
    from n26.library.models import AllowsAtMost

    return AllowsAtMost.objects.create(at_most=at_most, **_countable_kwarg(thing))


@guarded_write
def op_adds_model(profile):
    """A stored effect: assigning the carrier brings this model into the gang."""
    from n26.library.models import OpAddsMiniature

    return OpAddsMiniature.objects.create(profile=profile)


@guarded_write
def op_changes_counter(counter, mode="set", amount=0):
    """A stored effect: assigning the carrier moves the bearer's counter,
    through the ledger — ``op_changes_counter(xp, "set", 61)`` for a
    selection whose sheet says it starts with 61 XP."""
    from n26.library.models import OpChangesCounter

    return OpChangesCounter.objects.create(counter=counter, mode=mode, amount=amount)


@guarded_write
def op_sets_status(status):
    """A stored effect: assigning the carrier puts the bearer into a
    status — ``op_sets_status("recovery")`` on Grievous Wound, so the
    pick landing sends the fighter into Recovery on the ledger."""
    from n26.library.models import OpSetsStatus

    return OpSetsStatus.objects.create(status=status)


def _assignable_kwarg(thing):
    from n26.library.models import (
        Action,
        Asset,
        AssetTable,
        Collection,
        Hidden,
        Power,
        RankTable,
        Rule,
        Skill,
        Slot,
        Subtype,
        Trait,
        Wargear,
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
        (Wargear, "wargear"),
        (Hidden, "hidden"),
        (Slot, "slot"),
        (AssetTable, "asset_table"),
        (Asset, "asset"),
        (Action, "action"),
        (RankTable, "rank_table"),
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


@guarded_write
@preserves_income_choices
def modifier(name, scope, effect, attach_to=None, **kwargs):
    """One scope plus one effect; optionally hung on an assignable."""
    from n26.library.models import Modifier

    row = Modifier.objects.create(name=name, **_parts(scope, effect), **kwargs)
    if attach_to is not None:
        attach_to.modifiers.add(row)
    return row


@guarded_write
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


@guarded_write
@preserves_income_choices
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


@guarded_write
@preserves_income_choices
def attach_modifiers_to(assignable, modifiers):
    """Hang already-built (reusable) modifiers on a further carrier."""
    assignable.modifiers.add(*modifiers)
    return assignable


@guarded_write
@preserves_income_choices
def detach_modifier(assignable, modifier):
    """Take a modifier off one carrier. The modifier itself survives —
    it may hang on other carriers, or wait as a reusable."""
    assignable.modifiers.remove(modifier)
    return assignable


@guarded_write
@transaction.atomic
def configure_trading_post_visit(excluded_gang_types=()):
    """Replace the gang types whose usual Trading Post setup links are hidden."""
    from n26.library.models import BuiltInAction

    types = list(excluded_gang_types)
    if GangType.objects.filter(
        pk__in=[gang_type.pk for gang_type in types], pack__campaign__isnull=False
    ).exists():
        raise ValidationError("Choose gang types from the content library.")
    action, _ = BuiltInAction.objects.get_or_create(
        key=BuiltInAction.Key.TRADING_POST_VISIT
    )
    action.excluded_gang_types.set(types)
    return action
