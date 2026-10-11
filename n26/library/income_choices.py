"""Declare the ordinary choice that carries an asset's base Income.

The declaration identifies one modifier rather than a second income number.
It supports a direct, single-pick gang slot with an unambiguous Income option.
Authoring changes validate affected declarations inside their transaction.
"""

from dataclasses import dataclass
from functools import wraps

from django.core.exceptions import ValidationError
from django.db.models import Q


@dataclass(frozen=True)
class IncomeChoice:
    slot: object
    pickable: object
    modifier: object


def declared_income_choice(asset):
    """Read a declared choice by its stored identities, without name matching."""
    if not asset.base_income_modifier_id:
        return None
    from n26.library.models import Pickable, Slot

    pickable = Pickable.objects.get(modifiers=asset.base_income_modifier_id)
    slot = Slot.objects.get(
        pk__in=asset.modifiers.filter(adds_assignable__slot__isnull=False).values_list(
            "adds_assignable__slot_id", flat=True
        ),
        picklist__members__pickable=pickable,
    )
    return IncomeChoice(slot, pickable, asset.base_income_modifier)


def _carriers(modifier):
    from django.apps import apps

    from n26.library.models.assignable import Assignable

    return [
        carrier
        for model in apps.get_app_config("library").get_models()
        if issubclass(model, Assignable)
        for carrier in model.objects.filter(modifiers=modifier)
    ]


def validate_income_choice(asset):
    """Validate the supported direct graph; return its declared choice."""
    if not asset.base_income_modifier_id:
        return None
    from n26.library.income import is_income_contribution
    from n26.library.models import Asset, DefaultAssignment, Modifier, Pickable, Slot

    def refuse(message):
        raise ValidationError({"base_income_modifier": message})

    modifier = asset.base_income_modifier
    if Modifier.objects.filter(adds_assignable__asset=asset).exists():
        refuse(
            "Selectable base income requires an owned asset assignment or a campaign holding."
        )
    if modifier.pack_id != asset.pack_id or not is_income_contribution(modifier):
        refuse("Select an unconditional gang Income contribution in this asset's pack.")
    if (
        Asset.objects.filter(base_income_modifier=modifier)
        .exclude(pk=asset.pk)
        .exists()
    ):
        refuse("Each asset needs its own base income modifier.")
    carriers = _carriers(modifier)
    if len(carriers) != 1 or not isinstance(carriers[0], Pickable):
        refuse("The base income modifier must belong to exactly one Income pickable.")
    pickable = carriers[0]
    if pickable.pack_id != asset.pack_id or pickable.built_ins_id:
        refuse(
            "The Income pickable must be in this asset's pack and have no built-ins."
        )
    if pickable.record_only:
        refuse("The Income pickable must apply its modifiers when selected.")
    grants = list(asset.modifiers.filter(adds_assignable__slot__isnull=False))
    if len(grants) != 1:
        refuse("The asset must directly grant exactly one boon choice.")
    grant = grants[0]
    slot = grant.adds_assignable.slot
    if (
        grant.targets_gang_id is None
        or grant.targets_gang.echoes
        or grant.targets_gang.is_conditional
        or grant.adds_assignable.with_pick_id is not None
        or slot.pack_id != asset.pack_id
        or slot.hidden
        or slot.mode != Slot.Mode.STANDARD
        or slot.assigned_to != "gang"
        or slot.min_picks != 1
        or slot.max_picks != 1
        or slot.follows_status
        or slot.built_ins_id
        or slot.modifiers.exists()
        or slot.picklist.dice
        or slot.picklist.pack_id != asset.pack_id
        or slot.slot_type_id != pickable.slot_type_id
        or slot.picklist.slot_type_id != slot.slot_type_id
        or not slot.slot_type.allows_repeats
    ):
        refuse("Use one visible, standard gang choice with exactly one pick.")
    if (
        _carriers(grant) != [asset]
        or Modifier.objects.filter(adds_assignable__slot=slot)
        .exclude(pk=grant.pk)
        .exists()
        or slot.picklist.slots.exclude(pk=slot.pk).exists()
        or pickable.listed_on.exclude(picklist=slot.picklist).exists()
        or not slot.picklist.members.filter(pickable=pickable).exists()
        or DefaultAssignment.objects.filter(slot=slot).exists()
        or DefaultAssignment.objects.filter(default_pickable=pickable).exists()
        or Modifier.objects.filter(adds_assignable__with_pick=pickable).exists()
    ):
        refuse("The Income option and its choice must belong only to this asset.")
    return IncomeChoice(slot, pickable, modifier)


def _affected_assets(rows):
    """Find declared assets linked to the content being edited."""
    from django.db.models import Model

    from n26.library.models import Asset

    query = Q(pk__in=[])
    paths = {
        "asset": ("pk",),
        "modifier": (
            "base_income_modifier_id",
            "modifiers",
            "modifiers__adds_assignable__slot__picklist__members__pickable__modifiers",
        ),
        "slot": ("modifiers__adds_assignable__slot",),
        "slottype": ("modifiers__adds_assignable__slot__slot_type",),
        "picklist": ("modifiers__adds_assignable__slot__picklist",),
        "picklistmember": ("modifiers__adds_assignable__slot__picklist__members",),
        "pickable": ("modifiers__adds_assignable__slot__picklist__members__pickable",),
        "targetsgang": (
            "base_income_modifier__targets_gang",
            "modifiers__targets_gang",
        ),
        "contributestocounter": ("base_income_modifier__contributes_to_counter",),
        "addsassignable": ("modifiers__adds_assignable",),
        "counter": ("base_income_modifier__contributes_to_counter__counter",),
    }

    def visit(value):
        nonlocal query
        if isinstance(value, Model):
            if value._meta.model_name == "addsassignable" and value.asset_id:
                query |= Q(pk=value.asset_id)
            if value._meta.model_name == "addsassignable" and value.slot_id:
                query |= Q(modifiers__adds_assignable__slot=value.slot_id)
            if value._meta.model_name == "addsassignable" and value.with_pick_id:
                query |= Q(
                    modifiers__adds_assignable__slot__picklist__members__pickable=value.with_pick_id
                )
            if value._meta.model_name == "defaultassignment" and value.slot_id:
                query |= Q(modifiers__adds_assignable__slot=value.slot_id)
            if (
                value._meta.model_name == "defaultassignment"
                and value.default_pickable_id
            ):
                query |= Q(
                    modifiers__adds_assignable__slot__picklist__members__pickable=value.default_pickable_id
                )
            for path in paths.get(value._meta.model_name, ()):
                query |= Q(**{path: value.pk})
        elif isinstance(value, (list, tuple, set)):
            for member in value:
                visit(member)

    for row in rows:
        visit(row)
    return Asset.objects.filter(query, base_income_modifier__isnull=False).distinct()


def preserves_income_choices(function):
    """Reject content edits that invalidate an existing Income declaration."""

    @wraps(function)
    def preserving(*args, **kwargs):
        # Attachment accepts arbitrary iterables. Materialise once so the
        # guard inspects the same modifiers that the write will attach.
        if function.__name__ == "attach_modifiers_to":
            if len(args) > 1:
                args = (args[0], tuple(args[1]), *args[2:])
            else:
                kwargs = {**kwargs, "modifiers": tuple(kwargs["modifiers"])}
        assets = list(_affected_assets((*args, *kwargs.values())))
        result = function(*args, **kwargs)
        for asset in assets:
            if type(asset).objects.filter(pk=asset.pk).exists():
                asset.refresh_from_db()
                if not asset.base_income_modifier_id:
                    raise ValidationError(
                        "An asset with selectable income must keep its base income modifier."
                    )
                validate_income_choice(asset)
        return result

    return preserving
