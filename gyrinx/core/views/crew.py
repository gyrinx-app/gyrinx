"""Views for battle crews (#1346).

A crew is a virtual sub-gang assigned to a battle: the recipe (the scenario's
selection method, its numbers, and the card each chosen fighter brings) while it
is a draft, then the frozen attendees once it is locked at battle start. These
views cover the whole lifecycle — create, edit, lock, extras, archive — but
never write to the gang's canonical cost, credits, or audit stream. Once locked,
a crew is a historical record and can no longer be edited.

The selection method is URL state (``?method=custom|random|hybrid``): the
picker is a set of server-rendered links and the server returns the form
variant for that method. No JavaScript decides which fields exist — see the
"URL-Driven UI" convention.
"""

import uuid
from urllib.parse import urlencode

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse

from gyrinx.core.forms.crew import (
    CrewEligibilityForm,
    CrewForm,
    CrewLineItemForm,
    CrewLoadoutsForm,
)
from gyrinx.core.handlers.crew import (
    TOGGLEABLE_CREW_CATEGORIES,
    crew_battle_spread,
    crew_whole_gang_projection,
    eligible_crew_fighters_for_loadouts,
    handle_crew_archive,
    handle_crew_lock,
    handle_crew_loadouts_save,
    handle_crew_recipe_save,
)
from gyrinx.core.models import Battle
from gyrinx.core.models.crew import Crew, CrewLineItem
from gyrinx.core.models.list import List

VALID_METHODS = {value for value, _ in Crew.SELECTION_METHOD_CHOICES}


def _resolve_included(request, default=()):
    """The opted-in categories for this request, from the ``?include=`` toggles
    (comma-separated slugs) or the re-posted hidden field. Absent entirely →
    ``default`` (the crew's stored opt-ins on edit, nothing on create).

    Returns the canonical category values in display order, deduped; unknown
    slugs (a hand-edited URL or stale field) are dropped, so what gets persisted
    is always clean regardless of the raw string's order or repeats."""
    raw = request.GET.get("include")
    if raw is None:
        raw = request.POST.get("include")
    if raw is None:
        return list(default)
    slugs = set(raw.split(","))
    return [cat for cat, slug, _ in TOGGLEABLE_CREW_CATEGORIES if slug in slugs]


def _include_csv(included):
    """The include set as a canonical comma-separated slug string (display
    order) — what the ``?include=`` querystring and hidden field carry."""
    included = set(included)
    return ",".join(
        slug for cat, slug, _ in TOGGLEABLE_CREW_CATEGORIES if cat in included
    )


def _resolve_method(request, default):
    """The selection method for this request, from the URL (or the re-posted
    hidden field). A bad ``?method=`` is a navigation accident, not something to
    error on, so anything unrecognised silently falls back to ``default``."""
    method = request.GET.get("method") or request.POST.get("method")
    return method if method in VALID_METHODS else default


def _method_picker(*, base_url, current, extra=None):
    """Entries for the selection-method picker: one link per method, pointing at
    this same page with the method swapped. ``extra`` carries any query
    parameters the page needs to keep (the gang, on create)."""
    entries = []
    for value, label in Crew.SELECTION_METHOD_CHOICES:
        params = dict(extra or {}, method=value)
        entries.append(
            {
                "method": value,
                "label": label,
                "url": f"{base_url}?{urlencode(params)}",
                "is_current": value == current,
            }
        )
    return entries


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
    try:
        # Missing or malformed ?list= — can't identify a gang; fail closed with
        # a message rather than 500ing on a bad UUID in get_object_or_404.
        uuid.UUID(str(list_id))
    except ValueError:
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

    # Only a live crew counts: an archived crew is a withdrawn record and must
    # not stand in the way of picking a fresh one (nor be redirected to).
    existing = Crew.objects.filter(battle=battle, list=gang, archived=False).first()
    if existing:
        messages.info(request, f"{gang.name} already has a crew for this battle.")
        return _redirect_crew(existing)

    method = _resolve_method(request, Crew.CUSTOM)
    # A new crew's toggles start from the campaign's default (e.g. an Ash-Wastes
    # campaign that opts vehicle crew in for everyone); the player can still
    # change them per crew, and once toggled the ?include= drives it.
    included = _resolve_included(
        request, default=battle.campaign.default_included_crew_categories
    )

    if request.method == "POST":
        form = CrewForm(request.POST, gang=gang, method=method, included=included)
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
                    handle_crew_recipe_save(
                        user=request.user,
                        crew=crew,
                        method=method,
                        custom_count=form.cleaned_data.get("custom_count"),
                        chosen_fighters=form.cleaned_data.get("chosen_fighters"),
                        random_spec=form.cleaned_data.get("random_spec", ""),
                        equipment_sets=form.cleaned_data.get("equipment_sets"),
                        included_categories=included,
                    )
            except IntegrityError:
                existing = Crew.objects.filter(
                    battle=battle, list=gang, archived=False
                ).first()
                if existing:
                    messages.info(
                        request, f"{gang.name} already has a crew for this battle."
                    )
                    return _redirect_crew(existing)
                raise
            messages.success(request, "Crew created.")
            return _redirect_crew(crew)
    else:
        form = CrewForm(gang=gang, method=method, included=included)

    base_url = reverse("core:crew-new", args=[battle.id])
    method_extra = {"list": str(gang.id), "include": _include_csv(included)}
    return render(
        request,
        "core/crew/crew_form.html",
        {
            "form": form,
            "battle": battle,
            "gang": gang,
            "is_create": True,
            "method": method,
            "included_csv": _include_csv(included),
            "method_picker": _method_picker(
                base_url=base_url,
                current=method,
                extra=method_extra,
            ),
        },
    )


@login_required
def crew_detail(request, battle_id, crew_id):
    """Show a crew as an itemised receipt: attendees, extras, and the total.

    The headline rating is live until the battle ends, then what was fielded
    (see :meth:`Crew.rating`). Where that differs from what the crew was picked
    at, the page says so — before the battle because the gang has changed since
    selection, after it because the crew that fought wasn't quite the one
    chosen.
    """
    crew = _get_crew(battle_id, crew_id)
    receipt = crew.receipt()
    note = receipt["note"]
    can_manage = crew.can_manage(request.user)

    # A draft whole-gang crew has no members yet — the roster resolves at
    # battle start — so instead of an empty section, forecast it: who is
    # eligible now, the set each would bring, and what that would cost. Shown
    # as provisional; the confirmed crew legitimately differs if the gang
    # changes in the meantime.
    projection = None
    provisional_total = None
    if not crew.is_locked and crew.is_whole_gang and not receipt["attendees"]:
        projection = crew_whole_gang_projection(crew)
        # The receipt's own total is extras-only while there are no attendees.
        provisional_total = projection["total"] + receipt["total"]

    # Informational only: how far this crew sits below the highest crew in the
    # battle, in credits. Just the number — the humans decide what, if anything,
    # it entitles them to. None when the gap can't be worked out (no opponent
    # crew, or one still pending its draw) or this crew is the top.
    rating_gap = crew_battle_spread(crew)

    return render(
        request,
        "core/crew/crew.html",
        {
            "crew": crew,
            "battle": crew.battle,
            "can_manage": can_manage,
            "receipt": receipt,
            # Whether to show the note at all, and which of the two it is —
            # decided here so the template only reads flags.
            "show_rating_note": bool(note and note["differs"]),
            "rating_note": note,
            "projection": projection,
            "provisional_total": provisional_total,
            "can_edit_loadouts": bool(projection and can_manage),
            "rating_gap": rating_gap,
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

    # No ?method= (the plain "Edit" link) keeps the crew on the method it was
    # saved with. Likewise no ?include= keeps the crew's stored opt-ins.
    method = _resolve_method(request, crew.selection_method)
    included = _resolve_included(request, default=crew.included_categories)

    if request.method == "POST":
        gang = crew.list
        # Re-fetch under a row lock so a crew being locked concurrently can't
        # slip a recipe edit past the is_locked guard above — locked crews can
        # no longer be re-drawn (mirrors handle_crew_lock's own lock).
        crew = Crew.objects.select_for_update().get(pk=crew.pk)
        if crew.is_locked:
            messages.info(
                request, "This crew was just locked and can no longer be re-drawn."
            )
            return _redirect_crew(crew)
        form = CrewForm(
            request.POST, instance=crew, gang=gang, method=method, included=included
        )
        if form.is_valid():
            crew = form.save(commit=False)
            handle_crew_recipe_save(
                user=request.user,
                crew=crew,
                method=method,
                custom_count=form.cleaned_data.get("custom_count"),
                chosen_fighters=form.cleaned_data.get("chosen_fighters"),
                random_spec=form.cleaned_data.get("random_spec", ""),
                equipment_sets=form.cleaned_data.get("equipment_sets"),
                included_categories=included,
            )
            messages.success(request, "Crew updated.")
            return _redirect_crew(crew)
    else:
        form = CrewForm(instance=crew, gang=crew.list, method=method, included=included)

    base_url = reverse("core:crew-edit", args=[crew.battle_id, crew.id])
    method_extra = {"include": _include_csv(included)}
    return render(
        request,
        "core/crew/crew_form.html",
        {
            "form": form,
            "battle": crew.battle,
            "gang": crew.list,
            "crew": crew,
            "method": method,
            "included_csv": _include_csv(included),
            "method_picker": _method_picker(
                base_url=base_url,
                current=method,
                extra=method_extra,
            ),
        },
    )


@login_required
@transaction.atomic
def crew_eligibility_edit(request, battle_id, crew_id):
    """Set which of the gang's fighters are eligible for this crew — Included
    (always join), Eligible (may be picked or drawn), or Excluded — before the
    selection method picks from the pool. Sensible defaults per fighter, so most
    of the time it's a confirm; locked crews can't be changed.
    """
    crew = _get_crew(battle_id, crew_id)

    if not crew.can_manage(request.user):
        messages.error(
            request, "You don't have permission to edit this crew's eligibility."
        )
        return _redirect_crew(crew)

    if crew.is_locked:
        messages.info(
            request, "This crew is locked, so its eligibility can no longer change."
        )
        return _redirect_crew(crew)

    if request.method == "POST":
        # Re-fetch under a row lock so a crew being locked concurrently can't
        # slip an eligibility change past the guard above (mirrors crew_edit).
        crew = Crew.objects.select_for_update().get(pk=crew.pk)
        if crew.is_locked:
            messages.info(
                request,
                "This crew was just locked, so its eligibility can no longer change.",
            )
            return _redirect_crew(crew)
        form = CrewEligibilityForm(request.POST, crew=crew)
        if form.is_valid():
            form.save()
            crew.save_with_user(user=request.user)
            messages.success(request, "Crew eligibility updated.")
            return HttpResponseRedirect(
                reverse("core:crew-edit", args=[crew.battle_id, crew.id])
            )
    else:
        form = CrewEligibilityForm(crew=crew)

    return render(
        request,
        "core/crew/crew_eligibility.html",
        {
            "form": form,
            "crew": crew,
            "battle": crew.battle,
            "gang": crew.list,
        },
    )


@login_required
@transaction.atomic
def crew_loadouts(request, battle_id, crew_id):
    """Choose the equipment set each fighter brings when a whole-gang crew is
    confirmed.

    Whole-gang crews are the one case with nowhere else to say this: they have
    no members until the lock enrols the roster, so the choices are stored on
    the crew as advisory intent and read back by the same resolver the lock and
    the forecast use. Every other selection method asks for the card on the crew
    form itself (chosen fighters) or draws it at random, so those are sent
    there.
    """
    crew = _get_crew(battle_id, crew_id)

    if not crew.can_manage(request.user):
        messages.error(request, "You don't have permission to edit this crew.")
        return _redirect_crew(crew)

    if crew.is_locked:
        messages.info(
            request, "This crew is locked — its loadouts can no longer be changed."
        )
        return _redirect_crew(crew)

    if not (crew.is_whole_gang and not crew.members.exists()):
        messages.info(
            request,
            "Loadouts for this crew are chosen with its fighters — edit the crew.",
        )
        return _redirect_crew(crew)

    fighters = list(
        eligible_crew_fighters_for_loadouts(
            crew.list, included=crew.included_categories
        )
    )

    if request.method == "POST":
        form = CrewLoadoutsForm(request.POST, crew=crew, fighters=fighters)
        if form.is_valid():
            handle_crew_loadouts_save(
                user=request.user, crew=crew, choices=form.loadout_choices()
            )
            messages.success(request, "Loadouts saved.")
            return _redirect_crew(crew)
    else:
        form = CrewLoadoutsForm(crew=crew, fighters=fighters)

    return render(
        request,
        "core/crew/crew_loadouts.html",
        {"form": form, "crew": crew, "battle": crew.battle},
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

    chosen_count = crew.members.count()
    return render(
        request,
        "core/crew/crew_lock.html",
        {
            "crew": crew,
            "battle": crew.battle,
            "chosen_count": chosen_count,
            # Custom Selection with no number in brackets and nobody chosen =
            # the whole eligible roster attends.
            "whole_gang": crew.is_whole_gang and not chosen_count,
        },
    )


@login_required
@transaction.atomic
def crew_archive(request, battle_id, crew_id):
    """Archive a crew: withdraw it from the battle but keep it as a record.

    Not a delete — the crew's members and extras are kept and its detail page
    still renders. Archiving frees the gang to pick a fresh crew for the same
    battle (the unique constraint is conditional on ``archived=False``) and is
    logged as a battle-linked CampaignAction (see ``handle_crew_archive``).
    ``can_manage`` returns False once a crew is archived, so this also guards
    against re-archiving one.
    """
    crew = _get_crew(battle_id, crew_id)
    battle = crew.battle

    # Checked before can_manage: an archived crew fails that too, and "no
    # permission" would be the wrong message for its owner trying again.
    if crew.archived:
        messages.info(request, "This crew has already been archived.")
        return _redirect_crew(crew)

    if not crew.can_manage(request.user):
        messages.error(request, "You don't have permission to archive this crew.")
        return _redirect_crew(crew)

    if request.method == "POST":
        try:
            handle_crew_archive(user=request.user, crew=crew)
        except ValidationError as exc:
            # The loser of a concurrent double-archive.
            messages.info(request, exc.messages[0])
            return _redirect_crew(crew)
        messages.success(request, "Crew archived.")
        return _redirect_battle(battle)

    return render(
        request,
        "core/crew/crew_archive.html",
        {"crew": crew, "battle": battle},
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

    # Extras — hired guns, balancing credits — are worked out once the crew is
    # set: the underdog allowance is calculated after crews are chosen, and a
    # random/hybrid crew isn't even known until the draw. So a *new* extra can
    # only be added to a locked crew (editing an existing one is always fine).
    if item is None and not crew.is_locked:
        messages.info(
            request, "Confirm the crew first — extras are added once it's set."
        )
        return _redirect_crew(crew)

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
