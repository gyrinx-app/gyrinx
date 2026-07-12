"""Views for battle crews (#1346).

A crew is a virtual sub-gang assigned to a battle: the recipe (chosen fighters
+ a random-draw spec) while it is a draft, then the frozen attendees once it is
locked at battle start. These views cover the whole lifecycle — create, edit,
lock, per-member loadout, extras, delete — but never write to the gang's
canonical cost, credits, or audit stream.
"""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx.core.forms.crew import (
    CrewForm,
    CrewLineItemForm,
    CrewMemberLoadoutForm,
)
from gyrinx.core.handlers.crew import handle_crew_lock
from gyrinx.core.models import Battle
from gyrinx.core.models.crew import Crew, CrewLineItem, CrewMember
from gyrinx.core.models.list import List


def _get_battle(battle_id):
    return get_object_or_404(
        Battle.objects.select_related("campaign", "owner"), id=battle_id
    )


def _get_crew(battle_id, crew_id):
    return get_object_or_404(
        Crew.objects.select_related("battle", "battle__campaign", "list", "owner"),
        id=crew_id,
        battle_id=battle_id,
    )


def _redirect_crew(crew):
    return HttpResponseRedirect(reverse("core:crew", args=[crew.battle_id, crew.id]))


def _redirect_battle(battle):
    return HttpResponseRedirect(reverse("core:battle", args=[battle.id]))


@login_required
@transaction.atomic
def crew_new(request, battle_id):
    """Create a crew for one of a battle's gangs (gang chosen via ``?list=``)."""
    battle = _get_battle(battle_id)

    list_id = request.POST.get("list") or request.GET.get("list")
    if not list_id:
        messages.error(request, "No gang was specified for the crew.")
        return _redirect_battle(battle)
    gang = get_object_or_404(List, id=list_id)

    if not battle.participants.filter(pk=gang.pk).exists():
        messages.error(request, "That gang is not taking part in this battle.")
        return _redirect_battle(battle)

    if not Crew.can_manage_new(request.user, battle, gang):
        messages.error(
            request, "You don't have permission to add a crew for that gang."
        )
        return _redirect_battle(battle)

    existing = Crew.objects.filter(battle=battle, list=gang).first()
    if existing:
        messages.info(request, f"{gang.name} already has a crew for this battle.")
        return _redirect_crew(existing)

    if request.method == "POST":
        form = CrewForm(request.POST, gang=gang)
        if form.is_valid():
            crew = form.save(commit=False)
            crew.battle = battle
            crew.list = gang
            # Owned by the gang's player (list-scoped convention), even when an
            # arbitrator creates it; save_with_user records who acted.
            crew.owner_id = gang.owner_id
            try:
                # Savepoint so a lost race on the (battle, list) unique
                # constraint rolls back cleanly and leaves the outer
                # transaction usable for the redirect lookup below.
                with transaction.atomic():
                    crew.save_with_user(user=request.user)
                    crew.chosen_fighters.set(form.cleaned_data["chosen_fighters"])
            except IntegrityError:
                existing = Crew.objects.filter(battle=battle, list=gang).first()
                if existing:
                    messages.info(
                        request, f"{gang.name} already has a crew for this battle."
                    )
                    return _redirect_crew(existing)
                raise
            messages.success(request, "Crew created.")
            return _redirect_crew(crew)
    else:
        form = CrewForm(gang=gang)

    return render(
        request,
        "core/crew/crew_form.html",
        {"form": form, "battle": battle, "gang": gang, "is_create": True},
    )


@login_required
def crew_detail(request, battle_id, crew_id):
    """Show a crew as an itemised receipt: attendees, extras, and the total."""
    crew = _get_crew(battle_id, crew_id)

    return render(
        request,
        "core/crew/crew.html",
        {
            "crew": crew,
            "battle": crew.battle,
            "can_manage": crew.can_manage(request.user),
            "receipt": crew.receipt(),
        },
    )


@login_required
@transaction.atomic
def crew_edit(request, battle_id, crew_id):
    """Edit a draft crew's recipe. Locked crews can't be re-drawn."""
    crew = _get_crew(battle_id, crew_id)

    if not crew.can_manage(request.user):
        messages.error(request, "You don't have permission to edit this crew.")
        return _redirect_crew(crew)

    if crew.is_locked:
        messages.info(request, "This crew is locked and can no longer be re-drawn.")
        return _redirect_crew(crew)

    if request.method == "POST":
        form = CrewForm(request.POST, instance=crew, gang=crew.list)
        if form.is_valid():
            crew = form.save(commit=False)
            crew.save_with_user(user=request.user)
            crew.chosen_fighters.set(form.cleaned_data["chosen_fighters"])
            messages.success(request, "Crew updated.")
            return _redirect_crew(crew)
    else:
        form = CrewForm(instance=crew, gang=crew.list)

    return render(
        request,
        "core/crew/crew_form.html",
        {"form": form, "battle": crew.battle, "gang": crew.list, "crew": crew},
    )


@login_required
@transaction.atomic
def crew_lock(request, battle_id, crew_id):
    """Lock (draw) a crew: roll the random spec and freeze the attendees."""
    crew = _get_crew(battle_id, crew_id)

    if not crew.can_manage(request.user):
        messages.error(request, "You don't have permission to lock this crew.")
        return _redirect_crew(crew)

    if crew.is_locked:
        messages.info(request, "This crew is already locked.")
        return _redirect_crew(crew)

    if request.method == "POST":
        try:
            result = handle_crew_lock(user=request.user, crew=crew)
        except ValidationError as exc:
            messages.error(request, exc.messages[0])
            return _redirect_crew(crew)

        if result.whole_gang:
            messages.success(
                request,
                f"Crew set: whole gang ({result.chosen_count} fighters).",
            )
        elif result.random_count or result.roll_detail:
            detail = f" — {result.roll_detail}" if result.roll_detail else ""
            messages.success(
                request,
                f"Crew rolled: {result.chosen_count} chosen, "
                f"{result.random_count} random{detail}.",
            )
        else:
            messages.success(
                request,
                f"Crew set: {result.chosen_count} chosen.",
            )
        if result.skipped_ineligible:
            n = result.skipped_ineligible
            noun = "fighter" if n == 1 else "fighters"
            was = "was" if n == 1 else "were"
            messages.warning(
                request,
                f"{n} chosen {noun} {was} skipped — no longer available for a crew.",
            )
        return _redirect_crew(crew)

    chosen_fighters = list(crew.chosen_fighters.all())
    return render(
        request,
        "core/crew/crew_lock.html",
        {
            "crew": crew,
            "battle": crew.battle,
            "chosen_fighters": chosen_fighters,
            # No picks and no random draw = the whole eligible roster attends.
            "whole_gang": not chosen_fighters and not (crew.random_spec or "").strip(),
        },
    )


@login_required
@transaction.atomic
def crew_delete(request, battle_id, crew_id):
    """Delete a crew and its members/extras."""
    crew = _get_crew(battle_id, crew_id)
    battle = crew.battle

    if not crew.can_manage(request.user):
        messages.error(request, "You don't have permission to delete this crew.")
        return _redirect_crew(crew)

    if request.method == "POST":
        crew.delete()
        messages.success(request, "Crew deleted.")
        return _redirect_battle(battle)

    return render(
        request,
        "core/crew/crew_delete.html",
        {"crew": crew, "battle": battle},
    )


@login_required
@transaction.atomic
def crew_member_loadout(request, battle_id, crew_id, member_id):
    """Choose the equipment set a locked crew member brings to the battle."""
    crew = _get_crew(battle_id, crew_id)

    if not crew.can_manage(request.user):
        messages.error(request, "You don't have permission to edit this crew.")
        return _redirect_crew(crew)

    member = get_object_or_404(
        CrewMember.objects.select_related("list_fighter"), id=member_id, crew=crew
    )

    if request.method == "POST":
        form = CrewMemberLoadoutForm(request.POST, instance=member)
        if form.is_valid():
            member = form.save(commit=False)
            member.save_with_user(user=request.user)
            messages.success(request, "Loadout updated.")
            return _redirect_crew(crew)
    else:
        form = CrewMemberLoadoutForm(instance=member)

    return render(
        request,
        "core/crew/crew_member_loadout.html",
        {"form": form, "crew": crew, "battle": crew.battle, "member": member},
    )


@login_required
@transaction.atomic
def crew_extra(request, battle_id, crew_id, item_id=None):
    """Add or edit a crew extra (tactics card, etc.)."""
    crew = _get_crew(battle_id, crew_id)

    if not crew.can_manage(request.user):
        messages.error(request, "You don't have permission to edit this crew.")
        return _redirect_crew(crew)

    item = None
    if item_id is not None:
        item = get_object_or_404(CrewLineItem, id=item_id, crew=crew)

    if request.method == "POST":
        form = CrewLineItemForm(request.POST, instance=item)
        if form.is_valid():
            line_item = form.save(commit=False)
            line_item.crew = crew
            # Owned by the gang's player, matching the crew and its members.
            line_item.owner_id = crew.list.owner_id
            line_item.save_with_user(user=request.user)
            messages.success(request, "Extra saved.")
            return _redirect_crew(crew)
    else:
        form = CrewLineItemForm(instance=item)

    return render(
        request,
        "core/crew/crew_extra_form.html",
        {"form": form, "crew": crew, "battle": crew.battle, "item": item},
    )


@login_required
@transaction.atomic
def crew_extra_delete(request, battle_id, crew_id, item_id):
    """Delete a crew extra (POST only)."""
    crew = _get_crew(battle_id, crew_id)

    if not crew.can_manage(request.user):
        messages.error(request, "You don't have permission to edit this crew.")
        return _redirect_crew(crew)

    item = get_object_or_404(CrewLineItem, id=item_id, crew=crew)

    if request.method == "POST":
        item.delete()
        messages.success(request, "Extra removed.")

    return _redirect_crew(crew)
