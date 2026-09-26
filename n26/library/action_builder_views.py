"""The guided staff pages for creating and granting fighter actions."""

from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from n26.library.action_builder import (
    create_from_draft,
    grant_to_profiles,
    set_use_limit,
)
from n26.library.forms import cross_pack_refusal
from n26.library.models import (
    Action,
    Counter,
    Outcome,
    Profile,
    ProfileType,
    RankTable,
    Slot,
    SlotType,
    Subtype,
)


def _options(model):
    return [
        {"value": str(row.pk), "label": str(row)}
        for row in model.objects.outside_campaign_packs()
        .unarchived()
        .filter(pack__owner__isnull=True)
    ]


def _outcome_detail(row):
    if row.augment_carried_item_id:
        return f"Advance a carried item in {row.augment_carried_item.slot_type}"
    if row.resolve_advancement_id:
        return f"Resolve the {row.resolve_advancement.slot} slot"
    details = []
    for member in row.apply_changes.changes.all():
        if member.counter_change_id:
            change = member.counter_change
            if change.mode == "set":
                details.append(f"Set {change.counter} to {change.amount}")
            elif change.mode == "add":
                details.append(f"Add {change.amount} to {change.counter}")
            else:
                details.append(f"Subtract {change.amount} from {change.counter}")
        else:
            details.append(f"Remove picks from {member.remove_picks.slot_type}")
    return "; ".join(details)


@staff_member_required
def new_action(request):
    error = None
    draft = request.POST.get("draft", "") if request.method == "POST" else ""
    if request.method == "POST":
        try:
            action = create_from_draft(draft)
        except (ValidationError, IntegrityError) as refused:
            error = (
                "; ".join(refused.messages)
                if isinstance(refused, ValidationError)
                else ("An action or outcome with that name already exists.")
            )
        else:
            messages.success(request, f"Created {action.name}.")
            return redirect("authoring-action-grant", pk=action.pk)
    return render(
        request,
        "authoring/action_builder.html",
        {
            "kind": "action",
            "error": error,
            "builder": {
                "draft": draft,
                "counters": _options(Counter),
                "rankTables": [
                    {
                        "value": str(row.pk),
                        "label": str(row),
                        "counter": str(row.counter_id),
                    }
                    for row in RankTable.objects.outside_campaign_packs()
                    .unarchived()
                    .filter(pack__owner__isnull=True)
                    .select_related("counter")
                ],
                "slotTypes": _options(SlotType),
                "slots": _options(Slot),
                "outcomes": [
                    {
                        "value": str(row.pk),
                        "label": row.name,
                        "detail": _outcome_detail(row),
                    }
                    for row in Outcome.objects.outside_campaign_packs()
                    .unarchived()
                    .filter(pack__owner__isnull=True)
                    .select_related(
                        "augment_carried_item__slot_type",
                        "resolve_advancement__slot",
                        "apply_changes",
                    )
                    .prefetch_related(
                        "apply_changes__changes__counter_change__counter",
                        "apply_changes__changes__remove_picks__slot_type",
                    )
                ],
            },
        },
    )


@staff_member_required
def grant_action(request, pk):
    action = get_object_or_404(
        Action.objects.outside_campaign_packs()
        .select_related("pack")
        .prefetch_related(
            "usable_by_profile_types", "usable_by_subtypes", "usable_by_profiles"
        ),
        pk=pk,
    )
    error = None
    if request.method == "POST":
        try:
            if request.POST.get("act") == "use_limit":
                set_use_limit(action, request.POST.get("use_limit", ""))
            else:
                count = grant_to_profiles(action, request.POST.getlist("profiles"))
        except ValidationError as refused:
            error = "; ".join(refused.messages)
        else:
            if request.POST.get("act") == "use_limit":
                messages.success(request, f"Updated who may use {action.name}.")
                return redirect("authoring-action-grant", pk=action.pk)
            messages.success(
                request,
                f"Granted {action.name} to {count} fighter entr{'y' if count == 1 else 'ies'}.",
            )
            return redirect("authoring-detail", kind="action", pk=action.pk)
    profiles = list(
        Profile.objects.outside_campaign_packs()
        .unarchived()
        .filter(profile_type__name="Fighter")
        .select_related("gang_type", "profile_type", "built_ins", "pack")
        .prefetch_related("built_ins__members")
        .order_by("gang_type__name", "name")
    )
    rows = [
        {
            "pk": str(row.pk),
            "name": row.name,
            "gang": row.gang_type.name,
            "granted": bool(
                row.built_ins
                and any(
                    not member.archived and member.action_id == action.pk
                    for member in row.built_ins.members.all()
                )
            ),
        }
        for row in profiles
        if not cross_pack_refusal(row.pack, action)
    ]
    limits = [
        *(f"type:{row.pk}" for row in action.usable_by_profile_types.all()),
        *(f"subtype:{row.pk}" for row in action.usable_by_subtypes.all()),
        *(f"entry:{row.pk}" for row in action.usable_by_profiles.all()),
    ]
    limit_options = []
    for kind, model in (
        ("type", ProfileType),
        ("subtype", Subtype),
        ("entry", Profile),
    ):
        source = (
            model.objects.outside_campaign_packs().unarchived().select_related("pack")
        )
        if kind == "entry":
            source = source.filter(profile_type__name="Fighter").select_related(
                "gang_type", "profile_type"
            )
        elif kind == "type":
            source = source.filter(name="Fighter")
        limit_options.extend(
            {
                "value": f"{kind}:{row.pk}",
                "label": f"{row} ({model._meta.verbose_name})",
            }
            for row in source
            if not cross_pack_refusal(action.pack, row)
        )
    return render(
        request,
        "authoring/action_grant.html",
        {
            "kind": "action",
            "action": action,
            "is_archived": action.archived or action.pack.archived,
            "rows": rows,
            "grant_rows": {"rows": rows},
            "error": error,
            "current_limit": limits[0]
            if len(limits) == 1
            else "any"
            if not limits
            else "custom",
            "limit_options": limit_options,
        },
    )
