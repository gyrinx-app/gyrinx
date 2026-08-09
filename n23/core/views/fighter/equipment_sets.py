"""Fighter equipment-set (Tools of the Trade) views.

Equipment sets are "cards": named subsets of a fighter's equipment that let a
fighter field different loadouts (see #1853). Selecting a set is display-only —
it never changes the fighter's canonical cost, so these views mutate only the
set rows / the fighter's ``active_equipment_set`` and never touch the cost,
credits, audit or pinning machinery.
"""

from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import Http404, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx import messages
from gyrinx.analytics.models import EventVerb, log_event
from gyrinx.http import safe_redirect
from n23.core.events import EventNoun
from n23.core.models.list import ListFighterEquipmentSet
from n23.core.views.fighter.permissions import get_list_and_fighter


def _manage_url(lst, fighter):
    return reverse("core:list-fighter-equipment-sets", args=(lst.id, fighter.id))


def _list_anchor_url(lst, fighter):
    return reverse("core:list", args=(lst.id,)) + f"#{fighter.id}"


def _requires_rule_redirect(request, lst, fighter):
    """Guard for mutation views: block fighters without the rule.

    Returns a redirect response when the fighter lacks the "Tools of the Trade"
    rule, else None. The display views render a message instead.
    """
    if fighter.has_tools_of_the_trade:
        return None
    messages.error(
        request, "This fighter does not have the requisite rule (Tools of the Trade)."
    )
    return HttpResponseRedirect(_manage_url(lst, fighter))


def _direct_assignment_options(fighter):
    """The fighter's direct (non-default) assignments as display wrappers.

    Returns the ``VirtualListFighterEquipmentAssignment`` wrappers for the
    fighter's own assignments — the toggleable items in a set. Default template
    kit is always shown and is not part of set membership (v1, #1853).
    """
    return [va for va in fighter.assignments() if va.kind() == "assigned"]


@login_required
def edit_list_fighter_equipment_sets(request, id, fighter_id):
    """
    Manage the equipment sets (cards) of a :model:`core.ListFighter`.

    **Template**

    :template:`core/list_fighter_equipment_sets.html`
    """
    lst, fighter, _perms = get_list_and_fighter(request, id, fighter_id)

    if not fighter.has_tools_of_the_trade:
        return render(
            request,
            "core/list_fighter_equipment_sets.html",
            {"list": lst, "fighter": fighter},
        )

    active_id = fighter.active_equipment_set_id
    # Resolve item names from the fighter's already-prefetched direct
    # assignments (which carry content_equipment) so building the summaries adds
    # no queries — the set membership is prefetched via equipment_sets__assignments.
    name_by_assignment = {
        a.id: a.content_equipment.name
        for a in fighter.listfighterequipmentassignment_set.all()
    }
    equipment_sets = [
        {
            "set": s,
            "is_active": s.id == active_id,
            "item_names": [
                name_by_assignment[a.id]
                for a in s.assignments.all()
                if a.id in name_by_assignment
            ],
        }
        for s in fighter.equipment_sets.all()
    ]

    return render(
        request,
        "core/list_fighter_equipment_sets.html",
        {
            "list": lst,
            "fighter": fighter,
            "equipment_sets": equipment_sets,
            "has_active_set": bool(active_id),
        },
    )


@login_required
def edit_list_fighter_equipment_set(request, id, fighter_id, set_id):
    """
    Edit which of a fighter's assignments belong to a single equipment set.

    **Template**

    :template:`core/list_fighter_equipment_set_edit.html`
    """
    lst, fighter, _perms = get_list_and_fighter(request, id, fighter_id)

    if not fighter.has_tools_of_the_trade:
        # POST can't mutate without the rule — redirect like the other mutation
        # views; GET shows the explanatory message.
        if request.method == "POST":
            return _requires_rule_redirect(request, lst, fighter)
        return render(
            request,
            "core/list_fighter_equipment_sets.html",
            {"list": lst, "fighter": fighter},
        )

    equipment_set = get_object_or_404(
        ListFighterEquipmentSet, id=set_id, list_fighter=fighter
    )

    options = _direct_assignment_options(fighter)

    if request.method == "POST":
        selected_ids = set(request.POST.getlist("assignment"))
        # Validate against this fighter's own assignments in a single scoped
        # query, so only genuine ids are accepted (no coupling to the virtual
        # wrapper internals).
        chosen = list(
            fighter.listfighterequipmentassignment_set.filter(id__in=selected_ids)
        )
        # The card is named here too (rename lives on the edit page).
        name = (request.POST.get("name") or "").strip()
        with transaction.atomic():
            if name:
                equipment_set.name = name
            equipment_set.assignments.set(chosen)
            equipment_set.save_with_user(user=request.user)

        log_event(
            user=request.user,
            noun=EventNoun.LIST_FIGHTER,
            verb=EventVerb.UPDATE,
            object=fighter,
            request=request,
            fighter_name=fighter.name,
            list_id=str(lst.id),
            list_name=lst.name,
            field="equipment_sets",
            action="update_set_membership",
            equipment_set_name=equipment_set.name,
            item_count=len(chosen),
        )

        messages.success(request, f"Updated {equipment_set.name}")
        return HttpResponseRedirect(_manage_url(lst, fighter))

    included_ids = set(equipment_set.assignments.values_list("id", flat=True))
    # Expose plain fields — Django templates can't read the leading-underscore
    # ``_assignment`` attribute on the virtual wrapper.
    items = [
        {
            "id": va.id,
            "name": va.name(),
            "is_weapon": va.is_weapon_cached,
            "included": va.id in included_ids,
        }
        for va in options
    ]

    return render(
        request,
        "core/list_fighter_equipment_set_edit.html",
        {
            "list": lst,
            "fighter": fighter,
            "equipment_set": equipment_set,
            "items": items,
        },
    )


@login_required
def create_list_fighter_equipment_set(request, id, fighter_id):
    """
    Create a new equipment set (card), seeded with all of the fighter's
    current equipment, then jump to editing its membership.
    """
    if request.method != "POST":
        raise Http404()

    lst, fighter, _perms = get_list_and_fighter(request, id, fighter_id)
    guard = _requires_rule_redirect(request, lst, fighter)
    if guard:
        return guard

    name = (request.POST.get("name") or "").strip()
    if not name:
        messages.error(request, "Please give the card a name.")
        return HttpResponseRedirect(_manage_url(lst, fighter))

    with transaction.atomic():
        equipment_set = ListFighterEquipmentSet.objects.create_with_user(
            user=request.user,
            list_fighter=fighter,
            name=name,
            owner=lst.owner,
        )
        # Seed with every current direct assignment; the user then trims it.
        equipment_set.assignments.set(fighter._direct_assignments())

    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.CREATE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        field="equipment_sets",
        action="create_set",
        equipment_set_name=name,
    )

    messages.success(request, f"Created {name}")
    return HttpResponseRedirect(
        reverse(
            "core:list-fighter-equipment-set-edit",
            args=(lst.id, fighter.id, equipment_set.id),
        )
    )


@login_required
def rename_list_fighter_equipment_set(request, id, fighter_id, set_id):
    """Rename an equipment set."""
    if request.method != "POST":
        raise Http404()

    lst, fighter, _perms = get_list_and_fighter(request, id, fighter_id)
    guard = _requires_rule_redirect(request, lst, fighter)
    if guard:
        return guard
    equipment_set = get_object_or_404(
        ListFighterEquipmentSet, id=set_id, list_fighter=fighter
    )

    name = (request.POST.get("name") or "").strip()
    if not name:
        messages.error(request, "Please give the card a name.")
        return HttpResponseRedirect(_manage_url(lst, fighter))

    equipment_set.name = name
    equipment_set.save_with_user(user=request.user)

    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.UPDATE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        field="equipment_sets",
        action="rename_set",
        equipment_set_name=name,
    )

    messages.success(request, f"Renamed to {name}")
    return HttpResponseRedirect(_manage_url(lst, fighter))


@login_required
def delete_list_fighter_equipment_set(request, id, fighter_id, set_id):
    """Delete an equipment set. If it was active, fall back to the Default card."""
    if request.method != "POST":
        raise Http404()

    lst, fighter, _perms = get_list_and_fighter(request, id, fighter_id)
    guard = _requires_rule_redirect(request, lst, fighter)
    if guard:
        return guard
    equipment_set = get_object_or_404(
        ListFighterEquipmentSet, id=set_id, list_fighter=fighter
    )
    name = equipment_set.name

    with transaction.atomic():
        if fighter.active_equipment_set_id == equipment_set.id:
            fighter.active_equipment_set = None
            fighter.save_with_user(
                user=request.user,
                update_fields=["active_equipment_set", "modified"],
            )
        # Attribute the SimpleHistory delete record to the acting user.
        equipment_set._history_user = request.user
        equipment_set.delete()

    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.DELETE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        field="equipment_sets",
        action="delete_set",
        equipment_set_name=name,
    )

    messages.success(request, f"Deleted {name}")
    return HttpResponseRedirect(_manage_url(lst, fighter))


@login_required
def activate_list_fighter_equipment_set(request, id, fighter_id, set_id):
    """Make an equipment set the fighter's active card."""
    if request.method != "POST":
        raise Http404()

    lst, fighter, _perms = get_list_and_fighter(request, id, fighter_id)
    guard = _requires_rule_redirect(request, lst, fighter)
    if guard:
        return guard
    equipment_set = get_object_or_404(
        ListFighterEquipmentSet, id=set_id, list_fighter=fighter
    )

    fighter.active_equipment_set = equipment_set
    fighter.save_with_user(
        user=request.user, update_fields=["active_equipment_set", "modified"]
    )

    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.ACTIVATE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        field="equipment_sets",
        action="activate_set",
        equipment_set_name=equipment_set.name,
    )

    messages.success(request, f"Now showing {equipment_set.name}")
    # The manage page passes ?next so it stays put; the card switcher omits it
    # and returns to the fighter on the list.
    return safe_redirect(
        request, request.POST.get("next"), _list_anchor_url(lst, fighter)
    )


@login_required
def activate_default_equipment_set(request, id, fighter_id):
    """Switch the fighter back to the implicit Default card (show everything)."""
    if request.method != "POST":
        raise Http404()

    lst, fighter, _perms = get_list_and_fighter(request, id, fighter_id)
    guard = _requires_rule_redirect(request, lst, fighter)
    if guard:
        return guard

    fighter.active_equipment_set = None
    fighter.save_with_user(
        user=request.user, update_fields=["active_equipment_set", "modified"]
    )

    log_event(
        user=request.user,
        noun=EventNoun.LIST_FIGHTER,
        verb=EventVerb.ACTIVATE,
        object=fighter,
        request=request,
        fighter_name=fighter.name,
        list_id=str(lst.id),
        list_name=lst.name,
        field="equipment_sets",
        action="activate_default",
    )

    messages.success(request, "Now showing all equipment (Default)")
    return safe_redirect(
        request, request.POST.get("next"), _list_anchor_url(lst, fighter)
    )
