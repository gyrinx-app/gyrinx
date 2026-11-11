"""Select skills and powers through a model's placed grids or checkbox editor.

The dedicated skills page limits offers to placed tiers. The edit-page offer
includes every skill and power set, grouped into placed or already-held sets
and the remaining options. These partitions affect presentation only.

Normally selections are free assignments with no cause. When a selected skill
matches an unresolved starting-skill offer, settle that offer instead so it
stops requesting a duplicate starting skill. Removing that selection reopens it.
Computed grants remain fixed because no stored assignment can be removed.
"""

import dataclasses
from urllib.parse import urlencode
from uuid import uuid4

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404, JsonResponse
from django.middleware.csrf import get_token
from django.shortcuts import redirect, render
from django.urls import reverse
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_http_methods, require_POST

from n26.core import skill_selection, skills_workflow
from n26.core.skill_selection import content_key as _key
from n26.core.views.permissions import _own_gang_or_404, _own_miniature_or_404


def link_skills(*cards, among=None):
    """Link placed card skill grids to the model's checkbox editor.

    Read selectable collections once for all cards, or reuse ``among``.
    Preview cards without model identifiers remain unlinked.
    """
    from n26.core.access import model_collections

    selectable = {
        str(collection.pk)
        for collection in (model_collections() if among is None else among)
    }
    for card in cards:
        if card.id and set(card.placed_in) & selectable:
            card.skills_href = (
                reverse("n26-edit-fighter", args=[card.id]) + "#n26-skills-box"
            )


def _rows_on(card):
    """Index unsuppressed, non-broadcast root assignments by content identity."""
    rows = {}
    for node in card.roots:
        if node.broadcast or node.suppressed or node.assignment is None:
            continue
        rows.setdefault(_key(node.assignable), node.assignment)
    return rows


def _grants_on(computed):
    """Index computed skill and power grants with their granting sources."""
    return {
        _key(contribution.thing): contribution.source
        for contribution in (*computed.skills, *computed.powers)
    }


@dataclasses.dataclass(frozen=True)
class SkillsOffer:
    """One complete offer and its presentation partitions.

    Apply saves against ``everything``; ``own`` and ``rest`` only organise display.
    """

    #: Complete grouped offer used for saving and the All sets tab.
    everything: object
    #: Placed or already-held sets, including skills from outside the model's grid.
    own: object
    #: Flattened remaining options for search.
    rest: list


def _sets_on_offer(card, computed, among=None, *, include_staged=False):
    """Browse all skill and power collections, retaining fallback tiers.

    Mark tiers reached by placements and preserve section captions when the
    collection has several tiers. Query each collection independently so the
    editor can also offer unplaced sets.
    """
    from n26.core.access import model_collections
    from n26.core.browse import (
        EQUIPMENT_LIST,
        browse,
        narrow,
        placements_for,
        regrouped_by_placement,
        usability_for,
        with_use_notes,
    )
    from n26.core.render import offer_from_view
    from n26.library.models import Power, Skill

    held = _rows_on(card)
    granted = _grants_on(computed)
    found = []
    for collection in model_collections() if among is None else among:
        placements = placements_for(computed, collection)
        placed = {placement.section.name for placement in placements.values()}
        listed = with_use_notes(
            regrouped_by_placement(
                # Exclude subtypes because their checkbox editor uses a different write path.
                # Including them here could remove subtypes absent from this form's submitted skills.
                narrow(
                    browse(collection, EQUIPMENT_LIST, include_staged=include_staged),
                    kinds=(Skill, Power),
                ),
                placements,
                fallback=collection.default_section(),
                name=str(collection),
            ),
            usability_for(computed),
        )
        tiered = len(listed.sections) > 1
        for section in listed.sections:
            offer = offer_from_view(
                dataclasses.replace(listed, sections=[section]),
                label=str(collection),
                held=held,
                granted=granted,
            )
            for group in offer.groups:
                if tiered:
                    group.caption = section.name
                found.append((section.name in placed, group))
    return found


def skills_offer(card, computed, among=None, *, include_staged=False):
    """Build the complete checkbox offer and its placed, held and remaining partitions.

    Existing picks are checked; computed grants are fixed. Keep sets containing
    held skills in the main partition so their assignments can be cleared.
    Reuse ``among`` when the caller already loaded selectable collections.
    """
    from n26.core.render import ChoiceOffer

    own, rest, every = [], [], []
    for placed, group in _sets_on_offer(
        card, computed, among, include_staged=include_staged
    ):
        every.append(group)
        if placed or any(option.is_current for option in group.options):
            own.append(group)
        else:
            rest.extend(group.options)
    return SkillsOffer(
        everything=ChoiceOffer(label="", groups=every),
        own=ChoiceOffer(label="", groups=own),
        rest=rest,
    )


def _settled_by(computed):
    """Map assigned content to the starting-skill offers it currently settles."""
    found = {}
    for slot in computed.choices:
        if slot.offer is None:
            continue
        for pick in slot.picks:
            if pick.assignment is None:
                continue
            found[_key(pick.assignable)] = slot
    return found


def apply_ticks(op, miniature, card, computed, ticked, *, include_staged=False):
    """Make stored skill selections match the complete current checkbox offer.

    Rebuild the offer server-side. A stale submission can clear newer selections
    across the whole offer, independently of its displayed tab. Ignore fixed grants
    on both sides of the comparison.

    Remove old selections first so a reopened starting-skill offer can receive a
    replacement in the same operation. Use standing selection when no offer matches.
    """
    offer = skills_offer(card, computed, include_staged=include_staged).everything
    rows = _rows_on(card)
    granted = _grants_on(computed)
    offers = skill_selection.open_offers(computed)
    lists = {
        id(slot): skill_selection.offered_keys(
            slot, computed, include_staged=include_staged
        )
        for slot in offers
    }
    settled = _settled_by(computed)

    # Deduplicate skill identities shared by multiple collections before selecting.
    options = {}
    for group in offer.groups:
        for option in group.options:
            options.setdefault(option.key, option)

    # Remove old selections first so a reopened offer can receive its replacement.
    selected, cleared = [], []
    for key, option in options.items():
        if key in granted or key in ticked or key not in rows:
            continue
        op.remove(rows[key])
        cleared.append(option.name)
        slot = settled.get(key)
        if slot is not None and slot not in offers:
            offers.append(slot)
            lists.setdefault(
                id(slot),
                skill_selection.offered_keys(
                    slot, computed, include_staged=include_staged
                ),
            )

    for key, option in options.items():
        if key in granted:
            continue
        if key in ticked and key not in rows:
            skill_selection.select_from_offer(
                op, miniature, option.thing, offers, lists
            )
            selected.append(option.name)
    return selected, cleared


def _display(request, miniature, screen, form):
    """Project one current placed offer for both initial and refused submissions."""
    from n26.core.navigation import fighter_switcher, switcher_props
    from n26.core.people import person_link
    from n26.core.views.equip import collection_tabs

    gang = miniature.gang
    here = reverse("n26-skills", args=[miniature.pk])
    action = here + (
        "?" + urlencode({"list": str(screen.chosen.pk)}) if screen.chosen else ""
    )
    badges = {}
    owner = person_link(gang.owner, badges)
    owner["badge"] = badges.get(owner.get("badge"))
    return {
        "name": miniature.name,
        "lead": f"Select skills for {miniature.name}.",
        "gangName": gang.name,
        "gangHref": reverse("n26-gang", args=[gang.pk]),
        "owner": owner,
        "back": reverse("n26-edit-fighter", args=[miniature.pk]),
        "switcher": switcher_props(
            fighter_switcher(gang, miniature, route="n26-skills"), hotkey="r"
        ),
        "collections": collection_tabs(screen.collections, screen.chosen),
        "nothingToSelect": not screen.collections,
        "groups": [
            {
                "name": group.name,
                "caption": group.caption,
                "options": [
                    {
                        "key": option.key,
                        "name": option.name,
                        "remark": option.remark,
                        "summary": option.summary,
                        "rating": option.rating,
                    }
                    for option in group.options
                ],
            }
            for group in screen.offer.groups
        ]
        if screen.offer
        else [],
        "values": {
            "gang": str(gang.pk),
            "collection": form["collection"].value() or "",
            "thing": form["thing"].value() or "",
            "thing_label": str(form.data.get("thing_label", ""))[:2000]
            if form.is_bound
            else "",
            "request_key": str(form["request_key"].value() or ""),
        },
        "errors": dict(form.errors),
        "action": action,
        "recoveryHref": action + ("&" if "?" in action else "?") + "recover=1",
        "commandHref": reverse("n26-skills-command", args=[miniature.pk]),
        "signInHref": reverse("account_login")
        + "?"
        + urlencode({"next": action + ("&" if "?" in action else "?") + "recover=1"}),
        "csrfToken": get_token(request),
        "recoveryKey": f"model-skills:{request.user.pk}:{gang.pk}:{miniature.pk}",
        "messages": [
            {
                "text": str(message),
                "tone": message.level_tag
                if message.level_tag in {"success", "error", "warning"}
                else "info",
            }
            for message in messages.get_messages(request)
        ],
    }


def _feedback(request, result):
    if not result.replayed:
        from n26.analytics import EventVerb, N26Noun, record

        record(
            request,
            N26Noun.ASSIGNMENT,
            EventVerb.CREATE,
            result.subject,
            **result.facts,
        )
    tag = f"model-skills-{result.form.cleaned_data['request_key']}"
    storage = messages.get_messages(request)
    queued = any(tag in (message.extra_tags or "").split() for message in storage)
    storage.used = False
    if not queued:
        message = (
            result.message + " This selection was already saved."
            if result.replayed
            else result.message
        )
        messages.success(request, message, extra_tags=tag)


def _destination(gang, model_key):
    from n26.core.models import Miniature

    live = Miniature.objects.filter(
        pk=model_key, membership__gang=gang, membership__archived=False
    ).exists()
    return (
        reverse("n26-edit-fighter", args=[model_key])
        if live
        else reverse("n26-gang", args=[gang.pk])
    )


def _recovery_display(request, pk, result=None):
    from n26.core.model_choice_recovery import target_for
    from n26.core.people import person_link

    target = target_for(pk, request.user, action="skill")
    if target is None:
        raise Http404("No such model")
    gang = target.gang
    here = reverse("n26-skills", args=[pk])
    collection = (
        result.form.data.get("collection", "")
        if result
        else request.GET.get("list", "")
    )
    recovery = (
        here
        + "?"
        + urlencode({"recover": "1", **({"list": collection} if collection else {})})
    )
    badges = {}
    owner = person_link(gang.owner, badges)
    owner["badge"] = badges.get(owner.get("badge"))
    values = {
        "gang": str(gang.pk),
        "collection": collection,
        "thing": "",
        "thing_label": "",
        "request_key": str(uuid4()),
    }
    if result is not None:
        values.update({name: str(result.form.data.get(name, "")) for name in values})
    props = {
        "recoveryOnly": True,
        "removed": bool(result and result.removed),
        "name": target.name,
        "lead": "",
        "gangName": gang.name,
        "gangHref": reverse("n26-gang", args=[gang.pk]),
        "owner": owner,
        "back": reverse("n26-gang", args=[gang.pk]),
        "switcher": None,
        "collections": [],
        "nothingToSelect": False,
        "groups": [],
        "values": values,
        "errors": dict(result.form.errors) if result else {},
        "action": recovery,
        "recoveryHref": recovery,
        "commandHref": reverse("n26-skills-command", args=[pk]),
        "signInHref": reverse("account_login") + "?" + urlencode({"next": recovery}),
        "csrfToken": get_token(request),
        "recoveryKey": f"model-skills:{request.user.pk}:{gang.pk}:{pk}",
        "messages": [
            {
                "text": str(message),
                "tone": message.level_tag
                if message.level_tag in {"success", "error", "warning"}
                else "info",
            }
            for message in messages.get_messages(request)
        ],
    }
    return {
        "gang": gang,
        "recovery_name": target.name,
        "skills_title": "Recover skill selection",
        "skills_props": props,
    }


@login_required
@never_cache
@require_http_methods(["GET", "POST"])
def skills(request, pk):
    """Only the signed-in gang owner may inspect or select placed skills and powers."""
    result = None
    if request.method == "POST":
        gang = _own_gang_or_404(request, request.POST.get("gang", ""))
        result = skills_workflow.change(gang, request.user, pk, request.POST)
        if result.saved:
            _feedback(request, result)
            return redirect(_destination(gang, pk))
    if result and result.removed:
        return render(
            request,
            "n26/skills.html",
            _recovery_display(request, pk, result),
            status=409,
        )
    try:
        miniature = _own_miniature_or_404(request, pk)
    except Http404:
        if request.GET.get("recover") != "1":
            raise
        return render(
            request,
            "n26/skills.html",
            _recovery_display(request, pk, result),
            status=409 if result else 200,
        )
    collection_key = (
        request.POST.get("collection", "") if result else request.GET.get("list", "")
    )
    screen = skills_workflow.prepare(miniature, request.user, collection_key)
    form = result.form if result else skills_workflow.initial(miniature.gang, screen)
    props = _display(request, miniature, screen, form)
    return render(
        request,
        "n26/skills.html",
        {
            "gang": miniature.gang,
            "miniature": miniature,
            "skills_title": str(screen.chosen) if screen.chosen else "Skills",
            "skills_props": props,
        },
        status=422 if result else 200,
    )


@require_POST
@never_cache
def skills_command(request, pk):
    """Share native skill selection, locked access and receipt replay with React."""
    if not request.user.is_authenticated:
        return JsonResponse(
            {"error": "Sign in again to select a skill or power."}, status=401
        )
    gang = _own_gang_or_404(request, request.POST.get("gang", ""))
    result = skills_workflow.change(gang, request.user, pk, request.POST)
    if result.saved:
        _feedback(request, result)
        return JsonResponse({"nextUrl": _destination(gang, pk)})
    if result.removed:
        return JsonResponse(
            {"code": "model_removed", "errors": dict(result.form.errors)}, status=409
        )
    return JsonResponse({"errors": dict(result.form.errors)}, status=422)
