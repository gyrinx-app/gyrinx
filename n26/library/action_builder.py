"""Compile the action builder's draft through the public authoring verbs."""

import json

from django.core.exceptions import ValidationError
from django.db import transaction

from n26.library import authoring
from n26.library.forms import cross_pack_refusal
from n26.library.models import (
    Counter,
    Outcome,
    Profile,
    ProfileType,
    RankTable,
    Slot,
    SlotType,
    Subtype,
)
from n26.library.references import carrying_models


def _choice(model, pk, label):
    try:
        return (
            model.objects.outside_campaign_packs()
            .unarchived()
            .get(pk=pk, pack__owner__isnull=True)
        )
    except model.DoesNotExist, ValueError, TypeError, ValidationError:
        raise ValidationError(f"Choose a valid {label}.") from None


def _integer(value, label, *, minimum=0):
    try:
        number = int(value)
    except TypeError, ValueError:
        raise ValidationError(f"Enter a number for {label}.") from None
    if number < minimum:
        raise ValidationError(f"{label.capitalize()} must be at least {minimum}.")
    if number > 2_147_483_647:
        raise ValidationError(f"{label.capitalize()} is too large.")
    return number


def _outcome(spec):
    if not isinstance(spec, dict):
        raise ValidationError("Choose a valid outcome.")
    if spec.get("existing"):
        return _choice(Outcome, spec.get("existing"), "outcome")
    name = str(spec.get("name", "")).strip()
    if not name:
        raise ValidationError("Name every outcome.")
    kind = spec.get("operation")
    if kind == "augment":
        operation = authoring.augment_carried_item(
            _choice(SlotType, spec.get("slotType"), "tier slot type")
        )
    elif kind == "advancement":
        operation = authoring.resolve_advancement(
            _choice(Slot, spec.get("slot"), "advancement slot")
        )
    elif kind == "changes":
        changes = []
        if not isinstance(spec.get("changes"), list):
            raise ValidationError(f"Add valid changes to {name}.")
        for change in spec["changes"]:
            if not isinstance(change, dict):
                raise ValidationError(f"Add valid changes to {name}.")
            if change.get("kind") == "counter":
                if change.get("mode") not in ("set", "add", "subtract"):
                    raise ValidationError("Choose how the counter changes.")
                changes.append(
                    authoring.counter_change(
                        _choice(Counter, change.get("counter"), "counter"),
                        change.get("mode"),
                        _integer(change.get("amount"), "change amount", minimum=0),
                    )
                )
            elif change.get("kind") == "picks":
                changes.append(
                    authoring.remove_picks(
                        _choice(SlotType, change.get("slotType"), "slot type")
                    )
                )
            else:
                raise ValidationError("Choose a change type.")
        if not changes:
            raise ValidationError(f"Add a change to {name}.")
        operation = authoring.apply_changes(*changes)
    else:
        raise ValidationError("Choose what each outcome does.")
    outcome = authoring.create_outcome(name, operation=operation)
    return outcome


@transaction.atomic
def create_from_draft(raw):
    """Validate the whole draft and create one action atomically."""
    try:
        draft = json.loads(raw)
    except TypeError, ValueError:
        raise ValidationError(
            "The action draft could not be read. Reload and try again."
        ) from None
    if not isinstance(draft, dict):
        raise ValidationError(
            "The action draft could not be read. Reload and try again."
        )
    name = str(draft.get("name", "")).strip()
    if not name:
        raise ValidationError("Name the action.")
    timing = draft.get("timing")
    if timing not in ("recruitment", "post_cycle"):
        raise ValidationError("Choose when the action starts.")
    specs = draft.get("outcomes")
    if not isinstance(specs, list) or not specs:
        raise ValidationError("Add at least one outcome.")
    if len(specs) > 20:
        raise ValidationError("An action cannot have more than 20 outcomes.")
    mode = draft.get("useMode")
    allowance = None
    price = []
    if mode == "paid":
        parts = draft.get("prices")
        if not isinstance(parts, list) or not parts:
            raise ValidationError("Add a price or choose no use price.")
        for part in parts:
            if not isinstance(part, dict):
                raise ValidationError("Choose a valid price part.")
            resource = part.get("resource")
            if resource not in ("credits", "counter"):
                raise ValidationError("Choose a price resource.")
            payer = part.get("payer")
            if resource == "credits":
                payer = "gang"
            elif payer not in ("gang", "fighter"):
                raise ValidationError("Choose who pays the counter.")
            price.append(
                {
                    "resource": resource,
                    "payer": payer,
                    "amount": _integer(part.get("amount"), "price", minimum=1),
                    "counter": (
                        _choice(Counter, part.get("counter"), "price counter")
                        if resource == "counter"
                        else None
                    ),
                }
            )
    elif mode == "recruitment":
        if timing != "recruitment":
            raise ValidationError("Recruitment uses need recruitment timing.")
        allowance = authoring.recruitment_allowance_rule()
    elif mode == "rank":
        if timing != "post_cycle":
            raise ValidationError("Rank uses need after-cycle timing.")
        table = _choice(RankTable, draft.get("rankTable"), "rank table")
        counter = _choice(Counter, draft.get("rankCounter"), "rank counter")
        if table.counter_id != counter.pk:
            raise ValidationError("The rank table must use the selected counter.")
        allowance = authoring.rank_allowance_rule(counter)
    elif mode != "free":
        raise ValidationError("Choose how uses work.")
    outcomes = [_outcome(spec) for spec in specs]
    if len({row.pk for row in outcomes}) != len(outcomes):
        raise ValidationError("Each outcome can appear only once.")
    action = authoring.create_action(
        name,
        timing,
        outcomes=outcomes,
        use_price=price,
        allowance_rule=allowance,
        price=_integer(draft.get("acquisitionPrice", 0), "acquisition price"),
    )
    return action


@transaction.atomic
def grant_to_profiles(action, profile_ids):
    """Grant a live action to selected fighter entries, skipping existing grants."""
    if action.staged:
        raise ValidationError(
            "Put the action live before granting it to fighter entries."
        )
    if action.archived or action.pack.archived:
        raise ValidationError("Archived actions cannot be granted.")
    ids = list(dict.fromkeys(profile_ids))
    if not ids:
        raise ValidationError("Select at least one fighter entry.")
    profiles = list(
        Profile.objects.outside_campaign_packs()
        .unarchived()
        .filter(pk__in=ids)
        .select_related("pack", "profile_type")
    )
    if len(profiles) != len(ids) or any(
        p.profile_type.name != "Fighter" for p in profiles
    ):
        raise ValidationError("Select valid fighter entries.")
    for profile in profiles:
        refusal = cross_pack_refusal(profile.pack, action)
        if refusal:
            raise ValidationError(refusal)
    selected = {profile.pk for profile in profiles}
    shared_sets = {profile.built_ins_id for profile in profiles if profile.built_ins_id}
    if shared_sets:
        for model in carrying_models():
            if not hasattr(model, "built_ins"):
                continue
            others = model.objects.filter(built_ins_id__in=shared_sets)
            if model is Profile:
                others = others.exclude(pk__in=selected)
            if others.exists():
                raise ValidationError(
                    "A selected fighter entry shares its built-ins with other content. "
                    "Select every entry sharing that set, or give it separate built-ins first."
                )
    missing = [
        profile
        for profile in profiles
        if not profile.built_ins
        or not profile.built_ins.members.filter(action=action).exists()
    ]
    written_sets = set()
    for profile in missing:
        if profile.built_ins_id in written_sets:
            continue
        authoring.add_built_in(profile, action, pack=profile.pack)
        written_sets.add(profile.built_ins_id)
    return len(missing)


@transaction.atomic
def set_use_limit(action, value):
    """Narrow who may use a granted action; this never grants the action."""
    if action.archived or action.pack.archived:
        raise ValidationError(
            "You cannot change this action's use limit. The action or its pack is archived."
        )
    allowed = {"type": ProfileType, "subtype": Subtype, "entry": Profile}
    if value == "any":
        authoring.set_usable_by(
            action,
            usable_by_profile_types=[],
            usable_by_subtypes=[],
            usable_by_profiles=[],
        )
        return
    kind, separator, pk = value.partition(":")
    if not separator or kind not in allowed:
        raise ValidationError("Choose a valid use limit.")
    model = allowed[kind]
    try:
        row = model.objects.outside_campaign_packs().unarchived().get(pk=pk)
    except model.DoesNotExist, ValueError, TypeError, ValidationError:
        raise ValidationError("Choose a valid use limit.") from None
    refusal = cross_pack_refusal(action.pack, row)
    if refusal:
        raise ValidationError(refusal)
    if kind == "entry" and row.profile_type.name != "Fighter":
        raise ValidationError("Choose a fighter entry.")
    authoring.set_usable_by(
        action,
        usable_by_profile_types=[row] if kind == "type" else [],
        usable_by_subtypes=[row] if kind == "subtype" else [],
        usable_by_profiles=[row] if kind == "entry" else [],
    )
